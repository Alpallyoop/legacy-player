"""The friends layer: a separate service with no sign-ups, and Legacy Player's optional page on top of it."""
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from launcher.app import AppError, LauncherApp
from server.social import SocialError, SocialService, norm_code
from server.social.__main__ import make_handler
from tests.friends_kit import hello, read, send

CODE = r"^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$"


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class ServiceRules(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.s = SocialService(None, self.clock)
        self.a = hello(self.s, "Alec")
        self.b = hello(self.s, "Bea")

    def test_hello_gives_a_code_and_nothing_personal_is_asked(self):
        self.assertRegex(self.a["code"], CODE)                     # about 60 bits: never found by guessing
        self.assertEqual(set(self.s.hello("Cal")), {"id", "secret", "code", "name"})
        with self.assertRaises(SocialError):
            self.s.heartbeat(self.a["id"], "wrong secret")

    def test_friend_request_by_code_then_accept_then_see_each_other(self):
        inbox = self.s.request(self.a["id"], self.a["secret"], self.b["code"].lower().replace("-", ""))   # codes are forgiving
        self.assertEqual([self.b["id"]], [x["id"] for x in inbox["sent"]])
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertEqual(["Alec"], [r["name"] for r in bb["requests"]])
        bb = self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)
        self.assertEqual(["Alec"], [f["name"] for f in bb["friends"]])
        self.assertTrue(bb["friends"][0]["online"])
        self.clock.t += 120
        aa = self.s.heartbeat(self.a["id"], self.a["secret"])
        self.assertFalse(aa["friends"][0]["online"])              # Bea's app has not checked in for two minutes
        with self.assertRaises(SocialError):
            self.s.request(self.a["id"], self.a["secret"], "ZZZ-ZZZZ")
        with self.assertRaises(SocialError):
            self.s.request(self.a["id"], self.a["secret"], self.a["code"])

    def test_requests_crossing_become_friends_at_once(self):
        self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        inbox = self.s.request(self.b["id"], self.b["secret"], self.a["code"])
        self.assertEqual(["Alec"], [f["name"] for f in inbox["friends"]])

    def _befriend(self):
        self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)

    def test_room_is_shared_only_while_online_and_invites_carry_the_way_in(self):
        self._befriend()
        self.s.heartbeat(self.a["id"], self.a["secret"], status="in a room",
                         room={"invite_code": "ABCDE-FGH12", "game": "Mario Kart 64", "server_code": "LP-XYZ", "players": 1, "max_players": 4})
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertEqual("ABCDE-FGH12", bb["friends"][0]["room"]["invite_code"])
        self.assertEqual("in a room", bb["friends"][0]["status"])
        self.s.invite(self.a["id"], self.a["secret"], self.b["id"], "ABCDE-FGH12", "Mario Kart 64", "LP-XYZ")
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertEqual(1, len(bb["invites"]))
        self.assertEqual("Alec", bb["invites"][0]["name"])
        bb = self.s.dismiss_invite(self.b["id"], self.b["secret"], self.a["id"])
        self.assertEqual([], bb["invites"])
        self.clock.t += 120
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertIsNone(bb["friends"][0]["room"])                 # gone quiet: nothing to join is shown
        c = self.s.hello("Stranger")
        with self.assertRaises(SocialError):
            self.s.invite(c["id"], c["secret"], self.b["id"], "ABCDE-FGH12", "x")

    def test_messages_go_both_ways_and_count_unread(self):
        self._befriend()
        send(self.s, self.a, self.b, "game tonight?")
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertEqual(1, bb["friends"][0]["unread"])
        t = self.s.thread(self.b["id"], self.b["secret"], self.a["id"])
        self.assertFalse(t["messages"][0]["mine"])
        self.assertNotIn("text", t["messages"][0])                  # the service only has the sealed envelope
        self.assertEqual([(self.a["id"], "game tonight?")], read(self.s, self.b, self.a))
        self.assertEqual(0, self.s.heartbeat(self.b["id"], self.b["secret"])["friends"][0]["unread"])
        with self.assertRaises(SocialError):
            self.s.message(self.a["id"], self.a["secret"], self.b["id"], "plain text is refused")
        self.s.remove(self.a["id"], self.a["secret"], self.b["id"])
        self.assertEqual([], self.s.heartbeat(self.b["id"], self.b["secret"])["friends"])
        with self.assertRaises(SocialError):
            send(self.s, self.a, self.b, "hi")

    def test_goodbye_and_forgetting_the_idle(self):
        self._befriend()
        self.s.goodbye(self.b["id"], self.b["secret"])
        self.assertEqual([], self.s.heartbeat(self.a["id"], self.a["secret"])["friends"])
        self.clock.t += 61 * 86400
        self.s.hello("Someone")                                     # a tidy runs on hello
        self.assertNotIn(self.a["id"], self.s.players)

    def test_state_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            s = SocialService(Path(d), self.clock)
            a = s.hello("Alec")
            again = SocialService(Path(d), self.clock)
            self.assertEqual(a["code"], again.players[a["id"]]["code"])
            self.assertEqual(a["id"], again.codes[norm_code(a["code"])])


