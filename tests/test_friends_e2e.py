"""End-to-end encrypted friends messages, through a real running friends service with real apps: the service stores
only ciphertext, reports reveal just the reported messages' keys and are checked against the service's own copy,
keys are pinned with a warning when they change, group chats follow the friendship rules, and old apps are told to
update."""
import json
import tempfile
import threading
import unittest
from pathlib import Path

from launcher.app import AppError, LauncherApp
from server.social import MAX_GROUP, SocialError, SocialService, e2e, norm_code
from server.social import purecrypto as pc
from server.social.__main__ import FriendsHTTPServer, make_handler
from tests.friends_kit import befriend, hello, key_of, read, send, send_group


class Clock:
    def __init__(self):
        self.t = 5_000_000.0

    def __call__(self):
        return self.t


class ThroughARunningService(unittest.TestCase):
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

    def test_a_message_is_sealed_on_one_app_and_opened_on_the_other(self):
        self.api("Alec", action="message", to=self.ids["Bea"], text="meet at the castle, 8pm")
        inbox = self.api("Bea", action="poll")["inbox"]
        conv = next(c for c in inbox["conversations"] if c["id"] == self.ids["Alec"])
        self.assertEqual("meet at the castle, 8pm", conv["last"])                       # the preview is opened in the app
        thread = self.api("Bea", action="thread", friend=self.ids["Alec"])
        self.assertEqual(["meet at the castle, 8pm"], [m["text"] for m in thread["messages"]])
        self.assertEqual("", thread["messages"][0]["problem"])
        self.assertEqual(["meet at the castle, 8pm"], [m["text"] for m in self.api("Alec", action="thread", friend=self.ids["Bea"])["messages"]])
        # the service, in memory and on disk, holds no trace of the words
        self.service.flush()
        on_disk = (Path(self.tmp.name) / "social" / "players.json").read_text()
        self.assertNotIn("castle", on_disk)
        self.assertNotIn("castle", json.dumps(self.service.players))
        stored = self.service.players[self.ids["Bea"]]["messages"][self.ids["Alec"]][0]["e"]
        with self.assertRaises(e2e.E2EError):                    # and no key it has opens it
            e2e.open_with_key(stored, pc.b64d(stored["keys"][self.ids["Bea"]]["w"])[:32])
        # the private keys never left the apps
        for name, app in self.apps.items():
            key_file = Path(self.tmp.name) / name / "friends_identity.key"
            private = json.loads(key_file.read_text())["private"]
            self.assertNotIn(private, on_disk)
            self.assertNotIn(private, json.dumps(app.catalog.data))
            if hasattr(key_file.stat(), "st_mode") and __import__("os").name == "posix":
                self.assertEqual(0o600, key_file.stat().st_mode & 0o777)

    def test_the_safety_code_matches_and_a_new_key_is_flagged(self):
        a = self.api("Alec", action="thread", friend=self.ids["Bea"])
        b = self.api("Bea", action="thread", friend=self.ids["Alec"])
        self.assertRegex(a["safety_code"], r"^\d{5} \d{5} \d{5} \d{5}$")
        self.assertEqual(a["safety_code"], b["safety_code"])
        self.assertFalse(b["key_changed"])
        self.api("Alec", action="message", to=self.ids["Bea"], text="before")
        with self.assertRaises(AppError):
            self.api("Alec", action="replace_key")                                        # asks first
        self.api("Alec", action="replace_key", confirm=True)
        inbox = self.api("Bea", action="poll")["inbox"]
        self.assertTrue(next(f for f in inbox["friends"] if f["id"] == self.ids["Alec"])["key_changed"])
        b2 = self.api("Bea", action="thread", friend=self.ids["Alec"])
        self.assertTrue(b2["key_changed"])
        self.assertNotEqual(b["safety_code"], b2["safety_code"])
        self.assertEqual(self.api("Alec", action="thread", friend=self.ids["Bea"])["safety_code"], b2["safety_code"])
        self.api("Alec", action="message", to=self.ids["Bea"], text="after")              # sealed with the new key
        texts = [m["text"] for m in self.api("Bea", action="thread", friend=self.ids["Alec"])["messages"]]
        self.assertEqual(["before", "after"], texts)                                      # Bea still reads both
        self.api("Bea", action="verify_key", friend=self.ids["Alec"])
        self.assertFalse(self.api("Bea", action="thread", friend=self.ids["Alec"])["key_changed"])

    def test_a_report_reveals_only_those_keys_and_moderators_read_the_real_words(self):
        for text in ("hi", "good game", "you are trash, quit"):
            self.api("Alec", action="message", to=self.ids["Bea"], text=text)
        self.api("Bea", action="message", to=self.ids["Alec"], text="what?")
        self.api("Alec", action="message", to=self.ids["Bea"], text="later message, not part of it")
        thread = self.api("Bea", action="thread", friend=self.ids["Alec"])["messages"]
        bad = next(m for m in thread if m["text"] == "you are trash, quit")
        self.api("Bea", action="report", player=self.ids["Alec"], category="harassment", message=bad["id"])
        rep = self.service.admin_reports()["reports"][0]
        self.assertEqual("you are trash, quit", rep["message"]["text"])
        self.assertTrue(rep["message"]["verified"])
        self.assertEqual(["hi", "good game"], [c["text"] for c in rep["context"]])
        self.assertNotIn("later message", json.dumps(rep))
        self.assertNotIn("what?", json.dumps(rep))                                         # after it: not shared

    def test_a_made_up_key_or_text_is_refused(self):
        self.api("Alec", action="message", to=self.ids["Bea"], text="hello there")
        self.api("Alec", action="message", to=self.ids["Bea"], text="second")
        bea = self.apps["Bea"].catalog.data["friends"]
        rows = self.service.thread(bea["id"], bea["secret"], self.ids["Alec"])["messages"]
        for keys in ({rows[0]["id"]: pc.b64e(pc.random_bytes(32))},                     # a key that was never used
                     {rows[0]["id"]: self.apps["Bea"].friends._open(rows[1]["e"])[1] and pc.b64e(self.apps["Bea"].friends._open(rows[1]["e"])[1])},
                     {}):                                                                  # no key at all
            with self.assertRaises(SocialError):
                self.service.report(bea["id"], bea["secret"], self.ids["Alec"], "harassment", message_id=rows[0]["id"], keys=keys)
        self.assertEqual([], self.service.admin_reports()["reports"])
        # a "text" sent along is ignored: only the service's own copy is ever quoted
        good = {rows[0]["id"]: pc.b64e(self.apps["Bea"].friends._open(rows[0]["e"])[1])}
        self.service.report(bea["id"], bea["secret"], self.ids["Alec"], "spam", message_id=rows[0]["id"], keys=good)
        self.assertEqual("hello there", self.service.admin_reports()["reports"][0]["message"]["text"])

    def test_group_chat_between_friends(self):
        out = self.api("Alec", action="group_create", name="Kart night", members=[self.ids["Bea"], self.ids["Cal"]])
        gid = out["group"]
        self.api("Bea", action="group_message", group=gid, text="who brings snacks?")
        cal = self.api("Cal", action="poll")["inbox"]
        g = next(x for x in cal["groups"] if x["id"] == gid)
        self.assertEqual(("Kart night", 1, "who brings snacks?", "Bea"), (g["name"], g["unread"], g["last"], g["last_name"]))
        self.assertEqual({"Alec", "Bea", "Cal"}, {m["name"] for m in g["members"]})
        t = self.api("Cal", action="group_thread", group=gid)
        self.assertEqual(["who brings snacks?"], [m["text"] for m in t["messages"]])
        self.assertEqual(t["safety_code"], self.api("Alec", action="group_thread", group=gid)["safety_code"])
        self.assertNotIn("snacks", json.dumps(self.service.groups))
        # report a group message: verified from the service's copy
        self.api("Cal", action="report", player=self.ids["Bea"], category="spam", message=t["messages"][0]["id"], group=gid)
        rep = self.service.admin_reports()["reports"][0]
        self.assertEqual(("who brings snacks?", "Kart night"), (rep["message"]["text"], rep["group"]))
        # members leave; the creator renames
        self.api("Alec", action="group_rename", group=gid, name="Kart night!")
        with self.assertRaises(AppError):
            self.api("Bea", action="group_rename", group=gid, name="mine now")
        self.api("Cal", action="group_leave", group=gid)
        self.assertEqual([], self.api("Cal", action="poll")["inbox"]["groups"])
        with self.assertRaises(AppError):
            self.api("Cal", action="group_message", group=gid, text="still here?")

    def test_an_old_app_is_told_to_update_and_cannot_send_plain_text(self):
        old = self.service.hello("Oldie")                       # an app from before encryption: no key
        me = self.apps["Alec"].catalog.data["friends"]
        self.service.request(old["id"], old["secret"], self.service.players[me["id"]]["code"])
        self.api("Alec", action="decide", **{"from": old["id"]}, accept=True)
        self.api("Alec", action="poll")
        with self.assertRaises(AppError) as ctx:
            self.api("Alec", action="message", to=old["id"], text="hey")
        self.assertIn("Update Legacy Player to message Oldie", str(ctx.exception))
        self.assertFalse(next(f for f in self.api("Alec", action="poll")["inbox"]["friends"] if f["id"] == old["id"])["e2e"])
        with self.assertRaises(SocialError) as ctx:
            self.service.message(old["id"], old["secret"], me["id"], "plain words")
        self.assertIn("Update Legacy Player", str(ctx.exception))
        with self.assertRaises(AppError):                       # nor can they be put in a group chat
            self.api("Alec", action="group_create", name="g", members=[old["id"], self.ids["Bea"]])


