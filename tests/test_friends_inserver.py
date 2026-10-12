"""Friends and messages through the multiplayer server itself: the host's game server answers friends calls on its own
TLS port, a friend who joined with the server code uses them with nothing else to set up, messages stay end-to-end
encrypted, server codes in invites are sealed for the one friend they go to, the app checks in from the background, and
new messages, requests and invites are announced once (tray balloon while the window is closed, otherwise a notice)."""
import asyncio
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from launcher.app import AppError, LauncherApp
from launcher.friendspulse import FriendsNotices, FriendsPulse, summary
from server.social import SocialError, SocialService
from server.social.inserver import InServerFriends


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class GameServer:
    """A real game server (json_server.serve, TLS with the host app's own certificate) on a thread of its own."""

    def __init__(self, state: Path, port: int) -> None:
        from server.selfsigned import ensure_certificate
        self.state, self.port = state, port
        self.cert, self.key, _ = ensure_certificate(state / "tls")
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        from server.api import json_server
        asyncio.set_event_loop(self.loop)
        self.loop.add_signal_handler = mock.Mock(side_effect=NotImplementedError)     # not the main thread
        self.loop.run_until_complete(json_server.serve("0.0.0.0", self.port, self.state / "replays", state_dir=self.state,
                                                       tls_cert=self.cert, tls_key=self.key, autosave_seconds=3600))

    def start(self) -> "GameServer":
        from server import cli
        self.thread.start()
        for _ in range(100):
            try:
                cli._admin_call(self.state, "admin_status", timeout=1.0)
                return self
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("the game server did not start")

    def stop(self) -> None:
        from server import cli
        try:
            cli._admin_call(self.state, "admin_shutdown", timeout=2.0)
        except Exception:
            pass
        self.thread.join(15)


