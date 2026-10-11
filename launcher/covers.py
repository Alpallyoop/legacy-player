"""Cover art. Console games: the libretro thumbnails project (thumbnails.libretro.com), the same pictures RetroArch uses.
Steam and Epic games: first the pictures the launchers already keep on this computer (no internet at all), then, only
when the player allowed internet downloads and pressed Get cover art, the Steam store's picture server (and Epic's
picture server for an address Epic's own launcher cache already holds).

What is sent: for console games, the console's picture list is asked for once and then each picture by its name; for a
Steam game its store number; for an Epic game without a cached picture address, its name to the Steam store search.
Nothing else. Every address is checked against ALLOWED_HOSTS (redirects too), one picture at a time, and every picture
is kept on this computer."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOST = "thumbnails.libretro.com"
STEAM_STORE = "store.steampowered.com"
STEAM_CDN = "shared.akamai.steamstatic.com"
EPIC_CDNS = {"cdn1.epicgames.com", "cdn2.epicgames.com", "cdn1.unrealengine.com", "cdn2.unrealengine.com"}
ALLOWED_HOSTS = {HOST, STEAM_STORE, STEAM_CDN, "cdn.cloudflare.steamstatic.com", "steamcdn-a.akamaihd.net"} | EPIC_CDNS

# Legacy Player console id -> libretro-thumbnails system folder. Ids the app does not use yet are harmless here, so every
# system the picture library has is listed under the id Legacy Player would give it.
SYSTEMS = {
    "nes": "Nintendo - Nintendo Entertainment System", "snes": "Nintendo - Super Nintendo Entertainment System",
    "fds": "Nintendo - Family Computer Disk System", "gb": "Nintendo - Game Boy", "gbc": "Nintendo - Game Boy Color",
    "gba": "Nintendo - Game Boy Advance", "n64": "Nintendo - Nintendo 64", "n64dd": "Nintendo - Nintendo 64DD",
    "ds": "Nintendo - Nintendo DS", "dsi": "Nintendo - Nintendo DSi", "3ds": "Nintendo - Nintendo 3DS",
    "gamecube": "Nintendo - GameCube", "wii": "Nintendo - Wii", "wiiu": "Nintendo - Wii U", "vb": "Nintendo - Virtual Boy",
    "pokemini": "Nintendo - Pokemon Mini", "satellaview": "Nintendo - Satellaview",
    "genesis": "Sega - Mega Drive - Genesis", "sms": "Sega - Master System - Mark III", "gamegear": "Sega - Game Gear",
    "segacd": "Sega - Mega-CD - Sega CD", "32x": "Sega - 32X", "saturn": "Sega - Saturn", "dreamcast": "Sega - Dreamcast",
    "sg1000": "Sega - SG-1000", "naomi": "Sega - Naomi",
    "ps1": "Sony - PlayStation", "ps2": "Sony - PlayStation 2", "ps3": "Sony - PlayStation 3", "ps4": "Sony - PlayStation 4",
    "psp": "Sony - PlayStation Portable", "psvita": "Sony - PlayStation Vita",
    "xbox": "Microsoft - Xbox", "x360": "Microsoft - Xbox 360", "msx": "Microsoft - MSX", "msx2": "Microsoft - MSX2",
    "atari": "Atari - 2600", "atari2600": "Atari - 2600", "atari5200": "Atari - 5200", "atari7800": "Atari - 7800",
    "jaguar": "Atari - Jaguar", "lynx": "Atari - Lynx", "atarist": "Atari - ST",
    "pce": "NEC - PC Engine - TurboGrafx 16", "pcecd": "NEC - PC Engine CD - TurboGrafx-CD", "pcfx": "NEC - PC-FX",
    "neogeo": "SNK - Neo Geo", "neogeocd": "SNK - Neo Geo CD", "ngp": "SNK - Neo Geo Pocket", "ngpc": "SNK - Neo Geo Pocket Color",
    "wonderswan": "Bandai - WonderSwan", "wonderswancolor": "Bandai - WonderSwan Color", "3do": "The 3DO Company - 3DO",
    "cdi": "Philips - CD-i", "colecovision": "Coleco - ColecoVision", "intellivision": "Mattel - Intellivision",
    "vectrex": "GCE - Vectrex", "c64": "Commodore - 64", "amiga": "Commodore - Amiga", "dos": "DOS", "arcade": "FBNeo - Arcade Games",
}
# A file type that pins down the system more exactly than the console shelf it sits on (the Atari shelf holds four).
EXTENSION_SYSTEMS = {".a78": "Atari - 7800", ".a52": "Atari - 5200", ".j64": "Atari - Jaguar", ".jag": "Atari - Jaguar",
                     ".lnx": "Atari - Lynx", ".fds": "Nintendo - Family Computer Disk System", ".dsi": "Nintendo - Nintendo DSi",
                     ".ndd": "Nintendo - Nintendo 64DD"}
MAX_BYTES = 3_000_000
LIST_MAX_BYTES = 12_000_000
REGIONS = ("USA", "World", "Europe", "USA, Europe", "Japan, USA", "Japan", "UK", "Australia", "Germany", "France", "Spain", "Italy", "Korea", "Asia")
_AVOID = re.compile(r"\((?:[^)]*\b(?:Beta|Proto|Prototype|Demo|Sample|Kiosk|Pirate|Unl|Hack|Aftermarket|Debug|Alpha)\b[^)]*)\)", re.I)
GENERIC_STEMS = {"default", "default.xex", "game", "eboot", "main", "boot", "disc", "disc1", "track 01", "track01"}


def clean_name(name: str) -> str:
    """libretro stores names with these characters turned into underscores."""
    return re.sub(r'[&*/:`<>?\\|"]', "_", name).strip()


def norm_key(name: str) -> str:
    """The part of a name both sides agree on: no (tags), "Legend of Zelda, The" == "The Legend of Zelda", no punctuation."""
    base = re.sub(r"\s*[\(\[].*$", "", str(name)).strip()
    m = re.match(r"^(.*?),\s*(The|A|An|Les|Le|La|Der|Die|Das)(\s+-\s+.*|\s*:.*)?$", base, re.I)
    if m:
        base = f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"
    base = base.lower().replace("&", "and").replace("_", " ")
    base = re.sub(r"\band\b", "", base)
    return re.sub(r"[^a-z0-9]+", "", base)


def _base_name(game: dict) -> tuple[str, str]:
    """(name to look up, region) for a game: a matched game-list (DAT) name wins, then the file name, then its folder."""
    dat = game.get("dat") or {}
    if dat.get("name"):
        return dat["name"], dat.get("region") or game.get("region") or ""
    path = Path(str(game.get("path") or ""))
    stem = path.stem
    if stem.lower() in GENERIC_STEMS and path.parent.name:
        stem = path.parent.name                     # Xbox 360 default.xex, PS3 EBOOT.BIN: the folder carries the name
    return stem or str(game.get("title") or ""), str(game.get("region") or "")


def candidates(game: dict) -> list[str]:
    """Names to try one by one when the picture list cannot be read: the exact name, then the plain title with each
    common region, then the title alone, and the "Title, The" form No-Intro uses."""
    stem, region = _base_name(game)
    out = [stem]
    base = re.sub(r"\s*[\(\[].*$", "", stem).strip() or str(game.get("title") or "")
    bases = [base]
    m = re.match(r"^(The|A|An)\s+(.+)$", base, re.I)
    if m:
        bases.append(f"{m.group(2)}, {m.group(1)}")
    if str(game.get("title") or "") and norm_key(game["title"]) != norm_key(base):
        bases.append(str(game["title"]))
    regions = ([region] if region else []) + [r for r in REGIONS[:6] if r != region]
    for b in bases:
        out += [f"{b} ({r})" for r in regions]
    out += bases
    seen, uniq = set(), []
    for c in out:
        c = clean_name(c)
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq[:16]


def systems_for(game: dict) -> list[str]:
    ext = str(game.get("extension") or Path(str(game.get("path") or "")).suffix).lower()
    out = [EXTENSION_SYSTEMS[ext]] if ext in EXTENSION_SYSTEMS else []
    if game.get("console") in SYSTEMS and SYSTEMS[game["console"]] not in out:
        out.append(SYSTEMS[game["console"]])
    return out


def best_listed(game: dict, listing: dict[str, list[str]]) -> str | None:
    """The picture in a system's list that fits this game best: same title, then the game's own region, then the usual
    regions, avoiding betas, demos and hacks."""
    stem, region = _base_name(game)
    exact = clean_name(stem)
    keys = [norm_key(stem)]
    if game.get("title"):
        keys.append(norm_key(str(game["title"])))
    for key in keys:
        names = listing.get(key) or []
        if not names:
            continue
        if exact in names:
            return exact
        wanted = [r for r in ([region] if region else []) + list(REGIONS)]

        def score(n: str):
            tags = re.findall(r"\(([^)]*)\)", n)
            reg = tags[0] if tags else ""
            parts = {p.strip() for p in reg.split(",")}
            rank = next((i for i, r in enumerate(wanted) if r == reg or (r in parts)), len(wanted))
            return (bool(_AVOID.search(n)), rank, len(tags), len(n), n)
        return min(names, key=score)
    return None


def cover_path(cache: Path, game_id: str) -> Path:
    return Path(cache) / (re.sub(r"[^A-Za-z0-9_-]", "_", game_id) + ".png")


class _OnlyAllowed(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urllib.parse.urlsplit(newurl)
        if parts.hostname not in ALLOWED_HOSTS or parts.scheme != "https":
            raise urllib.error.URLError("redirected away from the picture servers")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_open(request, timeout=12):
    return urllib.request.build_opener(_OnlyAllowed()).open(request, timeout=timeout)


def http_get(url: str, opener=None, limit: int = MAX_BYTES, test_hosts: set[str] | None = None) -> bytes | None:
    """GET one address from the allowed picture hosts (https only). None on any failure or when the answer is too big."""
    parts = urllib.parse.urlsplit(url)
    ok_host = parts.hostname in ALLOWED_HOSTS and parts.scheme == "https"
    if not ok_host and not (test_hosts and parts.netloc in test_hosts):
        return None
    try:
        with (opener or _default_open)(urllib.request.Request(url, headers={"User-Agent": "LegacyPlayer-covers"}), timeout=12) as resp:
            data = resp.read(limit + 1)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data if len(data) <= limit else None


def fetch_png(system: str, name: str, opener=None, scheme: str = "https", host: str = HOST) -> bytes | None:
    url = f"{scheme}://{host}/{urllib.parse.quote(system)}/Named_Boxarts/{urllib.parse.quote(name)}.png"
    data = http_get(url, opener, MAX_BYTES, {host})
    return data if data and data[:8] == b"\x89PNG\r\n\x1a\n" else None


def fetch_listing(system: str, opener=None, scheme: str = "https", host: str = HOST) -> dict[str, list[str]] | None:
    """The names of every box art picture the library has for a system (its folder listing), grouped by norm_key. One
    request per system instead of a dozen guesses per game; it carries no game names at all."""
    url = f"{scheme}://{host}/{urllib.parse.quote(system)}/Named_Boxarts/"
    data = http_get(url, opener, LIST_MAX_BYTES, {host})
    if not data:
        return None
    names = [urllib.parse.unquote(m.decode("utf-8", errors="replace"))[:-4]
             for m in re.findall(rb'href="([^"?/][^"/]*\.png)"', data)]
    if not names:
        return None
    out: dict[str, list[str]] = {}
    for n in names:
        out.setdefault(norm_key(n), []).append(n)
    return out


# --- Steam and Epic games ---------------------------------------------------------------------------------------------
def _picture(data: bytes | None, limit: int) -> bytes | None:
    if not data or len(data) > limit:
        return None
    return data if data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")) or (data[:4] == b"RIFF" and data[8:12] == b"WEBP") else None


def steam_cdn_art(appid: str, opener=None, limit: int = 1_500_000) -> bytes | None:
    """Steam's public tall cover for a store number (the same picture the Steam library shows)."""
    if not str(appid).isdigit():
        return None
    for name in ("library_600x900.jpg", "library_600x900_2x.jpg", "header.jpg"):
        data = _picture(http_get(f"https://{STEAM_CDN}/store_item_assets/steam/apps/{appid}/{name}", opener, limit), limit)
        if data:
            return data
    return None