class OverHttpAndInTheApp(unittest.TestCase):
    def setUp(self):
        self.service = SocialService(None)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.app = LauncherApp(Path(self.tmp.name) / "data")

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def test_page_is_off_until_an_address_is_set_then_hello_poll_and_invite(self):
        self.app.catalog.set_setting("friends_use_server", False)      # no link and the game server's friends list off: no friends
        st = self.app.api_friends({"action": "status"})
        self.assertFalse(st["enabled"])
        with self.assertRaises(AppError):
            self.app.api_friends({"action": "hello"})
        self.app.catalog.set_setting("friends_server", "http://example.com/")           # plain http to a stranger is refused
        self.assertFalse(self.app.api_friends({})["enabled"])
        self.app.catalog.set_setting("friends_server", self.url)
        self.assertTrue(self.app.api_friends({})["enabled"])
        out = self.app.api_friends({"action": "hello"})
        self.assertRegex(out["me"]["code"], CODE)
        self.assertNotIn("secret", out["me"])
        self.assertIn("secret", self.app.catalog.data["friends"])
        other = hello(self.service, "Bea")
        inbox = self.app.api_friends({"action": "request", "code": other["code"]})["inbox"]
        self.assertEqual([other["code"]], [x["name"] for x in inbox["sent"]])        # their name only once they say yes
        self.service.decide(other["id"], other["secret"], self.app.catalog.data["friends"]["id"], True)
        inbox = self.app.api_friends({"action": "poll"})["inbox"]
        self.assertEqual(["Bea"], [f["name"] for f in inbox["friends"]])
        with self.assertRaises(AppError):
            self.app.api_friends({"action": "invite", "to": other["id"]})                 # no room yet
        self.app.room = {"invite_code": "ABCDE-FGH12", "game": "Tetris", "role": "host", "members": [{"name": "me"}], "max_players": 2, "session": {}}
        with self.assertRaises(AppError) as no_way:                                      # own server not open to friends: nothing joinable
            self.app.api_friends({"action": "invite", "to": other["id"]})
        self.assertIn("Let friends connect", str(no_way.exception))
        self.assertIn("Let friends connect", self.app.api_friends({"action": "status"})["invite_block"])
        for k, v in (("server_host", "203.0.113.9"), ("server_remote_port", 8765), ("server_tls", True),
                     ("server_fingerprint", "ab" * 32), ("server_access_key", "cd" * 5)):
            self.app.catalog.set_setting(k, v)                                           # in a room on a friend's server
        self.app.api_friends({"action": "invite", "to": other["id"]})
        self.app.api_friends({"action": "poll"})                                          # the page's regular check-in shares the room
        bb = self.service.heartbeat(other["id"], other["secret"])
        self.assertEqual("ABCDE-FGH12", bb["invites"][0]["invite_code"])
        self.assertEqual("", bb["invites"][0]["server_code"])                            # the server code is only kept sealed
        self.assertNotIn("203.0.113.9", json.dumps(self.service.players))
        self.assertEqual("", bb["friends"][0]["room"]["server_code"])
        self.assertEqual("Tetris", bb["friends"][0]["room"]["game"])
        self.app.catalog.set_setting("friends_share_room", False)
        self.app.api_friends({"action": "poll"})
        self.assertIsNone(self.service.heartbeat(other["id"], other["secret"])["friends"][0]["room"])
        self.app.api_friends({"action": "message", "to": other["id"], "text": "hello"})
        self.assertEqual(["hello"], [m["text"] for m in self.app.api_friends({"action": "thread", "friend": other["id"]})["messages"]])
        me = self.app.catalog.data["friends"]["id"]
        self.assertEqual([(me, "hello")], read(self.service, other, {"id": me}))           # Bea's app opens it with her key
        self.app.api_friends({"action": "goodbye"})
        self.assertEqual({}, self.app.catalog.data["friends"])

    def test_http_front_refuses_junk(self):
        def post(body):
            req = urllib.request.Request(self.url + "/", data=body, method="POST", headers={"Content-Type": "application/json"})
            try:
                return urllib.request.urlopen(req, timeout=5).status
            except urllib.error.HTTPError as err:
                return err.code
        self.assertEqual(400, post(b"{nope"))
        self.assertEqual(400, post(json.dumps({"op": "fly"}).encode()))
        self.assertEqual(413, post(b"x" * 70000))
        self.assertEqual(200, urllib.request.urlopen(self.url + "/health", timeout=5).status)


