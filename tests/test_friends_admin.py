"""The friends service's moderation console: accounts with scrypt passwords and TOTP codes, lockout with backoff,
sessions with idle and absolute limits, CSRF on every change, logout, invites, an audit log without addresses, and the
local moderator key that only works from the computer running the service."""
import json
import os
import re
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from server.social import SocialService
from server.social import purecrypto as pc
from server.social.__main__ import FriendsHTTPServer, create_admin, make_handler
from server.social.admin_auth import FREE_TRIES, AdminStore, AuthError, Locked, Sessions
from tests.friends_kit import hello


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def make_account(store, name="owner", password="a long password", role="owner"):
    started = store.begin(name, password, role)
    secret = pc.totp_secret_bytes(started["secret"])
    store.finish(name, pc.totp(secret, store.clock()))
    return secret


class Accounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.store = AdminStore(Path(self.tmp.name), self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def test_password_and_code_are_both_needed_and_a_code_works_once(self):
        with self.assertRaises(AuthError):
            self.store.begin("owner", "short", "owner")                       # at least 10 characters
        secret = make_account(self.store)
        data = json.loads((Path(self.tmp.name) / "admins.json").read_text())
        self.assertNotIn("a long password", json.dumps(data))
        self.assertEqual(64, len(data["users"]["owner"]["hash"]))           # scrypt, with its own salt
        if os.name == "posix":
            self.assertEqual(0o600, (Path(self.tmp.name) / "admins.json").stat().st_mode & 0o777)
        with self.assertRaises(AuthError):                                   # the code used to finish set-up: not again
            self.store.login("owner", "a long password", pc.totp(secret, self.clock()))
        self.clock.t += 30
        code = pc.totp(secret, self.clock())
        with self.assertRaises(AuthError):
            self.store.login("owner", "wrong password!", code)
        self.assertEqual({"name": "owner", "role": "owner"}, self.store.login("owner", "a long password", code))
        with self.assertRaises(AuthError):
            self.store.login("owner", "a long password", code)               # replayed
        self.clock.t += 60
        self.store.login("owner", "a long password", pc.totp(secret, self.clock() - 30))   # one step of drift is fine

    def test_a_set_up_code_cannot_be_guessed(self):
        self.store.begin("owner", "a long password", "owner")
        for _ in range(FREE_TRIES - 1):
            with self.assertRaises(AuthError):
                self.store.finish("owner", "000000")
        with self.assertRaises(AuthError) as ctx:
            self.store.finish("owner", "000000")
        self.assertIn("Start the set-up again", str(ctx.exception))
        self.assertEqual([], self.store.accounts())
        with self.assertRaises(AuthError):                                   # the pending set-up is gone
            self.store.finish("owner", "123456")

    def test_wrong_tries_lock_the_name_with_growing_waits(self):
        secret = make_account(self.store)
        for _ in range(FREE_TRIES - 1):
            with self.assertRaises(AuthError):
                self.store.login("owner", "nope nope nope", "000000")
        with self.assertRaises(Locked) as ctx:
            self.store.login("owner", "nope nope nope", "000000")
        first = ctx.exception.seconds
        self.clock.t += 31
        with self.assertRaises(Locked):                                      # still locked, even with the right answer?
            self.store.login("owner", "nope again!!", "000000")
        self.assertGreater(self.store._fails["owner"][1] - self.clock(), first)              # the wait doubled
        with self.assertRaises(Locked):
            self.store.login("owner", "a long password", pc.totp(secret, self.clock()))
        self.clock.t += 3600
        self.store.login("owner", "a long password", pc.totp(secret, self.clock()))
        log = [e["event"] for e in self.store.audit_tail()]
        self.assertIn("locked", log)
        self.assertIn("login_failed", log)
        self.assertIn("login", log)

    def test_unknown_names_get_the_same_answer_and_lock_too(self):
        make_account(self.store)
        with self.assertRaises(AuthError) as ctx:
            self.store.login("nobody", "whatever whatever", "123456")
        self.assertEqual("That name, password or code is not right.", str(ctx.exception))
        for _ in range(FREE_TRIES):
            try:
                self.store.login("nobody", "whatever whatever", "123456")
            except Locked:
                break
            except AuthError:
                pass
        with self.assertRaises(Locked):
            self.store.login("nobody", "whatever whatever", "123456")

    def test_invites_are_one_time_and_expire(self):
        make_account(self.store)
        inv = self.store.create_invite("owner")
        self.assertTrue(inv["code"].startswith("LPI-"))
        self.assertNotIn(inv["code"], (Path(self.tmp.name) / "admins.json").read_text())   # only its hash is kept
        started = self.store.begin_from_invite(inv["code"].lower(), "helper", "helper password")
        self.store.finish("helper", pc.totp(pc.totp_secret_bytes(started["secret"]), self.clock()))
        self.assertEqual("moderator", next(a for a in self.store.accounts() if a["name"] == "helper")["role"])
        with self.assertRaises(AuthError):
            self.store.begin_from_invite(inv["code"], "second", "helper password")
        old = self.store.create_invite("owner")
        self.clock.t += 49 * 3600
        with self.assertRaises(AuthError):
            self.store.begin_from_invite(old["code"], "late", "helper password")
        with self.assertRaises(AuthError):
            self.store.remove("owner", "owner")                                   # the last owner stays

    def test_command_line_set_up(self):
        lines = []
        answers = iter(["cli password 123", "cli password 123"])
        codes = []

        def code(_prompt):
            secret = re.search(r"Secret: (\w+)", "\n".join(lines)).group(1)
            codes.append(pc.totp(pc.totp_secret_bytes(secret), __import__("time").time()))
            return codes[-1]
        self.assertTrue(create_admin(Path(self.tmp.name), "cliowner", ask=lambda _p: next(answers), read_code=code, out=lines.append))
        self.assertEqual(["cliowner"], [a["name"] for a in AdminStore(Path(self.tmp.name)).accounts()])
        self.assertTrue(any("otpauth://totp/" in line for line in lines))
        answers = iter(["one password!!", "another password"])
        self.assertFalse(create_admin(Path(self.tmp.name), "x2", ask=lambda _p: next(answers), read_code=code, out=lines.append))


class SessionLimits(unittest.TestCase):
    def test_idle_and_absolute_expiry(self):
        clock = Clock(0.0)
        s = Sessions(clock, idle=60, lifetime=300)
        sid = s.create("owner", "owner")["id"]
        clock.t = 50
        self.assertIsNotNone(s.get(sid))
        clock.t = 111
        self.assertIsNone(s.get(sid))                                            # idle too long
        sid = s.create("owner", "owner")["id"]
        for t in range(150, 460, 50):
            clock.t = t
            alive = s.get(sid)
        self.assertIsNone(alive)                                                 # kept busy, but past its lifetime


class ConsoleOverHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.service = SocialService(None)
        self.store = AdminStore(self.folder)
        self.secret = make_account(self.store, "owner", "owner password 1")
        self.sessions = Sessions()
        self.httpd = FriendsHTTPServer(("127.0.0.1", 0), make_handler(self.service, "local-key", admins=self.store, sessions=self.sessions))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.player = hello(self.service, "Troll")

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def call(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}") if "json" in r.headers.get("Content-Type", "") else r.read(), dict(r.headers)
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"{}"), dict(err.headers)

    def login(self, step_offset=30, **extra):
        code = pc.totp(self.secret, __import__("time").time() + step_offset)
        status, out, headers = self.call("/admin/login", {"name": "owner", "password": "owner password 1", "code": code}, extra or None)
        self.assertEqual(200, status, out)
        cookie = headers["Set-Cookie"]
        return cookie, out["csrf"]

    def test_nothing_without_a_session_and_the_page_is_only_a_form(self):
        status, page, _ = self.call("/admin")
        self.assertEqual(200, status)
        self.assertIn(b"Log in", page)
        self.assertNotIn(b"Troll", page)
        for path in ("/admin/reports", "/admin/players?q=", "/admin/accounts", "/admin/me"):
            self.assertEqual(401, self.call(path)[0], path)
        self.assertEqual(401, self.call("/admin/act", {"action": "ban", "player": self.player["id"]})[0])
        self.assertNotIn(self.player["id"], self.service.mod["bans"])

    def test_login_session_csrf_and_logout(self):
        cookie, csrf = self.login()
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Path=/admin", cookie)
        self.assertNotIn("Secure", cookie)                                      # plain http here (tests); https sets it
        sid = cookie.split(";")[0]
        status, out, _ = self.call("/admin/reports", headers={"Cookie": sid})
        self.assertEqual(200, status)
        ban = {"action": "ban", "player": self.player["id"], "reason": "test"}
        self.assertEqual(403, self.call("/admin/act", ban, {"Cookie": sid})[0])                       # no CSRF token
        self.assertEqual(403, self.call("/admin/act", ban, {"Cookie": sid, "X-CSRF-Token": "guess"})[0])
        self.assertEqual(403, self.call("/admin/act", ban, {"Cookie": sid, "X-CSRF-Token": csrf, "Origin": "https://evil.example"})[0])
        self.assertNotIn(self.player["id"], self.service.mod["bans"])
        self.assertEqual(200, self.call("/admin/act", ban, {"Cookie": sid, "X-CSRF-Token": csrf})[0])
        self.assertEqual("owner", self.service.mod["log"][-1]["by"])
        status, out, headers = self.call("/admin/logout", {}, {"Cookie": sid, "X-CSRF-Token": csrf})
        self.assertEqual(200, status)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(401, self.call("/admin/reports", headers={"Cookie": sid})[0])
        log = (self.folder / "admin_audit.log").read_text()
        for event in ('"login"', '"action"', '"logout"'):
            self.assertIn(event, log)
        self.assertIsNone(re.search(r"\d+\.\d+\.\d+\.\d+|::1", log))           # no addresses in the audit log

    def test_secure_cookie_behind_https_and_owner_only_account_pages(self):
        cookie, csrf = self.login(**{"X-Forwarded-Proto": "https"})
        self.assertIn("Secure", cookie)
        sid = cookie.split(";")[0]
        status, out, _ = self.call("/admin/invite/create", {"role": "moderator"}, {"Cookie": sid, "X-CSRF-Token": csrf})
        self.assertEqual(200, status)
        started = self.call("/admin/invite/begin", {"invite": out["code"], "name": "mod1", "password": "mod password 1"})[1]
        self.assertTrue(started["qr"].startswith("data:image/svg+xml;base64,"))
        mod_secret = pc.totp_secret_bytes(started["secret"])
        self.assertEqual(200, self.call("/admin/invite/finish", {"name": "mod1", "code": pc.totp(mod_secret, __import__("time").time())})[0])
        status, out, headers = self.call("/admin/login", {"name": "mod1", "password": "mod password 1",
                                                          "code": pc.totp(mod_secret, __import__("time").time() + 30)})
        self.assertEqual(("moderator", 200), (out["role"], status))
        mod_sid = headers["Set-Cookie"].split(";")[0]
        self.assertEqual(403, self.call("/admin/accounts", headers={"Cookie": mod_sid})[0])           # owners only
        self.assertEqual(200, self.call("/admin/reports", headers={"Cookie": mod_sid})[0])
        self.assertEqual(200, self.call("/admin/accounts/remove", {"name": "mod1"}, {"Cookie": sid, "X-CSRF-Token": csrf})[0])
        self.assertEqual(401, self.call("/admin/reports", headers={"Cookie": mod_sid})[0])           # their sessions end too

    def test_the_local_key_only_from_this_computer(self):
        self.assertEqual(200, self.call("/admin/reports", headers={"X-Admin-Token": "local-key"})[0])
        self.assertEqual(401, self.call("/admin/reports", headers={"X-Admin-Token": "wrong"})[0])
        status, out, _ = self.call("/admin/reports", headers={"X-Admin-Token": "local-key", "X-Forwarded-For": "198.51.100.4"})
        self.assertEqual(403, status)                                            # a proxy passing someone else's request
        self.assertIn("Log in", out["error"])
        status, _, _ = self.call("/admin/setup/begin", {"name": "x", "password": "y" * 12}, {"X-Admin-Token": "local-key", "Forwarded": "for=1.2.3.4"})
        self.assertEqual(403, status)
        # set-up through the key, from here: a second owner
        status, out, _ = self.call("/admin/setup/begin", {"name": "owner2", "password": "second owner pw"}, {"X-Admin-Token": "local-key"})
        self.assertEqual(200, status)
        self.assertEqual(200, self.call("/admin/setup/finish", {"name": "owner2", "code": pc.totp(pc.totp_secret_bytes(out["secret"]), __import__("time").time())},
                                        {"X-Admin-Token": "local-key"})[0])

    def test_the_key_from_another_computer_is_refused_unless_allowed(self):
        addr = None
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("192.0.2.1", 9))                                   # no packet is sent; it picks the outgoing address
                addr = s.getsockname()[0]
        except OSError:
            pass
        if not addr or addr.startswith("127."):
            self.skipTest("no non-loopback address on this machine")
        for allow, expected in ((False, 403), (True, 200)):
            httpd = FriendsHTTPServer(("0.0.0.0", 0), make_handler(self.service, "local-key", admins=self.store, allow_remote_key=allow))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                req = urllib.request.Request(f"http://{addr}:{httpd.server_address[1]}/admin/reports", headers={"X-Admin-Token": "local-key"})
                try:
                    status = urllib.request.urlopen(req, timeout=10).status
                except urllib.error.HTTPError as err:
                    status = err.code
                self.assertEqual(expected, status)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_logins_are_limited_per_address(self):
        from server.http_guard import AddressWindow
        from unittest import mock
        limit = AddressWindow(3, 600)
        httpd = FriendsHTTPServer(("127.0.0.1", 0), make_handler(self.service, "k", admins=self.store, login_limit=limit))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base, self.base = self.base, f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            with mock.patch("server.http_guard.key_for", return_value="198.51.100.7"):
                codes = [self.call("/admin/login", {"name": "x", "password": "y", "code": "1"})[0] for _ in range(4)]
            self.assertEqual([400, 400, 400, 429], codes)
        finally:
            self.base = base
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
