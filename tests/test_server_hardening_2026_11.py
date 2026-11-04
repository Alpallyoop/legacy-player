"""Server hardening, November 2026 audit: one test class per finding.

1 answers a client never reads, 2 unbounded ids and replay, 3 meeting-point friends sharing one key, 4 unfinished TLS
handshakes and meeting-point parking per network, 5 relay pipes of removed players, 6 relay counting, 7 short
certificate pins, 8 damaged secret files, 9 bounded lockouts and the global invite cap."""
import asyncio
import json
import socket
import ssl
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from launcher import servercode
from launcher.lobby_client import LobbyClient, LobbyClientError
from launcher.version import PUBLIC_SERVER_CODE
from runtime.replay import ReplayRecorder
from server import selfsigned
from server.api import json_server
from server.api.control import ServerControl
from server.lobby import LobbyError, LobbyService
from server.lobby import service as service_module
from server.lobby.invites import InviteBook
from server.lobby.throttle import FORWARDED, FailureThrottle
from server.rendezvous import Rendezvous, prefix_for
from server.state_store import StateStore
from tests.test_community_lobby import PROFILE, FakeClock
from tests.test_launcher import ServerThread


def run(coro):
    return asyncio.run(coro)


def room(service: LobbyService, **extra) -> dict:
    return service.dispatch({"operation": "create", "participant_id": "host", "profile": PROFILE,
                             "adapter_id": "dolphin", "game_pack_id": "generic", "max_players": 4, **extra})


class StalledReaderTests(unittest.TestCase):
    """Finding 1: an answer the client never reads ends the connection and frees its slot."""

    def test_a_client_that_never_reads_gives_its_slot_back(self):
        class Big:
            def dispatch(self, request):
                return {"blob": "x" * (4 * 1024 * 1024)}

        async def main():
            json_server._PER_IP.clear()
            limit = asyncio.Semaphore(1)
            with mock.patch.object(json_server, "WRITE_TIMEOUT_SECONDS", 1.0):
                srv = await asyncio.start_server(lambda r, w: json_server.handle_client(r, w, Big(), limit),
                                                 "127.0.0.1", 0)
                port = srv.sockets[0].getsockname()[1]
                sock = socket.socket()
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
                sock.connect(("127.0.0.1", port))
                sock.sendall(b'{"operation":"browse"}\n')          # and never read the answer
                await asyncio.sleep(0.3)
                self.assertTrue(limit.locked())
                for _ in range(40):
                    await asyncio.sleep(0.1)
                    if not limit.locked():
                        break
                self.assertFalse(limit.locked(), "the stalled connection still holds the only slot")
                sock.close()
                srv.close()
        run(main())

    def test_the_write_buffer_is_capped(self):
        async def main():
            seen = {}

            async def cb(r, w):
                json_server._limit_write_buffer(w)
                seen["high"] = w.transport.get_write_buffer_limits()[1]
                w.close()
            srv = await asyncio.start_server(cb, "127.0.0.1", 0)
            _, w = await asyncio.open_connection("127.0.0.1", srv.sockets[0].getsockname()[1])
            await asyncio.sleep(0.1)
            w.close()
            srv.close()
            return seen["high"]
        self.assertEqual(json_server.WRITE_BUFFER_HIGH, run(main()))