class GroupRules(unittest.TestCase):
    def setUp(self):
        self.s = SocialService(None, Clock())
        self.p = {n: hello(self.s, n) for n in ("A", "B", "C", "D")}
        for x, y in (("A", "B"), ("A", "C"), ("B", "C"), ("A", "D")):
            befriend(self.s, self.p[x], self.p[y])

    def ids(self, *names):
        return [self.p[n]["id"] for n in names]

    def create(self, who="A", members=("B", "C")):
        a = self.p[who]
        return self.s.group_create(a["id"], a["secret"], "G", self.ids(*members))["group"]

    def test_everyone_must_be_friends_with_everyone(self):
        with self.assertRaises(SocialError):
            self.create(members=("B", "D"))                     # B and D are not friends
        gid = self.create()
        a = self.p["A"]
        with self.assertRaises(SocialError) as ctx:
            self.s.group_add(a["id"], a["secret"], gid, self.p["D"]["id"])
        self.assertIn("friends with everyone", str(ctx.exception))
        befriend(self.s, self.p["B"], self.p["D"])
        befriend(self.s, self.p["C"], self.p["D"])
        self.s.group_add(a["id"], a["secret"], gid, self.p["D"]["id"])
        self.assertEqual(4, len(self.s.groups[gid]["members"]))

    def test_a_block_between_any_two_prevents_adding(self):
        befriend(self.s, self.p["B"], self.p["D"])
        befriend(self.s, self.p["C"], self.p["D"])
        gid = self.create()
        c = self.p["C"]
        self.s.players[c["id"]]["blocked"].append(self.p["D"]["id"])    # C blocked D (friendship left aside for the test)
        with self.assertRaises(SocialError):
            self.s.group_add(self.p["A"]["id"], self.p["A"]["secret"], gid, self.p["D"]["id"])

    def test_blocking_takes_you_out_of_shared_groups(self):
        gid = self.create()
        b = self.p["B"]
        self.s.block(b["id"], b["secret"], self.p["C"]["id"])
        self.assertNotIn(b["id"], self.s.groups[gid]["members"])

    def test_size_limit_and_who_may_remove(self):
        names = [f"X{i}" for i in range(MAX_GROUP)]
        people = [hello(self.s, n) for n in names]
        a = self.p["A"]
        for i, x in enumerate(people):
            befriend(self.s, a, x)
            for y in people[:i]:
                befriend(self.s, x, y)
        with self.assertRaises(SocialError):
            self.s.group_create(a["id"], a["secret"], "big", [x["id"] for x in people])        # 11 with A
        gid = self.s.group_create(a["id"], a["secret"], "ok", [x["id"] for x in people[:MAX_GROUP - 1]])["group"]
        x0, x1 = people[0], people[1]
        with self.assertRaises(SocialError):
            self.s.group_remove(x0["id"], x0["secret"], gid, x1["id"])                       # only the creator removes
        self.s.group_remove(a["id"], a["secret"], gid, x1["id"])
        self.assertNotIn(x1["id"], self.s.groups[gid]["members"])
        self.s.group_leave(a["id"], a["secret"], gid)
        self.assertEqual(x0["id"], self.s.groups[gid]["owner"])                                # the next member takes over

    def test_messages_are_sealed_for_every_member_and_newcomers_see_only_new_ones(self):
        befriend(self.s, self.p["B"], self.p["D"])
        befriend(self.s, self.p["C"], self.p["D"])
        gid = self.create()
        send_group(self.s, self.p["B"], gid, "before D")
        a = self.p["A"]
        with self.assertRaises(SocialError):                        # sealed for A and B only: refused
            env = e2e.seal(*a["key"], a["id"], e2e.group_conv(gid),
                           {m: pc.b64d(self.s.players[m]["pub"], 32) for m in self.ids("A", "B")}, "partial")
            self.s.group_message(a["id"], a["secret"], gid, env)
        self.s.group_add(a["id"], a["secret"], gid, self.p["D"]["id"])
        send_group(self.s, a, gid, "welcome D")
        d = self.p["D"]
        rows = self.s.group_thread(d["id"], d["secret"], gid)["messages"]
        self.assertEqual(["welcome D"], [e2e.open_envelope(r["e"], d["id"], *d["key"])[0] for r in rows])

    def test_moderation_applies(self):
        gid = self.create()
        b = self.p["B"]
        self.s.admin_act("timeout", player=b["id"], length="1h")
        with self.assertRaises(SocialError):
            send_group(self.s, b, gid, "muted words")
        self.s.admin_act("ban", player=self.p["C"]["id"])
        self.assertNotIn(self.p["C"]["id"], self.s.groups[gid]["members"])                   # a ban removes them


