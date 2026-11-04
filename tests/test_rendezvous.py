"""The meeting point: friends reach a player's own server through it, and nobody learns anybody's address.

Real servers on real sockets: a meeting point (server.api.json_server with meeting_point=True) and a player's server
(with meet=...) that listens on loopback only and parks connections at the meeting point. A friend's LobbyClient
connects through the meeting point with nothing but an LP3- code."""
import asyncio
import json
import socket
import ssl
import tempfile
import threading
import time
import unittest
from pathlib import Path

from adapters.retroarch import tunnel
from launcher import servercode
from launcher.lobby_client import LobbyClient, LobbyClientError, bridge
from server import selfsigned
from server.api import json_server
from server.rendezvous import Rendezvous, token_for
from server.state_store import StateStore
from tests.test_community_lobby import PROFILE
from tests.test_relay import echo_server


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServeThread:
    """json_server.serve() in its own loop and thread."""

    def __init__(self, folder: Path, **kw):
        self.folder, self.kw = folder, kw
        self.cert, self.key, self.fp = selfsigned.ensure_certificate(folder / "state" / "tls")   # where `server.cli start` keeps it
        self.port = free_port()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(json_server.serve("127.0.0.1", self.port, self.folder / "replays",
                                                           state_dir=self.folder / "state", tls_cert=self.cert,
                                                           tls_key=self.key, **self.kw))
        except Exception:
            pass

    def start(self):
        self.thread.start()
        for _ in range(100):
            if (self.folder / "state" / "server_info.json").exists():
                break
            time.sleep(0.05)
        return self

    def admin(self, operation: str) -> dict:
        store = StateStore(self.folder / "state")
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        with ctx.wrap_socket(socket.create_connection(("127.0.0.1", self.port), timeout=5)) as s:
            s.sendall(json.dumps({"operation": operation, "admin_token": store.admin_token()}).encode() + b"\n")
            return json.loads(s.makefile("rb").readline())

    def stop(self):
        try:
            self.admin("admin_shutdown")
        except OSError:
            pass
        self.thread.join(10)


class MeetingPointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        json_server._PER_IP.clear()
        self.meet = ServeThread(self.tmp / "meet", meeting_point=True).start()
        self.addCleanup(self.meet.stop)
        self.meet_info = {"host": "127.0.0.1", "port": self.meet.port, "fingerprint": self.meet.fp}
        self.home = ServeThread(self.tmp / "home", meet=self.meet_info).start()
        self.addCleanup(self.home.stop)
        self.status = self._wait_parked()

    def _wait_parked(self) -> dict:
        for _ in range(100):
            out = self.home.admin("admin_meet_status")
            parked = (out.get("result") or {}).get("parked") or {}
            if parked.get("state") == "ready" and parked.get("slots_parked", 0) >= 1:
                return parked
            time.sleep(0.1)
        self.fail(f"the home server never parked at the meeting point: {out}")

    def code(self) -> str:
        key = StateStore(self.tmp / "home" / "state").access_key()
        return servercode.encode_meet(self.status["token"], self.home.fp, key, self.meet_info)

    def client(self, code: str | None = None) -> LobbyClient:
        found = servercode.decode(code or self.code())
        return LobbyClient("", 0, tls=True, fingerprint=found["fingerprint"], access_key=found["key"],
                           via={**found["meet"], "token": found["token"]})

    def test_the_code_holds_no_address_of_the_home_computer(self):
        code = self.code()
        found = servercode.decode(code)
        self.assertEqual({"token", "fingerprint", "key", "meet"}, set(found))
        self.assertEqual(self.meet_info["port"], found["meet"]["port"])      # only the meeting point's own address
        self.assertNotIn("host", found)
        self.assertNotEqual(self.home.port, found["meet"]["port"])

    def test_a_friend_creates_and_joins_a_room_through_the_meeting_point(self):
        friend = self.client()
        created = friend.call({"operation": "create", "participant_id": "host", "profile": PROFILE,
                               "adapter_id": "retroarch", "game_pack_id": "generic", "max_players": 3})
        joined = self.client().call({"operation": "join", "invite_code": created["invite_code"], "participant_id": "g1",
                                     "profile": PROFILE})
        self.assertIn("credential", joined)

    def test_a_wrong_token_and_a_wrong_server_key_are_refused(self):
        found = servercode.decode(self.code())
        bad = LobbyClient("", 0, tls=True, fingerprint=found["fingerprint"], access_key=found["key"],
                          via={**found["meet"], "token": "00" * 12})
        with self.assertRaisesRegex(LobbyClientError, "not reachable right now"):
            bad.call({"operation": "browse"})
        wrong_fp = LobbyClient("", 0, tls=True, fingerprint="ab" * 10, access_key=found["key"],
                               via={**found["meet"], "token": found["token"]})
        with self.assertRaisesRegex(LobbyClientError, "certificate does not match"):
            wrong_fp.call({"operation": "browse"})
        wrong_meet = LobbyClient("", 0, tls=True, fingerprint=found["fingerprint"], access_key=found["key"],
                                 via={**found["meet"], "fingerprint": "cd" * 10, "token": found["token"]})
        with self.assertRaisesRegex(LobbyClientError, "certificate does not match"):
            wrong_meet.call({"operation": "browse"})

    def test_admin_operations_are_refused_to_friends_who_came_through(self):
        token = StateStore(self.tmp / "home" / "state").admin_token()
        with self.assertRaisesRegex(LobbyClientError, "only accepted from this machine"):
            self.client().call({"operation": "admin_status", "admin_token": token})

    def test_a_fresh_code_stops_the_old_one_at_once(self):
        old = self.code()
        self.client(old).call({"operation": "browse"})
        held = self.client(old)._connect()                      # a friend already connected through the meeting point
        self.addCleanup(held.close)
        rotated = self.home.admin("admin_rotate_key")["result"]
        self.assertTrue(rotated["key"])
        now = self.home.admin("admin_meet_status")["result"]["parked"]
        self.assertNotEqual(self.status["token"], now["token"])  # swapped at once: the old token is never reported again
        held.sendall(b'{"operation":"status","session_id":"x","participant_id":"x","credential":"x"}\n')
        self.assertIn(b"unknown session", held.makefile("rb").readline())     # ...and that friend stays connected
        for _ in range(100):
            parked = (self.home.admin("admin_meet_status")["result"] or {}).get("parked") or {}
            if parked.get("token") and parked["token"] != self.status["token"] and parked.get("slots_parked", 0) >= 1:
                break
            time.sleep(0.1)
        self.assertNotEqual(self.status["token"], parked["token"])
        with self.assertRaises(LobbyClientError):
            self.client(old).call({"operation": "browse"})
        self.status = parked
        self.client().call({"operation": "browse"})

    @unittest.skipUnless(tunnel.available(), "TLS-PSK needs Python 3.13+")
    def test_a_match_runs_through_the_relay_inside_the_meeting_point(self):
        """Three layers: meeting point TLS, the home server's TLS, and the match's own TLS-PSK."""
        lobby = self.client()
        created = lobby.call({"operation": "create", "participant_id": "host", "profile": PROFILE,
                              "adapter_id": "retroarch", "game_pack_id": "generic", "max_players": 3})
        sid = created["session"]["session_id"]
        host_auth = {"session_id": sid, "participant_id": "host", "credential": created["credential"]}
        joined = lobby.call({"operation": "join", "invite_code": created["invite_code"], "participant_id": "g1",
                             "profile": PROFILE})
        guest_auth = {"session_id": sid, "participant_id": "g1", "credential": joined["credential"]}
        echo = echo_server()
        self.addCleanup(echo.close)
        key = tunnel.new_key()
        host = tunnel.RelayHost(key, lambda: lobby.open_relay("host", host_auth, wait_paired=True),
                                "127.0.0.1", echo.getsockname()[1], slots=1).start()
        self.addCleanup(host.stop)
        guest = tunnel.Tunnel("guest", key, "127.0.0.1", 0, "", 0,
                              dial=lambda: self.client().open_relay("guest", guest_auth, wait_paired=True)).start()
        self.addCleanup(guest.stop)
        time.sleep(0.5)
        with socket.create_connection(("127.0.0.1", guest.port), timeout=10) as s:
            for i in range(20):
                s.sendall(b"frame-%02d" % i)
                self.assertEqual(b"frame-%02d" % i, s.recv(64))

    def test_finished_calls_do_not_linger_at_the_meeting_point(self):
        """Each lobby call is one connection. When it ends, the meeting point must let go of both sides at once:
        before, each lingered until the host server's idle timeout and a busy friend hit the per-address limit."""
        for _ in range(20):
            self.client().call({"operation": "browse"})
        time.sleep(0.5)
        status = self.meet.admin("admin_meet_status")["result"]["meeting_point"]
        self.assertEqual(0, status["carrying"], status)

    def test_the_cli_prints_the_same_lp3_code(self):
        import argparse
        import contextlib
        import io
        from server import cli
        meet_code = servercode.encode("127.0.0.1", self.meet.port, self.meet.fp)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.code(argparse.Namespace(meet=meet_code, address=None, port=0, state_dir=self.tmp / "home" / "state"))
        self.assertEqual(0, rc)
        found = servercode.decode(out.getvalue().strip())
        self.assertEqual(self.status["token"], found["token"])
        self.assertNotIn("host", found)
        self.client(out.getvalue().strip()).call({"operation": "browse"})

    def test_the_home_server_listens_on_this_computer_only(self):
        info = json.loads((self.tmp / "home" / "state" / "server_info.json").read_text())
        self.assertEqual("127.0.0.1", info["host"])