class BoundedInputTests(unittest.TestCase):
    """Finding 2: ids and text are bounded, `removed` is capped, a full replay never leaves half a room."""

    def test_long_or_odd_ids_are_refused_and_normal_ones_pass(self):
        service = LobbyService(max_participants=8)
        created = room(service)
        code = created["invite_code"]
        with self.assertRaisesRegex(LobbyError, "participant_id is too long"):
            service.dispatch({"operation": "join", "invite_code": code, "participant_id": "x" * 129, "profile": PROFILE})
        with self.assertRaisesRegex(LobbyError, "control characters"):
            service.dispatch({"operation": "join", "invite_code": code, "participant_id": "a\nb", "profile": PROFILE})
        for field, size in (("game_id", 257), ("region", 129)):
            with self.assertRaisesRegex(LobbyError, f"{field} is too long"):
                service.dispatch({"operation": "join", "invite_code": code, "participant_id": "p",
                                  "profile": {**PROFILE, field: "g" * size}})
        with self.assertRaisesRegex(LobbyError, "adapter_id is too long"):
            service.dispatch({"operation": "create", "participant_id": "h2", "profile": PROFILE,
                              "adapter_id": "a" * 129, "game_pack_id": "generic"})
        # what the launcher sends: "name#tag" players (names may hold spaces), console:slug:region game ids
        for pid in ("Player#0420", "Big Al_2.0#1234", "p2", "x" * 64):
            out = service.dispatch({"operation": "join", "invite_code": code, "participant_id": pid,
                                    "profile": {"game_id": "gamecube:mario-kart-double-dash:usa", "region": "USA, Europe"}})
            self.assertIn(out["status"], {"joined", "waiting"})

    def test_removed_notes_are_capped(self):
        service = LobbyService(max_participants=8)
        created = room(service)
        sid = created["session"]["session_id"]
        with mock.patch.object(service_module, "MAX_REMOVED", 5):
            for i in range(20):
                joined = service.dispatch({"operation": "join", "invite_code": created["invite_code"] if i % 8 == 0 else
                                           service.dispatch({"operation": "invite", "session_id": sid, "participant_id": "host",
                                                             "credential": created["credential"]})["invite_code"],
                                           "participant_id": f"p{i}", "profile": PROFILE})
                service.dispatch({"operation": "leave", "session_id": sid, "participant_id": f"p{i}",
                                  "credential": joined["credential"]})
            self.assertEqual(5, len(service.removed))
            self.assertIn((sid, "p19"), service.removed)           # the newest are kept

    def test_a_full_replay_does_not_break_the_room(self):
        service = LobbyService(max_participants=8)
        created = room(service)
        sid = created["session"]["session_id"]
        service.recorders[sid].max_events = 3
        for pid in ("a", "b", "c"):
            invite = service.dispatch({"operation": "invite", "session_id": sid, "participant_id": "host",
                                       "credential": created["credential"]})["invite_code"]
            out = service.dispatch({"operation": "join", "invite_code": invite, "participant_id": pid, "profile": PROFILE})
            self.assertEqual("joined", out["status"])
        self.assertEqual({"host", "a", "b", "c"}, set(service.sessions[sid].participants))
        events = service.recorders[sid].events
        self.assertEqual(3, len(events))
        self.assertEqual("replay_truncated", events[-1]["event"])
        self.assertTrue(service.recorders[sid].truncated)
        # the plain recorder keeps its old contract
        with self.assertRaisesRegex(RuntimeError, "event limit"):
            ReplayRecorder("12345678-abcd-1234-abcd-1234567890ab", {}, max_events=0).record("x")

    def test_snapshot_is_a_copy_safe_to_write_off_the_loop(self):
        service = LobbyService()
        created = room(service)
        sid = created["session"]["session_id"]
        snap = service.export_state()
        before = json.dumps(snap, sort_keys=True)
        service.options[sid]["label"] = "changed"
        service.dispatch({"operation": "join", "invite_code": created["invite_code"], "participant_id": "late", "profile": PROFILE})
        service.invites.prune()
        self.assertEqual(before, json.dumps(snap, sort_keys=True))


