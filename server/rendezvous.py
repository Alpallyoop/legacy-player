"""Meeting point (rendezvous): lets friends reach a player's own server without anyone learning its address.

A player's server keeps a few connections parked here, made outward from their computer, under a token. A friend's app
connects here, names the token (it is inside the server code), and is paired with one parked connection; from then on
this process copies bytes both ways. What flows through is the TLS connection between the friend's app and the player's
server (pinned to that server's certificate), so this process cannot read it.

Who sees which address:
- the player's server and the friend's app never see each other's address (each only talks to this meeting point);
- the person who runs the meeting point sees the addresses that connect to it, as with any server. It keeps no record of
  them: nothing here logs or stores an address.

The token is derived from a secret only the player's server holds (`token_for`), so nobody else can park under it, and a
fresh code (a new secret) makes every older code stop working at once.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
import time
from collections import deque

import ipaddress

from server.relay import _copy, _drain

TOKEN_BYTES = 12
_HEX = re.compile(r"[0-9a-f]+")


def new_secret() -> str:
    return secrets.token_hex(32)


def token_for(secret_hex: str) -> str:
    """The public token for a server's secret: what goes into the server code."""
    return hashlib.sha256(b"legacy-player-meeting-point:" + bytes.fromhex(secret_hex)).digest()[:TOKEN_BYTES].hex()


def prefix_for(peer) -> str | None:
    """The network a parked connection is counted against: an IPv4 /24 or an IPv6 /48 (what one customer or one
    small hosting account usually holds). None for this computer or an unknown peer (not counted)."""
    try:
        ip = ipaddress.ip_address(str(peer or ""))
    except ValueError:
        return None
    mapped = getattr(ip, "ipv4_mapped", None)
    ip = mapped or ip
    if ip.is_loopback:
        return None
    bits = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{bits}", strict=False))


def _clean(value, size: int) -> str:
    text = value if isinstance(value, str) else ""
    text = text.strip().lower()
    return text if len(text) == size * 2 and _HEX.fullmatch(text) else ""


