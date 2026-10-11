"""The Library: the filter panel (backend filtering with counts), hidden games, names shown inside Legacy Player only,
the official name, and which emulator opens a game (once, always, or for the whole console)."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from launcher import gamecard
from launcher.app import AppError, LauncherApp

from tests.test_gamecard import ANSWERS, fake_opener


def touch(path: Path, data: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


LOOKED = {
    "Super Mario Kart": {"found": True, "page": "Super Mario Kart", "fields": {
        "release": "1992-08-27", "developer": "Nintendo EAD", "publisher": "Nintendo", "genre": "kart racing game",
        "series": "Mario Kart", "max_players": 2}},
    "Mario Kart DS": {"found": True, "page": "Mario Kart DS", "fields": {
        "release": "2005-11-14", "developer": "Nintendo EAD", "publisher": "Nintendo", "genre": "kart racing game",
        "series": "Mario Kart", "max_players": 8}},
    "Doom": {"found": True, "page": "Doom (1993 video game)", "fields": {
        "release": "1995", "developer": "id Software", "publisher": "Williams Entertainment", "genre": "first-person shooter",
        "series": "Doom"}},
    "Tetris": {"found": True, "page": "Tetris (Game Boy video game)", "fields": {"release": "1989-06-14", "genre": "puzzle video game",
                                                                                "publisher": "Nintendo"}},
}


class LibraryBase(unittest.TestCase):
    def setUp(self):
        p = mock.patch("launcher.emulators.shutil.which", return_value=None)
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "Games"
        touch(self.root / "SNES" / "Super Mario Kart (USA).sfc")
        touch(self.root / "SNES" / "Doom (Europe).sfc")
        touch(self.root / "DS" / "Mario Kart DS (USA, Europe).nds")
        touch(self.root / "GB" / "Tetris (World).gb")
        touch(self.root / "GB" / "Unknown Thing (Japan).gb")
        self.app = LauncherApp(Path(self.tmp.name) / "data", roots=[str(self.root)])
        self.app.rescan()
        self.ids = {g["title"]: g["id"] for g in self.app.api_library({})["games"]}
        for title, answer in LOOKED.items():          # as if each game had been looked up already
            path = self.app.cards._path(self.ids[title])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(answer), encoding="utf-8")
        self.app.cards._memo.clear()                  # the app kept "not looked up" from the first listing

    def titles(self, **body):
        return sorted(g["title"] for g in self.app.api_library(body)["games"])


class Filters(LibraryBase):
    def test_existing_parameters_still_work(self):
        self.assertEqual(["Doom", "Super Mario Kart"], self.titles(console="snes"))
        self.assertEqual(["Tetris"], self.titles(q="tet"))
        self.app.api_favorite({"id": self.ids["Doom"], "favorite": True})
        self.assertEqual(["Doom"], self.titles(favorites=True))

    def test_each_filter_narrows_and_they_combine(self):
        self.assertEqual(["Mario Kart DS", "Super Mario Kart"], self.titles(series="mario kart"))
        self.assertEqual(["Mario Kart DS", "Super Mario Kart"], self.titles(developer="Nintendo EAD"))
        self.assertEqual(["Mario Kart DS", "Super Mario Kart", "Tetris"], self.titles(publisher="nintendo"))
        self.assertEqual(["Doom"], self.titles(genre="First-person shooter"))
        self.assertEqual(["Mario Kart DS", "Super Mario Kart"], self.titles(region="USA"))   # "USA, Europe" counts as both
        self.assertEqual(["Doom", "Mario Kart DS"], self.titles(region="Europe"))
        self.assertEqual(["Super Mario Kart"], self.titles(series="Mario Kart", console="snes"))
        self.assertEqual(["Doom", "Super Mario Kart", "Tetris"], self.titles(year_from=1985, year_to=1999))
        self.assertEqual(["Mario Kart DS"], self.titles(year_from="2000"))
        four = self.titles(players="4")                      # Wikidata says 8; the built-in list knows Super Mario Kart
        self.assertIn("Mario Kart DS", four)
        self.assertNotIn("Unknown Thing", four)              # not known: the console's guess is not a fact
        self.assertNotIn("Unknown Thing", self.titles(players="1"))
        self.assertEqual([], self.titles(series="Mario Kart", year_to=1990))
        self.assertEqual(sorted(LOOKED) + ["Unknown Thing"], self.titles(cover="no"))
        self.assertEqual([], self.titles(cover="yes"))

    def test_counts_follow_the_other_filters(self):
        d = self.app.api_library({"console": "snes"})
        facets = d["facets"]
        series = {f["value"]: f["count"] for f in facets["series"]}
        self.assertEqual({"Mario Kart": 1, "Doom": 1}, series)
        consoles = {f["value"]: f["count"] for f in facets["console"]}
        self.assertEqual(2, consoles["snes"])
        self.assertEqual(1, consoles["ds"])                  # the console filter does not shrink its own choices
        self.assertEqual({"min": 1992, "max": 1995, "known": 2}, facets["years"])
        self.assertEqual(["console"], d["filters_on"])
        d = self.app.api_library({"series": "Mario Kart"})
        self.assertEqual({"Mario Kart": 2, "Doom": 1}, {f["value"]: f["count"] for f in d["facets"]["series"]})
        self.assertEqual(2, {f["value"]: f["count"] for f in d["facets"]["developer"]}["Nintendo EAD"])

    def test_cards_carry_facts_for_the_year_and_tags(self):
        g = next(x for x in self.app.api_library({})["games"] if x["title"] == "Super Mario Kart")
        self.assertEqual("1992-08-27", g["facts"]["release"])
        self.assertEqual(1992, g["facts"]["year"])
        self.assertEqual("Mario Kart", g["facts"]["series"])
        u = next(x for x in self.app.api_library({})["games"] if x["title"] == "Unknown Thing")
        self.assertIsNone(u["facts"]["year"])                # unknown: nothing is shown
        self.assertEqual("", u["facts"]["series"])

    def test_the_players_own_text_wins_and_is_filterable(self):
        self.app.api_game_meta({"id": self.ids["Unknown Thing"], "series": "Mystery", "release": "2001"})
        self.assertEqual(["Unknown Thing"], self.titles(series="mystery"))
        self.assertEqual(["Mario Kart DS", "Unknown Thing"], self.titles(year_from=2000))
        self.app.api_game_meta({"id": self.ids["Doom"], "series": ""})
        self.assertEqual("Doom", self.app.api_game_card({"id": self.ids["Doom"]})["fields"]["series"]["value"])

    def test_year_sort_puts_unknown_last(self):
        order = [g["title"] for g in self.app.api_library({"sort": "year"})["games"]]
        self.assertEqual(["Tetris", "Super Mario Kart", "Doom", "Mario Kart DS", "Unknown Thing"], order)


class HiddenGames(LibraryBase):
    def test_hide_and_unhide(self):
        gid = self.ids["Doom"]
        self.app.api_game_meta({"id": gid, "hidden": True})
        normal = self.app.api_library({})
        self.assertNotIn("Doom", [g["title"] for g in normal["games"]])
        self.assertEqual(1, normal["hidden_total"])
        hidden = self.app.api_library({"hidden": True})
        self.assertEqual(["Doom"], [g["title"] for g in hidden["games"]])
        self.assertTrue(hidden["showing_hidden"])
        self.assertTrue(hidden["games"][0]["hidden"])
        self.app.api_game_meta({"id": gid, "hidden": False})
        self.assertIn("Doom", self.titles())
        self.assertEqual([], self.titles(hidden=True))


class Names(LibraryBase):
    def test_rename_changes_only_the_shown_name(self):
        gid = self.ids["Tetris"]
        path = Path(self.app.games[gid]["path"])
        g = self.app.api_game_meta({"id": gid, "title": "Tetris (my copy)"})
        self.assertEqual("Tetris (my copy)", g["title"])
        self.assertTrue(g["own_title"])
        self.assertEqual("Tetris", g["original_title"])
        self.assertTrue(path.exists())                       # the file keeps its name
        self.assertEqual(["Tetris (my copy)"], self.titles(q="my copy"))
        g = self.app.api_game_meta({"id": gid, "title": ""})   # Reset name
        self.assertEqual("Tetris", g["title"])
        self.assertFalse(g["own_title"])

    def test_official_name_one_and_all(self):
        self.assertEqual("Doom", gamecard.official_title({"page": "Doom (1993 video game)"}))
        self.assertEqual("Tetris", gamecard.official_title({"page": "Tetris (Game Boy video game)"}))
        self.assertEqual("Pokémon Red and Blue", gamecard.official_title({"page": "Pokémon Red and Blue"}))
        with self.assertRaises(AppError):
            self.app.api_official_name({"id": self.ids["Unknown Thing"]})        # never looked up
        self.app.api_game_meta({"id": self.ids["Super Mario Kart"], "title": "SMK"})
        out = self.app.api_official_name({"all": True})
        self.assertEqual(0, out["changed"])                  # the others already match; the player's own name is kept
        self.assertEqual("SMK", self.app.api_library({"q": "smk"})["games"][0]["title"])
        self.assertEqual(1, self.app.api_official_name({"all": True, "replace_own": True})["changed"])
        g = self.app.api_official_name({"id": self.ids["Super Mario Kart"]})
        self.assertEqual("Super Mario Kart", g["title"])
        self.assertTrue(Path(self.app.games[self.ids["Super Mario Kart"]]["path"]).exists())


class OpenWith(LibraryBase):
    def fake(self, name: str) -> tuple[Path, Path]:
        script = Path(self.tmp.name) / f"{name}.sh"
        out = Path(self.tmp.name) / f"{name}.txt"
        script.write_text(f'#!/bin/sh\nprintf "%s" "$0" > "{out}"\n')
        script.chmod(0o755)
        return script, out

    def wait(self, out: Path) -> bool:
        for _ in range(60):
            if out.exists():
                return True
            time.sleep(0.05)
        return False

    def test_per_game_choice_is_validated_and_shown(self):
        gid = self.ids["Super Mario Kart"]
        with self.assertRaises(AppError):
            self.app.api_game_meta({"id": gid, "emulator": "dolphin"})          # Dolphin does not run SNES games
        g = self.app.api_game_meta({"id": gid, "emulator": "bsnes"})
        self.assertEqual("bsnes", g["own_emulator"])
        self.assertEqual("bsnes", g["emulator_id"])
        self.assertEqual(["Super Mario Kart"], self.titles(emulator="bsnes"))
        g = self.app.api_game_meta({"id": gid, "emulator": ""})                  # Use the default for SNES
        self.assertEqual("", g["own_emulator"])

    @unittest.skipIf(sys.platform == "win32", "uses POSIX shell scripts as fake emulators")
    def test_launch_honours_once_then_always_then_console_default(self):
        gid = self.ids["Super Mario Kart"]
        snes9x, out9 = self.fake("snes9x")
        bsnes, outb = self.fake("bsnes")
        self.app.api_emulators({"emulator": "snes9x", "path": str(snes9x)})
        self.app.api_emulators({"emulator": "bsnes", "path": str(bsnes)})
        lib = self.app.api_library({})
        opts = lib["emulator_options"]["snes"]
        self.assertEqual({"snes9x", "bsnes"}, {o["id"] for o in opts["options"] if o["installed"]})
        self.assertEqual("snes9x", opts["now"])
        self.assertEqual("snes9x", self.app.api_launch({"id": gid})["emulator"].lower())   # automatic: the console's first
        r = self.app.api_launch({"id": gid, "emulator": "bsnes"})                       # Open with: once
        self.assertEqual("bsnes", r["emulator"])
        self.assertTrue(self.wait(outb))
        self.assertEqual("Snes9x", self.app.launch_check(self.app.games[gid])["emulator"])  # nothing was remembered
        with self.assertRaises(AppError):
            self.app.api_launch({"id": gid, "emulator": "dolphin"})
        with self.assertRaises(AppError):
            self.app.api_launch({"id": gid, "emulator": "retroarch"})                   # not on this computer
        self.app.api_game_meta({"id": gid, "emulator": "bsnes"})                        # Always open with
        self.assertEqual("bsnes", self.app.launch_check(self.app.games[gid])["emulator_id"])
        self.assertEqual("snes9x", self.app.launch_check(self.app.games[self.ids["Doom"]])["emulator_id"])
        self.app.api_game_meta({"id": gid, "emulator": ""})
        self.app.api_console_emulator({"console": "snes", "emulator": "bsnes"})        # Use this for every SNES game
        self.assertEqual("bsnes", self.app.launch_check(self.app.games[self.ids["Doom"]])["emulator_id"])
        self.assertEqual("bsnes", self.app.api_library({})["emulator_options"]["snes"]["chosen"])


class SeriesLookup(unittest.TestCase):
    def test_series_comes_from_wikidata_p179(self):
        answers = json.loads(json.dumps(ANSWERS))
        answers["Special:EntityData/Q1234"]["entities"]["Q1234"]["claims"]["P179"] = [{"mainsnak": {"datavalue": {"value": {"id": "Q11168"}}}}]
        answers["wbgetentities"]["entities"]["Q11168"] = {"labels": {"en": {"value": "Mario Kart"}}}
        out = gamecard.lookup("Mario Kart 64", "Nintendo 64", fake_opener(answers, []))
        self.assertEqual("Mario Kart", out["fields"]["series"])
        self.assertEqual("Nintendo", out["fields"]["developer"])
        self.assertEqual("Mario Kart 64", gamecard.official_title(out))

    def test_split_values_and_year(self):
        self.assertEqual(["Nintendo EAD", "Nintendo"], gamecard.split_values("Nintendo EAD, Nintendo"))
        self.assertEqual(1996, gamecard.year_of("1996-12-14"))
        self.assertIsNone(gamecard.year_of(""))


class BulkLookup(LibraryBase):
    def test_bulk_needs_consent_skips_known_games_and_can_stop(self):
        with self.assertRaises(AppError):
            self.app.api_game_info_all({"action": "start", "consent": True})        # look-ups are off by default
        self.app.catalog.set_setting("allow_game_info", True)
        with self.assertRaises(AppError):
            self.app.api_game_info_all({"action": "start"})                         # and it asks first
        log = []
        self.app.cards.opener = fake_opener(ANSWERS, log)
        items = [(gid, t, "SNES") for t, gid in self.ids.items()]
        state = self.app.cards.start_all(items, run_inline=True, pause=0)
        self.assertEqual("done", state["state"])
        self.assertEqual(1, state["total"])                  # only the game never looked up
        self.assertEqual(1, state["found"])
        self.assertTrue(log)
        self.assertTrue(self.app.cards.cached(self.ids["Unknown Thing"])["found"])
        cards = gamecard.CardLookups(Path(self.tmp.name) / "c2", fake_opener(ANSWERS, []))
        cards.PAUSE = 5
        first = cards.start_all([("a", "A", "NES"), ("b", "B", "NES"), ("c", "C", "NES")])
        self.assertEqual("running", first["state"])
        time.sleep(0.3)
        cards.stop_all()
        for _ in range(50):
            if cards.bulk_state()["state"] == "stopped":
                break
            time.sleep(0.05)
        self.assertEqual("stopped", cards.bulk_state()["state"])
        self.assertLess(cards.bulk_state()["done"], 3)


if __name__ == "__main__":
    unittest.main()
