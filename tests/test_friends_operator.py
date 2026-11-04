"""A friends service that lies: it can't get a room's server code by listing a made-up friend, can't read messages by
swapping a friend's key, can't show a message in another thread or under another name, and repeating an old message
shows it once. (Audit 2026-11-04, findings F1, F2, F4.)"""
import copy
import tempfile
import threading
import unittest
from pathlib import Path

from tests.consenthelp import allow
from launcher.app import AppError, LauncherApp
from server.social import SocialService, e2e
from server.social import purecrypto as pc
from server.social.__main__ import FriendsHTTPServer, make_handler


class LyingService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.service = SocialService(base / "social")
        self.httpd = FriendsHTTPServer(("127.0.0.1", 0), make_handler(self.service, "local-key"))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.apps = {}
        for name in ("Alec", "Bea", "Cal"):
            app = LauncherApp(base / name)
            app.catalog.set_setting("display_name", name)
            app.catalog.set_setting("friends_server", url)
            allow(app, "friends")
            app.api_friends({"action": "hello"})
            self.apps[name] = app
        self.ids = {n: a.catalog.data["friends"]["id"] for n, a in self.apps.items()}
        for x, y in (("Alec", "Bea"), ("Alec", "Cal"), ("Bea", "Cal")):
            code = self.apps[y].api_friends({"action": "poll"})["inbox"]["me"]["code"]
            self.apps[x].api_friends({"action": "request", "code": code})
            self.apps[y].api_friends({"action": "decide", "from": self.ids[x], "accept": True})
        for a in self.apps.values():
            a.api_friends({"action": "poll"})

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def api(self, who, **body):
        return self.apps[who].api_friends(body)

    def test_a_made_up_friend_gets_no_server_code(self):
        client = self.apps["Alec"].friends
        evil = pc.x25519_keypair()
        real_call, sent = client._call, []

        def lying(body):
            out = real_call(body)
            if body.get("op") == "heartbeat":
                sent.append(copy.deepcopy(body.get("room")))
                out.setdefault("friends", []).append({"id": "operator-made-up", "name": "Totally Bea", "online": True,
                                                       "pub": pc.b64e(evil[1]), "status": ""})
            return out

        client._call = lying
        room = {"game": "Mario Kart", "players": 1, "max_players": 4, "server_code": "LP3-SECRET-SERVER-CODE"}
        client.heartbeat("Alec", room=room)
        inbox = client.heartbeat("Alec", room=room)
        fake = next(f for f in inbox["friends"] if f["id"] == "operator-made-up")
        self.assertFalse(fake["added_here"])
        self.assertTrue(next(f for f in inbox["friends"] if f["id"] == self.ids["Bea"])["added_here"])
        for env in sent[-1]["sealed"]:
            self.assertNotIn("operator-made-up", env["keys"])
            with self.assertRaises(e2e.E2EError):
                e2e.unwrap(env, "operator-made-up", *evil)
        with self.assertRaises(Exception):
            client.invite("operator-made-up", "ABCD", "Mario Kart", server_code="LP3-SECRET-SERVER-CODE")

    def test_a_swapped_key_stops_sending_until_checked(self):
        self.api("Alec", action="message", to=self.ids["Bea"], text="hello")
        evil = pc.x25519_keypair()
        self.service.players[self.ids["Bea"]]["pub"] = pc.b64e(evil[1])          # the operator swaps Bea's key
        with self.assertRaises(AppError) as caught:
            self.api("Alec", action="message", to=self.ids["Bea"], text="my secret")
        self.assertIn("safety code", str(caught.exception))
        for rows in self.service.players[self.ids["Bea"]]["messages"].values():
            self.assertEqual(1, len(rows))                                       # nothing new was sealed
        # a room's code is not sealed for the swapped key either
        client = self.apps["Alec"].friends
        self.assertEqual("", client.trusted_key(self.ids["Bea"]))
        # after the player says they compared it, sending works again (for the key they compared)
        self.api("Alec", action="verify_key", friend=self.ids["Bea"])
        self.api("Alec", action="message", to=self.ids["Bea"], text="checked")

    def test_a_swapped_key_in_a_group_stops_sending_until_checked(self):
        gid = self.api("Alec", action="group_create", name="Crew", members=[self.ids["Bea"], self.ids["Cal"]])["inbox"]["groups"][0]["id"]
        self.api("Alec", action="group_message", group=gid, text="hi all")
        evil = pc.x25519_keypair()
        self.service.players[self.ids["Cal"]]["pub"] = pc.b64e(evil[1])
        with self.assertRaises(AppError):
            self.api("Alec", action="group_message", group=gid, text="secret plan")
        self.api("Alec", action="verify_group", members=[self.ids["Cal"]])
        self.api("Alec", action="group_message", group=gid, text="ok now")

    def test_a_message_moved_to_another_thread_or_name_does_not_open(self):
        self.api("Alec", action="message", to=self.ids["Bea"], text="for Bea, from Alec")
        bea = self.service.players[self.ids["Bea"]]
        row = copy.deepcopy(bea["messages"][self.ids["Alec"]][0])
        row["from"] = self.ids["Cal"]                                            # shown as Cal's, in Cal's thread
        bea["messages"].setdefault(self.ids["Cal"], []).append(row)
        rows = self.api("Bea", action="thread", friend=self.ids["Cal"])["messages"]
        self.assertEqual(["unreadable"], [m["problem"] for m in rows])
        self.assertNotIn("for Bea, from Alec", [m["text"] for m in rows])

    def test_an_old_message_sent_again_shows_once(self):
        self.api("Alec", action="message", to=self.ids["Bea"], text="once")
        msgs = self.service.players[self.ids["Bea"]]["messages"][self.ids["Alec"]]
        again = copy.deepcopy(msgs[0])
        again["at"] += 1000
        msgs.append(again)
        rows = self.api("Bea", action="thread", friend=self.ids["Alec"])["messages"]
        self.assertEqual(["once"], [m["text"] for m in rows])


if __name__ == "__main__":
    unittest.main()
