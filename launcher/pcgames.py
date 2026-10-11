"""Steam and Epic Games library entries, and launching them through their own launchers.

Read-only: this looks at the small text files Steam and the Epic Games Launcher keep about installed games
(libraryfolders.vdf, appmanifest_*.acf and *.item) and at the few registry values that say where they are installed.
It never opens a game's own files, never signs in and never sends anything. A game starts the way the launcher itself
would start it: steam://rungameid/<id> or the Epic launch address, so the client does its own updates, sign-in and
anti-cheat.

"Launcher installed" and "games found" are two separate facts: Steam can be installed with nothing in it yet, and the
doctor reports both (store_status)."""
from __future__ import annotations

import base64
import json
import os
import re
import struct
import sys
from pathlib import Path

NOT_GAMES = ("steamworks common redistributables", "steam linux runtime", "proton ", "steam controller configs", "steamvr")
STEAM_ID64_BASE = 76561197960265728          # a SteamID64 minus this is the account id used for userdata/<id>


# --- small readers ---------------------------------------------------------------------------------------------------
def registry_value(hive: str, key: str, name: str = "") -> str | None:
    """One registry value as text, or None. hive is "HKCU", "HKLM" or "HKCR". Kept as one small function so tests (and
    any computer without a registry) can replace it."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    root = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCR": winreg.HKEY_CLASSES_ROOT}.get(hive)
    if root is None:
        return None
    try:
        with winreg.OpenKey(root, key) as k:
            value = winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None
    return str(value) if value not in (None, "") else None


def _env_get(env, name: str) -> str:
    """Environment lookup that ignores capitals: on Windows dict(os.environ) has PROGRAMFILES(X86), not ProgramFiles(x86)."""
    if not env:
        return ""
    value = env.get(name)
    if value:
        return str(value)
    lowered = name.lower()
    for k, v in env.items():
        if str(k).lower() == lowered and v:
            return str(v)
    return ""


def _read_text(path: Path, limit: int = 32_000_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError:
        return ""


_VDF_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|(//[^\n]*)|([^\s{}"]+)', re.S)
_VDF_ESCAPES = {"\\\\": "\\", '\\"': '"', "\\n": "\n", "\\t": "\t"}


def _vdf_unescape(text: str) -> str:
    # Only the escapes Valve writes are undone; "D:\Games" written without escaping keeps its backslash.
    return re.sub(r'\\[\\"nt]', lambda m: _VDF_ESCAPES[m.group(0)], text)


def parse_vdf(text: str) -> dict:
    """Valve's text KeyValues (VDF/ACF) as nested dicts. Tolerant: comments, unquoted words, [$WIN32] conditions and
    stray braces are skipped instead of failing the whole file."""
    root: dict = {}
    stack = [root]
    key: str | None = None
    for m in _VDF_TOKEN.finditer(text or ""):
        quoted, brace, comment, bare = m.groups()
        if comment is not None:
            continue
        if brace == "{":
            child: dict = {}
            if key is not None:
                existing = stack[-1].get(key)
                if isinstance(existing, dict):        # the same block twice: merge
                    child = existing
                else:
                    stack[-1][key] = child
            stack.append(child)
            key = None
            continue
        if brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
            continue
        if bare is not None and bare.startswith("[") and bare.endswith("]"):
            continue                                  # a platform condition, not data
        token = _vdf_unescape(quoted) if quoted is not None else bare
        if key is None:
            key = token
        else:
            stack[-1][key] = token
            key = None
    return root


def _ci(d, *names):
    """d[name] ignoring capitals, following several names in turn (a path into nested dicts)."""
    cur = d
    for name in names:
        if not isinstance(cur, dict):
            return None
        if name in cur:
            cur = cur[name]
            continue
        lowered = name.lower()
        cur = next((v for k, v in cur.items() if str(k).lower() == lowered), None)
    return cur


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _windows_path(text: str) -> Path:
    """A path from a launcher file: forward slashes, doubled backslashes and quotes all come out as one plain path."""
    text = str(text).strip().strip('"').strip()
    if sys.platform == "win32":
        text = text.replace("/", "\\")
        text = re.sub(r"(?<!^)\\\\+", "\\\\", text)  # keep a leading \\server share; fold doubled separators elsewhere
    return Path(text)


# --- Steam -----------------------------------------------------------------------------------------------------------
def _steam_candidates(env) -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    if _env_get(env, "STEAM_ROOT"):
        out.append((_windows_path(_env_get(env, "STEAM_ROOT")), "your Steam folder setting"))
    for hive, key, name in (("HKCU", r"Software\Valve\Steam", "SteamPath"),
                            ("HKLM", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                            ("HKLM", r"SOFTWARE\Valve\Steam", "InstallPath")):
        value = registry_value(hive, key, name)
        if value:
            out.append((_windows_path(value), "the registry"))
    exe = registry_value("HKCU", r"Software\Valve\Steam", "SteamExe")
    if exe:
        out.append((_windows_path(exe).parent, "the registry"))
    for var in ("ProgramFiles(x86)", "ProgramFiles", "ProgramW6432"):
        if _env_get(env, var):
            out.append((Path(_env_get(env, var)) / "Steam", "the usual folder"))
    if sys.platform == "win32":
        out.append((Path(r"C:\Program Files (x86)\Steam"), "the usual folder"))
    seen, unique = set(), []
    for path, how in out:
        if _norm(path) not in seen:
            seen.add(_norm(path))
            unique.append((path, how))
    return unique


def steam_install(env: dict | None = None) -> dict:
    """Where Steam is installed. installed is true when Steam's program or its steamapps folder is there, even with no
    games installed yet."""
    env = env if env is not None else os.environ
    for path, how in _steam_candidates(env):
        try:
            exe = next((path / n for n in ("steam.exe", "Steam.exe", "steam.sh") if (path / n).is_file()), None)
            apps = (path / "steamapps").is_dir()
        except OSError:
            continue
        if exe is not None or apps:
            return {"installed": True, "root": str(path), "exe": str(exe or ""), "how": how}
    return {"installed": False, "root": "", "exe": "", "how": ""}


def _steam_root(env: dict | None = None) -> Path | None:
    info = steam_install(env)
    return Path(info["root"]) if info["installed"] else None


def steam_libraries(root: Path) -> list[Path]:
    """Steam's own folder plus every library listed in libraryfolders.vdf (any drive), in the old format
    ("1" "D:\\\\SteamLibrary") and the new one ("0" { "path" "D:\\\\SteamLibrary" ... })."""
    libraries = [Path(root)]
    seen = {_norm(root)}
    for vdf in (Path(root) / "steamapps" / "libraryfolders.vdf", Path(root) / "config" / "libraryfolders.vdf"):
        data = parse_vdf(_read_text(vdf))
        top = _ci(data, "libraryfolders")
        if not isinstance(top, dict):
            continue
        for k, v in top.items():
            if not str(k).isdigit():
                continue
            text = v if isinstance(v, str) else _ci(v, "path")
            if not isinstance(text, str) or not text.strip():
                continue
            path = _windows_path(text)
            if _norm(path) not in seen:
                seen.add(_norm(path))
                libraries.append(path)
    return libraries


def _acf_value(text: str, key: str) -> str:
    m = re.search(r'"%s"\s+"([^"]*)"' % re.escape(key), text, re.I)
    return m.group(1) if m else ""


def _manifests(lib: Path) -> list[Path]:
    try:
        return sorted((lib / "steamapps").glob("appmanifest_*.acf"))
    except OSError:
        return []


def steam_games(env: dict | None = None) -> list[dict]:
    root = _steam_root(env)
    if root is None:
        return []
    games: dict[str, dict] = {}
    for lib in steam_libraries(root):
        for manifest in _manifests(lib):
            state = _ci(parse_vdf(_read_text(manifest, 4_000_000)), "AppState")
            if not isinstance(state, dict):
                continue
            appid = str(_ci(state, "appid") or "")
            if not appid.isdigit():
                appid = manifest.stem.split("_", 1)[-1]
            name = str(_ci(state, "name") or _ci(state, "installdir") or "").strip()
            if not appid.isdigit() or not name or name.lower().startswith(NOT_GAMES):
                continue
            flags = str(_ci(state, "StateFlags") or "")
            if flags.isdigit() and not int(flags) & 4:        # bit 4 = fully installed
                continue
            size = str(_ci(state, "SizeOnDisk") or "")
            games[appid] = {"store": "steam", "key": appid, "title": name, "uri": f"steam://rungameid/{appid}",
                            "size": int(size) if size.isdigit() else 0, "library": str(lib)}
    return list(games.values())


# --- Epic Games ------------------------------------------------------------------------------------------------------
def _epic_manifest_dirs(env) -> list[Path]:
    out: list[Path] = []
    if _env_get(env, "EPIC_MANIFESTS"):
        return [Path(_env_get(env, "EPIC_MANIFESTS"))]
    for key in (r"SOFTWARE\WOW6432Node\Epic Games\EpicGamesLauncher", r"SOFTWARE\Epic Games\EpicGamesLauncher"):
        data = registry_value("HKLM", key, "AppDataPath")
        if data:
            out.append(_windows_path(data) / "Manifests")
    program_data = _env_get(env, "ProgramData") or (r"C:\ProgramData" if sys.platform == "win32" else "")
    if program_data:
        out.append(Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests")
    seen, unique = set(), []
    for p in out:
        if _norm(p) not in seen:
            seen.add(_norm(p))
            unique.append(p)
    return unique


def _epic_exe_candidates(env) -> list[Path]:
    out: list[Path] = []
    command = registry_value("HKCR", r"com.epicgames.launcher\shell\open\command", "")
    if command:
        m = re.match(r'\s*"([^"]+)"|\s*(\S+)', command)
        if m:
            out.append(_windows_path(m.group(1) or m.group(2)))
    for var in ("ProgramFiles(x86)", "ProgramFiles"):
        base = _env_get(env, var)
        if base:
            for arch in ("Win64", "Win32"):
                out.append(Path(base) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / arch / "EpicGamesLauncher.exe")
    return out


def epic_install(env: dict | None = None) -> dict:
    """Whether the Epic Games Launcher is installed: its program, or the data folder it keeps its game list in."""
    env = env if env is not None else os.environ
    exe = ""
    for p in _epic_exe_candidates(env):
        try:
            if p.is_file():
                exe = str(p)
                break
        except OSError:
            continue
    manifests = ""
    for d in _epic_manifest_dirs(env):
        try:
            if d.is_dir():
                manifests = str(d)
                break
        except OSError:
            continue
    program_data = _env_get(env, "ProgramData") or (r"C:\ProgramData" if sys.platform == "win32" else "")
    installed_dat = Path(program_data) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat" if program_data else None
    has_dat = bool(installed_dat and installed_dat.is_file())
    return {"installed": bool(exe or manifests or has_dat), "exe": exe, "manifests": manifests,
            "how": "the program" if exe else ("its game list" if manifests or has_dat else "")}


def epic_games(env: dict | None = None) -> list[dict]:
    env = env if env is not None else os.environ
    games: dict[str, dict] = {}
    for folder in _epic_manifest_dirs(env):
        try:
            items = sorted(folder.glob("*.item"))
        except OSError:
            continue
        for item in items:
            try:
                data = json.loads(_read_text(item, 4_000_000) or "null")
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            name, app = str(data.get("DisplayName") or "").strip(), str(data.get("AppName") or "").strip()
            if not name or not app or data.get("bIsIncompleteInstall") or app in games:
                continue
            if data.get("bIsApplication") is False:            # content packs and engine plug-ins, not something to start
                continue
            cats = data.get("AppCategories")
            if isinstance(cats, list) and cats and "games" not in cats:
                continue
            main = data.get("MainGameAppName")
            if main and main != app:                               # add-on content, not a game of its own
                continue
            ns, cid = str(data.get("CatalogNamespace") or ""), str(data.get("CatalogItemId") or "")
            uri = f"com.epicgames.launcher://apps/{ns}%3A{cid}%3A{app}?action=launch&silent=true" if ns and cid else \
                  f"com.epicgames.launcher://apps/{app}?action=launch&silent=true"
            try:
                size = int(data.get("InstallSize") or 0)
            except (TypeError, ValueError):
                size = 0
            games[app] = {"store": "epic", "key": app, "title": name, "uri": uri, "size": size, "namespace": ns, "item": cid,
                          "install": str(data.get("InstallLocation") or "")}
    return list(games.values())


def installed_games(env: dict | None = None) -> list[dict]:
    return steam_games(env) + epic_games(env)


def store_status(env: dict | None = None) -> dict:
    """What the doctor says about PC games: is each launcher installed, and how many games does it have."""
    env = env if env is not None else os.environ
    steam, epic = steam_install(env), epic_install(env)
    try:
        steam["games"] = len(steam_games(env)) if steam["installed"] else 0
    except Exception:
        steam["games"] = 0
    try:
        epic["games"] = len(epic_games(env))
    except Exception:
        epic["games"] = 0
    parts = []
    for label, info in (("Steam", steam), ("Epic", epic)):
        n = info["games"]
        if info["installed"]:
            parts.append(f"{label} is installed: {n} game{'' if n == 1 else 's'}")
        elif n:
            parts.append(f"{label}: {n} game{'' if n == 1 else 's'} found")
    text = "; ".join(parts) + "." if parts else "Neither Steam nor the Epic Games Launcher was found on this computer."
    return {"steam": steam, "epic": epic, "ready": bool(steam["installed"] or epic["installed"]), "text": text}


def library_entries(env: dict | None = None) -> list[dict]:
    """The games in the same shape the library uses for files on disk."""
    out = []
    for g in installed_games(env):
        title = g["title"]
        entry = {
            "id": f"{g['store']}-{re.sub(r'[^A-Za-z0-9]+', '', g['key'])[:40]}", "console": "pc", "title": title,
            "sort_title": re.sub(r"^(the|a|an) ", "", title.lower()), "region": "", "tags": [g["store"].title()],
            "path": g["uri"], "root": g["store"], "size": g["size"], "extension": "." + g["store"], "is_archive": False,
            "compat_id": f"pc:{g['store']}:{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}",
            "store_key": g["key"],
        }
        if g["store"] == "epic":
            entry["epic_ns"], entry["epic_item"] = g.get("namespace", ""), g.get("item", "")
        out.append(entry)
    return out


def store_ids(game: dict) -> dict:
    """The store's own ids for a library entry: {"store", "appid"} for Steam, {"store", "app", "ns", "item"} for Epic.
    Older library caches lack the extra fields, so the launch address is read as well."""
    uri = str(game.get("path") or "")
    if game.get("root") == "steam":
        appid = str(game.get("store_key") or uri.rsplit("/", 1)[-1])
        return {"store": "steam", "appid": appid if appid.isdigit() else ""}
    if game.get("root") == "epic":
        ns, item, app = game.get("epic_ns", ""), game.get("epic_item", ""), game.get("store_key", "")
        m = re.match(r"com\.epicgames\.launcher://apps/([^?]+)", uri)
        if m:
            parts = m.group(1).split("%3A")
            if len(parts) == 3:
                ns, item, app = ns or parts[0], item or parts[1], app or parts[2]
            elif not app:
                app = parts[0]
        return {"store": "epic", "app": app, "ns": ns, "item": item}
    return {"store": ""}


def launch(uri: str) -> None:
    """Hand the launch address to Windows, which gives it to Steam or the Epic launcher."""
    if not (uri.startswith("steam://rungameid/") or uri.startswith("com.epicgames.launcher://apps/")):
        raise ValueError("Not a Steam or Epic launch address.")
    if sys.platform != "win32":
        raise OSError("Steam and Epic games start from Windows.")
    os.startfile(uri)      # noqa: S606 - the address was checked above


def image_size(data: bytes) -> tuple[int, int] | None:
    """Width and height of a PNG or JPEG from its header, without decoding it (nothing outside the standard library)."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                length = int.from_bytes(data[i + 2:i + 4], "big")
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
                i += 2 + length
    except (IndexError, ValueError):
        pass
    return None


