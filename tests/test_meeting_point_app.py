"""The app side of the meeting point: sharing a server makes an LP3- code with no address of this computer, a fresh
code cuts the old one off, a friend's app connects with it, and friends get the same code passed on. Real servers
(the app's own server process and a meeting point), real sockets."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import servercode
from launcher.app import AppError, ConsentNeeded, LauncherApp
from tests.consenthelp import allow
from tests.test_rendezvous import ServeThread, free_port


class MeetingPointAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = mock.patch.dict(os.environ, {"LEGACY_PLAYER_NO_BACKGROUND": "1"})
        cls.env.start()
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.meet = ServeThread(base / "meet", meeting_point=True).start()
        cls.meet_code = servercode.encode("127.0.0.1", cls.meet.port, cls.meet.fp)
        cls.host = LauncherApp(base / "host")
        cls.guest = LauncherApp(base / "guest")
        cls.host.api_settings({"key": "fallback_server_code", "value": cls.meet_code})
        allow(cls.host, "fallback")
        cls.host.api_settings({"key": "server_port", "value": free_port()})
        cls.started = cls.host.api_server_control({"action": "start", "share": True})

    @classmethod
    def tearDownClass(cls):
        try:
            cls.host.api_server_control({"action": "stop"})
        finally:
            cls.meet.stop()
            cls.env.stop()
            cls.tmp.cleanup()

    def test_sharing_parks_at_the_meeting_point_and_listens_on_this_computer_only(self):
        self.assertEqual("meeting_point", self.started["reach"]["state"], self.started)
        from server.state_store import StateStore
        info = StateStore(self.host.data_dir / "server").read_info()
        self.assertEqual("127.0.0.1", info["host"])

    def test_the_code_holds_no_address_and_a_friend_connects_with_it(self):
        out = self.host.api_server_code({})
        self.assertNotIn("address", out)
        code = out["code"]
        self.assertTrue(code.startswith("LP3-"))
        found = servercode.decode(code)
        self.assertNotIn("host", found)
        self.assertEqual(self.meet.port, found["meet"]["port"])
        self.guest.api_consent({"action": "decide", "item": "fallback", "decision": "decline"})
        with self.assertRaises(ConsentNeeded) as refused:                  # connecting to a meeting point is a permission of its own
            self.guest.api_server_connect({"code": code})
        self.assertEqual("fallback", refused.exception.item)
        self.assertNotEqual(LauncherApp.MEET_HOST, self.guest.catalog.settings()["server_host"])      # nothing was changed
        allow(self.guest, "fallback")
        joined = self.guest.api_server_connect({"code": code})
        self.assertTrue(joined["connected"], joined)
        self.assertEqual(LauncherApp.MEET_HOST, self.guest.catalog.settings()["server_host"])
        self.assertTrue(self.guest.api_server_status({})["online"])
        # a friend of the guest gets the same way in (the same LP3 code), never an address
        passed_on = self.guest._server_code_for_friends()
        self.assertEqual(servercode.decode(code), servercode.decode(passed_on))
        self.assertTrue(self.guest.api_server_connect({"local": True}) is not None)
        self.assertIsNone(self.guest._via())

    def test_a_fresh_code_stops_the_old_one(self):
        old = self.host.api_server_code({})["code"]
        fresh = self.host.api_server_code({"refresh": True})
        self.assertTrue(fresh["rotated"])
        self.assertNotEqual(servercode.decode(old)["token"], servercode.decode(fresh["code"])["token"])
        allow(self.guest, "fallback")
        before = dict(self.guest.catalog.settings())
        out = self.guest.api_server_connect({"code": old})
        self.assertFalse(out["connected"])
        self.assertIn("Nothing was changed", out["message"])
        self.assertEqual(before["server_host"], self.guest.catalog.settings()["server_host"])      # undone
        self.assertTrue(self.guest.api_server_connect({"code": fresh["code"]})["connected"])
        self.guest.api_server_connect({"local": True})

    def test_reach_says_which_way_works(self):
        out = self.host.api_reach({})
        self.assertTrue(out["meeting_point"])
        self.assertEqual("ready", out["meeting_point_state"])
        self.assertNotIn("ipv6", out)


class HomeNetworkOnlyTests(unittest.TestCase):
    def test_without_a_meeting_point_the_code_holds_only_a_home_network_address(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"LEGACY_PLAYER_NO_BACKGROUND": "1"}):
            app = LauncherApp(Path(tmp) / "data")
            args = app._server_args(True)
            self.assertEqual("", args.meet)
            from server.selfsigned import ensure_certificate
            ensure_certificate(app.data_dir / "server" / "tls")
            with mock.patch("launcher.app.detect_lan_address", return_value="192.168.1.20"):
                out = app.api_server_code({})
            self.assertEqual("192.168.1.20", servercode.decode(out["code"])["host"])
            self.assertEqual("home_network", out["reach_state"])
            for public in ("93.184.216.34", "203.0.113.9", "100.64.3.4", "2001:db8::1", "127.0.0.1"):      # never a public one
                with mock.patch("launcher.app.detect_lan_address", return_value=public):
                    out = app.api_server_code({})
                self.assertIsNone(out["code"], public)
                self.assertIn("Meeting point", out["error"])

    def test_a_player_code_is_never_taken_as_a_meeting_point(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"LEGACY_PLAYER_NO_BACKGROUND": "1"}):
            app = LauncherApp(Path(tmp) / "data")
            lp3 = servercode.encode_meet("ab" * 12, "cd" * 16, "ef" * 5, {"host": "203.0.113.5", "port": 8765, "fingerprint": "12" * 16})
            app.api_settings({"key": "fallback_server_code", "value": lp3})
            allow(app, "fallback")
            with self.assertRaisesRegex(AppError, "player's code"):
                app._meet_code()
            with self.assertRaises(AppError):
                app.api_router_test({})
