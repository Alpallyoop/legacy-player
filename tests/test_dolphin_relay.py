"""Dolphin NetPlay through the relay: UDP datagrams travel inside the match's TLS-PSK stream, so no player learns
another's address. A UDP echo stands in for the host's Dolphin."""
import socket
import threading
import time
import unittest

from adapters.dolphin.udp_relay import UdpGuest, UdpHost
from adapters.retroarch import tunnel
from launcher.lobby_client import LobbyClient
from tests.test_community_lobby import PROFILE
from tests.test_launcher import ServerThread


def udp_echo():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))

    def run():
        while True:
            try:
                data, src = s.recvfrom(65535)
            except OSError:
                return
            s.sendto(b"echo:" + data, src)
    threading.Thread(target=run, daemon=True).start()
    return s


@unittest.skipUnless(tunnel.available(), "TLS-PSK needs Python 3.13+")
class DolphinRelayTests(unittest.TestCase):
    def setUp(self):
        self.server = ServerThread().start()
        self.addCleanup(self.server.stop)
        self.client = LobbyClient("127.0.0.1", self.server.port)
        created = self.client.call({"operation": "create", "participant_id": "host", "profile": PROFILE,
                                    "adapter_id": "dolphin", "game_pack_id": "generic", "max_players": 3})
        sid = created["session"]["session_id"]
        self.host_auth = {"session_id": sid, "participant_id": "host", "credential": created["credential"]}
        joined = self.client.call({"operation": "join", "invite_code": created["invite_code"], "participant_id": "g1",
                                   "profile": PROFILE})
        self.guest_auth = {"session_id": sid, "participant_id": "g1", "credential": joined["credential"]}
        self.dolphin = udp_echo()
        self.addCleanup(self.dolphin.close)

    def test_datagrams_reach_the_host_dolphin_and_come_back(self):
        key = tunnel.new_key()
        host = UdpHost(key, lambda: self.client.open_relay("host", self.host_auth, wait_paired=True),
                       self.dolphin.getsockname()[1], slots=2).start()
        self.addCleanup(host.stop)
        guest = UdpGuest(key, lambda: self.client.open_relay("guest", self.guest_auth, wait_paired=True)).start()
        self.addCleanup(guest.stop)
        time.sleep(0.3)
        me = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(me.close)
        me.settimeout(5)
        for i in range(30):
            me.sendto(b"enet-%02d" % i, ("127.0.0.1", guest.port))
            data, _ = me.recvfrom(2048)
            self.assertEqual(b"echo:enet-%02d" % i, data)
        big = bytes(range(256)) * 5
        me.sendto(big, ("127.0.0.1", guest.port))
        self.assertEqual(b"echo:" + big, me.recvfrom(4096)[0])
        self.assertEqual(1, host.served)

    def test_a_wrong_key_carries_nothing(self):
        host = UdpHost(tunnel.new_key(), lambda: self.client.open_relay("host", self.host_auth, wait_paired=True),
                       self.dolphin.getsockname()[1], slots=1).start()
        self.addCleanup(host.stop)
        guest = UdpGuest(tunnel.new_key(), lambda: self.client.open_relay("guest", self.guest_auth, wait_paired=True)).start()
        self.addCleanup(guest.stop)
        time.sleep(0.3)
        me = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(me.close)
        me.settimeout(1.5)
        me.sendto(b"hello", ("127.0.0.1", guest.port))
        with self.assertRaises(socket.timeout):
            me.recvfrom(2048)