def _portrait(data: bytes) -> bool:
    size = image_size(data)
    return bool(size) and size[1] > size[0] * 1.2          # a tall picture (600x900 or 300x450), not the wide header or hero


def steam_art(appid: str, env: dict | None = None, limit: int = 1_500_000) -> bytes | None:
    """Steam's own picture for an installed game, read from the copy Steam already keeps on this computer. Nothing is
    downloaded. Steam has used three layouts over the years, and all three are read:

      appcache/librarycache/<appid>_library_600x900.jpg              (older clients)
      appcache/librarycache/<appid>/<hash>/library_600x900.jpg       (2024 clients: a folder per game, one per version)
      appcache/librarycache/<appid>/<hash>.jpg                        (newest clients: files named by content, so the tall one
                                                                        is told apart from the wide header by its shape)
    A picture the player chose in Steam (userdata/<account>/config/grid/<appid>p.*) wins over all of them."""
    root = _steam_root(env)
    if root is None or not str(appid).isdigit():
        return None
    appid = str(appid)

    def read(path: Path) -> bytes | None:
        try:
            if path.is_file() and 0 < path.stat().st_size <= limit:
                return path.read_bytes()
        except OSError:
            pass
        return None

    try:                                                    # the player's own choice inside Steam
        for grid in sorted((root / "userdata").glob("*/config/grid")):
            for ext in ("png", "jpg", "jpeg", "webp"):
                data = read(grid / f"{appid}p.{ext}")
                if data:
                    return data
    except OSError:
        pass
    cache = root / "appcache" / "librarycache"
    named = ("library_600x900.jpg", "library_600x900_2x.jpg", "library_capsule.jpg", "library_capsule_2x.jpg",
             "library_600x900.png", "library_capsule.png")
    for n in named:                                         # old flat names, then the per-game folders
        data = read(cache / f"{appid}_{n}")
        if data:
            return data
    folder = cache / appid
    if folder.is_dir():
        try:
            for n in named:
                for path in sorted(folder.rglob(n)):
                    data = read(path)
                    if data:
                        return data
            tall: list[tuple[int, bytes]] = []
            for path in sorted(folder.rglob("*")):            # content-named files: keep the tallest, biggest one
                if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                    continue
                data = read(path)
                if data and _portrait(data):
                    tall.append((len(data), data))
            if tall:
                return max(tall, key=lambda t: t[0])[1]
        except OSError:
            pass
    for n in ("header.jpg", "library_header.jpg", "library_hero.jpg"):   # last resort: the wide picture
        data = read(cache / f"{appid}_{n}")
        if data:
            return data
        if folder.is_dir():
            try:
                for path in sorted(folder.rglob(n)):
                    data = read(path)
                    if data:
                        return data
            except OSError:
                pass
    return None