class Hardening(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.s = SocialService(None, self.clock)
        self.a, self.b = hello(self.s, "Alec"), hello(self.s, "Bea")

    def test_names_presence_and_ids_are_not_given_to_strangers(self):
        out = self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        self.assertEqual([self.b["code"]], [x["name"] for x in out["sent"]])     # a pending request shows the code typed
        self.assertNotIn("Bea", json.dumps(out))
        self.assertEqual({"messages": []}, self.s.thread(self.a["id"], self.a["secret"], self.b["id"]))   # no name lookup by id
        with self.assertRaises(SocialError):
            self.s.block(self.a["id"], self.a["secret"], hello(self.s, "Stranger")["id"])     # nor via blocking
        self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)
        send(self.s, self.a, self.b, "hi")
        c = hello(self.s, "Cal")
        befriend(self.s, self.a, c)
        send(self.s, c, self.a, "yo")
        self.s.players[c["id"]]["friends"].remove(self.a["id"])                         # Cal is no longer a friend
        conv = next(x for x in self.s.heartbeat(self.a["id"], self.a["secret"])["conversations"] if x["id"] == c["id"])
        self.assertFalse(conv["online"])                                                 # an ex-friend's presence is not shown
        self.assertFalse(conv["friend"])
        self.s.remove(self.b["id"], self.b["secret"], self.a["id"])
        conv = self.s.heartbeat(self.a["id"], self.a["secret"])["conversations"]
        self.assertNotIn(self.b["id"], [x["id"] for x in conv])                          # removing deletes both copies

    def test_codes_are_long_typed_any_way_and_old_short_ones_are_replaced(self):
        code = self.b["code"]
        self.assertEqual(14, len(code))
        self.s.request(self.a["id"], self.a["secret"], code.lower().replace("-", " "))
        with tempfile.TemporaryDirectory() as d:
            s = SocialService(Path(d), self.clock)
            p = hello(s, "Old")
            s.players[p["id"]]["code"] = "MK7-4Q2X"
            s.players[p["id"]]["messages"] = {"x": [{"from": "x", "to": p["id"], "text": "old plain text", "at": self.clock.t}]}
            s.save()
            again = SocialService(Path(d), self.clock)
            self.assertEqual(14, len(again.players[p["id"]]["code"]))
            self.assertEqual(p["id"], again.codes[norm_code(again.players[p["id"]]["code"])])
            self.assertEqual({}, again.players[p["id"]]["messages"])                       # plain-text leftovers are dropped
            self.assertNotIn("old plain text", (Path(d) / "players.json").read_text())

    def test_invites_and_groups_are_rate_limited(self):
        befriend(self.s, self.a, self.b)
        with self.assertRaises(SocialError):
            for i in range(40):
                self.s.invite(self.a["id"], self.a["secret"], self.b["id"], "ABCDE-FGH12", "x")
        with self.assertRaises(SocialError):
            for i in range(15):
                self.s.group_create(self.a["id"], self.a["secret"], f"g{i}", [self.b["id"]])


if __name__ == "__main__":
    unittest.main()
