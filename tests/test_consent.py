"""Permissions are enforced in Python: every action that reaches outside this computer or changes it is refused with
needs_consent (and does nothing) until the player allowed it through the permission dialog's endpoint. Turning a setting
on is not a yes; a yes counts only for the item's current version; turning an item off turns its settings off and
undoes what it did; every decision is written to an append-only history."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import consent, privacy
from launcher.app import AppError, ConsentNeeded, LauncherApp

from tests.consenthelp import allow

NES = b"NES\x1a" + b"\0" * 32


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.app = LauncherApp(self.base / "data")

    def add_game(self):
        games = self.base / "g" / "NES"
        games.mkdir(parents=True, exist_ok=True)
        (games / "Alpha (USA).nes").write_bytes(NES)
        self.app.catalog.set_roots([str(games.parent)])
        self.app.rescan()
        return next(iter(self.app.games))

    def refused(self, item, fn, *args):
        with self.assertRaises(ConsentNeeded) as ctx:
            fn(*args)
        self.assertEqual(item, ctx.exception.item)
        self.assertEqual(item, ctx.exception.extra["needs_consent"])
        self.assertEqual(item, ctx.exception.extra["consent"]["id"])          # the dialog's words travel with it
        self.assertTrue(ctx.exception.extra["consent"]["sends"])
        return ctx.exception


class Defaults(Base):
    def test_everything_that_goes_online_or_changes_the_pc_is_off_by_default(self):
        s = self.app.catalog.settings()
        for key in ("allow_internet", "allow_game_info", "auto_network_test", "server_use_fallback",
                    "friends_share_room", "dolphin_manage_pads"):
            self.assertIs(False, s[key], key)
        self.assertEqual("off", s["error_reports"])
        self.assertEqual("", s["friends_server"])
        out = self.app.api_consent({})
        self.assertEqual(0, out["allowed"])
        self.assertEqual(0, out["to_review"])
        self.assertEqual({"undecided"}, {i["state"] for i in out["items"]})

    def test_every_item_has_its_words_and_settings_are_known(self):
        from launcher.catalog import SETTINGS_SCHEMA
        for it in consent.ITEMS:
            for key in ("id", "title", "what", "sends", "changes", "undo", "group"):
                self.assertTrue(it.get(key), (it["id"], key))
            self.assertIsInstance(it["version"], int)
            for key in it["settings"]:
                self.assertIn(key, SETTINGS_SCHEMA)
        self.assertEqual(len(consent.ITEMS), len(consent.BY_ID))

    def test_the_old_informed_shortcut_and_settings_alone_never_grant(self):
        self.app.api_settings({"key": "allow_internet", "value": True, "informed": True})
        self.assertTrue(self.app.catalog.settings()["allow_internet"])
        self.assertFalse(self.app._allowed("downloads"))
        with mock.patch.object(self.app.installer, "start") as start:
            self.refused("downloads", self.app.api_engines_install, {"engine": "mgba", "confirm": True})
        start.assert_not_called()
        # and it shows up as something to review, because it is switched on without a yes
        self.assertEqual(["downloads"], [i["id"] for i in consent.needs_review(self.app.catalog.data, self.app.catalog.settings())])
        self.assertEqual(1, self.app.api_home({})["permissions_to_review"])
        with self.assertRaises(AppError):
            self.app.api_privacy({"action": "keep_all"})                   # no blanket yes


class Gates(Base):
    """Each gated action: refused without the yes (the network or system call is never made), works with it."""

    def test_downloads_installs_updates_and_lookups(self):
        with mock.patch.object(self.app.installer, "start", return_value={"state": "running"}) as one, \
                mock.patch.object(self.app.installer, "start_many", return_value={"state": "running"}) as many, \
                mock.patch.object(self.app.setup, "start", return_value={"state": "running"}) as setup, \
                mock.patch.object(self.app.update_all, "start", return_value={"state": "running"}) as everything, \
                mock.patch("launcher.app.latest_release") as latest, \
                mock.patch.object(self.app.self_update, "check") as check:
            self.refused("downloads", self.app.api_engines_install, {"engine": "mgba", "confirm": True})
            self.refused("downloads", self.app.api_engines_install_all, {"confirm": True})
            self.refused("downloads", self.app.api_setup_install, {"what": "all", "confirm": True})
            self.refused("downloads", self.app.api_update_all, {"action": "start", "confirm": True})
            self.refused("downloads", self.app.api_engines_source, {"engine": "mgba", "lookup": True})
            with mock.patch.object(self.app.self_update, "mode", return_value="release"):
                self.refused("downloads", self.app.api_check_update, {})
                self.refused("downloads", self.app.api_app_update, {"action": "check"})
            for m in (one, many, setup, everything, latest, check):
                m.assert_not_called()
            allow(self.app, "downloads")
            self.assertTrue(self.app.catalog.settings()["allow_internet"])          # allowing switched it on
            self.app.api_engines_install({"engine": "mgba", "confirm": True})
            self.app.api_setup_install({"what": "all", "confirm": True})
            self.app.api_update_all({"action": "start", "confirm": True})
            one.assert_called_once()
            setup.assert_called_once()
            everything.assert_called_once()

    def test_box_art(self):
        gid = self.add_game()
        with mock.patch.object(self.app.covers, "start") as start:
            self.refused("covers", self.app.api_covers, {"action": "start", "consent": True})
            self.refused("covers", self.app.api_game_fetch_cover, {"id": gid, "consent": True})
            start.assert_not_called()
            allow(self.app, "covers")
            self.app.api_covers({"action": "start"})
            self.app.api_game_fetch_cover({"id": gid})
            self.assertEqual(2, start.call_count)
        self.assertFalse(self.app.catalog.settings()["allow_internet"])          # box art does not need downloads

    def test_game_details(self):
        gid = self.add_game()
        with mock.patch.object(self.app.cards, "start") as start, mock.patch.object(self.app.cards, "start_all", return_value={}) as start_all:
            self.refused("game_info", self.app.api_game_card, {"id": gid, "action": "lookup", "consent": True})
            self.refused("game_info", self.app.api_game_info_all, {"action": "start", "consent": True})
            start.assert_not_called()
            start_all.assert_not_called()
            allow(self.app, "game_info")
            self.app.api_game_card({"id": gid, "action": "lookup"})
            self.app.api_game_info_all({"action": "start"})
            start.assert_called_once()
            start_all.assert_called_once()

    def test_network_test(self):
        with mock.patch("launcher.app.netcheck.ping_server") as ping:
            self.refused("network_test", self.app._network_check, {})
            self.refused("network_test", self.app.api_network_start, {})
            quiet = self.app.api_network_start({"auto": True})                  # the start-up test never opens a dialog
            self.assertFalse(quiet["running"])
            self.assertEqual("network_test", quiet["needs_consent"])
            ping.assert_not_called()
            allow(self.app, "network_test")
            self.assertFalse(self.app.catalog.settings()["auto_network_test"])  # pressing the button does not turn the start-up test on
            ping.return_value = {"ok": False, "error": "x"}
            self.app._network_check({})
            ping.assert_called_once()

    def test_the_router_is_never_opened_and_its_old_yes_is_retired(self):
        with mock.patch("launcher.app.portmap.open_port") as open_port, mock.patch("launcher.app.portmap.close_port"):
            with self.assertRaisesRegex(AppError, "no longer opens your router"):
                self.app.api_router_test({})
            self.app._share_reach("start", 0, True, mock.Mock(meet=""))
            self.app._friends_host_router(True)
            open_port.assert_not_called()
        with self.assertRaisesRegex(AppError, "no longer opens your router"):
            self.app._need("router")
        self.assertNotIn("router", consent.BY_ID)

    def test_firewall(self):
        with mock.patch("launcher.app.firewall.allow", return_value={"allowed": True}) as fw:
            self.refused("firewall", self.app.api_firewall_allow, {"consent": True})
            self.refused("firewall", self.app.api_friends_host, {"action": "firewall", "consent": True})
            fw.assert_not_called()
            allow(self.app, "firewall")
            self.app.api_firewall_allow({"consent": True})
            fw.assert_called_once()
        with mock.patch("launcher.app.firewall.exists", return_value=True), \
                mock.patch("launcher.app.firewall.remove", return_value={"removed": True}) as remove:
            out = self.app.api_consent({"action": "decide", "item": "firewall", "decision": "decline"})
        remove.assert_called_once()
        self.assertIn("Removed", out["undo"][0])

    def test_tray_firewall_waits_for_the_yes(self):
        from launcher.tray import TrayController
        tray = TrayController.__new__(TrayController)
        tray.app, tray.native = self.app, mock.Mock()
        with mock.patch("launcher.firewall.supported", return_value=True), \
                mock.patch("launcher.firewall.status", return_value={"allowed": False}), \
                mock.patch("launcher.firewall.allow") as fw:
            tray._firewall_for_friends()
            fw.assert_not_called()
            allow(self.app, "firewall")
            tray._firewall_for_friends()
            fw.assert_called_once()

    def test_meeting_point(self):
        self.app.catalog.set_setting("fallback_server_code", "LP-TEST")
        self.app.catalog.set_setting("server_use_fallback", True)
        self.assertEqual("", self.app._fallback_code())
        self.assertEqual("", self.app._meet_code())
        allow(self.app, "fallback")
        self.assertEqual("LP-TEST", self.app._fallback_code())
        with self.assertRaisesRegex(AppError, "not right"):                  # a broken code is said, never skipped
            self.app._meet_code()
        with self.assertRaisesRegex(AppError, "not right"):
            self.app._server_args(True)
        from launcher import servercode
        good = servercode.encode("203.0.113.5", 8765, "ab" * 16, "cd" * 5)
        self.app.catalog.set_setting("fallback_server_code", good)
        self.assertEqual(good, self.app._meet_code())
        args = self.app._server_args(True)
        self.assertEqual(good, args.meet)
        self.assertEqual("127.0.0.1", args.host)                             # nothing listens beyond this computer
        self.app.api_consent({"action": "decide", "item": "fallback", "decision": "decline"})
        self.assertEqual("", self.app._meet_code())
        self.assertEqual("", self.app._server_args(True).meet)

    def test_name_tag_claim_and_no_install_id(self):
        client = mock.Mock()
        client.call.return_value = {"tag": "0042", "alias": "Al", "player": "Al#0042"}
        with mock.patch.object(self.app, "_client", return_value=client):
            self.refused("name_tag", self.app.api_profile, {"claim": True})
            self.assertIsNone(self.app._claim_alias())             # hosting and joining quietly use a tag made here
            self.app.api_profile({"alias": "Al"})
            client.call.assert_not_called()
            self.assertRegex(self.app._player_tag(), r"^Al#\d{4}$")
            allow(self.app, "name_tag")
            self.assertEqual("0042", self.app.api_profile({"claim": True})["tag"])
        sent = client.call.call_args[0][0]
        self.assertEqual("claim_alias", sent["operation"])
        self.assertNotEqual(self.app.catalog.data["install_id"], sent["install_id"])        # never the install id any more
        self.assertEqual(self.app._server_key(), sent["install_id"])                       # a number made for this server only
        self.app.catalog.set_setting("server_host", "203.0.113.5")
        self.assertNotEqual(sent["install_id"], self.app._server_key())                    # another server gets another one
        self.assertEqual("Al#0042", self.app._player_tag())
        self.app.api_consent({"action": "decide", "item": "name_tag", "decision": "decline"})
        self.assertEqual("", self.app.catalog.data["alias_tag"])
        self.assertEqual({}, self.app.catalog.data["alias_keys"])

    def test_retired_address_features_are_refused(self):
        with mock.patch("launcher.privatelink.start_install") as install, \
                mock.patch("launcher.privatelink.start_login", return_value=True) as login:
            for call in (lambda: self.app.api_server_use_ipv6({}), lambda: self.app.api_server_use_tailscale({}),
                         lambda: self.app.api_tailscale({"action": "install", "confirm": True}),
                         lambda: self.app.api_tailscale({"action": "login"})):
                with self.assertRaises(AppError):
                    call()
            install.assert_not_called()
            login.assert_not_called()
        for item in ("code_address", "tailscale", "private_link", "direct", "friends_host", "router"):
            self.assertFalse(self.app._allowed(item))
            with self.assertRaises(AppError):
                self.app._need(item)
            with self.assertRaises(Exception):
                self.app.api_consent({"action": "decide", "item": item, "decision": "allow"})

    def test_tailscale_is_left_alone_by_update_everything(self):
        with mock.patch("launcher.updateall.privatelink.find_tailscale", return_value="ts.exe"), \
                mock.patch("launcher.updateall.privatelink.winget_path", return_value="winget.exe"), \
                mock.patch("launcher.updateall.subprocess.run") as run:
            state, why = self.app.update_all._tailscale()
            self.assertEqual("skipped", state)
            self.assertIn("no longer uses Tailscale", why)
            run.assert_not_called()

    def test_dolphin_config(self):
        self.app.catalog.set_setting("dolphin_manage_pads", True)
        with mock.patch.object(self.app, "_emulators", return_value={"dolphin": {"path": "/x/Dolphin.exe"}}), \
                mock.patch("launcher.app.dolphinpads.apply", return_value={"notes": []}) as pads, \
                mock.patch("launcher.app.dolphinpads.restore", return_value={}) as restore, \
                mock.patch("launcher.app.dolphinpaths.add_game_folders", return_value={"added": [], "already": 0}) as folders:
            self.refused("dolphin_config", self.app.api_dolphin_folders, {})
            notes = self.app._prepare_dolphin("/x/Dolphin.exe", "gamecube")
            self.assertIn("permission", notes[0])
            pads.assert_not_called()
            folders.assert_not_called()
            allow(self.app, "dolphin_config")
            self.assertTrue(self.app.catalog.settings()["dolphin_manage_pads"])
            self.app._prepare_dolphin("/x/Dolphin.exe", "gamecube")
            pads.assert_called_once()
            self.app.api_consent({"action": "decide", "item": "dolphin_config", "decision": "decline"})
            restore.assert_called_with("/x/Dolphin.exe")                     # the player's own pad file comes back
            self.assertFalse(self.app.catalog.settings()["dolphin_manage_pads"])

    def test_problem_reports_sent_automatically(self):
        self.app.catalog.set_setting("error_reports", "auto")                   # switched on, but never allowed
        self.assertEqual("ask", self.app.reports.mode())
        with mock.patch.object(self.app.reports, "send") as send:
            self.app.reports.capture("test", None, "boom", {})
            send.assert_not_called()
        self.refused("reports", self.app.api_report_decide, {"id": "x", "choice": "auto"})
        allow(self.app, "reports")
        self.assertEqual("auto", self.app.reports.mode())
        self.app.catalog.set_setting("report_url", "https://elsewhere.example.org/r")    # a different address: asked again
        self.assertEqual("ask", self.app.reports.mode())
        self.assertEqual("changed", consent.state(self.app.catalog.data, "reports", self.app.catalog.settings()))
        allow(self.app, "reports")
        self.app.api_consent({"action": "decide", "item": "reports", "decision": "decline"})
        self.assertEqual("ask", self.app.catalog.settings()["error_reports"])


class Friends(Base):
    def setUp(self):
        super().setUp()
        self.app.catalog.set_setting("friends_server", "https://friends.example.org")
        self.f = self.app.friends

    def test_sign_up_poll_and_messages_need_the_friends_yes(self):
        with mock.patch.object(self.f, "hello") as hello, mock.patch.object(self.f, "heartbeat") as beat, \
                mock.patch.object(self.f, "message") as message, mock.patch.object(self.f, "identity", return_value={"id": "me"}):
            self.refused("friends", self.app.api_friends, {"action": "hello"})
            self.refused("friends", self.app.api_friends, {"action": "message", "to": "x", "text": "hi"})
            polled = self.app.api_friends({"action": "poll"})                   # the background poll never asks
            self.assertEqual("friends", polled["needs_consent"])
            self.refused("friends", self.app.api_friends_mod, {"action": "reports"})
            for m in (hello, beat, message):
                m.assert_not_called()
            self.assertFalse(self.app.api_friends({"action": "status"})["permissions"]["service"])
            allow(self.app, "friends")
            beat.return_value = {"friends": []}
            self.app.api_friends({"action": "poll"})
            beat.assert_called_once()
            name, status, room = beat.call_args[0][:3]
            self.assertEqual("", status)                     # 'now playing' is its own yes
            self.assertIsNone(room)

    def test_presence_and_room_sharing_have_their_own_yes(self):
        allow(self.app, "friends")
        self.app.room = {"invite_code": "ABCD", "game": "Alpha", "session": {"participants": {"me": {}}}, "max_players": 2}
        self.app.running = {"title": "Alpha", "pid": 1}
        with mock.patch.object(self.app, "_running_now", return_value=self.app.running), \
                mock.patch.object(self.f, "identity", return_value={"id": "me"}), \
                mock.patch.object(self.f, "heartbeat", return_value={}) as beat, \
                mock.patch.object(self.f, "invite") as invite, \
                mock.patch.object(self.app, "_server_code_for_friends", return_value="LP-CODE"):
            self.app.catalog.set_setting("friends_share_room", True)            # a setting alone shares nothing
            self.refused("friends_share_room", self.app.api_friends, {"action": "invite", "to": "x"})
            invite.assert_not_called()
            self.app.api_friends({"action": "poll"})
            self.assertEqual(("", None), (beat.call_args[0][1], beat.call_args[0][2]))
            allow(self.app, "friends_presence", "friends_share_room")
            self.app.api_friends({"action": "poll"})
            self.assertEqual("playing Alpha", beat.call_args[0][1])
            self.assertEqual("LP-CODE", beat.call_args[0][2]["server_code"])
            self.app.api_friends({"action": "invite", "to": "x"})
            invite.assert_called_once()
            beat.reset_mock()
            self.app.api_consent({"action": "decide", "item": "friends_presence", "decision": "decline"})
            self.app.api_consent({"action": "decide", "item": "friends_share_room", "decision": "decline"})
            self.assertEqual(("", None), (beat.call_args[0][1], beat.call_args[0][2]))      # told the service straight away
            self.assertFalse(self.app.catalog.settings()["friends_share_room"])

    def test_turning_friends_off_forgets_the_link_and_allowing_again_brings_it_back(self):
        allow(self.app, "friends")
        self.app.api_consent({"action": "decide", "item": "friends", "decision": "decline"})
        self.assertEqual("", self.app.catalog.settings()["friends_server"])
        with mock.patch.object(self.f, "goodbye") as bye, mock.patch.object(self.f, "identity", return_value={"id": "me"}):
            self.app.api_friends({"action": "goodbye"})                         # leaving is always possible
            bye.assert_called_once()
        allow(self.app, "friends")
        self.assertEqual("https://friends.example.org", self.app.catalog.settings()["friends_server"])
        self.app.catalog.set_setting("friends_server", "https://other.example.org")     # another service: asked again
        self.assertFalse(self.app._friends_may("service"))

    def test_a_friends_service_on_this_computer_is_not_offered(self):
        with mock.patch.object(self.app.social_host, "start") as start, \
                mock.patch("launcher.app.portmap.open_port") as open_port:
            with self.assertRaisesRegex(AppError, "no longer offered"):
                self.app.api_friends_host({"action": "start", "switch": True})
            start.assert_not_called()
            open_port.assert_not_called()
        self.assertEqual({"link": "", "address": ""}, self.app._friends_share_link())

    def test_an_old_friends_service_is_not_started_again(self):
        self.app.catalog.data["friends_host_wanted"] = True
        with mock.patch.dict("os.environ", {"LEGACY_PLAYER_NO_BACKGROUND": ""}), \
                mock.patch("launcher.app.threading.Thread") as thread, mock.patch.object(self.app.social_host, "start") as start:
            self.app._resume_friends_service()
            thread.assert_not_called()
            start.assert_not_called()
        self.assertFalse(self.app.catalog.data["friends_host_wanted"])


class Direct(Base):
    def test_no_launch_can_show_an_address(self):
        import inspect
        src = inspect.getsource(LauncherApp.api_mp_launch) + inspect.getsource(LauncherApp._launch_dolphin)
        self.assertNotIn("punch.", src)                    # the hole-punching module is gone
        self.assertNotIn('"kind": "direct"', src)
        self.assertNotIn('"kind": "code"', src)

    def test_direct_launch_is_refused_before_anything_starts(self):
        self.app.room = {"role": "host", "game_id": "x", "session_id": "s", "me": "m", "credential": "c"}
        game = {"id": "x", "console": "snes", "path": "/g.sfc", "title": "G"}
        with mock.patch.object(self.app, "_game", return_value=game), \
                mock.patch.object(self.app, "netplay_check", return_value={"ready": True, "engine": "retroarch", "exe": "ra", "core": "c"}), \
                mock.patch.object(self.app, "_retroarch_extra", return_value=[]), \
                mock.patch.object(self.app, "_call", return_value={"session": {"state": "ready-barrier"}}), \
                mock.patch("launcher.app.emulators.launch_command") as launch:
            with self.assertRaisesRegex(AppError, "not offered"):
                self.app.api_mp_launch({"relay": False, "address": "1.2.3.4", "expose_address": True})
            launch.assert_not_called()


class Record(Base):
    def test_history_versions_and_revoke(self):
        allow(self.app, "downloads")
        self.app.api_consent({"action": "decide", "item": "downloads", "decision": "decline"})
        allow(self.app, "downloads")
        rec = self.app.catalog.data["consent"]
        self.assertEqual(["granted", "declined", "granted"], [h["decision"] for h in rec["history"]])
        self.assertTrue(all(h["version"] == consent.BY_ID["downloads"]["version"] and h["at"] for h in rec["history"]))
        self.assertEqual("dialog", rec["history"][0]["how"])
        listed = self.app.api_consent({})
        self.assertEqual("downloads", listed["history"][0]["item"])               # newest first on the page
        self.assertEqual("Internet downloads and updates", listed["history"][0]["title"])
        # saved to disk and read back
        again = LauncherApp(self.base / "data")
        self.assertTrue(again._allowed("downloads"))
        # a new version of what the item does: the old yes no longer counts
        with mock.patch.dict(consent.BY_ID["downloads"], {"version": consent.BY_ID["downloads"]["version"] + 1}):
            self.assertEqual("changed", consent.state(self.app.catalog.data, "downloads", self.app.catalog.settings()))
            self.assertFalse(self.app._allowed("downloads"))
            with mock.patch.object(self.app.installer, "start") as start:
                err = self.refused("downloads", self.app.api_engines_install, {"engine": "mgba", "confirm": True})
                start.assert_not_called()
            self.assertIn("changed", str(err))
            self.assertEqual(["downloads"], [i["id"] for i in consent.needs_review(self.app.catalog.data, self.app.catalog.settings())])
            doctor = [i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"]
            self.assertIn("Please review 1 permission", doctor[0]["text"])

    def test_revoking_turns_settings_off(self):
        allow(self.app, "game_info", "fallback", "friends_share_room")
        for item, key in (("game_info", "allow_game_info"), ("fallback", "server_use_fallback"), ("friends_share_room", "friends_share_room")):
            self.assertTrue(self.app.catalog.settings()[key])
            self.app.api_consent({"action": "decide", "item": item, "decision": "decline"})
            self.assertFalse(self.app.catalog.settings()[key], key)

    def test_turning_a_setting_off_by_hand_stops_the_feature_and_allowing_turns_it_back_on(self):
        allow(self.app, "downloads")
        self.app.api_settings({"key": "allow_internet", "value": False})
        err = self.refused("downloads", self.app.api_engines_install, {"engine": "mgba", "confirm": True})
        self.assertIn("switched off", str(err))
        allow(self.app, "downloads")
        self.assertTrue(self.app._allowed("downloads"))

    def test_bad_requests(self):
        for body in ({"action": "decide", "item": "nope", "decision": "allow"}, {"action": "decide", "item": "downloads", "decision": "maybe"},
                     {"action": "explode"}):
            with self.assertRaises(AppError):
                self.app.api_consent(body)

    def test_old_privacy_record_is_migrated_and_needs_a_new_look(self):
        data = self.base / "old"
        data.mkdir()
        (data / "user_data.json").write_text(json.dumps({
            "settings": {"allow_internet": True, "friends_server": "https://f.example.org", "auto_network_test": True},
            "privacy_ok": {"downloads": "on", "friends": "https://f.example.org", "network_test": "on"}}), encoding="utf-8")
        app = LauncherApp(data)
        out = app.api_consent({})
        states = {i["id"]: i["state"] for i in out["items"]}
        self.assertEqual("changed", states["downloads"])
        self.assertEqual("changed", states["friends"])
        self.assertEqual({"downloads", "friends", "network_test"}, {i["id"] for i in out["items"] if i["needs_review"]})
        self.assertEqual(3, out["to_review"])
        self.assertNotIn("privacy_ok", app.catalog.data)
        self.assertEqual({"migrated"}, {h["how"] for h in app.catalog.data["consent"]["history"]})
        self.assertFalse(app._allowed("downloads"))                              # the feature does not run until the player looks
        app.catalog.save()
        self.assertEqual("changed", consent.state(LauncherApp(data).catalog.data, "downloads", app.catalog.settings()))

    def test_privacy_module_matches_the_permissions(self):
        ids = {i["id"] for i in privacy.items(self.app.catalog.settings(), self.app.catalog.data)}
        self.assertEqual(set(consent.BY_ID), ids)
        self.assertIn("server code made by Legacy Player holds no address", privacy.NEVER)
        self.assertIn("whoever runs the meeting point", privacy.NEVER)                 # said plainly, not hidden
        self.assertIn("never see your address", json.dumps(consent.BY_ID["fallback"]))


class Page(unittest.TestCase):
    def test_the_page_knows_every_setting_a_permission_controls_and_asks_on_needs_consent(self):
        import re
        html = (Path(__file__).resolve().parent.parent / "launcher" / "ui" / "index.html").read_text(encoding="utf-8")
        keys = dict(re.findall(r'(\w+):"(\w+)"', re.search(r"const PRIVACY_KEYS=\{([^}]*)\}", html).group(1)))
        self.assertEqual(consent.setting_items(), keys)
        self.assertIn("j.needs_consent", html)
        self.assertIn('api("consent",{action:"decide",item:id,decision:"allow"', html)
        self.assertNotIn("informed:true", html)
        self.assertIn('const p=await api("profile");S.profile=p', html)    # the welcome screen never claims a tag by itself


class WebLayer(Base):
    def test_needs_consent_reaches_the_page(self):
        import threading
        from http.server import ThreadingHTTPServer
        from launcher import web
        from tests.test_web_lifecycle import post
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        port = httpd.server_address[1]
        httpd.RequestHandlerClass = web.make_handler(self.app, "tok", lambda: port)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        with mock.patch.object(self.app.installer, "start") as start:
            status, out = post(port, "/api/engines_install", {"engine": "mgba", "confirm": True}, {"X-LP-Token": "tok"})
        start.assert_not_called()
        self.assertEqual(400, status)
        self.assertEqual("downloads", out["needs_consent"])
        self.assertEqual("Internet downloads and updates", out["consent"]["title"])
        status, out = post(port, "/api/consent", {"action": "decide", "item": "downloads", "decision": "allow"}, {"X-LP-Token": "tok"})
        self.assertEqual(200, status)
        self.assertTrue(self.app._allowed("downloads"))


if __name__ == "__main__":
    unittest.main()


class ANoIsAnAnswer(Base):
    def test_declined_friends_on_the_game_server_is_not_asked_again(self):
        self.app.catalog.data["friends_ids"] = {"server:own": {"id": "x", "secret": "y", "code": "C"}}
        s = self.app.catalog.settings()
        self.assertIn("friends", [i["id"] for i in consent.needs_review(self.app.catalog.data, s)])      # never asked
        self.app.api_consent({"action": "decide", "item": "friends", "decision": "decline"})
        s = self.app.catalog.settings()
        self.assertNotIn("friends", [i["id"] for i in consent.needs_review(self.app.catalog.data, s)])
        self.assertFalse(consent.one(self.app.catalog.data, "friends", s)["needs_review"])
        self.assertFalse(self.app._friends_may("service"))                                            # and still off