# --- games hidden inside Steam ---------------------------------------------------------------------------------------
def steam_accounts(root: Path) -> list[str]:
    """The userdata/<account id> folders to read: the account that signed in most recently (config/loginusers.vdf),
    or every account on this computer when that cannot be told."""
    try:
        folders = sorted(p.name for p in (Path(root) / "userdata").iterdir() if p.is_dir() and p.name.isdigit() and p.name != "0")
    except OSError:
        return []
    users = _ci(parse_vdf(_read_text(Path(root) / "config" / "loginusers.vdf", 2_000_000)), "users")
    if isinstance(users, dict):
        recent = [(str(_ci(v, "Timestamp") or "0"), k) for k, v in users.items()
                  if isinstance(v, dict) and str(k).isdigit() and str(_ci(v, "MostRecent") or "0") == "1"]
        for _, sid in sorted(recent, reverse=True):
            account = str(int(sid) - STEAM_ID64_BASE) if int(sid) > STEAM_ID64_BASE else sid
            if account in folders:
                return [account]
    return folders


def _hidden_from_cloud_storage(path: Path) -> set[str] | None:
    """Steam's library collections (2019 and later): config/cloudstorage/cloud-storage-namespace-1.json is a list of
    [key, {"key", "value": "<JSON text>", "is_deleted", ...}]; the "user-collections.hidden" value lists the hidden app
    ids in "added". None when the file says nothing about hidden games (then the older files are read)."""
    text = _read_text(path, 64_000_000)
    if not text:
        return None
    try:
        rows = json.loads(text)
    except ValueError:
        return None
    if not isinstance(rows, list):
        return None
    found: set[str] | None = None
    for row in rows:
        if not (isinstance(row, list) and len(row) == 2 and isinstance(row[1], dict)):
            continue
        key, obj = str(row[0]), row[1]
        try:
            value = json.loads(obj.get("value") or "null") if isinstance(obj.get("value"), str) else obj.get("value")
        except ValueError:
            value = None
        is_hidden = key == "user-collections.hidden" or (isinstance(value, dict) and value.get("id") == "hidden")
        if not is_hidden:
            continue
        found = set() if found is None else found
        if obj.get("is_deleted") or not isinstance(value, dict):
            continue
        removed = {str(a) for a in value.get("removed") or [] if str(a).isdigit()}
        found |= {str(a) for a in value.get("added") or [] if str(a).isdigit()} - removed
    return found


