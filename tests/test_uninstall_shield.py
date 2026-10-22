"""Uninstall must not delete the player's own games or saves just because they sit inside the data folder."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import selfuninstall


class ShieldTests(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp()) / "LegacyPlayerData"
        self.data.mkdir()
        (self.data / "user_data.json").write_text("{}")
        (self.data / "covers").mkdir()
        (self.data / "covers" / "a.png").write_bytes(b"x")
        self.roms = self.data / "roms"                                    # a games folder the player put inside the data folder
        (self.roms / "snes").mkdir(parents=True)
        (self.roms / "snes" / "game.sfc").write_bytes(b"rom")
        self.mine = self.data / "MySaves"                                 # a save folder the player chose, also inside it
        (self.mine / "snes").mkdir(parents=True)
        (self.mine / "snes" / "a.srm").write_bytes(b"save")
        (self.data / "mixed" / "deep").mkdir(parents=True)                # a folder that merely CONTAINS a games folder
        (self.data / "mixed" / "junk.txt").write_text("ours")
        (self.data / "mixed" / "deep" / "games").mkdir()
        (self.data / "mixed" / "deep" / "games" / "g.nes").write_bytes(b"rom")
        (self.data / "mixed" / "deep" / "cache.bin").write_bytes(b"ours")

    def run_it(self, keep_saves, **kw):
        with mock.patch("launcher.selfuninstall._spawn_cleanup", lambda *a: None) as spawn:
            return selfuninstall.execute(self.data, keep_saves, False, game_paths=[str(self.roms), str(self.data / "mixed" / "deep" / "games")],
                                         keep_paths=[str(self.mine)], **kw), spawn

    def test_keep_saves_keeps_games_and_saves_and_removes_the_rest(self):
        report, _ = self.run_it(True)
        self.assertTrue((self.roms / "snes" / "game.sfc").exists())
        self.assertTrue((self.mine / "snes" / "a.srm").exists())
        self.assertTrue((self.data / "mixed" / "deep" / "games" / "g.nes").exists())
        self.assertFalse((self.data / "covers").exists())                 # ours still goes
        self.assertFalse((self.data / "user_data.json").exists())
        self.assertFalse((self.data / "mixed" / "junk.txt").exists())
        self.assertFalse((self.data / "mixed" / "deep" / "cache.bin").exists())
        self.assertEqual([], report["problems"])

    def test_not_keeping_saves_still_never_deletes_games(self):
        seen = []
        with mock.patch("launcher.selfuninstall._spawn_cleanup", lambda exe, deferred, purge, extras: seen.append(purge)):
            selfuninstall.execute(self.data, False, False, game_paths=[str(self.roms)], keep_paths=[str(self.mine)])
        self.assertTrue((self.roms / "snes" / "game.sfc").exists())       # games always stay
        self.assertFalse((self.mine / "snes" / "a.srm").exists())         # the player said not to keep saves
        self.assertNotIn(self.data, seen)                                 # and nothing sweeps the whole data folder afterwards

    def test_without_such_folders_everything_is_removed_as_before(self):
        seen = []
        with mock.patch("launcher.selfuninstall._spawn_cleanup", lambda exe, deferred, purge, extras: seen.append(purge)):
            selfuninstall.execute(self.data, False, False, game_paths=[], keep_paths=[])
        self.assertEqual([self.data], seen)

    def test_the_plan_says_what_will_be_left(self):
        plan = selfuninstall.plan(self.data, shield=[str(self.roms), str(self.data / "saves"), "", "C:/elsewhere"])
        self.assertEqual([str(self.roms)], [k["path"] for k in plan["never_touched"]])


if __name__ == "__main__":
    unittest.main()
