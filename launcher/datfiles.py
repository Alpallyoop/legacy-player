"""Game lists (DAT files) the player supplies, used to name their own game files exactly.

Legacy Player never bundles, downloads or shares a DAT file or a game. The player picks No-Intro or Redump lists they got
themselves (Logiqx XML or clrmamepro text). When the player presses the button, Legacy Player reads the player's own game
files on this computer to work out their CRC32 and SHA-1 checksums (zlib and hashlib, nothing leaves the computer) and
looks them up in those lists. A match gives the canonical name, region, languages, revision and whether the list calls it
a verified good dump. Checksums are cached by path, size and modification time so a file is only read once.

Safety: DAT files are untrusted input. XML is parsed with the standard library only after refusing any document type
declaration that carries an internal subset or any ENTITY declaration (no entity expansion is ever possible); a plain
external DOCTYPE line (which real No-Intro and Redump files have) is removed before parsing, so the parser never sees a
DOCTYPE at all. Sizes are capped.

The "dat" shape exposed per game (also documented in the report and in docs/LEGAL_POSITION.md):
    {"name": "Super Mario Bros. (World)", "title": "Super Mario Bros.", "region": "World", "languages": ["En"],
     "revision": "", "status": "verified"|"good"|"baddump", "verified": bool, "matched_by": "sha1"|"crc32",
     "list": "<the DAT's own name>", "file": "<file name inside the DAT>"}
"""
from __future__ import annotations

import io
import json
import os
import re
import threading
import time
import zipfile
import zlib
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_DAT_BYTES = 128 * 1024 * 1024
DEFAULT_LIMIT_MB = 1024
CHUNK = 1024 * 1024
REGION_WORDS = {"USA", "Europe", "Japan", "World", "Asia", "Australia", "Brazil", "Canada", "China", "France", "Germany",
                "Hong Kong", "Italy", "Korea", "Netherlands", "Spain", "Sweden", "Taiwan", "UK", "Russia", "Scandinavia",
                "Latin America", "Mexico", "Portugal", "Denmark", "Finland", "Norway", "Poland", "Greece", "Belgium",
                "Switzerland", "Austria", "India", "Ireland", "New Zealand", "South Africa", "Unknown"}
_LANG = re.compile(r"^[A-Z][a-z](?:-[A-Z][a-z]+)?(?:,[A-Z][a-z](?:-[A-Z][a-z]+)?)*$")
_REV = re.compile(r"^(?:Rev [0-9A-Za-z.]+|v[0-9][0-9A-Za-z.]*)$")


class DatError(ValueError):
    pass


# --- reading DAT files ----------------------------------------------------------------------------------------------------
def _safe_xml(data: bytes) -> bytes:
    """Refuse entity declarations and internal DTD subsets; drop a plain external DOCTYPE line."""
    lowered = data.lower()
    if b"<!entity" in lowered:
        raise DatError("This game list declares XML entities, which Legacy Player refuses to read.")
    start = lowered.find(b"<!doctype")
    if start >= 0:
        end = lowered.find(b">", start)
        if end < 0 or b"[" in lowered[start:end]:
            raise DatError("This game list has an inline document type definition, which Legacy Player refuses to read.")
        if lowered.find(b"<!doctype", end) >= 0:
            raise DatError("This game list has more than one document type declaration.")
        data = data[:start] + data[end + 1:]
    if b"<!" in data.replace(b"<![CDATA[", b"").replace(b"<!--", b""):
        raise DatError("This game list has declarations Legacy Player does not read.")
    return data


def _rom(attrs: dict) -> dict | None:
    crc = str(attrs.get("crc") or "").strip().lower()
    sha1 = str(attrs.get("sha1") or "").strip().lower()
    try:
        size = int(str(attrs.get("size") or "").strip())
    except ValueError:
        size = -1
    if not re.fullmatch(r"[0-9a-f]{8}", crc):
        crc = ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha1):
        sha1 = ""
    if not crc and not sha1:
        return None
    return {"name": str(attrs.get("name") or ""), "size": size, "crc": crc, "sha1": sha1,
            "status": str(attrs.get("status") or attrs.get("flags") or "").strip().lower()}