def _hidden_from_vdf(path: Path) -> set[str]:
    """Older Steam (and some current files): an app's block in sharedconfig.vdf / localconfig.vdf with "Hidden" "1",
    or a tag named hidden."""
    hidden: set[str] = set()

    def walk(node, depth: int = 0) -> None:
        if not isinstance(node, dict) or depth > 8:
            return
        for k, v in node.items():
            if str(k).lower() == "apps" and isinstance(v, dict):
                for appid, block in v.items():
                    if not (str(appid).isdigit() and isinstance(block, dict)):
                        continue
                    if str(_ci(block, "Hidden") or "") == "1":
                        hidden.add(str(appid))
                    tags = _ci(block, "tags")
                    if isinstance(tags, dict) and any(str(t).strip().lower() == "hidden" for t in tags.values()):
                        hidden.add(str(appid))
            elif isinstance(v, dict):
                walk(v, depth + 1)
    walk(parse_vdf(_read_text(path)))
    return hidden


def steam_hidden(env: dict | None = None) -> set[str]:
    """App ids the player marked as hidden inside Steam (Manage > Hide this game). Read-only, ids only."""
    root = _steam_root(env)
    hidden: set[str] = set()
    if root is None:
        return hidden
    for account in steam_accounts(root):
        base = root / "userdata" / account
        cloud = _hidden_from_cloud_storage(base / "config" / "cloudstorage" / "cloud-storage-namespace-1.json")
        if cloud is not None:                          # the collections file is what current Steam uses: it decides
            hidden |= cloud
            continue
        for f in (base / "7" / "remote" / "sharedconfig.vdf", base / "config" / "localconfig.vdf"):
            hidden |= _hidden_from_vdf(f)
    return hidden