class FriendsOverTheGameServer(unittest.TestCase):
    """Al hosts; his brother joins with the server code; they become friends and talk, through Al's game server."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.al = LauncherApp(base / "al")
        cls.bro = LauncherApp(base / "bro")
        cls.al.catalog.set_setting("display_name", "Al")
        cls.bro.catalog.set_setting("display_name", "Bro")
        port = free_port()
        cls.server = GameServer(cls.al.data_dir / "server", port).start()
        for k, v in (("server_port", port), ("server_tls", True), ("server_fingerprint", cls.al.server_fingerprint())):
            cls.al.catalog.set_setting(k, v)
        # the brother is on "another computer": another loopback address, so his app treats it as a friend's server
        code = cls.al.api_server_code({"address": "127.0.0.2"})["code"]
        cls.code = code
        assert cls.bro.api_server_connect({"code": code})["connected"]

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.tmp.cleanup()

    def friends(self, app, **body):
        return app.api_friends(body)

    def test_1_both_use_the_game_servers_friends_list_with_no_link(self):
        for app, own in ((self.al, True), (self.bro, False)):
            st = self.friends(app, action="status")
            self.assertTrue(st["enabled"])
            self.assertEqual("server", st["mode"])
            self.assertEqual(own, st["own_server"])
            self.assertIn("server", st["where"])
            self.assertEqual("", app.catalog.settings()["friends_server"])

    def test_2_request_accept_message_receive_invite_and_moderation(self):
        al, bro = self.al, self.bro
        al_me = self.friends(al, action="hello")["me"]
        bro_me = self.friends(bro, action="hello")["me"]
        self.assertIn("server:own", al.catalog.data["friends_ids"])
        self.assertTrue(any(k.startswith("server:") and k != "server:own" for k in bro.catalog.data["friends_ids"]))
        # the brother adds Al's code; Al accepts
        self.friends(bro, action="request", code=al_me["code"])
        inbox = self.friends(al, action="poll")["inbox"]
        self.assertEqual(["Bro"], [r["name"] for r in inbox["requests"]])
        self.friends(al, action="decide", **{"from": bro_me["id"], "accept": True})
        inbox = self.friends(bro, action="poll")["inbox"]
        self.assertEqual(["Al"], [f["name"] for f in inbox["friends"]])
        self.assertTrue(inbox["friends"][0]["online"])
        # Al writes; the brother's app opens it
        self.friends(al, action="message", to=bro_me["id"], text="hi brother, castle at 8")
        bro._notices.clear()
        inbox = self.friends(bro, action="poll")["inbox"]
        conv = next(c for c in inbox["conversations"] if c["id"] == al_me["id"])
        self.assertEqual("hi brother, castle at 8", conv["last"])
        self.assertEqual(1, conv["unread"])
        notes = [n for n in bro._notices if n.get("kind") == "friends"]
        self.assertEqual(1, len(notes))                                        # announced once, as a notice that opens Friends
        self.assertEqual("friends", notes[0]["page"])
        self.assertIn("castle at 8", notes[0]["text"])
        self.friends(bro, action="poll")
        self.assertEqual(1, len([n for n in bro._notices if n.get("kind") == "friends"]))     # not again
        self.assertEqual(1, self.friends(bro, action="cached")["inbox"]["unread"])          # the badge, without a network call
        thread = self.friends(bro, action="thread", friend=al_me["id"])
        self.assertEqual(["hi brother, castle at 8"], [m["text"] for m in thread["messages"]])
        self.friends(bro, action="message", to=al_me["id"], text="on my way")
        self.assertEqual("on my way", self.friends(al, action="thread", friend=bro_me["id"])["messages"][-1]["text"])
        # an invite on the same server needs no server code at all, so none is sent or kept
        al.room = {"invite_code": "ABCDE-FGH12", "game": "Mario Kart 64", "role": "host", "members": [{"name": "Al"}],
                   "max_players": 4, "session": {}}
        try:
            self.assertEqual("", self.friends(al, action="status")["invite_block"])
            self.friends(al, action="invite", to=bro_me["id"])
            self.friends(al, action="poll")
            inbox = self.friends(bro, action="poll")["inbox"]
            self.assertEqual("ABCDE-FGH12", inbox["invites"][0]["invite_code"])
            self.assertEqual("", inbox["invites"][0]["server_code"])
            self.assertTrue(inbox["friends"][0]["room"]["same_server"])
        finally:
            al.room = None
        # the brother reports; Al moderates his own server's friends list from his app
        self.friends(bro, action="report", player=al_me["id"], category="spam", details="test report")
        reports = al.api_friends_mod({"action": "reports"})
        self.assertEqual(["test report"], [r["details"] for r in reports["reports"]])
        self.assertTrue(self.friends(al, action="status")["moderator"])
        with self.assertRaises(AppError):
            bro.api_friends_mod({"action": "reports"})                         # only whoever runs the server
        # the friends list is kept in the server's own folder, and the server never had the words
        self.server_social = al.data_dir / "server" / "social" / "players.json"
        for _ in range(40):
            if self.server_social.exists():
                break
            time.sleep(0.1)
        time.sleep(2.5)
        stored = self.server_social.read_text(encoding="utf-8")
        self.assertIn('"Bro"', stored)
        for plain in ("castle", "on my way", self.code, "127.0.0.2"):
            self.assertNotIn(plain, stored)

    def test_3_a_new_identity_needs_the_server_codes_key(self):
        from launcher.lobby_client import LobbyClient, LobbyClientError
        s = self.bro.catalog.settings()
        stranger = LobbyClient("127.0.0.2", s["server_remote_port"], tls=True, fingerprint=s["server_fingerprint"], access_key="00" * 5)
        with self.assertRaises(LobbyClientError) as no:
            stranger.call({"operation": "friends", "friends": {"op": "hello", "name": "Eve"}})
        self.assertIn("server code", str(no.exception))


class InServerRules(unittest.TestCase):
    def test_hello_checks_the_key_and_other_calls_do_not(self):
        lobby = mock.Mock(access_key="ab" * 5, key_throttle=None)
        f = InServerFriends(None)
        with self.assertRaises(PermissionError):
            f.handle({"friends": {"op": "hello", "name": "x"}, "_peer": "203.0.113.4", "access_key": "nope"}, lobby)
        me = f.handle({"friends": {"op": "hello", "name": "x"}, "_peer": "203.0.113.4", "access_key": "ab" * 5}, lobby)
        lobby.access_key = "cd" * 5                         # the host made a fresh server code: friends already here keep working
        out = f.handle({"friends": {"op": "heartbeat", "id": me["id"], "secret": me["secret"]}, "_peer": "203.0.113.4"}, lobby)
        self.assertEqual(me["code"], out["me"]["code"])
        with self.assertRaises(SocialError):
            f.handle({"friends": "junk"}, lobby)

    def test_new_identities_per_address_are_limited(self):
        f = InServerFriends(None)
        for _ in range(10):
            f.handle({"friends": {"op": "hello", "name": "x"}, "_peer": "198.51.100.7"}, None)
        with self.assertRaises(SocialError):
            f.handle({"friends": {"op": "hello", "name": "x"}, "_peer": "198.51.100.7"}, None)

    def test_moderation_calls(self):
        f = InServerFriends(None)
        a = f.handle({"friends": {"op": "hello", "name": "Ann"}}, None)
        self.assertEqual(1, f.admin({"what": "reports"})["players"])
        f.admin({"what": "act", "action": "ban", "player": a["id"], "reason": "test"})
        with self.assertRaises(SocialError):
            f.handle({"friends": {"op": "heartbeat", "id": a["id"], "secret": a["secret"]}}, None)
        self.assertTrue(f.admin({"what": "filter", "on": True})["filter"]["on"])


class SealedServerCodes(unittest.TestCase):
    """With a separate friends service (a link), the server code of a room travels sealed for the friend(s) it is for."""

    def setUp(self):
        from server.social.__main__ import FriendsHTTPServer, make_handler
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.service = SocialService(base / "social")
        self.httpd = FriendsHTTPServer(("127.0.0.1", 0), make_handler(self.service, "k"))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.a, self.b = LauncherApp(base / "a"), LauncherApp(base / "b")
        for app, name in ((self.a, "Ann"), (self.b, "Ben")):
            app.catalog.set_setting("display_name", name)
            app.catalog.set_setting("friends_server", url)
            app.api_friends({"action": "hello"})
        bcode = self.b.api_friends({"action": "poll"})["inbox"]["me"]["code"]
        self.a.api_friends({"action": "request", "code": bcode})
        self.b.api_friends({"action": "decide", "from": self.a.catalog.data["friends"]["id"], "accept": True})
        self.b.api_friends({"action": "poll"})
        self.a.api_friends({"action": "poll"})
        for k, v in (("server_host", "203.0.113.9"), ("server_remote_port", 8765), ("server_tls", True),
                     ("server_fingerprint", "ab" * 32), ("server_access_key", "cd" * 5)):
            self.a.catalog.set_setting(k, v)
        self.a.room = {"invite_code": "ROOM1-23456", "game": "Tetris", "role": "host", "members": [], "max_players": 2, "session": {}}

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def test_invite_and_room_carry_the_code_sealed_and_the_friend_opens_it(self):
        expected = self.a._server_code_for_friends()
        self.assertTrue(expected.startswith("LP"))
        self.a.api_friends({"action": "invite", "to": self.b.catalog.data["friends"]["id"]})
        self.a.api_friends({"action": "poll"})                                       # shares the room, sealed for Ben
        stored = json.dumps(self.service.players)
        self.assertNotIn(expected, stored)
        self.assertNotIn("203.0.113.9", stored)
        inbox = self.b.api_friends({"action": "poll"})["inbox"]
        self.assertEqual(expected, inbox["invites"][0]["server_code"])
        self.assertEqual(expected, inbox["friends"][0]["room"]["server_code"])
        self.assertNotIn("sealed", inbox["invites"][0])

    def test_an_invite_sealed_by_someone_else_is_refused(self):
        from server.social import e2e
        from server.social import purecrypto as pc
        aid, bid = self.a.catalog.data["friends"]["id"], self.b.catalog.data["friends"]["id"]
        other = pc.x25519_keypair()                          # not Ann's key: the service checks the sender's key
        env = e2e.seal(other[0], other[1], aid, e2e.invite_conv(aid, bid),
                       {aid: other[1], bid: pc.b64d(self.service.players[bid]["pub"], 32)}, "LP-FAKE")
        with self.assertRaises(SocialError):
            self.service.invite(aid, self.a.catalog.data["friends"]["secret"], bid, "ROOM1", "Tetris", sealed=env)

    def test_plain_server_codes_from_an_older_app_are_not_kept(self):
        aid, bid = self.a.catalog.data["friends"]["id"], self.b.catalog.data["friends"]["id"]
        self.service.invite(aid, self.a.catalog.data["friends"]["secret"], bid, "ROOM1", "Tetris", server_code="LP-PLAIN-CODE")
        self.service.heartbeat(aid, self.a.catalog.data["friends"]["secret"],
                               room={"invite_code": "ROOM1", "server_code": "LP-PLAIN-CODE", "game": "Tetris"})
        self.assertNotIn("LP-PLAIN-CODE", json.dumps(self.service.players))


class BackgroundCheckIns(unittest.TestCase):
    def test_the_pulse_beats_until_stopped(self):
        beats = []
        pulse = FriendsPulse(lambda: beats.append(1), interval=0.02)
        self.assertTrue(pulse.start())
        self.assertFalse(pulse.start())                      # one thread only
        for _ in range(100):
            if len(beats) >= 3:
                break
            time.sleep(0.02)
        pulse.stop()
        self.assertFalse(pulse.running())
        n = len(beats)
        time.sleep(0.1)
        self.assertEqual(n, len(beats))
        self.assertGreaterEqual(n, 3)

    def test_a_failing_beat_does_not_stop_it(self):
        calls = []

        def beat():
            calls.append(1)
            raise OSError("offline")
        pulse = FriendsPulse(beat, interval=0.02)
        pulse.start()
        for _ in range(100):
            if len(calls) >= 2:
                break
            time.sleep(0.02)
        pulse.stop()
        self.assertGreaterEqual(len(calls), 2)

    def test_the_app_checks_in_only_with_friends_in_use_and_stops_on_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp) / "data")
            with mock.patch.object(app, "api_friends") as poll:
                app._friends_beat()                          # no identity: nothing goes anywhere
                poll.assert_not_called()
                app.catalog.data["friends_ids"] = {"server:own": {"id": "x", "secret": "y", "code": "C"}}
                app._friends_beat()
                poll.assert_called_once_with({"action": "poll", "background": True})
            with mock.patch.dict("os.environ", {"LEGACY_PLAYER_NO_BACKGROUND": ""}):
                with mock.patch.object(app.friends_pulse, "start") as start:
                    app._friends_pulse_on()
                    start.assert_called_once()
            app.friends_pulse.beat = lambda: None
            app.friends_pulse.interval = 0.02
            app.friends_pulse.start()
            app.shutdown()
            self.assertFalse(app.friends_pulse.running())
            app.catalog.set_setting("friends_use_server", False)
            with mock.patch.object(app, "api_friends") as poll:
                app._friends_beat()                          # switched off: no check-ins
                poll.assert_not_called()


class Notices(unittest.TestCase):
    def inbox(self, **kw):
        base = {"me": {"id": "me"}, "requests": [], "invites": [], "conversations": [], "groups": []}
        base.update(kw)
        return base

    def test_each_thing_is_announced_once_even_after_a_restart(self):
        cat = mock.Mock(data={})
        n = FriendsNotices(cat)
        box = self.inbox(requests=[{"id": "p1", "name": "Bea"}],
                         conversations=[{"id": "p2", "name": "Cal", "unread": 1, "mine": False, "last_id": "m1", "last": "yo"}])
        first = n.news("svc", box)
        self.assertEqual({"request", "message"}, {e["kind"] for e in first})
        self.assertEqual([], n.news("svc", box))
        self.assertEqual([], FriendsNotices(cat).news("svc", box))         # kept in the catalog: a restart does not repeat it
        box["invites"] = [{"from": "p2", "name": "Cal", "game": "Tetris", "at": 5}]
        self.assertEqual(["invite"], [e["kind"] for e in n.news("svc", box)])
        self.assertNotIn("yo", json.dumps(cat.data))                       # ids and times only, never words
        self.assertEqual(["request"], [e["kind"] for e in n.news("other service", self.inbox(requests=[{"id": "p1", "name": "Bea"}]))])

    def test_my_own_message_and_read_ones_are_not_announced(self):
        n = FriendsNotices(mock.Mock(data={}))
        box = self.inbox(conversations=[{"id": "p2", "name": "Cal", "unread": 0, "mine": True, "last_id": "m1", "last": "x"}],
                         groups=[{"id": "g", "name": "G", "unread": 1, "last_id": "m2", "last_from": "me", "last": "x"}])
        self.assertEqual([], n.news("svc", box))

    def test_summary_reads_well(self):
        events = [{"kind": "message", "title": "Message from Cal", "text": "hi"}, {"kind": "request", "title": "Friend request", "text": "x"},
                  {"kind": "message", "title": "Message from Bea", "text": "yo"}]
        title, text = summary(events)
        self.assertEqual("Friends", title)
        self.assertIn("2 new messages and a friend request", text)
        self.assertEqual(("Friend request", "x"), summary(events[1:2]))

    def test_tray_balloon_while_the_window_is_closed_otherwise_a_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp) / "data")
            app.catalog.data["friends_ids"] = {"server:own": {"id": "me", "secret": "s", "code": "C"}}
            tray = mock.Mock()
            app.on_friends_notice = tray
            app.tray_mode = True
            box = self.inbox(conversations=[{"id": "p2", "name": "Cal", "unread": 1, "mine": False, "last_id": "m1", "last": "yo"}])
            app._friends_announce(box)
            app._friends_announce(box)
            tray.assert_called_once_with("Message from Cal", "yo")
            self.assertEqual([], [x for x in app._notices if x.get("kind") == "friends"])
            app.tray_mode = False
            box["requests"] = [{"id": "p3", "name": "Dee"}]
            app._friends_announce(box)
            self.assertEqual(1, tray.call_count)
            note = [x for x in app._notices if x.get("kind") == "friends"]
            self.assertEqual(1, len(note))
            self.assertEqual("friends", note[0]["page"])
            self.assertIn("Dee", note[0]["text"])

    def test_a_click_on_the_balloon_opens_the_friends_page(self):
        from launcher.tray import TrayController
        with tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp) / "data")
            opened = []
            tc = TrayController(app, lambda: opened.append(1))
            self.assertEqual(tc.friends_notice, app.on_friends_notice)
            with mock.patch.object(tc.native, "_notify", create=True) as balloon:
                app.on_friends_notice("Message from Cal", "yo")
                balloon.assert_called_once_with("Message from Cal", "yo")
            tc.command("balloon")
            self.assertEqual([1], opened)
            self.assertEqual("friends", app._notices[-1]["nav"])


if __name__ == "__main__":
    unittest.main()