if __name__ == "__main__":
    unittest.main()


class BlockingAndInbox(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.s = SocialService(None, self.clock)
        self.a, self.b = hello(self.s, "Alec"), hello(self.s, "Bea")
        self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)

    def test_inbox_lists_conversations_newest_first_with_unread(self):
        from server.social import e2e
        c = hello(self.s, "Cal")
        self.s.request(self.a["id"], self.a["secret"], c["code"])
        self.s.decide(c["id"], c["secret"], self.a["id"], True)
        send(self.s, self.b, self.a, "first")
        self.clock.t += 5
        send(self.s, c, self.a, "second")
        inbox = self.s.heartbeat(self.a["id"], self.a["secret"])
        self.assertEqual(["Cal", "Bea"], [x["name"] for x in inbox["conversations"]])
        self.assertEqual(2, inbox["unread"])
        self.assertEqual("second", e2e.open_envelope(inbox["conversations"][0]["last_e"], self.a["id"], *self.a["key"])[0])
        inbox = self.s.read_all(self.a["id"], self.a["secret"])
        self.assertEqual(0, inbox["unread"])
        inbox = self.s.clear_thread(self.a["id"], self.a["secret"], c["id"])
        self.assertEqual(["Bea"], [x["name"] for x in inbox["conversations"]])
        self.assertEqual([(c["id"], "second")], read(self.s, c, self.a))                                 # theirs stays

    def test_block_cuts_everything_and_is_not_announced(self):
        send(self.s, self.b, self.a, "hi")
        self.s.invite(self.b["id"], self.b["secret"], self.a["id"], "ABCDE-FGH12", "Tetris")
        inbox = self.s.block(self.a["id"], self.a["secret"], self.b["id"])
        self.assertEqual([], inbox["friends"])
        self.assertEqual([], inbox["conversations"])
        self.assertEqual([], inbox["invites"])
        self.assertEqual(["Bea"], [x["name"] for x in inbox["blocked"]])
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertEqual([], bb["friends"])                                   # Bea no longer sees Alec at all
        with self.assertRaises(SocialError) as ctx:
            self.s.request(self.b["id"], self.b["secret"], self.a["code"])
        self.assertIn("No player has that friend code", str(ctx.exception))   # the same answer as a wrong code
        with self.assertRaises(SocialError):
            send(self.s, self.b, self.a, "hello?")
        with self.assertRaises(SocialError):
            self.s.request(self.a["id"], self.a["secret"], self.b["code"])   # the blocker is told to unblock first
        self.s.unblock(self.a["id"], self.a["secret"], self.b["id"])
        self.s.request(self.b["id"], self.b["secret"], self.a["code"])
        self.assertEqual(["Bea"], [r["name"] for r in self.s.heartbeat(self.a["id"], self.a["secret"])["requests"]])
