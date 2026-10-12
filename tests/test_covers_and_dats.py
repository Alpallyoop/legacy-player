"""Cover art (libretro systems and name matching, Steam and Epic pictures from this computer and, with consent, from the
store picture servers) and game identification from the player's own DAT files."""
import base64
import hashlib
import json
import struct
import tempfile
import time
import unittest
import urllib.error
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from launcher import covers, datfiles, pcgames, privacy, scanner
from launcher.consoles import CONSOLES

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _jpeg(w: int, h: int, tail: bytes = b"") -> bytes:
    sof = b"\xff\xc0" + (11).to_bytes(2, "big") + b"\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big") + b"\x01\x01\x11\x00"
    return b"\xff\xd8\xff\xe0\x00\x02" + sof + b"\xff\xd9" + tail


class Resp:
    def __init__(self, data):
        self.data = data

    def read(self, n=-1):
        return self.data if n < 0 else self.data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_web(pages: dict, asked: list):
    def opener(req, timeout=0):
        asked.append(req.full_url)
        for prefix, body in pages.items():
            if req.full_url == prefix or (prefix.endswith("*") and req.full_url.startswith(prefix[:-1])):
                return Resp(body)
        raise urllib.error.URLError("404")
    return opener


def wait(f):
    for _ in range(200):
        if f.state != "running":
            return
        time.sleep(0.02)


class Systems(unittest.TestCase):
    def test_every_console_has_a_picture_library(self):
        for c in CONSOLES:
            if c.id != "pc":
                self.assertIn(c.id, covers.SYSTEMS, c.id)
        for name in ("Microsoft - Xbox 360", "Microsoft - Xbox", "Sony - PlayStation 2", "Sony - PlayStation 3",
                     "Sony - PlayStation Portable", "Nintendo - Wii U", "Nintendo - Nintendo 3DS"):
            self.assertIn(name, covers.SYSTEMS.values())
        self.assertEqual(["Atari - 7800", "Atari - 2600"], covers.systems_for({"console": "atari", "path": "/g/atari/Galaga.a78"}))

    def test_names_libretro_style(self):
        self.assertEqual("Ratchet _ Clank_ Size Matters", covers.clean_name("Ratchet & Clank: Size Matters"))
        self.assertEqual(covers.norm_key("Legend of Zelda, The - A Link to the Past (USA)"), covers.norm_key("The Legend of Zelda: A Link to the Past"))
        self.assertEqual(covers.norm_key("Ratchet _ Clank (USA)"), covers.norm_key("Ratchet & Clank"))

    def test_best_listed_prefers_own_region_and_avoids_betas(self):
        names = ["Halo 3 (USA)", "Halo 3 (Europe) (En,Fr,De)", "Halo 3 (USA) (Beta)", "Halo 3 (Japan)", "Halo 3 - ODST (USA)"]
        listing = {}
        for n in names:
            listing.setdefault(covers.norm_key(n), []).append(n)
        g = {"console": "x360", "path": "/g/Xbox 360/Halo 3/default.xex", "title": "Halo 3", "region": ""}
        self.assertEqual("Halo 3 (USA)", covers.best_listed(g, listing))
        self.assertEqual("Halo 3 (Europe) (En,Fr,De)", covers.best_listed({**g, "region": "Europe"}, listing))
        self.assertIsNone(covers.best_listed({**g, "path": "/g/x/Gears.iso", "title": "Gears"}, listing))
        # a matched game-list name is the most exact there is
        self.assertEqual("Halo 3 (Japan)", covers.best_listed({**g, "dat": {"name": "Halo 3 (Japan)", "region": "Japan"}}, listing))

    def test_guesses_use_the_folder_for_default_xex_and_move_the(self):
        c = covers.candidates({"path": "/g/Xbox 360/The Orange Box/default.xex", "title": "default", "region": ""})
        self.assertEqual("The Orange Box", c[0])
        self.assertIn("The Orange Box (USA)", c)
        self.assertIn("Orange Box, The (USA)", c)
        self.assertIn("The Orange Box", c)

    def test_scanner_titles_xbox_360_games_by_their_folder(self):
        with tempfile.TemporaryDirectory() as d:
            game = Path(d) / "Xbox 360" / "Halo 3 (USA)"
            game.mkdir(parents=True)
            (game / "default.xex").write_bytes(b"XEX2")
            found = scanner.scan([Path(d)])["games"]
        self.assertEqual([("x360", "Halo 3", "USA")], [(g.console, g.title, g.region) for g in found])


