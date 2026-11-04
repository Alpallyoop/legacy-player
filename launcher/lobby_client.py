"""Tiny synchronous client for the Legacy Player coordination server."""
from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl
import threading
import time

MAX_ANSWER_BYTES = 8 * 1024 * 1024
MIN_PIN_HEX = 10            # 40 bits: the least any pin may be (short LP- codes made without a server key carry only this)
MIN_INNER_PIN_HEX = 20      # 80 bits: a player's own server reached through a meeting point (LP3- codes always carry 80)


class LobbyClientError(RuntimeError):
    pass


def _read_line(sock: socket.socket, limit: int = 4096) -> bytes:
    out = bytearray()
    while len(out) < limit:
        ch = sock.recv(1)
        if not ch:
            break
        out += ch
        if ch == b"\n":
            break
    return bytes(out)


def bridge(sock: socket.socket) -> socket.socket:
    """A plain socket that carries `sock`'s stream. Wrapping TLS straight onto a TLS socket does not work in Python: the
    ssl module takes the raw socket away from the outer layer and the outer encryption is silently lost. So a socket
    pair is put in between and two threads copy bytes; the caller can then speak TLS (or anything) over the plain end.
    A plain socket is returned as it is."""
    if not isinstance(sock, ssl.SSLSocket):
        return sock
    mine, theirs = socket.socketpair()
    sock.settimeout(None)

    def pump(a, b) -> None:
        try:
            while data := a.recv(65536):
                b.sendall(data)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def run() -> None:
        other = threading.Thread(target=pump, args=(theirs, sock), daemon=True)
        other.start()
        pump(sock, theirs)
        other.join(5)
        for s in (theirs, sock):
            try:
                s.close()
            except OSError:
                pass
    threading.Thread(target=run, daemon=True).start()
    return mine