def steam_store_search(title: str, opener=None) -> str | None:
    """The Steam store number of a game with exactly this name (after tidying), or None. Sends only the name."""
    term = str(title or "").strip()[:100]
    if not term:
        return None
    raw = http_get(f"https://{STEAM_STORE}/api/storesearch/?term={urllib.parse.quote(term)}&l=english&cc=US", opener, 400_000)
    try:
        items = json.loads(raw or b"null").get("items") or []
    except (ValueError, AttributeError):
        return None
    want = norm_key(term)
    for it in items:
        if isinstance(it, dict) and it.get("type", "app") == "app" and norm_key(str(it.get("name") or "")) == want and str(it.get("id", "")).isdigit():
            return str(it["id"])
    return None


def pc_online_art(game: dict, epic_urls: list[str] | None = None, opener=None, limit: int = 1_500_000) -> bytes | None:
    """A Steam or Epic game's picture from the internet (only called after the player said yes): Steam's own store number
    for a Steam game; for an Epic game, a picture address Epic's launcher cache already listed, else the Steam store's
    picture of the game with the same name."""
    from .pcgames import store_ids
    ids = store_ids(game)
    if ids.get("store") == "steam":
        return steam_cdn_art(ids.get("appid", ""), opener, limit)
    if ids.get("store") == "epic":
        for url in epic_urls or []:
            if urllib.parse.urlsplit(url).hostname in EPIC_CDNS:
                sep = "&" if "?" in url else "?"
                data = _picture(http_get(url + sep + "h=900&w=600&resize=1&quality=medium", opener, limit), limit)
                if data:
                    return data
        appid = steam_store_search(str(game.get("title") or ""), opener)
        return steam_cdn_art(appid, opener, limit) if appid else None
    return None