class FetchConsoleCovers(unittest.TestCase):
    def test_one_listing_request_then_one_picture(self):
        listing = b'<a href="?C=N;O=D">Name</a><a href="/Microsoft%20-%20Xbox%20360/">up</a>' \
                  b'<a href="Halo%203%20%28USA%29.png">x</a><a href="Portal%202%20%28USA%29.png">x</a>'
        base = "https://thumbnails.libretro.com/Microsoft%20-%20Xbox%20360/Named_Boxarts/"
        asked = []
        web = fake_web({base: listing, base + "Halo%203%20%28USA%29.png": PNG}, asked)
        f = covers.CoverFetcher(Path(tempfile.mkdtemp()), opener=web, pause=0)
        games = [{"id": "h3", "console": "x360", "title": "Halo 3", "path": "/g/Xbox 360/Halo 3/default.xex", "region": ""},
                 {"id": "gw", "console": "x360", "title": "Gears", "path": "/g/Xbox 360/Gears of War/default.xex", "region": ""}]
        f.start(games)
        wait(f)
        self.assertEqual(("done", 1, 2), (f.state, f.found, f.done))
        self.assertEqual([base, base + "Halo%203%20%28USA%29.png"], asked)       # no guessing when the list is known
        self.assertTrue(covers.cover_path(f.cache, "h3").is_file())
        # the list is kept for a week: a second run asks for nothing but the picture
        asked.clear()
        f2 = covers.CoverFetcher(f.cache, opener=web, pause=0)
        f2.start(games, force=True)
        wait(f2)
        self.assertNotIn(base, asked)

    def test_only_allowed_hosts(self):
        asked = []
        self.assertIsNone(covers.http_get("https://example.com/x.png", fake_web({"https://example.com/x.png": PNG}, asked)))
        self.assertIsNone(covers.http_get("http://thumbnails.libretro.com/x.png", fake_web({}, asked)))
        self.assertEqual([], asked)
        self.assertIn("store.steampowered.com", covers.ALLOWED_HOSTS)
        box_art = next(i for i in privacy.items({}, {}) if i["id"] == "covers")      # the permission names every host it may reach
        for host in covers.ALLOWED_HOSTS:
            self.assertIn(host, box_art["sends"])


