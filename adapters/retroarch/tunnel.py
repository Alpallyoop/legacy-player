"""Encrypted tunnel for RetroArch netplay (TLS 1.2 with a pre-shared key).

RetroArch's netplay socket is plain TCP. This wraps it:

    guest RetroArch -> 127.0.0.1:L  [guest tunnel]  ==TLS-PSK==>  [host tunnel] :P -> host RetroArch 127.0.0.1:R

The host tunnel takes the public port the guests dial; RetroArch itself is started on a
different private port. The key is never sent anywhere: the host publishes only a public key
(X25519) through the lobby, each guest makes its own throw-away key pair, names itself with
its public half as the TLS-PSK identity and both sides derive the same secret from the two
halves. A lobby or relay that only passes bytes along therefore never learns the key. (A
server that actively swaps public keys could still sit in the middle; the key agreement
keeps a passive or logging operator out, which is what the consent text promises.)
The older shared-hex-key form (`new_key()`) still works for hosts and guests of earlier versions.
Needs Python 3.13+ (ssl PSK support); older Pythons report the tunnel as unavailable and the
launcher says so plainly.

Limit: RetroArch still listens on its own private port without a firewall rule of ours, so
keep that port closed at your router/firewall (Windows blocks it unless you allow RetroArch).
"""
from __future__ import annotations

import re
import secrets
import socket
import ssl
import sys
import threading
import time

from server.social import purecrypto as pc

IDENTITY = "legacy-player"
CIPHERS = "PSK-AES256-GCM-SHA384:PSK-CHACHA20-POLY1305:PSK-AES128-GCM-SHA256"


class TunnelUnavailable(RuntimeError):
    pass


def available() -> bool:
    return hasattr(ssl.SSLContext, "set_psk_server_callback") and hasattr(ssl.SSLContext, "set_psk_client_callback")


def new_key() -> str:
    return secrets.token_hex(32)


_KDF_SALT = b"legacy-player-tunnel-v1"


def _derive(shared: bytes, host_public: bytes, guest_public: bytes) -> bytes:
    return pc.hkdf(shared, _KDF_SALT, host_public + guest_public, 32)


class KeyAgreement:
    """Host side. Publish `public_hex`; each guest's identity (the hex of its own public key) yields that guest's secret."""

    def __init__(self) -> None:
        self._private, public = pc.x25519_keypair()
        self.public = public
        self.public_hex = public.hex()

    def secret_for(self, identity: str) -> bytes | None:
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
            return None
        try:
            guest = bytes.fromhex(identity)
            return _derive(pc.shared_secret(self._private, guest), self.public, guest)
        except ValueError:
            return None


def guest_credentials(host_public_hex: str) -> tuple[str, bytes]:
    """Guest side: (identity, secret) for one match, from the host's published public key."""
    if not isinstance(host_public_hex, str) or not re.fullmatch(r"[0-9a-f]{64}", host_public_hex):
        raise TunnelUnavailable("The host's match key is not valid; ask them to relaunch.")
    host = bytes.fromhex(host_public_hex)
    private, public = pc.x25519_keypair()
    try:
        return public.hex(), _derive(pc.shared_secret(private, host), host, public)
    except ValueError as exc:
        raise TunnelUnavailable("The host's match key is not valid; ask them to relaunch.") from exc


def _context(server: bool, key) -> ssl.SSLContext:
    """key: a hex string (the shared-key form), a KeyAgreement (host) or the (identity, secret) of guest_credentials (guest)."""
    if not available():
        raise TunnelUnavailable("Encrypted matches need Python 3.13 or newer (the Legacy Player app includes it).")
    if isinstance(key, KeyAgreement):
        agreement = key
        identity_for = lambda identity: agreement.secret_for(identity) or b"\x00" * 32       # an unknown guest fails the handshake
        client = None
    elif isinstance(key, tuple):
        identity_for, client = None, key
    else:
        secret = bytes.fromhex(key)
        identity_for = lambda identity: secret if identity == IDENTITY else b"\x00" * 32
        client = (IDENTITY, secret)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
    if not server:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    context.set_ciphers(CIPHERS)
    if server:
        context.set_psk_server_callback(identity_for)
    else:
        context.set_psk_client_callback(lambda hint: client)
    return context


