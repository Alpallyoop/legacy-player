"""Uninstalling Legacy Player itself. Only ever touches what Legacy Player made: its own data folder,
its logs folder and its own program (LegacyPlayer.exe and its _internal folder). Your games, and emulators you installed
yourself, are never touched."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import datadir

KEEPABLE = ("saves", "save_backups")


def _size(path: Path) -> int:
    if path.is_symlink():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                pass
    return total


def _mb(n: int) -> float:
    return round(n / 1048576, 1)


def log_folder(data_dir: Path | None = None) -> Path | None:
    """The logs folder (<data folder>\\logs, or the one the player chose)."""
    return datadir.logs_folder(data_dir) if data_dir is not None else None


PROGRAM_EXTRAS = ("_internal", datadir.POINTER_NAME, "VERSION.txt", "READ ME FIRST.txt")


def program_file() -> Path | None:
    """The downloaded program itself, only when this is the packaged app (never a source checkout)."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return exe if exe.is_file() else None
    return None


def program_extras(exe: Path | None) -> list[Path]:
    """What belongs to the program next to LegacyPlayer.exe: its _internal folder, the data-location.txt pointer and the
    package's own notes. Only those exact names; nothing else in that folder."""
    if exe is None:
        return []
    return [exe.parent / n for n in PROGRAM_EXTRAS if (exe.parent / n).exists()]


def start_menu_shortcut() -> Path | None:
    """The Start menu shortcut install.ps1 makes ("Legacy Player.lnk" in the user's Programs folder), when it exists."""
    if os.name != "nt":
        return None
    base = os.environ.get("APPDATA")
    if not base:
        return None
    lnk = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Legacy Player.lnk"
    return lnk if lnk.is_file() else None


def created_folders(custom_save_root: str, custom_backup_root: str, console_ids, data_dir: Path | None = None) -> list[dict]:
    """Folders Legacy Player itself made inside places the player chose. Only the exact shapes it creates:
    <save root>/<console>/(saves|states) and LegacyPlayer-*.zip backups. Anything else in those places is never listed."""
    out = []
    ids = set(console_ids or [])
    if custom_save_root:
        root = Path(custom_save_root)
        if root.is_dir() and not (data_dir and _inside(root, Path(data_dir))):
            for cid in sorted(ids):
                d = root / cid
                if d.is_dir() and not d.is_symlink():
                    kids = [k.name for k in d.iterdir()]
                    if kids and set(kids) <= {"saves", "states"}:
                        out.append({"kind": "saves", "label": f"Saves for {cid}", "path": str(d), "mb": _mb(_size(d))})
    if custom_backup_root:
        root = Path(custom_backup_root)
        if root.is_dir() and not (data_dir and _inside(root, Path(data_dir))):
            zips = [z for z in sorted(root.glob("LegacyPlayer-*.zip")) if z.is_file() and not z.is_symlink()]
            if zips:
                out.append({"kind": "backups", "label": f"{len(zips)} backup file{'s' if len(zips) != 1 else ''}", "path": str(root),
                            "files": [str(z) for z in zips], "mb": _mb(sum(_size(z) for z in zips))})
    return out


def check_data_dir(data_dir: Path) -> str | None:
    """Why this folder must not be cleaned out, or None when it is clearly Legacy Player's own. Legacy Player deletes
    the contents of its data folder, so it first makes sure that is really what the folder is."""
    try:
        d = Path(data_dir).resolve()
    except OSError:
        return "I can not read that folder."
    home = Path.home().resolve()
    if d == d.parent or d == home or d in home.parents:
        return "That is not a folder only Legacy Player uses, so I will not clear it."
    if d.name.lower() in {"documents", "desktop", "downloads", "pictures", "music", "videos", "windows", "program files", "program files (x86)"}:
        return "That is one of your own folders, so I will not clear it."
    if d.is_dir() and any(d.iterdir()) and not ((d / "user_data.json").is_file() or (d / ".legacy-player").is_file()
                                              or any((d / n).is_dir() for n in ("emulators", "server", "retroarch_append", "save_backups"))):
        return "That folder does not look like Legacy Player's own, so I will not clear it."
    return None