class EncryptedRelayTests(unittest.TestCase):
    """Regression: a match relayed through an encrypted (TLS) server used to lose the server's encryption silently,
    because Python's ssl module takes the raw socket away from a TLS socket that is wrapped again."""

    @unittest.skipUnless(tunnel.available(), "TLS-PSK needs Python 3.13+")
    def test_relay_through_a_tls_server(self):
        tmp = Path(tempfile.mkdtemp())
        server = ServeThread(tmp / "srv").start()
        self.addCleanup(server.stop)
        key_hex = StateStore(tmp / "srv" / "state").access_key()
        c = LobbyClient("127.0.0.1", server.port, tls=True, fingerprint=server.fp, access_key=key_hex)
        created = c.call({"operation": "create", "participant_id": "host", "profile": PROFILE,
                          "adapter_id": "retroarch", "game_pack_id": "generic", "max_players": 3})
        sid = created["session"]["session_id"]
        ha = {"session_id": sid, "participant_id": "host", "credential": created["credential"]}
        j = c.call({"operation": "join", "invite_code": created["invite_code"], "participant_id": "g1", "profile": PROFILE})
        ga = {"session_id": sid, "participant_id": "g1", "credential": j["credential"]}
        echo = echo_server()
        self.addCleanup(echo.close)
        k = tunnel.new_key()
        h = tunnel.RelayHost(k, lambda: c.open_relay("host", ha, wait_paired=True), "127.0.0.1", echo.getsockname()[1],
                             slots=1).start()
        self.addCleanup(h.stop)
        g = tunnel.Tunnel("guest", k, "127.0.0.1", 0, "", 0, dial=lambda: c.open_relay("guest", ga, wait_paired=True)).start()
        self.addCleanup(g.stop)
        time.sleep(0.4)
        with socket.create_connection(("127.0.0.1", g.port), timeout=10) as s:
            s.sendall(b"hello")
            self.assertEqual(b"hello", s.recv(64))

    def test_bridge_leaves_a_plain_socket_alone(self):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        self.assertIs(a, bridge(a))


class ReviewFindingTests(unittest.TestCase):
    def test_friends_through_a_meeting_point_share_one_throttle_bucket(self):
        from server.lobby.throttle import FORWARDED, key_for
        self.assertEqual(FORWARDED, key_for(FORWARDED))
        self.assertIsNone(key_for("127.0.0.1"))

    def test_a_meeting_point_connection_needs_both_pins_and_keeps_time_limits(self):
        with self.assertRaises(LobbyClientError):
            LobbyClient("", 0, fingerprint="", via={"host": "h", "port": 1, "fingerprint": "ab" * 10, "token": "cd" * 12})

    def test_an_old_direct_endpoint_does_not_survive_a_restart(self):
        from server.lobby.service import LobbyService
        svc = LobbyService()
        made = svc.dispatch({"operation": "create", "participant_id": "host", "profile": PROFILE, "adapter_id": "retroarch",
                             "game_pack_id": "generic"})
        sid = made["session"]["session_id"]
        state = svc.export_state()
        state["options"][sid]["endpoint"] = {"kind": "direct", "address": "192.0.2.7", "port": 55435}
        again = LobbyService()
        again.import_state(state)
        self.assertNotIn("192.0.2.7", repr(again.export_state()))


class TokenTests(unittest.TestCase):
    def test_only_the_secret_holder_can_park(self):
        r = Rendezvous()

        class W:
            def __init__(self):
                self.out = b""

            def write(self, data):
                self.out += data

            async def drain(self):
                pass

            def is_closing(self):
                return False
        w = W()
        secret = "11" * 32
        asyncio.run(r.handle({"operation": "rv_park", "secret": "22" * 32, "token": token_for(secret)}, None, w))
        self.assertIn(b"does not belong", w.out)
        self.assertEqual({}, r.parked)