class Meter:
    """Counts bytes and messages through the tunnel so the app can show speeds. Numbers only."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.rx = self.tx = self.msgs = 0
        self._last = (time.monotonic(), 0, 0, 0)

    def add(self, direction: str, size: int) -> None:
        with self._lock:
            if direction == "rx":
                self.rx += size
            else:
                self.tx += size
            self.msgs += 1

    def rates(self) -> dict:
        """Kilobits per second and messages per second since the previous call."""
        with self._lock:
            now = time.monotonic()
            t0, rx0, tx0, m0 = self._last
            span = max(now - t0, 0.001)
            out = {"rx_kbps": round((self.rx - rx0) * 8 / 1000 / span, 1),
                   "tx_kbps": round((self.tx - tx0) * 8 / 1000 / span, 1),
                   "updates_per_s": round((self.msgs - m0) / span, 1)}
            self._last = (now, self.rx, self.tx, self.msgs)
            return out


METER = Meter()


def _exclusive_bind_option(sock: socket.socket) -> None:
    """Windows' SO_REUSEADDR lets a second socket take a port that is already in use, so there the port is claimed
    exclusively instead; elsewhere SO_REUSEADDR only allows quick rebinding after a close, which is what we want."""
    if sys.platform == "win32":
        option = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if option is not None:
            sock.setsockopt(socket.SOL_SOCKET, option, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


def _close(sock) -> None:
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


class _Connections:
    """The live sockets of a tunnel, so stop() can cut every match that is still running. After a socket is wrapped
    in TLS the raw one is detached (closing it does nothing), so the wrapped socket is what gets tracked."""

    def _init_connections(self) -> None:
        self._conn_lock = threading.Lock()
        self.open_sockets: set = set()

    def _track(self, sock) -> None:
        with self._conn_lock:
            if not self.stopped.is_set():
                self.open_sockets.add(sock)
                return
        _close(sock)                                    # arrived after stop(): never left running

    def _swap(self, old, new) -> None:
        """`old` became `new` (wrapped in TLS)."""
        with self._conn_lock:
            self.open_sockets.discard(old)
        self._track(new)

    def _forget(self, *socks) -> None:
        with self._conn_lock:
            for s in socks:
                self.open_sockets.discard(s)
        for s in socks:
            _close(s)

    def _close_all(self) -> None:
        with self._conn_lock:
            socks = list(self.open_sockets)
            self.open_sockets.clear()
        for s in socks:
            _close(s)


def _pipe(a: socket.socket, b: socket.socket, direction: str = "") -> None:
    try:
        while data := a.recv(65536):
            if direction:
                METER.add(direction, len(data))
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _nodelay(*socks) -> None:
    for s in socks:
        s.settimeout(None)
        try:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (OSError, AttributeError):
            pass


class Tunnel(_Connections):
    """mode 'host': TLS in -> plain out to RetroArch. mode 'guest': plain in from RetroArch -> TLS out."""

    def __init__(self, mode: str, key, listen_host: str, listen_port: int, target_host: str, target_port: int,
                 dial=None) -> None:
        """dial: optional callable returning an already-connected socket to use instead of
        target_host:target_port (relay mode: the lobby server pairs it with the host)."""
        if mode not in {"host", "guest"}:
            raise ValueError("mode must be host or guest")
        self.mode, self.target, self.dial = mode, (target_host, target_port), dial
        self.context = _context(mode == "host", key)
        self.stopped = threading.Event()
        self._init_connections()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _exclusive_bind_option(self.listener)
        self.listener.bind((listen_host, listen_port))
        self.listener.listen(8)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._accept, daemon=True)

    def start(self) -> "Tunnel":
        self.thread.start()
        return self

    def stop(self) -> None:
        """Stop listening and cut every connection still running through the tunnel."""
        self.stopped.set()
        try:
            self.listener.close()
        except OSError:
            pass
        self._close_all()

    def _accept(self) -> None:
        while not self.stopped.is_set():
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        upstream = raw = None
        self._track(conn)
        try:
            conn.settimeout(10)
            if self.mode == "host":
                wrapped = self.context.wrap_socket(conn, server_side=True)  # bad key -> handshake fails -> dropped
                self._swap(conn, wrapped)
                conn = wrapped
                upstream = socket.create_connection(self.target, timeout=10)
                self._track(upstream)
            else:
                raw = self.dial() if self.dial else socket.create_connection(self.target, timeout=10)
                self._track(raw)
                upstream = self.context.wrap_socket(raw, server_hostname=None)
                self._swap(raw, upstream)
            if self.stopped.is_set():
                raise OSError("tunnel stopped")
            _nodelay(conn, upstream)
        except (OSError, ssl.SSLError, RuntimeError):
            self._forget(*(s for s in (conn, upstream, raw) if s is not None))
            return
        outward = "tx" if self.mode == "guest" else "rx"
        inward = "rx" if self.mode == "guest" else "tx"
        threading.Thread(target=_pipe, args=(conn, upstream, outward), daemon=True).start()
        _pipe(upstream, conn, inward)
        self._forget(conn, upstream)


def _wants_tracker(fn) -> bool:
    import inspect
    try:
        return len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        return False


class RelayHost(_Connections):
    """Host side of relay mode: keep a few connections parked at the lobby server; when the
    server pairs one with a guest, speak TLS-PSK over it and pipe to the local RetroArch."""

    def __init__(self, key, dial, local_host: str, local_port: int, slots: int = 4) -> None:
        self.context = _context(True, key)
        self.dial, self.local, self.slots = dial, (local_host, local_port), slots
        self.stopped = threading.Event()
        self.threads: list[threading.Thread] = []
        self.errors: list[str] = []
        self.served = 0
        self._init_connections()

    def start(self) -> "RelayHost":
        for _ in range(self.slots):
            t = threading.Thread(target=self._slot, daemon=True)
            t.start()
            self.threads.append(t)
        return self

    def stop(self) -> None:
        """Stop parking connections and cut every relayed match that is still running."""
        self.stopped.set()
        self._close_all()

    def _slot(self) -> None:
        while not self.stopped.is_set():
            try:
                raw = self.dial(self._track) if _wants_tracker(self.dial) else self.dial()
            except Exception as exc:         # relay refused / server gone: back off, try again
                if self.stopped.is_set():
                    return
                self.errors.append(str(exc)[:120])
                del self.errors[:-10]
                if self.stopped.wait(2.0):
                    return
                continue
            self._track(raw)                 # a dial that did not track it itself
            conn = upstream = None
            try:
                conn = self.context.wrap_socket(raw, server_side=True)
                self._swap(raw, conn)
                upstream = socket.create_connection(self.local, timeout=10)
                self._track(upstream)
                if self.stopped.is_set():
                    raise OSError("relay stopped")
                _nodelay(conn, upstream)
            except (OSError, ssl.SSLError):
                self._forget(*(s for s in (raw, conn, upstream) if s is not None))
                continue
            self.served += 1
            threading.Thread(target=_pipe, args=(conn, upstream, "rx"), daemon=True).start()
            _pipe(upstream, conn, "tx")
            self._forget(conn, upstream)