def steam_diagnostics(env: dict | None = None) -> dict:
    """Why Steam games do or do not show: where Steam is, which libraries it lists and how many games were found."""
    install = steam_install(env)
    root = Path(install["root"]) if install["installed"] else None
    out: dict = {"found": root is not None, "root": str(root) if root else "", "how": install["how"], "libraries": [], "manifests": 0, "games": 0}
    if root is None:
        return out
    for lib in steam_libraries(root):
        n = len(_manifests(lib))
        out["libraries"].append({"path": str(lib), "manifests": n, "exists": (lib / "steamapps").is_dir()})
        out["manifests"] += n
    out["games"] = len(steam_games(env))
    return out


# --- Epic's own pictures, from the launcher's caches on this computer -----------------------------------------------------
EPIC_TALL = ("DieselGameBoxTall", "OfferImageTall", "DieselStoreFrontTall", "CodeRedemption_340x440", "Thumbnail")
EPIC_WIDE = ("DieselGameBox", "OfferImageWide", "DieselStoreFrontWide", "DieselGameBoxLogo")
_SIMPLE_MAGIC = struct.pack("<Q", 0xFCFB6D1BA7725C30)        # Chromium "simple" disk cache entry
_SIMPLE_EOF = struct.pack("<Q", 0xF4FA6F45970D41D8)
_BLOCK_MAGIC = 0xC104CAC3                                     # Chromium "blockfile" disk cache (data_0..data_3, f_xxxxxx)
_BLOCK_SIZES = {1: 36, 2: 256, 3: 1024, 4: 4096, 5: 8, 6: 104, 7: 48}
_IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF8", b"RIFF")


