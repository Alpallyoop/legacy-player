"""Dolphin NetPlay through the room's relay, so players never learn each other's address.

Dolphin NetPlay talks UDP (ENet) straight from player to player; even its traversal server only introduces the players,
who then see each other's addresses. Here each player's Dolphin talks only to this computer:

    guest Dolphin -> UDP 127.0.0.1:L [UdpGuest] ==TLS-PSK over the relay==> [UdpHost] -> UDP 127.0.0.1:2626 host Dolphin

Datagrams travel inside the match's TLS-PSK stream, each with a 2-byte length in front. The relay (the server, and a
meeting point when there is one) only carries encrypted bytes and never hands out an address.
"""
from __future__ import annotations

import socket
import ssl
import struct
import threading

from adapters.retroarch.tunnel import METER, _close, _Connections, _context, _nodelay, _wants_tracker

MAX_DATAGRAM = 65507


def _send_frame(sock, data: bytes, lock: threading.Lock) -> None:
    with lock:
        sock.sendall(struct.pack(">H", len(data)) + data)


def _recv_exact(sock, n: int) -> bytes:
    out = bytearray()
    while len(out) < n:
        chunk = sock.recv(n - len(out))
        if not chunk:
            raise ConnectionError("stream closed")
        out += chunk
    return bytes(out)


def _recv_frame(sock) -> bytes:
    (size,) = struct.unpack(">H", _recv_exact(sock, 2))
    return _recv_exact(sock, size) if size else b""


def _stream_to_udp(stream, udp: socket.socket, where, direction: str) -> None:
    """Frames from the stream become datagrams to `where()` (a callable: the guest's Dolphin address can change)."""
    try:
        while True:
            data = _recv_frame(stream)
            target = where()
            if target is not None:
                udp.sendto(data, target)
                METER.add(direction, len(data))
    except (OSError, ConnectionError, ssl.SSLError):
        pass


class UdpHost(_Connections):
    """Host side: keeps relay connections parked; each paired one is a guest, given its own UDP socket towards the host's
    Dolphin on this computer, so Dolphin sees every guest as a separate player at 127.0.0.1."""

    def __init__(self, key: str, dial, dolphin_port: int, slots: int = 3) -> None:
        self.context = _context(True, key)
        self.dial, self.dolphin, self.slots = dial, ("127.0.0.1", int(dolphin_port)), slots
        self.stopped = threading.Event()
        self.errors: list[str] = []
        self.served = 0
        self._init_connections()

    def start(self) -> "UdpHost":
        for _ in range(self.slots):
            threading.Thread(target=self._slot, daemon=True).start()
        return self

    def stop(self) -> None:
        self.stopped.set()
        self._close_all()

    def _slot(self) -> None:
        while not self.stopped.is_set():
            try:
                raw = self.dial(self._track) if _wants_tracker(self.dial) else self.dial()
            except Exception as exc:
                if self.stopped.is_set():
                    return
                self.errors.append(str(exc)[:120])
                del self.errors[:-10]
                if self.stopped.wait(2.0):
                    return
                continue
            self._track(raw)
            stream = udp = None
            try:
                stream = self.context.wrap_socket(raw, server_side=True)
                self._swap(raw, stream)
                _nodelay(stream)
                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp.bind(("127.0.0.1", 0))
                self._track(udp)
            except (OSError, ssl.SSLError):
                self._forget(*(s for s in (raw, stream, udp) if s is not None))
                continue
            self.served += 1
            lock = threading.Lock()
            threading.Thread(target=_stream_to_udp, args=(stream, udp, lambda: self.dolphin, "rx"), daemon=True).start()
            try:
                while True:
                    data, src = udp.recvfrom(MAX_DATAGRAM)
                    if self.stopped.is_set():
                        break
                    if src != self.dolphin:
                        continue                    # only the host's own Dolphin may answer through this socket
                    _send_frame(stream, data, lock)
                    METER.add("tx", len(data))
            except (OSError, ssl.SSLError):
                pass
            self._forget(stream, udp)


class UdpGuest(_Connections):
    """Guest side: a UDP port on this computer for the guest's Dolphin ('Direct Connection' to 127.0.0.1 and `port`),
    carried through the relay to the host. The stream is opened on the first datagram and again if it drops."""

    def __init__(self, key: str, dial) -> None:
        self.context = _context(False, key)
        self.dial = dial
        self.stopped = threading.Event()
        self._init_connections()
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", 0))
        self.port = self.udp.getsockname()[1]
        self._track(self.udp)
        self.client = None                      # the guest's Dolphin, as it last sent from
        self.stream = None
        self.lock = threading.Lock()
        self.errors: list[str] = []

    def start(self) -> "UdpGuest":
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def stop(self) -> None:
        self.stopped.set()
        self._close_all()

    def _open(self):
        raw = self.dial(self._track) if _wants_tracker(self.dial) else self.dial()
        self._track(raw)
        try:
            stream = self.context.wrap_socket(raw, server_hostname=None)
        except (OSError, ssl.SSLError):
            self._forget(raw)
            raise
        self._swap(raw, stream)
        _nodelay(stream)
        threading.Thread(target=self._down, args=(stream,), daemon=True).start()
        return stream

    def _down(self, stream) -> None:
        _stream_to_udp(stream, self.udp, lambda: self.client, "rx")
        if self.stream is stream:
            self.stream = None
        self._forget(stream)

    def _run(self) -> None:
        while not self.stopped.is_set():
            try:
                data, src = self.udp.recvfrom(MAX_DATAGRAM)
            except OSError:
                return
            if self.stopped.is_set():
                return
            if not src or src[0] != "127.0.0.1":
                continue                            # only Dolphin on this computer
            self.client = src
            try:
                if self.stream is None:
                    self.stream = self._open()
                _send_frame(self.stream, data, self.lock)
                METER.add("tx", len(data))
            except Exception as exc:              # relay gone: drop this datagram; ENet resends, and the next one re-dials
                self.errors.append(str(exc)[:120])
                del self.errors[:-10]
                if self.stream is not None:
                    _close(self.stream)
                self.stream = None
                if self.stopped.wait(0.5):
                    return