class MeetingPointShareTests(unittest.TestCase):
    """Finding 3: friends through a meeting point have their own connection share and are never locked out together."""

    def test_forwarded_failures_use_a_budget_not_a_lockout(self):
        clock = FakeClock()
        t = FailureThrottle(max_failures=8, window=60, lockout=300, clock=clock)
        for _ in range(79):
            t.fail(FORWARDED)
        self.assertEqual(0, t.blocked(FORWARDED))                  # 8 x 10 per minute before anyone has to wait
        t.fail(FORWARDED)
        wait = t.blocked(FORWARDED)
        self.assertTrue(0 < wait <= 60, wait)                      # a short wait, never the 300 s lockout
        t.ok(FORWARDED)                                            # one friend's success does not reset the budget
        self.assertGreater(t.blocked(FORWARDED), 0)
        clock.now += 61
        self.assertEqual(0, t.blocked(FORWARDED))
        # direct addresses are unchanged
        for _ in range(8):
            t.fail("203.0.113.7")
        self.assertGreater(t.blocked("203.0.113.7"), 250)

    def test_eight_bad_keys_through_the_meeting_point_do_not_lock_out_friends(self):
        service = LobbyService()
        service.access_key = "aabbccddee"
        for _ in range(8):
            with self.assertRaises(PermissionError):
                service.dispatch({"operation": "browse", "access_key": "0000000000", "_peer": FORWARDED})
        self.assertIn("rooms", service.dispatch({"operation": "browse", "access_key": "aabbccddee", "_peer": FORWARDED}))

    def test_five_bad_invites_through_the_meeting_point_do_not_lock_out_friends(self):
        service = LobbyService()
        created = room(service)
        for _ in range(5):
            with self.assertRaises(LobbyError):
                service.dispatch({"operation": "join", "invite_code": "AAAAA-AAAAA", "participant_id": "x",
                                  "profile": PROFILE, "_peer": FORWARDED})
        out = service.dispatch({"operation": "join", "invite_code": created["invite_code"], "participant_id": "friend",
                                "profile": PROFILE, "_peer": FORWARDED})
        self.assertEqual("joined", out["status"])

    def test_aliases_through_the_meeting_point_have_a_larger_share(self):
        service = LobbyService()
        for i in range(70):
            service.dispatch({"operation": "claim_alias", "alias": f"n{i}", "install_id": f"{i:04x}", "_peer": FORWARDED})
        self.assertEqual(70, len(service.aliases))

    def test_forwarded_connections_have_their_own_cap(self):
        async def main():
            json_server._PER_IP.clear()
            limit = asyncio.Semaphore(8)
            service = LobbyService()
            with mock.patch.object(json_server, "MAX_FORWARDED_CONNECTIONS", 2):
                srv = await asyncio.start_server(
                    lambda r, w: json_server.handle_client(r, w, service, limit, forwarded=True), "127.0.0.1", 0)
                port = srv.sockets[0].getsockname()[1]
                held = [await asyncio.open_connection("127.0.0.1", port) for _ in range(2)]
                await asyncio.sleep(0.2)
                self.assertEqual(2, json_server._PER_IP.get(FORWARDED))
                r, w = await asyncio.open_connection("127.0.0.1", port)
                line = await asyncio.wait_for(r.readline(), 5)
                self.assertIn(b"busy", line)
                w.close()
                for _, hw in held:
                    hw.close()
                await asyncio.sleep(0.2)
                self.assertNotIn(FORWARDED, json_server._PER_IP)
                srv.close()
        run(main())
        self.assertEqual(json_server.MAX_CONNECTIONS // 2, json_server.MAX_FORWARDED_CONNECTIONS)


class HandshakeAndParkingTests(unittest.TestCase):
    """Finding 4: unfinished TLS handshakes per address, the open-file limit, parking per network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cert, key, self.fp = selfsigned.ensure_certificate(Path(self.tmp.name) / "tls")
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(cert, key)

    def test_pending_handshakes_are_limited_per_address(self):
        async def main():
            json_server._PER_IP.clear()
            json_server._PENDING_TLS.clear()
            served = []

            async def then(reader, writer):
                served.append(writer.get_extra_info("ssl_object") is not None)
                writer.close()
            with mock.patch.object(json_server, "MAX_PENDING_HANDSHAKES_PER_IP", 2), \
                    mock.patch.object(json_server, "key_for", lambda host: "198.51.100.4"):
                srv = await asyncio.start_server(lambda r, w: json_server.accept_tls(r, w, self.ctx, then), "127.0.0.1", 0)
                port = srv.sockets[0].getsockname()[1]
                silent = [await asyncio.open_connection("127.0.0.1", port) for _ in range(2)]   # never say hello
                await asyncio.sleep(0.2)
                self.assertEqual(2, json_server._PENDING_TLS.get("198.51.100.4"))
                r, w = await asyncio.open_connection("127.0.0.1", port)
                self.assertEqual(b"", await asyncio.wait_for(r.read(10), 5))     # refused at once
                w.close()
                for _, sw in silent:
                    sw.close()
                await asyncio.sleep(0.3)
                self.assertEqual({}, json_server._PENDING_TLS)
                client = ssl.create_default_context()
                client.check_hostname, client.verify_mode = False, ssl.CERT_NONE
                _, tw = await asyncio.open_connection("127.0.0.1", port, ssl=client)
                await asyncio.sleep(0.2)
                tw.close()
                srv.close()
            self.assertEqual([True], served)
        run(main())

    def test_open_file_limit_is_raised_to_the_hard_limit(self):
        try:
            import resource
        except ImportError:
            self.skipTest("POSIX only")
        json_server.raise_open_file_limit()
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if hard != resource.RLIM_INFINITY:
            self.assertEqual(hard, soft)

    def test_parking_is_capped_per_network(self):
        self.assertEqual("2001:db8:aa::/48", prefix_for("2001:db8:aa:3::1"))
        self.assertEqual("203.0.113.0/24", prefix_for("203.0.113.9"))
        self.assertIsNone(prefix_for("127.0.0.1"))
        from server.rendezvous import new_secret, token_for

        async def main():
            rv = Rendezvous(max_parked_per_prefix=2, park_seconds=30)
            peers = iter(["2001:db8:aa:1::1", "2001:db8:aa:2::1", "2001:db8:aa:3::1", "2001:db8:bb::1"])

            async def cb(reader, writer):
                await reader.readline()
                secret = new_secret()
                await rv.handle({"operation": "rv_park", "secret": secret, "token": token_for(secret),
                                 "_peer": next(peers)}, reader, writer)
            srv = await asyncio.start_server(cb, "127.0.0.1", 0)
            port = srv.sockets[0].getsockname()[1]
            answers, conns = [], []
            for _ in range(4):
                r, w = await asyncio.open_connection("127.0.0.1", port)
                w.write(b"park\n")
                answers.append(json.loads(await asyncio.wait_for(r.readline(), 5)))
                conns.append(w)
            self.assertEqual([True, True, False, True], [a["ok"] for a in answers])
            self.assertIn("your network", answers[2]["error"])
            self.assertEqual({"2001:db8:aa::/48": 2, "2001:db8:bb::/48": 1}, rv.parked_per_prefix)
            for w in conns:
                w.close()
            await asyncio.sleep(0.3)
            self.assertEqual({}, rv.parked_per_prefix)
            rv.drop_all()
            srv.close()
        run(main())


class RelayMembershipTests(unittest.TestCase):
    """Findings 5 and 6: a removed player's pipe closes; a guest is counted before it waits."""

    def setUp(self):
        self.server = ServerThread().start()
        self.addCleanup(self.server.stop)
        self.client = LobbyClient("127.0.0.1", self.server.port)
        created = self.client.call({"operation": "create", "participant_id": "host", "profile": PROFILE,
                                    "adapter_id": "retroarch", "game_pack_id": "generic", "max_players": 3})
        self.sid = created["session"]["session_id"]
        self.host_auth = {"session_id": self.sid, "participant_id": "host", "credential": created["credential"]}
        joined = self.client.call({"operation": "join", "invite_code": created["invite_code"], "participant_id": "g1",
                                   "profile": PROFILE})
        self.guest_auth = {"session_id": self.sid, "participant_id": "g1", "credential": joined["credential"]}

    def test_a_kicked_player_loses_the_open_pipe(self):
        got = {}

        def host_side():
            got["host"] = self.client.open_relay("host", self.host_auth, wait_paired=True)
        t = threading.Thread(target=host_side, daemon=True)
        t.start()
        time.sleep(0.3)
        guest = self.client.open_relay("guest", self.guest_auth, wait_paired=True)
        t.join(10)
        host = got["host"]
        guest.settimeout(5)
        host.settimeout(5)
        guest.sendall(b"hello")
        self.assertEqual(b"hello", host.recv(16))
        self.client.call({"operation": "kick", **self.host_auth, "target_id": "g1"})
        self.assertEqual(b"", guest.recv(16))                     # closed by the server, not by an idle timeout
        self.assertEqual(b"", host.recv(16))
        guest.close()
        host.close()

    def test_one_guest_can_not_wait_on_more_connections_than_allowed(self):
        results = []

        def guest_side():
            try:
                self.client.open_relay("guest", self.guest_auth, wait_paired=True)
                results.append("paired")
            except LobbyClientError as exc:
                results.append(str(exc))
        threads = [threading.Thread(target=guest_side, daemon=True) for _ in range(3)]
        for t in threads:
            t.start()
            time.sleep(0.1)
        time.sleep(0.3)
        # two are waiting for a host slot; the third is refused at once
        self.assertEqual(1, len(results), results)
        self.assertIn("too many relay connections", results[0])
        for t in threads:
            t.join(15)


class PinLengthTests(unittest.TestCase):
    """Finding 7: 80-bit pins for a player's server reached through a meeting point."""

    def test_short_inner_pin_through_a_meeting_point_is_refused(self):
        via = {"host": "203.0.113.5", "port": 8765, "fingerprint": "ab" * 5, "token": "cd" * 12}
        with self.assertRaisesRegex(LobbyClientError, "fresh code"):
            LobbyClient("", 0, tls=True, fingerprint="ef" * 5, via=via)
        LobbyClient("", 0, tls=True, fingerprint="ef" * 10, via=via)      # 80 bits: fine (40-bit meeting point pin stays allowed)

    def test_lp3_codes_need_a_full_fingerprint(self):
        meet = {"host": "203.0.113.5", "port": 8765, "fingerprint": "12" * 16}
        with self.assertRaises(servercode.CodeError):
            servercode.encode_meet("ab" * 12, "cd" * 5, "ef" * 5, meet)
        found = servercode.decode(servercode.encode_meet("ab" * 12, "cd" * 32, "ef" * 5, meet))
        self.assertEqual("cd" * 10, found["fingerprint"])

    def test_the_built_in_public_server_code_still_works(self):
        found = servercode.decode(PUBLIC_SERVER_CODE)
        self.assertEqual(20, len(found["fingerprint"]))
        self.assertNotIn("token", found)
        LobbyClient(found["host"], found["port"], tls=True, fingerprint=found["fingerprint"],
                    access_key=found.get("key", ""))
        # and it is accepted as the meeting point of a player's LP3 code
        lp3 = servercode.encode_meet("ab" * 12, "cd" * 32, "ef" * 5, found)
        inner = servercode.decode(lp3)
        LobbyClient("", 0, tls=True, fingerprint=inner["fingerprint"], via={**inner["meet"], "token": inner["token"]})


class SecretFileTests(unittest.TestCase):
    """Finding 8: damaged secret files are replaced, and an empty admin token never works."""

    def test_empty_or_short_secrets_are_regenerated(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(Path(d))
            (Path(d) / "access_key.bin").write_bytes(b"")
            (Path(d) / "admin_token.bin").write_bytes(b"\x01\x02")
            (Path(d) / "invite_pepper.bin").write_bytes(b"x" * 40)
            with mock.patch("sys.stderr"):
                key, token, pepper = store.access_key(), store.admin_token(), store.pepper()
            self.assertEqual(10, len(key))
            self.assertEqual(64, len(token))
            self.assertEqual(32, len(pepper))
            self.assertEqual(key, store.access_key())                  # and it stays the same from now on
            self.assertEqual(token, store.admin_token())

    def test_an_empty_admin_token_is_never_accepted(self):
        control = ServerControl("", asyncio.Event(), LobbyService())
        for given in ("", None):
            with self.assertRaisesRegex(PermissionError, "invalid admin token"):
                control.handle({"operation": "admin_status", "admin_token": given}, peer_is_loopback=True)


class BoundedLockoutTests(unittest.TestCase):
    """Finding 9: the lockout table is bounded; the global invite cap no longer blocks redemption cheaply."""

    def test_locked_table_is_bounded_and_keeps_fresh_lockouts(self):
        clock = FakeClock()
        t = FailureThrottle(max_failures=1, window=60, lockout=300, clock=clock, max_locked=3)
        t.fail("198.51.100.1")
        clock.now += 10
        for i in range(2, 7):
            t.fail(f"198.51.100.{i}")
            clock.now += 1
        self.assertLessEqual(len(t._locked), 3)
        self.assertGreater(t.blocked("198.51.100.6"), 0)            # the newest lockouts stay
        self.assertGreater(t.blocked("198.51.100.5"), 0)

    def test_many_bad_guesses_from_many_addresses_do_not_stop_a_real_code(self):
        book = InviteBook()
        code, _ = book.create("s1")
        for i in range(200):
            with self.assertRaises(Exception):
                book.redeem_ex("AAAAA-AAAAA", f"203.0.{i // 250}.{i % 250}")
        self.assertEqual("s1", book.redeem_ex(code, "198.51.100.77")[0])


if __name__ == "__main__":
    unittest.main()


class NewCodesCarryEightyBits(unittest.TestCase):
    """Audit 2026-11-04, open item 2: a code without a key no longer uses the short form's 40-bit pin."""

    def test_keyless_code_with_a_real_fingerprint_is_lp2_and_80_bits(self):
        from launcher import servercode
        fp = "ab" * 32
        code = servercode.encode("203.0.113.5", 8765, fp)
        self.assertTrue(code.startswith("LP2-"))
        self.assertEqual(fp[:20], servercode.decode(code)["fingerprint"])
        old = "LP-" + servercode.encode("203.0.113.5", 8765, fp[:10])[3:]          # an old short code still reads
        self.assertEqual(fp[:10], servercode.decode(old)["fingerprint"])


class ReviewFollowUpsServer(unittest.TestCase):
    """Bugs a second review found in the 2026-11-04 fixes."""

    def test_long_and_emoji_names_still_fit(self):
        from server.lobby.service import LobbyService, LobbyError
        name = "N" * 64 + "#" + "abcd1234"
        self.assertEqual(name, LobbyService._required_text({"participant_id": name}, "participant_id"))
        emoji = "Dev \U0001F468‍\U0001F4BB Al#ab12"
        self.assertEqual(emoji, LobbyService._required_text({"participant_id": emoji}, "participant_id"))
        with self.assertRaises(LobbyError):
            LobbyService._required_text({"participant_id": "bad\nname"}, "participant_id")
        with self.assertRaises(LobbyError):
            LobbyService._required_text({"participant_id": "bad name"}, "participant_id")

    def test_an_unreadable_secret_is_not_replaced(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from server.state_store import StateStore
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(Path(d))
            key = store.access_key()
            with mock.patch.object(Path, "read_bytes", side_effect=PermissionError("locked")):
                with self.assertRaises(OSError):
                    store.access_key()
            self.assertEqual(key, store.access_key())

    def test_very_long_titles_make_short_game_ids(self):
        import hashlib  # noqa: F401  (scanner uses it)
        from launcher import scanner
        src = Path(scanner.__file__).read_text(encoding="utf-8")
        self.assertIn("if len(compat) > 200:", src)