def _epic_saved(env) -> Path | None:
    base = _env_get(env, "EPIC_LAUNCHER_SAVED")
    if base:
        return Path(base)
    local = _env_get(env, "LOCALAPPDATA")
    return Path(local) / "EpicGamesLauncher" / "Saved" if local else None


def _read_part(path: Path, start: int, size: int) -> bytes:
    try:
        with open(path, "rb") as f:
            f.seek(start)
            return f.read(size)
    except OSError:
        return b""


def chromium_cache_entries(folder: Path, limit_files: int = 40000):
    """(key, loader) for every entry of a Chromium disk cache folder, in either format Chromium (and so the Epic launcher's
    web view) uses. The key is the address the entry was fetched from; loader() returns the body (at most 8 MB).
    Read-only and best effort: anything that does not look right is skipped."""
    folder = Path(folder)
    out = []
    data1 = folder / "data_1"
    if data1.is_file() and (folder / "index").is_file():
        try:
            blob = data1.read_bytes() if data1.stat().st_size <= 64_000_000 else b""
        except OSError:
            blob = b""
        if len(blob) > 8192 and struct.unpack_from("<I", blob, 0)[0] == _BLOCK_MAGIC:
            entry_size = struct.unpack_from("<i", blob, 12)[0] or 256

            def addr_loader(addr: int, size: int):
                def load() -> bytes:
                    if not addr & 0x80000000 or not 0 < size <= 8_000_000:
                        return b""
                    kind = (addr >> 28) & 7
                    if kind == 0:
                        return _read_part(folder / f"f_{addr & 0x0FFFFFFF:06x}", 0, size)
                    block = _BLOCK_SIZES.get(kind)
                    if not block:
                        return b""
                    start = 8192 + (addr & 0xFFFF) * block
                    return _read_part(folder / f"data_{(addr >> 16) & 0xFF}", start, size)
                return load

            for off in range(8192, len(blob) - entry_size + 1, entry_size):
                key_len = struct.unpack_from("<i", blob, off + 32)[0]
                long_key = struct.unpack_from("<I", blob, off + 36)[0]
                if long_key or not 0 < key_len <= 4 * entry_size - 96 or off + 96 + key_len > len(blob):
                    continue
                key = blob[off + 96:off + 96 + key_len]
                if not (b"http" in key[:200]):
                    continue
                size1 = struct.unpack_from("<i", blob, off + 44)[0]
                addr1 = struct.unpack_from("<I", blob, off + 60)[0]
                out.append((key.decode("utf-8", errors="replace"), addr_loader(addr1, size1)))
                if len(out) >= limit_files:
                    break
        return out
    try:
        names = sorted(p for p in folder.iterdir() if re.fullmatch(r"[0-9a-f]{16}_0", p.name))[:limit_files]
    except OSError:
        return out
    for p in names:
        head = _read_part(p, 0, 4096)
        if len(head) < 24 or head[:8] != _SIMPLE_MAGIC:
            continue
        key_len = struct.unpack_from("<I", head, 12)[0]
        if not 0 < key_len <= 4000:
            continue
        key = (head[24:24 + key_len] if 24 + key_len <= len(head) else _read_part(p, 24, key_len)).decode("utf-8", errors="replace")

        def load(p=p, start=24 + key_len) -> bytes:
            try:
                if p.stat().st_size > 9_000_000:
                    return b""
                data = p.read_bytes()
            except OSError:
                return b""
            end = data.find(_SIMPLE_EOF, start)
            return data[start:end if end >= 0 else len(data)]
        out.append((key, load))
    return out