class LobbyClient:
    def __init__(self, host: str, port: int, *, tls: bool = False, verify: bool = True, timeout: float = 5.0,
                 fingerprint: str = "", access_key: str = "", via: dict | None = None) -> None:
        self.access_key = re.sub(r"[^0-9a-f]", "", access_key.lower())
        self.host, self.port, self.tls, self.verify, self.timeout = host, port, tls, verify, timeout
        # A pinned SHA-256 of the server certificate (what the in-app server shows its owner).
        self.fingerprint = re.sub(r"[^0-9a-f]", "", fingerprint.lower())
        # A server reached through a meeting point (rendezvous): {"host", "port", "fingerprint", "token"}. The host's
        # server keeps connections parked there; this client connects to the meeting point, names the token, and then
        # speaks TLS to the host's server through it, end to end. Neither side ever learns the other's address.
        self.via = dict(via) if via else None
        if self.via is not None:
            self.via["fingerprint"] = re.sub(r"[^0-9a-f]", "", str(self.via.get("fingerprint", "")).lower())
            self.via["token"] = re.sub(r"[^0-9a-f]", "", str(self.via.get("token", "")).lower())
            if len(self.via["fingerprint"]) < MIN_PIN_HEX or len(self.via["token"]) < 16:
                raise LobbyClientError("That server code is not complete.")      # both servers are always pinned
            if len(self.fingerprint) < MIN_INNER_PIN_HEX:
                # The host's server is what really has to be the right one (the meeting point only carries its TLS),
                # and 40 bits of a certificate fingerprint can be matched by a forged certificate with enough tries.
                raise LobbyClientError("That server code is from an older Legacy Player and is not safe enough to use. "
                                       "Ask the host for a fresh code.")
            self.tls = True                                  # the host's server is always reached over TLS this way

    def _where(self) -> str:
        """How a server is named in messages shown to the player. A friend's address is never printed:
        it ends up in screenshots, toasts and bug reports."""
        if self.via is not None:
            return "the host's server (through the meeting point)"
        return "this computer's server" if self.host in {"127.0.0.1", "localhost", "::1"} else "the server"

    @staticmethod
    def _pinned(sock: socket.socket, host: str, fingerprint: str, verify: bool = True) -> socket.socket:
        context = ssl.create_default_context()
        if fingerprint or not verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE   # pinning below replaces CA verification
        sock = context.wrap_socket(sock, server_hostname=host)
        if fingerprint:
            seen = hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
            if not seen.startswith(fingerprint) or len(fingerprint) < MIN_PIN_HEX:
                sock.close()
                raise LobbyClientError(
                    "The server's certificate does not match the fingerprint you entered. "
                    "Ask the host for the fingerprint shown in their app, or someone may be in the middle.")
        return sock

    def _raw(self) -> socket.socket:
        """A connection that reaches the server's own port: straight, or through the meeting point."""
        if self.via is None:
            return socket.create_connection((self.host, self.port), timeout=self.timeout)
        v = self.via
        for attempt in range(4):
            sock = socket.create_connection((v["host"], int(v["port"])), timeout=self.timeout)
            try:
                sock = self._pinned(sock, v["host"], v["fingerprint"])
                sock.sendall(json.dumps({"operation": "rv_join", "token": v["token"]}).encode() + b"\n")
                first = json.loads(_read_line(sock) or b"{}")
                if not first.get("ok"):
                    raise LobbyClientError(first.get("error") or "The meeting point did not let this connection through.")
                break
            except LobbyClientError as exc:
                sock.close()
                # every parked connection of the host may be busy for a moment (it parks a new one at once): try again
                if attempt == 3 or "not reachable right now" not in str(exc):
                    raise
                time.sleep(0.4)
            except BaseException:
                sock.close()
                raise
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)      # a host that vanished is noticed
        except OSError:
            pass
        plain = bridge(sock)
        plain.settimeout(self.timeout)                  # the same time limits as a straight connection
        return plain

    def _connect(self) -> socket.socket:
        sock = self._raw()
        try:
            return self._secure(sock)
        except BaseException:
            sock.close()
            raise

    def _secure(self, sock: socket.socket) -> socket.socket:
        if self.tls:
            sock = self._pinned(sock, self.host or "legacy-player", self.fingerprint, self.verify)
        return sock

    def open_relay(self, role: str, auth: dict, *, wait_paired: bool, on_socket=None) -> socket.socket:
        """Open a relay connection through the lobby server. Returns the raw socket once the
        server has parked it (host) or paired it (guest); the caller then speaks TLS-PSK over it."""
        try:
            sock = self._connect()
            if on_socket is not None:
                on_socket(sock)
            sock.sendall(json.dumps({"operation": "relay", "role": role, **auth}).encode() + b"\n")
            if role == "guest":
                sock.settimeout(max(self.timeout, 15.0))   # the relay may wait up to 10 s for the host's next slot
            # Read exactly one line at a time, unbuffered: the bytes right after the last
            # line are the other player's TLS handshake and must stay in the socket.
            first = json.loads(_read_line(sock) or b"{}")
            if not first.get("ok"):
                sock.close()
                raise LobbyClientError(first.get("error", "relay refused"))
            if wait_paired and not first["result"].get("paired"):
                sock.settimeout(None)
                second = json.loads(_read_line(sock) or b"{}")
                if not second.get("ok") or not second["result"].get("paired"):
                    sock.close()
                    raise LobbyClientError("relay connection ended before a player arrived")
            sock.settimeout(None)
            plain = bridge(sock)
            plain.settimeout(None)                      # a relay pipe waits for the match as long as it takes
            return plain            # the match speaks its own TLS over this, so an encrypted server needs a bridge
        except (OSError, ssl.SSLError, ValueError) as exc:
            raise LobbyClientError(f"Could not open a relay through {self._where()} ({exc}).") from exc

    def call(self, request: dict) -> dict:
        if self.access_key and "access_key" not in request:
            request = {**request, "access_key": self.access_key}
        try:
            sock = self._connect()
            with sock:
                sock.sendall(json.dumps(request).encode() + b"\n")
                line = sock.makefile("rb").readline(MAX_ANSWER_BYTES)     # bounded: a wrong server cannot fill memory
        except (OSError, ssl.SSLError) as exc:
            raise LobbyClientError(
                f"Could not reach the multiplayer server at {self._where()} ({exc}). "
                "The server may not be running, or a firewall or router is blocking it (ask the host to check Windows Firewall and their router), or the server code is out of date."
            ) from exc
        try:
            response = json.loads(line)
        except ValueError as exc:
            raise LobbyClientError(f"Something answered at {self._where()} but it is not a Legacy Player server.") from exc
        if not response.get("ok"):
            raise LobbyClientError(response.get("error", "server error"))
        return response["result"]