def _holds_saves(folder: Path, keep_paths) -> bool:
    """An emulator folder that also keeps the player's saves (a portable Dolphin's User/GC, a saves or states folder)."""
    for k in keep_paths or []:
        if k and _inside(Path(k), folder):
            return True
    for sub in (("User", "GC"), ("User", "StateSaves"), ("saves",), ("states",), ("memcards",)):
        d = folder.joinpath(*sub)
        try:
            if d.is_dir() and any(d.iterdir()):
                return True
        except OSError:
            pass
    return False


def _shielded_inside(data_dir: Path, shield) -> list[Path]:
    """The folders the player keeps elsewhere in their own words (games, saves, backups) that sit INSIDE the data folder."""
    out = []
    for s in shield or []:
        if s and _inside(Path(s), data_dir) and not (Path(s).resolve().parent == data_dir.resolve() and Path(s).name in KEEPABLE):
            out.append(Path(s))                       # the data folder's own saves and backups folders are handled by their own row
    return out


def _touches(path: Path, shield: list[Path]) -> bool:
    """Is `path` one of the shielded folders, inside one, or does it contain one?"""
    return any(_inside(path, s) or _inside(s, path) for s in shield)


def _remove_around(path: Path, shield: list[Path], problems: list, held: list) -> None:
    """Remove `path` but leave every shielded folder (and the folders that lead to it) where it is."""
    if not _touches(path, shield):
        _remove(path, problems)
        return
    if any(_inside(path, s) for s in shield):          # it is a shielded folder, or inside one
        held.append(path.name)
        return
    held.append(path.name)                             # it contains one: empty it of everything else
    try:
        children = sorted(path.iterdir())
    except OSError as err:
        problems.append(f"{path} ({err.strerror or err})")
        return
    for child in children:
        _remove_around(child, shield, problems, [])


def plan(data_dir: Path, custom_save_root: str = "", custom_backup_root: str = "", console_ids=(), shield=()) -> dict:
    data_dir = Path(data_dir)
    items = []

    def add(key, label, why, paths, keepable=False):
        paths = [p for p in paths if p.exists() or p.is_symlink()]
        if not paths and key != "program":
            return
        items.append({"key": key, "label": label, "why": why, "keepable": keepable,
                      "paths": [str(p) for p in paths], "mb": _mb(sum(_size(p) for p in paths))})

    add("emulators", "Emulators Legacy Player downloaded", "Only the ones it installed itself into its own folder.", [data_dir / "emulators"])
    known = {"emulators", *KEEPABLE}
    logs = log_folder(data_dir)
    rest = [p for p in sorted(data_dir.iterdir()) if p.name not in known and not (logs and datadir.same(p, logs))] \
        if data_dir.is_dir() else []
    add("library", "Settings, library list, covers and server info", "Your name, favorites, collections, custom covers and the library list.", rest)
    add("saves", "Your game saves and backups", "Progress made in games, plus the backups Legacy Player made.",
        [data_dir / "saves", data_dir / "save_backups"], keepable=True)
    old_logs = datadir.old_app_log_folder()
    if logs:
        add("logs", "Activity logs", "Small text files for troubleshooting.", [logs] + ([old_logs] if old_logs and old_logs.is_dir() else []))
    exe = program_file()
    extras = program_extras(exe)
    items.append({"key": "program", "label": "The Legacy Player program", "keepable": False,
                  "why": "The program you downloaded (LegacyPlayer.exe and its _internal folder)." if exe else "You are running from source, so there is no program file to remove; delete the folder yourself if you want it gone.",
                  "paths": [str(exe), *map(str, extras)] if exe else [], "mb": _mb(_size(exe) + sum(_size(x) for x in extras)) if exe else 0.0,
                  "available": bool(exe)})
    kept_elsewhere = []
    if custom_save_root and not _inside(Path(custom_save_root), data_dir):
        kept_elsewhere.append({"label": "Save folder you chose", "path": custom_save_root})
    if custom_backup_root and not _inside(Path(custom_backup_root), data_dir):
        kept_elsewhere.append({"label": "Backup folder you chose", "path": custom_backup_root})
    for s in _shielded_inside(data_dir, shield):
        kept_elsewhere.append({"label": "A folder of yours inside this one (games or saves you chose)", "path": str(s)})
    return {"data_dir": str(data_dir), "items": items, "never_touched": kept_elsewhere, "refuse": check_data_dir(data_dir),
            "created": created_folders(custom_save_root, custom_backup_root, console_ids, data_dir),
            "total_mb": round(sum(i["mb"] for i in items), 1)}


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except (OSError, ValueError):
        return False