_MEMO: dict = {}


def _memo(key, path: Path, make):
    """Keep one decoded launcher file while it has not changed, so twenty Epic games do not decode it twenty times."""
    try:
        st = path.stat()
        stamp = (st.st_size, st.st_mtime_ns)
    except OSError:
        return make()
    hit = _MEMO.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    value = make()
    if len(_MEMO) > 16:
        _MEMO.clear()
    _MEMO[key] = (stamp, value)
    return value


def _cache_entries(folder: Path):
    marker = folder / "data_1" if (folder / "data_1").is_file() else folder
    return _memo(("cache", str(folder)), marker, lambda: chromium_cache_entries(folder))


def _epic_cache_folders(saved: Path) -> list[Path]:
    out = []
    try:
        for web in sorted(saved.glob("webcache*")):
            for sub in (web, web / "Cache", web / "Cache" / "Cache_Data", web / "Cache_Data"):
                if sub.is_dir() and ((sub / "data_1").is_file() or any(re.fullmatch(r"[0-9a-f]{16}_0", c.name) for c in sub.iterdir())):
                    out.append(sub)
    except OSError:
        pass
    return out


def _catalog_objects(blob, ns: str, item: str, app: str):
    """Catalog items (dicts with keyImages) for this game anywhere inside a decoded JSON document."""
    stack = [blob]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            if isinstance(node.get("keyImages"), list):
                ids = {str(node.get("id") or "")}
                for r in node.get("releaseInfo") or []:
                    if isinstance(r, dict):
                        ids.add(str(r.get("appId") or ""))
                same_ns = not ns or str(node.get("namespace") or "") == ns
                if (item and item in ids) or (app and app in ids and same_ns):
                    yield node
            stack.extend(v for v in node.values() if isinstance(v, (list, dict)))