class CoverFetcher:
    """Fetches box art in the background, one picture at a time. local_art(game) -> bytes|None gives a Steam or Epic
    game's picture from this computer (tried first); epic_urls(game) -> [addresses] lists the picture addresses Epic's
    launcher cache holds for a game."""

    LIST_DAYS = 7

    def __init__(self, cache: Path, opener=None, scheme: str = "https", host: str = HOST, pause: float = 0.05,
                 local_art=None, epic_urls=None) -> None:
        self.cache, self.opener, self.scheme, self.host, self.pause = Path(cache), opener, scheme, host, pause
        self.local_art, self.epic_urls = local_art, epic_urls
        self.cache.mkdir(parents=True, exist_ok=True)
        self.state, self.done, self.total, self.found, self.current = "idle", 0, 0, 0, ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._miss_file = self.cache / "_misses.json"
        self._lists: dict[str, dict | None] = {}

    def misses(self) -> dict:
        try:
            return json.loads(self._miss_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def wanted(self, game: dict) -> bool:
        return game.get("console") == "pc" or bool(systems_for(game))

    def _listing(self, system: str) -> dict | None:
        if system in self._lists:
            return self._lists[system]
        folder = self.cache / "_lists"
        path = folder / (re.sub(r"[^A-Za-z0-9]+", "_", system) + ".json")
        listing = None
        try:
            if time.time() - path.stat().st_mtime < self.LIST_DAYS * 86400:
                listing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            listing = None
        if not isinstance(listing, dict):
            listing = fetch_listing(system, self.opener, self.scheme, self.host)
            if listing:
                try:
                    folder.mkdir(exist_ok=True)
                    path.write_text(json.dumps(listing), encoding="utf-8")
                except OSError:
                    pass
        self._lists[system] = listing
        return listing

    def _console_art(self, g: dict) -> bytes | None:
        for system in systems_for(g):
            listing = self._listing(system)
            if listing is not None:                      # the list is the truth: one request for the right name, or none
                name = best_listed(g, listing)
                data = fetch_png(system, name, self.opener, self.scheme, self.host) if name else None
            else:                                        # no list: guess a few names
                data = None
                for name in candidates(g):
                    if self._stop.is_set():
                        return None
                    data = fetch_png(system, name, self.opener, self.scheme, self.host)
                    if data:
                        break
            if data:
                return data
        return None

    def _pc_art(self, g: dict) -> bytes | None:
        data = None
        if self.local_art is not None:
            try:
                data = self.local_art(g)
            except Exception:
                data = None
        if not data:
            urls = []
            if self.epic_urls is not None:
                try:
                    urls = self.epic_urls(g) or []
                except Exception:
                    urls = []
            data = pc_online_art(g, urls, self.opener)
        return data

    def start(self, games: list[dict], force: bool = False) -> dict:
        if self.state == "running":
            return self.view()
        misses = self.misses()
        todo = [g for g in games if self.wanted(g) and (force or (
                not cover_path(self.cache, g["id"]).exists() and custom_cover(self.cache, g["id"]) is None
                and time.time() - misses.get(g["id"], 0) > 7 * 86400))]
        self._stop.clear()
        self._lists = {}
        self.state, self.done, self.total, self.found = "running", 0, len(todo), 0

        def work() -> None:
            try:
                for g in todo:
                    if self._stop.is_set():
                        break
                    self.current = g["title"]
                    saved = False
                    if g.get("console") == "pc":
                        data = self._pc_art(g)
                        if data:
                            try:
                                set_custom_cover(self.cache, g["id"], data)
                                saved = True
                            except ValueError:
                                saved = False
                    else:
                        data = self._console_art(g)
                        if data:
                            cover_path(self.cache, g["id"]).write_bytes(data)
                            saved = True
                    if saved:
                        self.found += 1
                        misses.pop(g["id"], None)
                    else:
                        misses[g["id"]] = time.time()
                    self.done += 1
                    time.sleep(self.pause)
                self._miss_file.write_text(json.dumps(misses), encoding="utf-8")
                self.state = "stopped" if self._stop.is_set() else "done"
            except Exception:
                self.state = "error"

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        return self.view()

    def cancel(self) -> dict:
        self._stop.set()
        return self.view()

    def view(self) -> dict:
        have = sum(1 for _ in self.cache.glob("*.png"))
        try:
            have += sum(1 for _ in (self.cache / "custom").glob("*.*"))
        except OSError:
            pass
        return {"state": self.state, "done": self.done, "total": self.total, "found": self.found, "current": self.current, "have": have}


# --- covers the player picks themselves -----------------------------------------------------------------------------
CUSTOM_MAX = 1_600_000
_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF8", "gif"))
CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


def image_kind(data: bytes) -> str | None:
    for magic, kind in _MAGIC:
        if data.startswith(magic):
            return kind
    return "webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP" else None


def _safe(game_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", game_id)


def custom_cover(cache: Path, game_id: str) -> Path | None:
    for kind in CONTENT_TYPES:
        p = Path(cache) / "custom" / f"{_safe(game_id)}.{kind}"
        if p.is_file():
            return p
    return None


def set_custom_cover(cache: Path, game_id: str, data: bytes) -> Path:
    kind = image_kind(data)
    if kind is None:
        raise ValueError("That is not a picture Legacy Player can show (use PNG, JPG, GIF or WEBP).")
    if len(data) > CUSTOM_MAX:
        raise ValueError("That picture is too big. Pictures up to about 1.5 MB work.")
    clear_custom_cover(cache, game_id)
    folder = Path(cache) / "custom"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{_safe(game_id)}.{kind}"
    target.write_bytes(data)
    return target


def clear_custom_cover(cache: Path, game_id: str) -> None:
    p = custom_cover(cache, game_id)
    while p is not None:
        try:
            p.unlink()
        except OSError:
            break
        p = custom_cover(cache, game_id)
