"""Friends service limits from the 2026-11-04 audit: a service-wide limit on new identities (F5), a flood of made-up
login names can't wipe a real account's lockout (F6), and a set-up in progress can't be replaced by someone else (F8)."""
import tempfile
import unittest
from pathlib import Path

from server.social import HELLO_PER_HOUR_ALL, SocialError, SocialService
from server.social import admin_auth
from server.social import purecrypto as pc
from server.social.inserver import InServerFriends
from server.lobby.throttle import FORWARDED


class Clock:
    def __init__(self):
        self.t = 9_000_000.0

    def __call__(self):
        return self.t


class Limits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_identities_are_limited_for_the_whole_service(self):
        s = SocialService(Path(self.tmp.name) / "s", self.clock)
        for i in range(HELLO_PER_HOUR_ALL):
            s.hello(f"p{i}", pc.b64e(pc.x25519_keypair()[1]))
        with self.assertRaises(SocialError):
            s.hello("one too many", pc.b64e(pc.x25519_keypair()[1]))
        self.clock.t += 3601
        s.hello("later", pc.b64e(pc.x25519_keypair()[1]))

    def test_meeting_point_friends_share_a_bigger_window(self):
        f = InServerFriends(Path(self.tmp.name) / "in", self.clock)
        made = 0
        for i in range(30):                       # more than the 10 an hour one address gets
            f.handle({"friends": {"op": "hello", "name": f"x{i}", "pub": pc.b64e(pc.x25519_keypair()[1])}, "_peer": FORWARDED})
            made += 1
        self.assertEqual(30, made)
        with self.assertRaises(SocialError):
            for i in range(11):
                f.handle({"friends": {"op": "hello", "name": f"y{i}", "pub": pc.b64e(pc.x25519_keypair()[1])}, "_peer": "203.0.113.9"})

    def test_a_flood_of_made_up_names_keeps_a_real_lock(self):
        store = admin_auth.AdminStore(Path(self.tmp.name) / "admin", clock=self.clock)
        out = store.begin("owner", "a long enough password 1", "owner")
        store.finish("owner", pc.totp(pc.totp_secret_bytes(out["secret"]), self.clock()))
        for _ in range(admin_auth.FREE_TRIES):
            with self.assertRaises(admin_auth.AuthError):
                store.login("owner", "wrong", "000000")
        with self.assertRaises(admin_auth.Locked):
            store.login("owner", "a long enough password 1", "000000")
        for i in range(5100):
            store._failed(f"madeup{i}")
        with self.assertRaises(admin_auth.Locked):
            store.login("owner", "a long enough password 1", "000000")
        self.assertLessEqual(len(store._fails), 5101)

    def test_someone_elses_set_up_is_not_replaced(self):
        store = admin_auth.AdminStore(Path(self.tmp.name) / "admin2", clock=self.clock)
        first = store.create_invite("owner")["code"]
        second = store.create_invite("owner")["code"]
        store.begin_from_invite(first, "mod", "a long enough password 2")
        with self.assertRaises(admin_auth.AuthError):              # another invite can't take over that set-up
            store.begin_from_invite(second, "mod", "a long enough password 3")
        store.begin_from_invite(first, "mod", "a long enough password 4")     # the same invite may start over


if __name__ == "__main__":
    unittest.main()