def _decode_catalog(raw: bytes):
    raw = raw.strip()
    for attempt in (raw, None):
        if attempt is None:
            try:
                attempt = base64.b64decode(raw, validate=False)
            except ValueError:
                return None
        try:
            return json.loads(attempt.decode("utf-8-sig", errors="strict"))
        except (ValueError, UnicodeDecodeError):
            continue
    return None


def epic_key_images(ns: str, item: str, app: str, env: dict | None = None) -> list[str]:
    """Picture addresses Epic's launcher already has for this game in its catalog cache (tall box art first). Read from
    Saved/Data/Catalog/catcache.bin (base64 JSON) and from catalog answers in the launcher's web cache. Nothing is fetched."""
    env = env if env is not None else os.environ
    saved = _epic_saved(env)
    if saved is None or not (item or app):
        return []
    images: list[dict] = []
    for f in (saved / "Data" / "Catalog" / "catcache.bin", saved / "Data" / "Catalog" / "catcache.json"):
        try:
            if f.is_file() and f.stat().st_size <= 64_000_000:
                doc = _memo(("catalog", str(f)), f, lambda f=f: _decode_catalog(f.read_bytes()))
                for obj in _catalog_objects(doc, ns, item, app):
                    images += [i for i in obj["keyImages"] if isinstance(i, dict)]
        except OSError:
            continue
    if not images:
        looked = 0
        for folder in _epic_cache_folders(saved):
            for key, load in _cache_entries(folder):
                if looked > 300 or not re.search(r"catalog|graphql|store-content|/offers|/items", key, re.I):
                    continue
                looked += 1
                body = load()
                if (item and item.encode() in body) or (app and app.encode() in body):
                    doc = _decode_catalog(body)
                    for obj in _catalog_objects(doc, ns, item, app):
                        images += [i for i in obj["keyImages"] if isinstance(i, dict)]
    order = {t: n for n, t in enumerate(EPIC_TALL + EPIC_WIDE)}
    urls, seen = [], set()
    for img in sorted(images, key=lambda i: order.get(str(i.get("type")), 99)):
        url = str(img.get("url") or "")
        if str(img.get("type")) in order and url.startswith("https://") and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def epic_art(game: dict, env: dict | None = None, limit: int = 1_500_000) -> bytes | None:
    """The Epic launcher's own picture of a game, from the copy its web view already downloaded and keeps in its cache on
    this computer. Nothing is downloaded. None when the launcher has not shown that picture yet."""
    env = env if env is not None else os.environ
    ids = store_ids(game)
    if ids.get("store") != "epic":
        return None
    urls = epic_key_images(ids["ns"], ids["item"], ids["app"], env)
    saved = _epic_saved(env)
    if not urls or saved is None:
        return None
    wanted = [u.split("?", 1)[0] for u in urls]
    best: dict[int, bytes] = {}
    for folder in _epic_cache_folders(saved):
        for key, load in _cache_entries(folder):
            for rank, base in enumerate(wanted):
                if base in key and rank not in best:
                    data = load()
                    if data and len(data) <= limit and data.startswith(_IMAGE_MAGIC):
                        best[rank] = data
    if not best:
        return None
    tall = [r for r in sorted(best) if _portrait(best[r])]
    return best[tall[0]] if tall else best[min(best)]


def match_key(text: str) -> str:
    """"Hades II (2024).png" and "hades ii" meet in the middle."""
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"\s*[\(\[].*?[\)\]]", "", str(text).lower()))
