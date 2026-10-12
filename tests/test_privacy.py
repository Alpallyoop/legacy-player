"""The privacy check (now the Permissions page): every online feature has its own permission, nothing is on by default,
and anything switched on that the player never allowed for what it does now is flagged and does not run."""
import tempfile
import unittest
from pathlib import Path

from launcher import consent, privacy
from launcher.app import AppError, ConsentNeeded, LauncherApp

from tests.consenthelp import allow


class PrivacyCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = LauncherApp(Path(self.tmp.name) / "data")

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_send_nothing(self):
        out = self.app.api_privacy({})
        self.assertEqual(set(), {i["id"] for i in out["items"] if i["on"]})
        self.assertEqual(0, out["to_look_at"])
        self.assertIn("does not collect data", out["never"])
        self.assertFalse([i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"])

    def test_downloads_and_game_info_are_separate_permissions(self):
        ids = {i["id"]: i["settings"] for i in self.app.api_privacy({})["items"]}
        self.assertEqual(["allow_internet"], ids["downloads"])
        self.assertEqual(["allow_game_info"], ids["game_info"])
        allow(self.app, "downloads")
        games = Path(self.tmp.name) / "g" / "NES"
        games.mkdir(parents=True)
        (games / "Alpha (USA).nes").write_bytes(b"NES\x1a" + b"\0" * 32)
        self.app.catalog.set_roots([str(games.parent)])
        self.app.rescan()
        gid = next(iter(self.app.games))
        with self.assertRaises(ConsentNeeded) as ctx:                # downloads allowed does not open up look-ups
            self.app.api_game_card({"id": gid, "action": "lookup", "consent": True})
        self.assertEqual("game_info", ctx.exception.item)

    def test_something_switched_on_behind_the_players_back_is_flagged_until_allowed_or_turned_off(self):
        self.app.catalog.set_setting("allow_direct_connections", True)        # as if an old file or someone else did it
        self.app.catalog.set_setting("friends_server", "https://friends.example.org")
        issues = [i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"]
        self.assertEqual(1, len(issues))
        self.assertEqual({"direct", "friends"}, set(issues[0]["items"]))
        self.assertIn("Please review 2 permissions", issues[0]["text"])
        self.app.api_privacy({"action": "keep", "id": "direct"})              # the old page's "keep" is an allow
        self.app.api_privacy({"action": "off", "id": "friends"})
        self.assertEqual("", self.app.catalog.settings()["friends_server"])
        self.assertFalse([i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"])
        # a different address is a different thing to say yes to
        self.app.api_settings({"key": "friends_server", "value": "https://a.example.org", "informed": True})
        self.assertTrue([i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"])        # informed is gone
        allow(self.app, "friends")
        self.assertFalse([i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"])
        self.app.catalog.set_setting("friends_server", "https://b.example.org")
        self.assertTrue([i for i in self.app.api_doctor({})["issues"] if "friends" in i.get("items", [])])
        with self.assertRaises(AppError):
            self.app.api_privacy({"action": "keep", "id": "nope"})

    def test_every_item_says_where_it_goes_and_what_it_sends(self):
        for it in privacy.items(self.app.catalog.settings(), self.app.catalog.data):
            for key in ("title", "what", "sends", "changes", "undo"):
                self.assertTrue(it[key], (it["id"], key))
            for key in it["settings"]:
                self.assertIn(key, privacy.OFF_VALUES)
        self.assertEqual(set(consent.BY_ID), {i["id"] for i in privacy.items({}, {})})


if __name__ == "__main__":
    unittest.main()