def _remove(path: Path, problems: list) -> None:
    def onerror(func, p, exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError as err:
            problems.append(f"{p} ({err.strerror or err})")
    try:
        if path.is_symlink() or path.is_file():
            try:
                path.unlink()
            except OSError:
                os.chmod(path, 0o600)
                path.unlink()
        elif path.is_dir():
            shutil.rmtree(path, onerror=onerror)
    except OSError as err:
        problems.append(f"{path} ({err.strerror or err})")


def _remove_created(created: list[dict], problems: list) -> int:
    freed = 0
    for c in created:
        if c["kind"] == "saves":
            _remove(Path(c["path"]), problems)
        else:
            for f in c.get("files", []):
                _remove(Path(f), problems)
        freed += int(c["mb"] * 100)
    return freed                                      # the folders the player chose stay; only what we made goes


def execute(data_dir: Path, keep_saves: bool, remove_program: bool, created: list[dict] | None = None, delete_created: bool = False,
            keep_paths=(), game_paths=()) -> dict:
    """Do the clean-up. Returns a report with one row per step so the doctor can narrate it."""
    data_dir = Path(data_dir)
    why = check_data_dir(data_dir)
    if why:
        raise ValueError(why)
    steps, problems_all = [], []
    # Folders the player chose that happen to sit inside the data folder: their games and emulators always stay, their saves
    # stay when "keep my saves" is on. Everything else around them is still removed.
    shield = _shielded_inside(data_dir, [*game_paths, *(keep_paths if keep_saves else ())])
    pl = plan(data_dir)
    deferred = []
    for item in pl["items"]:
        key = item["key"]
        if key == "program":
            continue
        if item["keepable"] and keep_saves:
            steps.append({"key": key, "label": item["label"], "status": "kept", "mb": item["mb"]})
            continue
        if key == "logs":
            deferred += [Path(p) for p in item["paths"]]   # the log file is open right now: removed once we close
            steps.append({"key": key, "label": item["label"], "status": "after_close", "mb": item["mb"]})
            continue
        problems = []
        held = []
        for p in item["paths"]:
            if key == "emulators" and keep_saves and Path(p).is_dir():
                for child in sorted(Path(p).iterdir()):         # an emulator folder that also holds the player's saves stays
                    if child.is_dir() and _holds_saves(child, keep_paths):
                        held.append(child.name)
                    else:
                        _remove(child, problems)
                try:
                    Path(p).rmdir()
                except OSError:
                    pass
            elif shield and key != "emulators":
                _remove_around(Path(p), shield, problems, held)
            else:
                _remove(Path(p), problems)
        problems_all += problems
        steps.append({"key": key, "label": item["label"], "status": "problem" if problems else "removed", "mb": item["mb"], "kept_with_saves": held})
    if created:
        if delete_created:
            problems = []
            _remove_created(created, problems)
            problems_all += problems
            steps.append({"key": "created", "label": "Save folders I made in places you chose", "status": "problem" if problems else "removed",
                          "mb": round(sum(c["mb"] for c in created), 1)})
        else:
            steps.append({"key": "created", "label": "Save folders I made in places you chose", "status": "kept",
                          "mb": round(sum(c["mb"] for c in created), 1)})
    exe = program_file() if remove_program else None
    if remove_program:
        steps.append({"key": "program", "label": "The Legacy Player program", "mb": pl["items"][-1]["mb"],
                      "status": "after_close" if exe else "skipped"})
        lnk = start_menu_shortcut() if exe else None
        if lnk is not None:                     # the installer's Start menu shortcut goes with the program
            problems = []
            _remove(lnk, problems)
            problems_all += problems
            steps.append({"key": "shortcut", "label": "The Start menu shortcut", "mb": 0, "status": "problem" if problems else "removed"})
    purge = None
    if not keep_saves and not shield:                   # a folder of theirs inside the data folder: never sweep it all away
        purge = data_dir

    else:
        try:
            data_dir.rmdir()
        except OSError:
            pass
    if exe or deferred or purge:
        _spawn_cleanup(exe, deferred, purge, program_extras(exe))
    freed = round(sum(s["mb"] for s in steps if s["status"] in ("removed", "after_close")), 1)
    return {"steps": steps, "problems": problems_all, "freed_mb": freed, "kept_saves": bool(keep_saves), "kept_created": bool(created) and not delete_created,
            "program_pending": bool(exe), "never_touched": pl["never_touched"]}


def _hidden_flags() -> int:
    """Run the cleanup script with a hidden console and nothing else. Not DETACHED_PROCESS: that makes Windows ignore
    CREATE_NO_WINDOW, so every command in the script (each `ping`) would open its own visible console window."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def cleanup_lines(exe: Path | None, others: list, purge: Path | None, extras=()) -> list[str]:
    """The cleanup script: first the program (retried until the app has really closed), then the logs, then the data
    folder, then the program folder itself if that left it empty. The script removes itself last."""
    def q(value) -> str:      # percent signs would be expanded by the batch interpreter
        return str(value).replace("%", "%%")

    def gone(p: Path) -> str:
        return f'rmdir /s /q "{q(p)}" >nul 2>&1' if Path(p).is_dir() else f'del /f /q "{q(p)}" >nul 2>&1'
    lines = ["@echo off", "set n=0", ":again", "ping -n 3 127.0.0.1 >nul", "set /a n+=1"]
    if exe:
        lines.append(f'del /f /q "{q(exe)}" >nul 2>&1')
        lines += [gone(Path(x)) for x in extras]
        lines.append(f'if exist "{q(exe)}" if %n% lss 300 goto again')
    lines += [f'rmdir /s /q "{q(p)}" >nul 2>&1' for p in others]
    if purge:
        lines.append(f'rmdir /s /q "{q(purge)}" >nul 2>&1')
    tail = '(goto) 2>nul & del "%~f0"'
    if exe:
        tail += f' & rmdir "{q(Path(exe).parent)}" >nul 2>&1'      # only when empty (a kept data folder stays)
    return lines + [tail]


def _spawn_cleanup(exe: Path | None, others: list, purge: Path | None, extras=()) -> None:
    """After Legacy Player closes, remove the files that were in use. Retries for a while, then gives up quietly. The
    script lives in the program's folder (or the data folder's tmp), never in the user's own folders."""
    paths = ([exe] if exe else []) + list(extras) + list(others) + ([purge] if purge else [])
    try:
        if os.name == "nt":
            lines = cleanup_lines(exe, others, purge, extras)
            fd, bat = tempfile.mkstemp(suffix=".bat", prefix="lp-clean-", dir=str(Path(exe).parent) if exe else None)
            with os.fdopen(fd, "w") as f:
                f.write("\r\n".join(lines) + "\r\n")
            flags = _hidden_flags()
            subprocess.Popen(["cmd", "/c", bat], creationflags=flags, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            quoted = " ".join("'" + str(p).replace("'", "'\\''") + "'" for p in paths)
            subprocess.Popen(["sh", "-c", f"sleep 4; rm -rf {quoted}"], start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