class Rendezvous:
    def __init__(self, max_tokens: int = 2000, max_parked: int = 6, max_streams: int = 512, max_parked_total: int = 2000,
                 idle_seconds: float = 600.0, park_seconds: float = 240.0, go_seconds: float = 10.0,
                 max_parked_per_prefix: int = 64) -> None:
        self.max_tokens = max_tokens
        self.max_parked = max_parked
        self.max_streams = max_streams
        self.max_parked_total = max_parked_total    # with max_streams, keeps the open connections well under common limits
        self.idle_seconds = idle_seconds
        self.park_seconds = park_seconds          # a parked connection is ended after this; the server parks a new one
        self.go_seconds = go_seconds
        self.parked: dict[str, deque] = {}        # token -> idle server connections (reader, writer, paired future)
        # Idle parked connections per network (prefix_for): one network (a few IPv6 /56s inside one /48) can not take
        # all max_parked_total places. 64 is 16 servers parking 4 each. Counts only, never kept past the connection.
        self.max_parked_per_prefix = max_parked_per_prefix
        self.parked_per_prefix: dict[str, int] = {}
        self.active = 0
        self.paired_total = 0

    @staticmethod
    def _reply(writer: asyncio.StreamWriter, ok: bool, **payload) -> None:
        body = {"ok": ok, **({"result": payload} if ok else {"error": payload.get("error", "meeting point error")})}
        writer.write(json.dumps(body, separators=(",", ":")).encode() + b"\n")

    def status(self) -> dict:
        """Counts only: how many servers are waiting and how many connections are being carried."""
        return {"servers": sum(1 for q in self.parked.values() if q), "parked": sum(len(q) for q in self.parked.values()),
                "carrying": self.active, "paired_total": self.paired_total}

    async def handle(self, request: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Called by the server for a connection whose first line is rv_park or rv_join."""
        operation = request.get("operation")
        if operation == "rv_park":
            await self._park(request, reader, writer)
        elif operation == "rv_join":
            await self._join(request, reader, writer)
        else:
            self._reply(writer, False, error="unknown meeting point operation")
            await _drain(writer)

    async def _park(self, request: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        secret = _clean(request.get("secret"), 32)
        token = _clean(request.get("token"), TOKEN_BYTES)
        if not secret or not token or not secrets.compare_digest(token_for(secret), token):
            self._reply(writer, False, error="that token does not belong to this server")
            await _drain(writer)
            return
        queue = self.parked.get(token)
        if queue is None:
            if len(self.parked) >= self.max_tokens:
                self._tidy()
                if len(self.parked) >= self.max_tokens:
                    self._reply(writer, False, error="the meeting point is full; try again later")
                    await _drain(writer)
                    return
            queue = self.parked[token] = deque()
        live = [item for item in queue if not item[2].done() and not item[1].is_closing()]
        queue.clear()
        queue.extend(live)
        if sum(len(q) for q in self.parked.values()) >= self.max_parked_total:
            self._reply(writer, False, error="the meeting point is full; try again later")
            await _drain(writer)
            return
        if len(queue) >= self.max_parked:
            self._reply(writer, False, error="enough connections are parked for this server already")
            await _drain(writer)
            return
        where = prefix_for(request.get("_peer"))
        if where is not None and self.parked_per_prefix.get(where, 0) >= self.max_parked_per_prefix:
            if not queue:
                self.parked.pop(token, None)
            self._reply(writer, False, error="too many connections are parked from your network; try again later")
            await _drain(writer)
            return
        paired: asyncio.Future = asyncio.get_running_loop().create_future()
        queue.append((reader, writer, paired))
        if where is not None:
            self.parked_per_prefix[where] = self.parked_per_prefix.get(where, 0) + 1
        watcher = None
        try:
            self._reply(writer, True, parked=True, park_seconds=int(self.park_seconds))
            await _drain(writer)
            watcher = asyncio.ensure_future(self._watch(reader, paired))
            try:
                guest = await asyncio.wait_for(asyncio.shield(paired), self.park_seconds)
            except (asyncio.TimeoutError, TimeoutError):
                # a friend may have been paired in the same moment the park ran out: then serve them, never strand them
                guest = paired.result() if paired.done() and not paired.cancelled() else None
        except BaseException:
            if not paired.done():
                paired.set_result(None)
            self._drop(token, paired)
            raise
        finally:
            if where is not None:                # no longer idle: paired (then counted by max_streams) or gone
                left = self.parked_per_prefix.get(where, 1) - 1
                if left > 0:
                    self.parked_per_prefix[where] = left
                else:
                    self.parked_per_prefix.pop(where, None)
            if watcher is not None:
                watcher.cancel()
                try:
                    await watcher               # it must be gone before this coroutine reads from the connection again
                except BaseException:
                    pass
        if guest is None:
            if not paired.done():
                paired.set_result(None)
            self._drop(token, paired)
            return
        g_reader, g_writer, done = guest
        try:
            self._reply(writer, True, paired=True)
            await _drain(writer)
            line = await asyncio.wait_for(reader.readline(), self.go_seconds)    # the server is ready to speak TLS
            if json.loads(line or b"{}").get("go") is not True:
                raise ValueError("no go")
            self._reply(g_writer, True, paired=True)
            await _drain(g_writer)
        except Exception:
            self._reply(g_writer, False, error="the host's server did not take the connection; try again")
            try:
                await _drain(g_writer)
            except Exception:
                pass
            if not done.done():
                done.set_result(False)
            return
        self.active += 1
        self.paired_total += 1
        try:
            # When either side ends, both end. TLS can not pass on a half-close, so waiting for the other direction
            # would keep every finished lobby call open until the far server's idle timeout (and hold a per-address
            # slot here all that time).
            tasks = [asyncio.ensure_future(_copy(reader, g_writer, self.idle_seconds)),
                     asyncio.ensure_future(_copy(g_reader, writer, self.idle_seconds, first_seconds=self.go_seconds))]       # a guest must start speaking TLS at once
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in pending:
                try:
                    await task
                except BaseException:
                    pass
        finally:
            self.active -= 1
            for w in (writer, g_writer):
                try:
                    w.close()
                except Exception:
                    pass
            if not done.done():
                done.set_result(True)

    async def _join(self, request: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        token = _clean(request.get("token"), TOKEN_BYTES)
        if self.active >= self.max_streams:
            self._reply(writer, False, error="the meeting point is busy; try again in a moment")
            await _drain(writer)
            return
        queue = self.parked.get(token) if token else None
        while queue:
            h_reader, h_writer, paired = queue.popleft()
            if not paired.done() and not h_writer.is_closing():
                break
        else:
            self._reply(writer, False, error="The host's server is not reachable right now: it may be off, or this code "
                                             "may be an old one. Ask the host to start their server or send a fresh code.")
            await _drain(writer)
            return
        done: asyncio.Future = asyncio.get_running_loop().create_future()
        paired.set_result((reader, writer, done))
        await done                              # the server-side coroutine runs the copy and owns both writers

    async def _watch(self, reader: asyncio.StreamReader, paired: asyncio.Future) -> None:
        """A parked connection that hangs up (server stopped) is dropped at once."""
        try:
            await reader.read(1)
        except (OSError, asyncio.CancelledError):
            return
        if not paired.done():
            paired.set_result(None)

    def _drop(self, token: str, paired: asyncio.Future) -> None:
        queue = self.parked.get(token)
        if queue is None:
            return
        live = [item for item in queue if item[2] is not paired and not item[2].done()]
        if live:
            self.parked[token] = deque(live)
        else:
            self.parked.pop(token, None)

    def _tidy(self) -> None:
        for token in [t for t, q in self.parked.items() if not any(not item[2].done() for item in q)]:
            self.parked.pop(token, None)

    def drop_all(self) -> None:
        for queue in list(self.parked.values()):
            for _, writer, paired in list(queue):
                if not paired.done():
                    paired.set_result(None)
                try:
                    writer.close()
                except Exception:
                    pass
        self.parked.clear()


# ----------------------------------------------------------------------------------------------------------------
# The other side: a player's own server parking connections at a meeting point (runs inside that server's process).

class Parker:
    """Keeps `slots` connections parked at a meeting point and hands every paired one to `serve(reader, writer)` as if
    a friend had connected straight to this server, after this server's own TLS handshake inside the pairing.
    State is kept in `self.state` for the server's info file: words, never an address."""

    def __init__(self, meet: dict, secret_hex: str, server_ssl, serve, slots: int = 4, limit: int = 2 ** 17) -> None:
        self.meet = meet                         # {"host", "port", "fingerprint"} of the meeting point
        self.secret = secret_hex
        self.token = token_for(secret_hex)
        self.server_ssl = server_ssl
        self.serve = serve
        self.slots = slots
        self.limit = limit
        self.state = {"state": "starting", "message": "Connecting to the meeting point.", "since": time.time()}
        self.parked = 0
        self.served = 0
        self._tasks: list[asyncio.Task] = []
        self._carrying: set[asyncio.Task] = set()
        self._stop = asyncio.Event()

    def start(self) -> None:
        self._tasks = [asyncio.ensure_future(self._slot(i)) for i in range(self.slots)]

    def stop_parking(self) -> None:
        """Stop parking (the parked connections close, so this token stops working). Connections already carried for
        friends keep running."""
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        self.state = {"state": "retired", "message": "Replaced by a fresh code.", "since": time.time()}

    async def stop(self) -> None:
        self._stop.set()
        tasks = self._tasks + list(self._carrying)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except BaseException:
                pass

    def _set(self, state: str, message: str) -> None:
        if self.state.get("state") != state or self.state.get("message") != message:
            self.state = {"state": state, "message": message, "since": time.time()}

    async def _open(self):
        import ssl
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE          # pinned below to the meeting point's certificate
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.meet["host"], int(self.meet["port"]), ssl=context, server_hostname=self.meet["host"],
                                    limit=self.limit), 15)
        der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
        want = re.sub(r"[^0-9a-f]", "", str(self.meet.get("fingerprint", "")).lower())
        if len(want) < 10 or not hashlib.sha256(der).hexdigest().startswith(want):
            writer.close()
            raise PermissionError("the meeting point's certificate does not match its code")
        return reader, writer

    async def _carry(self, outer_reader, outer_writer, reader, writer) -> None:
        try:
            await self.serve(reader, writer)
        finally:
            try:
                outer_writer.close()
            except Exception:
                pass
            del outer_reader

    async def _slot(self, index: int) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            writer = None
            try:
                reader, writer = await self._open()
                writer.write(json.dumps({"operation": "rv_park", "token": self.token, "secret": self.secret}).encode() + b"\n")
                await _drain(writer)
                first = json.loads(await asyncio.wait_for(reader.readline(), 15) or b"{}")
                if not first.get("ok"):
                    raise PermissionError(str(first.get("error") or "the meeting point refused"))
                self.parked += 1
                self._set("ready", "Friends can reach this server through the meeting point.")
                backoff = 1.0
                try:
                    line = await reader.readline()     # waits until a friend is paired, or the meeting point ends the park
                finally:
                    self.parked -= 1
                reply = json.loads(line or b"{}")
                if not (reply.get("ok") and (reply.get("result") or {}).get("paired")):
                    writer.close()
                    continue                                       # park ended or server going: park again
                loop = asyncio.get_running_loop()
                writer.write(b'{"go":true}\n')
                inner_reader = asyncio.StreamReader(limit=self.limit)
                protocol = asyncio.StreamReaderProtocol(inner_reader)
                # No await between the write above and start_tls: the friend's handshake can only arrive after "go".
                transport = await asyncio.wait_for(
                    loop.start_tls(writer.transport, protocol, self.server_ssl, server_side=True), 15)
                protocol.connection_made(transport)
                inner_writer = asyncio.StreamWriter(transport, protocol, inner_reader, loop)
                self.served += 1
                # The outer stream objects must live as long as the friend's connection: a StreamWriter that is
                # garbage-collected closes its transport, which is the one the friend's TLS runs inside.
                carry = asyncio.ensure_future(self._carry(reader, writer, inner_reader, inner_writer))
                self._carrying.add(carry)
                carry.add_done_callback(self._carrying.discard)
                writer = None
            except asyncio.CancelledError:
                if writer is not None:
                    writer.close()
                raise
            except PermissionError as exc:
                self._set("refused", f"The meeting point refused this server ({exc}).")
                backoff = min(backoff * 2, 300.0)
            except Exception as exc:
                if writer is not None:
                    try:
                        writer.close()
                    except Exception:
                        pass
                self._set("unreachable", f"The meeting point can't be reached right now ({type(exc).__name__}); trying again.")
                backoff = min(backoff * 2, 60.0)
            else:
                continue
            try:
                await asyncio.wait_for(self._stop.wait(), backoff)
            except (asyncio.TimeoutError, TimeoutError):
                pass