def _parse_logiqx(data: bytes) -> dict:
    data = _safe_xml(data)
    header: dict = {}
    games: list[dict] = []
    try:
        for _, el in ET.iterparse(io.BytesIO(data), events=("end",)):
            tag = el.tag.rsplit("}", 1)[-1].lower()
            if tag == "header":
                header = {c.tag.lower(): (c.text or "").strip() for c in el if isinstance(c.tag, str)}
                el.clear()
            elif tag in ("game", "machine", "software"):
                roms = [r for r in (_rom(c.attrib) for c in el if isinstance(c.tag, str) and c.tag.lower() in ("rom", "disk")) if r]
                desc = el.find("description")
                name = str(el.attrib.get("name") or (desc.text if desc is not None else "") or "").strip()
                if name and roms:
                    games.append({"name": name, "description": (desc.text or "").strip() if desc is not None else name, "roms": roms})
                el.clear()
    except ET.ParseError as exc:
        raise DatError(f"This game list is not valid XML ({exc}).") from exc
    return {"kind": "logiqx", "header": header, "games": games}


_CMP_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([()])|([^\s()"]+)')


def _parse_clrmamepro(text: str) -> dict:
    """clrmamepro text: clrmamepro ( name "..." ) game ( name "..." rom ( name "..." size 1 crc ... sha1 ... ) )"""
    tokens = []                                      # (is_paren, text): a quoted "(" is a word, not a bracket
    for m in _CMP_TOKEN.finditer(text):
        quoted, paren, bare = m.groups()
        tokens.append((paren is not None, quoted.replace('\\"', '"') if quoted is not None else (paren or bare)))
    pos = 0

    def block(depth: int = 0) -> list:
        nonlocal pos
        items: list = []
        key = None
        while pos < len(tokens):
            is_paren, tok = tokens[pos]
            pos += 1
            if is_paren and tok == ")":
                return items
            if is_paren and tok == "(":
                if depth > 6:
                    raise DatError("This game list is nested too deeply.")
                inner = block(depth + 1)
                items.append((key or "", inner))
                key = None
                continue
            if key is None:
                key = tok
            else:
                items.append((key, tok))
                key = None
        return items

    top = block()
    header: dict = {}
    games: list[dict] = []
    for key, value in top:
        if not isinstance(value, list):
            continue
        fields = {k.lower(): v for k, v in value if not isinstance(v, list)}
        if key.lower() in ("clrmamepro", "header"):
            header = {k: str(v) for k, v in fields.items()}
        elif key.lower() in ("game", "machine", "resource"):
            roms = [r for r in (_rom({k.lower(): v for k, v in sub if not isinstance(v, list)})
                                for k2, sub in value if isinstance(sub, list) and k2.lower() in ("rom", "disk")) if r]
            name = str(fields.get("name") or "").strip()
            if name and roms:
                games.append({"name": name, "description": str(fields.get("description") or name), "roms": roms})
    return {"kind": "clrmamepro", "header": header, "games": games}


def parse_dat(path: Path) -> dict:
    """{"kind", "header": {...}, "games": [{"name", "description", "roms": [{"name", "size", "crc", "sha1", "status"}]}]}"""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise DatError("That file could not be read.") from exc
    if size > MAX_DAT_BYTES:
        raise DatError("That file is too big to be a game list.")
    data = path.read_bytes()
    if data[:2] == b"PK":                                   # a zipped DAT, as No-Intro hands them out
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                inner = [i for i in z.infolist() if i.filename.lower().endswith((".dat", ".xml")) and i.file_size <= MAX_DAT_BYTES]
                if not inner:
                    raise DatError("That zip has no .dat file inside.")
                data = z.read(inner[0])
        except (zipfile.BadZipFile, OSError) as exc:
            raise DatError("That zip could not be read.") from exc
    head = data.lstrip(b"\xef\xbb\xbf \t\r\n")[:64]
    if head.startswith(b"<"):
        out = _parse_logiqx(data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        if not re.match(r"\s*(clrmamepro|game|header)\s*\(", text):
            raise DatError("That does not look like a No-Intro or Redump game list (Logiqx XML or clrmamepro).")
        out = _parse_clrmamepro(text)
    if not out["games"]:
        raise DatError("That game list has no games with checksums in it.")
    h = out["header"]
    out["name"] = str(h.get("name") or h.get("description") or path.stem)[:160]
    blob = " ".join(str(v) for v in h.values()).lower()
    out["redump"] = "redump" in blob
    return out


# --- what a DAT name says ---------------------------------------------------------------------------------------------------
def describe(name: str) -> dict:
    """Region, languages and revision from a No-Intro / Redump name like "Game (Europe) (En,Fr,De) (Rev 1)"."""
    tags = re.findall(r"\(([^()]*)\)", name)
    title = re.sub(r"\s*[\(\[].*$", "", name).strip()
    m = re.match(r"^(.*), (The|A|An)(\s+-\s+.*)?$", title)
    if m:
        title = f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"
    region, languages, revision = "", [], ""
    for tag in tags:
        parts = [p.strip() for p in tag.split(",")]
        if not region and parts and all(p in REGION_WORDS for p in parts):
            region = ", ".join(parts)
        elif not languages and _LANG.match(tag.replace(" ", "")):
            languages = tag.replace(" ", "").split(",")
        elif not revision and _REV.match(tag):
            revision = tag
    return {"title": title, "region": region, "languages": languages, "revision": revision}


# --- checksums of the player's own files ------------------------------------------------------------------------------------
def file_hashes(path: Path, stop: threading.Event | None = None) -> dict | None:
    crc, sha = 0, hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while True:
                if stop is not None and stop.is_set():
                    return None
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                crc = zlib.crc32(chunk, crc)
                sha.update(chunk)
    except OSError:
        return None
    return {"crc": f"{crc & 0xFFFFFFFF:08x}", "sha1": sha.hexdigest()}


def _cue_tracks(cue: Path) -> list[Path]:
    try:
        text = cue.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return []
    out = []
    for m in re.finditer(r'^\s*FILE\s+"?([^"\r\n]+?)"?\s+\w+\s*$', text, re.I | re.M):
        p = (cue.parent / m.group(1).strip()).resolve()
        if p.parent == cue.parent.resolve() and p.is_file():
            out.append(p)
    return out


class DatLibrary:
    """The player's DAT files, the checksum cache and the matching job. Everything lives in <data>/gamelists/."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.state, self.done, self.total, self.current = "idle", 0, 0, ""
        self.matched, self.skipped_big, self.error = 0, 0, ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # stored data
    def _load(self, name: str, default):
        try:
            value = json.loads((self.folder / name).read_text(encoding="utf-8"))
            return value if isinstance(value, type(default)) else default
        except (OSError, ValueError):
            return default

    def _save(self, name: str, value) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / (name + ".tmp")
        tmp.write_text(json.dumps(value), encoding="utf-8")
        os.replace(tmp, self.folder / name)

    def settings(self) -> dict:
        s = self._load("settings.json", {})
        files = [f for f in s.get("files", []) if isinstance(f, dict) and isinstance(f.get("path"), str)]
        try:
            limit = int(s.get("limit_mb", DEFAULT_LIMIT_MB))
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT_MB
        return {"files": files, "limit_mb": max(1, min(limit, 64 * 1024))}

    def files(self) -> list[dict]:
        out = []
        for f in self.settings()["files"]:
            out.append({**f, "exists": Path(f["path"]).is_file()})
        return out

    def add(self, path: str) -> dict:
        p = Path(str(path or "").strip().strip('"'))
        if not str(p) or not p.is_file():
            raise DatError("That file does not exist. Type the full path of a .dat file you downloaded.")
        if p.suffix.lower() not in (".dat", ".xml", ".zip"):
            raise DatError("Pick a .dat (or .xml / zipped) game list from No-Intro or Redump.")
        dat = parse_dat(p)
        s = self.settings()
        s["files"] = [f for f in s["files"] if os.path.normcase(f["path"]) != os.path.normcase(str(p))]
        entry = {"path": str(p), "name": dat["name"], "games": len(dat["games"]), "kind": dat["kind"], "redump": dat["redump"],
                 "added": int(time.time())}
        s["files"].append(entry)
        self._save("settings.json", s)
        return entry

    def remove(self, path: str) -> None:
        s = self.settings()
        s["files"] = [f for f in s["files"] if os.path.normcase(f["path"]) != os.path.normcase(str(path or "").strip())]
        self._save("settings.json", s)

    def set_limit(self, mb: int) -> None:
        s = self.settings()
        s["limit_mb"] = max(1, min(int(mb), 64 * 1024))
        self._save("settings.json", s)

    def matches(self) -> dict:
        return self._load("matches.json", {})

    def match_for(self, game_id: str) -> dict | None:
        m = self.matches().get(game_id)
        return m if isinstance(m, dict) else None

    # the job
    def _index(self) -> tuple[dict, dict]:
        by_sha, by_crc = {}, {}
        for f in self.settings()["files"]:
            try:
                dat = parse_dat(Path(f["path"]))
            except (DatError, OSError):
                continue
            for g in dat["games"]:
                for r in g["roms"]:
                    ref = (g["name"], r, dat["name"], dat["redump"])
                    if r["sha1"]:
                        by_sha.setdefault(r["sha1"], ref)
                    if r["crc"]:
                        by_crc.setdefault((r["size"], r["crc"]), ref)
                        by_crc.setdefault((-1, r["crc"]), ref)
        return by_sha, by_crc

    @staticmethod
    def _result(ref, how: str) -> dict:
        name, rom, list_name, redump = ref
        status = rom["status"] or ("verified" if redump else "good")
        if status not in ("verified", "good", "baddump", "nodump"):
            status = "good"
        return {"name": name, **describe(name), "status": status, "verified": status == "verified",
                "good": status in ("verified", "good"), "matched_by": how, "list": list_name, "file": rom["name"]}

    def start(self, games: list[dict]) -> dict:
        with self._lock:
            if self.state == "running":
                return self.view()
            self._stop.clear()
            todo = [g for g in games if g.get("console") != "pc" and g.get("path")]
            self.state, self.done, self.total, self.matched, self.skipped_big, self.error = "running", 0, len(todo), 0, 0, ""

        def work() -> None:
            try:
                by_sha, by_crc = self._index()
                if not by_sha and not by_crc:
                    self.state, self.error = "error", "Add a game list (DAT file) first."
                    return
                cache = self._load("hashes.json", {})
                limit = self.settings()["limit_mb"] * 1024 * 1024
                results = self.matches()
                for g in todo:
                    if self._stop.is_set():
                        break
                    self.current = g.get("title", "")
                    found = self._match_one(Path(g["path"]), by_sha, by_crc, cache, limit)
                    if found:
                        results[g["id"]] = found
                        self.matched += 1
                    else:
                        results.pop(g["id"], None)
                    self.done += 1
                    if self.done % 25 == 0:
                        self._save("hashes.json", cache)
                self._save("hashes.json", cache)
                self._save("matches.json", results)
                self.state = "stopped" if self._stop.is_set() else "done"
            except Exception as exc:          # a damaged file must never leave the page waiting forever
                self.state, self.error = "error", str(exc)[:200]

        self._thread = threading.Thread(target=work, daemon=True, name="dat-match")
        self._thread.start()
        return self.view()

    def _hash_cached(self, path: Path, cache: dict, limit: int) -> dict | None:
        try:
            st = path.stat()
        except OSError:
            return None
        key = f"{path}|{st.st_size}|{int(st.st_mtime)}"
        if key in cache:
            return cache[key]
        if st.st_size > limit:
            self.skipped_big += 1
            return None
        h = file_hashes(path, self._stop)
        if h is not None:
            h["size"] = st.st_size
            cache[key] = h
        return h

    def _match_one(self, path: Path, by_sha: dict, by_crc: dict, cache: dict, limit: int) -> dict | None:
        ext = path.suffix.lower()
        if ext == ".zip":                                # the zip already records each file's size and CRC32
            try:
                with zipfile.ZipFile(path) as z:
                    for info in z.infolist():
                        ref = by_crc.get((info.file_size, f"{info.CRC & 0xFFFFFFFF:08x}"))
                        if ref:
                            return self._result(ref, "crc32")
            except (zipfile.BadZipFile, OSError):
                return None
            return None
        if ext in (".7z", ".rar"):
            return None
        files = [path] + (_cue_tracks(path) if ext == ".cue" else [])
        for f in files:
            h = self._hash_cached(f, cache, limit)
            if not h:
                continue
            ref = by_sha.get(h["sha1"])
            if ref:
                return self._result(ref, "sha1")
            ref = by_crc.get((h.get("size", -1), h["crc"]))
            if ref and not ref[1]["sha1"]:              # the list has no SHA-1 to compare: the CRC32 and size are all it has
                return self._result(ref, "crc32")
        return None

    def cancel(self) -> dict:
        self._stop.set()
        return self.view()

    def view(self) -> dict:
        return {"state": self.state, "done": self.done, "total": self.total, "current": self.current, "matched": self.matched,
                "skipped_big": self.skipped_big, "error": self.error}