# --- Chromium disk cache fixtures (what the Epic launcher's web view keeps) --------------------------------------------
def write_blockfile_cache(folder: Path, entries: list[tuple[str, bytes]]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index").write_bytes(b"\x00" * 256)
    header = bytearray(8192)
    struct.pack_into("<I", header, 0, 0xC104CAC3)
    struct.pack_into("<i", header, 12, 256)
    blocks = bytearray()
    for n, (key, body) in enumerate(entries, start=1):
        block = bytearray(256 * 2)                        # a long key spills into the next block, as Chromium does
        k = key.encode()
        struct.pack_into("<i", block, 32, len(k))
        struct.pack_into("<i", block, 44, len(body))
        struct.pack_into("<I", block, 60, 0x80000000 | n)     # stream 1 in an external file f_00000n
        block[96:96 + len(k)] = k
        blocks += block
        (folder / f"f_{n:06x}").write_bytes(body)
    (folder / "data_1").write_bytes(bytes(header) + bytes(blocks))


def write_simple_cache(folder: Path, entries: list[tuple[str, bytes]]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for n, (key, body) in enumerate(entries):
        k = key.encode()
        head = struct.pack("<QIII", 0xFCFB6D1BA7725C30, 5, len(k), 0) + b"\x00" * 4
        eof = struct.pack("<QIIi", 0xF4FA6F45970D41D8, 0, 0, len(body)) + b"\x00" * 4
        (folder / f"{n:016x}_0").write_bytes(head + k + body + eof + b"HTTP/1.1 200" + eof)


class PcPictures(unittest.TestCase):
    TALL = "https://cdn1.epicgames.com/offer/min/HadesTall_1200x1600-abc.jpg"
    WIDE = "https://cdn1.epicgames.com/offer/min/HadesWide_2560x1440-def.jpg"

    def epic_env(self, d: Path, cache_kind: str = "block", with_catcache: bool = True) -> dict:
        saved = d / "Local" / "EpicGamesLauncher" / "Saved"
        catalog = [{"id": "abc", "namespace": "min", "title": "Hades", "keyImages": [
            {"type": "DieselGameBox", "url": self.WIDE, "width": 2560, "height": 1440},
            {"type": "DieselGameBoxTall", "url": self.TALL, "width": 1200, "height": 1600}],
            "releaseInfo": [{"id": "r1", "appId": "Min", "platform": ["Windows"]}]},
            {"id": "zzz", "namespace": "other", "title": "Other", "keyImages": [{"type": "DieselGameBoxTall", "url": "https://cdn1.epicgames.com/other.jpg"}]}]
        if with_catcache:
            (saved / "Data" / "Catalog").mkdir(parents=True)
            (saved / "Data" / "Catalog" / "catcache.bin").write_bytes(base64.b64encode(json.dumps(catalog).encode()))
        entries = [("1/0/_dk_https://store.epicgames.com https://store.epicgames.com " + self.TALL + "?h=480&quality=medium&resize=1&w=360",
                    _jpeg(360, 480, b"epic-tall")),
                   ("1/0/_dk_https://store.epicgames.com https://store.epicgames.com " + self.WIDE, _jpeg(640, 360, b"epic-wide")),
                   ("https://catalog-public-service-prod06.ol.epicgames.com/catalog/api/shared/namespace/min/bulk/items?id=abc",
                    json.dumps({"abc": catalog[0]}).encode())]
        folder = saved / "webcache_4147" / "Cache" / ("Cache_Data" if cache_kind == "block" else "")
        (write_blockfile_cache if cache_kind == "block" else write_simple_cache)(folder, entries)
        return {"LOCALAPPDATA": str(d / "Local")}

    GAME = {"id": "epic-Min", "console": "pc", "title": "Hades", "root": "epic", "path": "com.epicgames.launcher://apps/min%3Aabc%3AMin?action=launch&silent=true"}

    def test_epic_picture_from_the_launchers_blockfile_cache(self):
        with tempfile.TemporaryDirectory() as d:
            env = self.epic_env(Path(d))
            self.assertEqual([self.TALL, self.WIDE], pcgames.epic_key_images("min", "abc", "Min", env))
            self.assertTrue(pcgames.epic_art(self.GAME, env).endswith(b"epic-tall"))

    def test_epic_picture_from_the_simple_cache_and_web_cache_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            env = self.epic_env(Path(d), cache_kind="simple", with_catcache=False)
            self.assertEqual([self.TALL, self.WIDE], pcgames.epic_key_images("min", "abc", "Min", env))
            self.assertTrue(pcgames.epic_art(self.GAME, env).endswith(b"epic-tall"))
            self.assertIsNone(pcgames.epic_art({**self.GAME, "path": "com.epicgames.launcher://apps/x%3Ay%3AZ?action=launch"}, env))

    def test_pc_games_get_local_art_first_then_steam_cdn_with_consent(self):
        cache = Path(tempfile.mkdtemp())
        asked = []
        web = fake_web({"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/730/library_600x900.jpg": _jpeg(600, 900, b"cdn"),
                        "https://store.steampowered.com/api/storesearch/*": json.dumps({"total": 2, "items": [
                            {"type": "app", "name": "Hades II", "id": 1145350}, {"type": "app", "name": "Fortnite™", "id": 99}]}).encode(),
                        "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/99/library_600x900.jpg": _jpeg(600, 900, b"byname")}, asked)
        local = {"steam-620": _jpeg(600, 900, b"local")}
        f = covers.CoverFetcher(cache, opener=web, pause=0, local_art=lambda g: local.get(g["id"]), epic_urls=lambda g: [])
        games = [{"id": "steam-620", "console": "pc", "root": "steam", "title": "Portal 2", "path": "steam://rungameid/620"},
                 {"id": "steam-730", "console": "pc", "root": "steam", "title": "CS", "path": "steam://rungameid/730"},
                 {"id": "epic-fn", "console": "pc", "root": "epic", "title": "Fortnite", "path": "com.epicgames.launcher://apps/fn%3Ax%3AFortnite?action=launch"},
                 {"id": "epic-none", "console": "pc", "root": "epic", "title": "Nothing Like It", "path": "com.epicgames.launcher://apps/q%3Ar%3AS?action=launch"}]
        f.start(games)
        wait(f)
        self.assertEqual(("done", 3, 4), (f.state, f.found, f.done))
        self.assertTrue(covers.custom_cover(cache, "steam-620").read_bytes().endswith(b"local"))
        self.assertTrue(covers.custom_cover(cache, "steam-730").read_bytes().endswith(b"cdn"))
        self.assertTrue(covers.custom_cover(cache, "epic-fn").read_bytes().endswith(b"byname"))
        self.assertFalse(any("620" in u for u in asked))                      # the local picture needed no internet
        self.assertTrue(all(u.split("/")[2] in covers.ALLOWED_HOSTS for u in asked))

    def test_epic_cdn_used_for_an_address_the_launcher_listed(self):
        asked = []
        web = fake_web({self.TALL + "?h=900&w=600&resize=1&quality=medium": _jpeg(600, 800, b"epiccdn")}, asked)
        data = covers.pc_online_art(self.GAME, [self.TALL, "https://evil.example.com/x.jpg"], web)
        self.assertTrue(data.endswith(b"epiccdn"))
        self.assertFalse(any("evil" in u for u in asked))

    def test_app_adopts_epic_art_on_scan(self):
        from launcher.app import LauncherApp
        app = LauncherApp(Path(tempfile.mkdtemp()))
        with mock.patch("launcher.app.pcgames.library_entries", return_value=[dict(self.GAME, sort_title="hades", region="", tags=["Epic"], size=1,
                                                                                    extension=".epic", is_archive=False, compat_id="pc:epic:hades")]), \
                mock.patch("launcher.app.pcgames.epic_art", return_value=_jpeg(300, 450, b"e")):
            out = app.rescan()
        self.assertEqual(1, out["steam_pictures"])
        self.assertTrue(covers.custom_cover(app.covers.cache, "epic-Min").is_file())


# --- DAT files ---------------------------------------------------------------------------------------------------------------
ROM = b"NES\x1a" + bytes(range(256)) * 4
ROM2 = b"another rom" * 50


def logiqx(rom: bytes, extra: str = "", doctype: bool = True) -> str:
    crc = f"{zlib.crc32(rom) & 0xFFFFFFFF:08X}"
    sha = hashlib.sha1(rom).hexdigest()
    crc2 = f"{zlib.crc32(ROM2) & 0xFFFFFFFF:08x}"
    return ('<?xml version="1.0"?>\n'
            + ('<!DOCTYPE datafile PUBLIC "-//Logiqx//DTD ROM Management Datafile//EN" "http://www.logiqx.com/Dats/datafile.dtd">\n' if doctype else "")
            + '<datafile>\n\t<header>\n\t\t<name>Nintendo - Nintendo Entertainment System (Headered)</name>\n\t\t<description>Nintendo - NES</description>\n'
            '\t\t<version>20240101-000000</version>\n\t\t<homepage>No-Intro</homepage>\n\t</header>\n'
            f'\t<game name="Legend of Zelda, The (Europe) (En,Fr,De) (Rev 1)">\n\t\t<description>Legend of Zelda, The (Europe) (En,Fr,De) (Rev 1)</description>\n'
            f'\t\t<rom name="Legend of Zelda, The (Europe) (En,Fr,De) (Rev 1).nes" size="{len(rom)}" crc="{crc}" md5="00" sha1="{sha.upper()}" status="verified"/>\n\t</game>\n'
            f'\t<game name="Other Game (Japan)">\n\t\t<description>Other Game (Japan)</description>\n'
            f'\t\t<rom name="Other Game (Japan).nes" size="{len(ROM2)}" crc="{crc2}"/>\n\t</game>\n'
            + extra + '</datafile>\n')


def clrmamepro(rom: bytes) -> str:
    return ('clrmamepro (\n\tname "Sony - PlayStation (Redump)"\n\tdescription "Sony - PlayStation"\n\tversion "2024"\n\thomepage "redump.org"\n)\n\n'
            'game (\n\tname "Crash ( \\"Bandicoot\\" ) (USA)"\n\tdescription "Crash (USA)"\n'
            f'\trom ( name "Crash (USA).cue" size {len(rom)} crc {zlib.crc32(rom) & 0xFFFFFFFF:08x} md5 x sha1 {hashlib.sha1(rom).hexdigest()} )\n)\n')


class DatFiles(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_describe_names(self):
        self.assertEqual({"title": "The Legend of Zelda", "region": "Europe", "languages": ["En", "Fr", "De"], "revision": "Rev 1"},
                         datfiles.describe("Legend of Zelda, The (Europe) (En,Fr,De) (Rev 1)"))
        self.assertEqual("USA, Europe", datfiles.describe("Tetris (USA, Europe)")["region"])

    def test_logiqx_with_a_plain_doctype_is_read(self):
        p = self.dir / "nes.dat"
        p.write_text(logiqx(ROM), encoding="utf-8")
        dat = datfiles.parse_dat(p)
        self.assertEqual(("logiqx", 2), (dat["kind"], len(dat["games"])))
        self.assertEqual("Nintendo - Nintendo Entertainment System (Headered)", dat["name"])
        self.assertEqual(hashlib.sha1(ROM).hexdigest(), dat["games"][0]["roms"][0]["sha1"])

    def test_entities_and_inline_dtds_are_refused(self):
        bomb = ('<?xml version="1.0"?>\n<!DOCTYPE lolz [\n <!ENTITY lol "lol">\n <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">\n'
                ' <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">\n]>\n'
                '<datafile><game name="&lol3;"><rom name="a" size="1" crc="00000000"/></game></datafile>\n')
        external = ('<?xml version="1.0"?>\n<!DOCTYPE datafile [<!ELEMENT datafile ANY>]>\n<datafile><game name="x"><rom name="a" size="1" crc="00000000"/></game></datafile>')
        sneaky = '<?xml version="1.0"?>\n<datafile>\n<!ENTITY x SYSTEM "file:///etc/passwd">\n</datafile>'
        for text in (bomb, external, sneaky):
            p = self.dir / "bad.dat"
            p.write_text(text, encoding="utf-8")
            with self.assertRaises(datfiles.DatError):
                datfiles.parse_dat(p)
        lib = datfiles.DatLibrary(self.dir / "lists")
        with self.assertRaises(datfiles.DatError):
            lib.add(str(self.dir / "bad.dat"))
        self.assertEqual([], lib.files())

    def test_clrmamepro_with_quoted_brackets(self):
        p = self.dir / "psx.dat"
        p.write_text(clrmamepro(b"FILE x"), encoding="utf-8")
        dat = datfiles.parse_dat(p)
        self.assertEqual(("clrmamepro", True), (dat["kind"], dat["redump"]))
        self.assertEqual('Crash ( "Bandicoot" ) (USA)', dat["games"][0]["name"])

    def test_not_a_dat(self):
        p = self.dir / "notes.dat"
        p.write_text("hello there", encoding="utf-8")
        with self.assertRaises(datfiles.DatError):
            datfiles.parse_dat(p)

    def test_matching_files_zips_and_the_hash_cache(self):
        games_dir = self.dir / "games"
        games_dir.mkdir()
        (games_dir / "zelda.nes").write_bytes(ROM)
        with zipfile.ZipFile(games_dir / "other.zip", "w") as z:
            z.writestr("Other Game (Japan).nes", ROM2)
        (games_dir / "unknown.nes").write_bytes(b"homebrew")
        (games_dir / "huge.nes").write_bytes(b"x" * (2 * 1024 * 1024))
        dat = self.dir / "nes.dat"
        dat.write_text(logiqx(ROM), encoding="utf-8")
        lib = datfiles.DatLibrary(self.dir / "lists")
        self.assertEqual(2, lib.add(str(dat))["games"])
        lib.set_limit(1)
        games = [{"id": n, "console": "nes", "title": n, "path": str(games_dir / f)} for n, f in
                 (("z", "zelda.nes"), ("o", "other.zip"), ("u", "unknown.nes"), ("h", "huge.nes"))]
        games.append({"id": "pc1", "console": "pc", "title": "Steam game", "path": "steam://rungameid/1"})
        lib.start(games)
        lib._thread.join(10)
        view = lib.view()
        self.assertEqual(("done", 4, 2, 1), (view["state"], view["total"], view["matched"], view["skipped_big"]))
        z = lib.match_for("z")
        self.assertEqual({"name": "Legend of Zelda, The (Europe) (En,Fr,De) (Rev 1)", "title": "The Legend of Zelda", "region": "Europe",
                          "languages": ["En", "Fr", "De"], "revision": "Rev 1", "status": "verified", "verified": True, "good": True,
                          "matched_by": "sha1", "list": "Nintendo - Nintendo Entertainment System (Headered)",
                          "file": "Legend of Zelda, The (Europe) (En,Fr,De) (Rev 1).nes"}, z)
        o = lib.match_for("o")
        self.assertEqual(("Other Game (Japan)", "Japan", "crc32", False, True), (o["name"], o["region"], o["matched_by"], o["verified"], o["good"]))
        self.assertIsNone(lib.match_for("u"))
        # the second run reads no file again: path + size + time are the same
        with mock.patch.object(datfiles, "file_hashes", side_effect=AssertionError("hashed again")):
            lib.start(games[:1] + games[2:3])
            lib._thread.join(10)
        self.assertEqual("done", lib.view()["state"])
        lib.remove(str(dat))
        self.assertEqual([], lib.files())

    def test_app_exposes_the_dat_field(self):
        from launcher.app import AppError, LauncherApp
        app = LauncherApp(Path(tempfile.mkdtemp()))
        root = self.dir / "roms" / "nes"
        root.mkdir(parents=True)
        (root / "Zelda.nes").write_bytes(ROM)
        app.catalog.set_roots([str(self.dir / "roms")])
        app.rescan()
        with self.assertRaises(AppError):
            app.api_dats({"action": "match"})                # no list yet
        dat = self.dir / "nes.dat"
        dat.write_text(logiqx(ROM, doctype=False), encoding="utf-8")
        out = app.api_dats({"action": "add", "path": str(dat)})
        self.assertEqual(1, len(out["files"]))
        app.api_dats({"action": "match"})
        app.dats._thread.join(10)
        out = app.api_dats({})
        self.assertEqual((1, 1, 1), (out["matched"], out["verified"], out["games"]))
        row = app.api_library({})["games"][0]
        self.assertEqual("Legend of Zelda, The (Europe) (En,Fr,De) (Rev 1)", row["dat"]["name"])
        self.assertTrue(app.api_game({"id": row["id"]})["dat"]["verified"])
        with self.assertRaises(AppError):
            app.api_dats({"action": "add", "path": str(self.dir / "missing.dat")})


if __name__ == "__main__":
    unittest.main()
