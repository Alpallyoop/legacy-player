"""Relay: pipe bytes between a room's host and its guests so nobody learns anyone's address.

The host parks a few outbound connections here; each guest connection is paired with one
idle host connection and the two are copied byte for byte. What flows through is the
TLS-PSK tunnel the players already use. The match key is agreed between the players from the host's public key
(the lobby never holds a secret), so a server that only passes bytes along cannot read the game traffic.
Only authenticated room members can use a room's relay.
"""
from __future__ import annotations

import asyncio
import json
from collections import deque


class Relay:
    def __init__(self, service, max_parked: int = 8, max_streams: int = 256, idle_seconds: float = 600.0,
                 per_member: int = 2) -> None:
        self.service = service
        self.max_parked = max_parked
        self.max_streams = max_streams
        self.idle_seconds = idle_seconds
        self.per_member = per_member
        self.parked: dict[str, deque] = {}          # session id -> idle host (reader, writer, paired future)
        self.active = 0
        self.member_streams: dict[tuple[str, str], int] = {}
        self.member_pipes: dict[tuple[str, str], set] = {}   # (session, player) -> open pipes, as (writer, writer)
        self.punch_parked: dict[str, deque] = {}    # session id -> waiting host (endpoint, paired future)
        self.punch_wait_seconds = 120.0
        self.guest_wait_seconds = 10.0      # the client waits longer for this reply (lobby_client.open_relay)

    @staticmethod
    def _reply(writer: asyncio.StreamWriter, ok: bool, **payload) -> None:
        body = {"ok": ok, **({"result": payload} if ok else {"error": payload.get("error", "relay error")})}
        writer.write(json.dumps(body, separators=(",", ":")).encode() + b"\n")

    def _count(self, member: tuple[str, str], step: int) -> None:
        value = self.member_streams.get(member, 0) + step
        if value > 0:
            self.member_streams[member] = value
        else:
            self.member_streams.pop(member, None)

    def drop_member(self, sid: str, participant_id: str) -> None:
        """A player who was removed from the room (kicked, left, seat released) loses their relay pipes at once: both
        ends of every pipe they are in are closed. Their parked connections (a host is never removed) go too."""
        member = (sid, participant_id)
        for writers in list(self.member_pipes.pop(member, ())):
            for w in writers:
                _abort(w)
        queue = self.parked.get(sid)
        if queue and participant_id == getattr(self.service.sessions.get(sid), "host_id", None):
            self.drop_session(sid)

    def _still_member(self, sid: str, participant_id: str) -> bool:
        check = getattr(self.service, "relay_member_ok", None)
        return True if check is None else bool(check(sid, participant_id))

    async def handle(self, request: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Called by the lobby server after it read the first JSON line of a connection."""
        try:
            session, participant_id = self.service.relay_authorize(request)
        except Exception as exc:  # LobbyError: wrong room, wrong credential
            self._reply(writer, False, error=str(exc))
            await _drain(writer)
            return
        role = request.get("role")
        sid = session.session_id
        member = (sid, participant_id)
        if self.member_streams.get(member, 0) >= self.per_member or self.active >= self.max_streams:
            self._reply(writer, False, error="too many relay connections; close one first")
            await _drain(writer)
            return
        if role == "host":
            if participant_id != session.host_id:
                self._reply(writer, False, error="only the host parks relay connections")
                await _drain(writer)
                return
            queue = self.parked.setdefault(sid, deque())
            if len(queue) >= self.max_parked:
                self._reply(writer, False, error="enough host connections are parked already")
                await _drain(writer)
                return
            paired: asyncio.Future = asyncio.get_running_loop().create_future()
            queue.append((reader, writer, paired))
            self._reply(writer, True, parked=True)
            await _drain(writer)
            watcher = asyncio.ensure_future(self._watch_parked(reader, paired))
            guest = await paired   # (reader, writer, done, member) of the guest, or None
            watcher.cancel()
            if guest is None:
                return
            # The guest counted itself before it started waiting (see below); the host is counted from here.
            self._count(member, +1)
            pipe = (writer, guest[1])
            for m in (member, guest[3]):
                self.member_pipes.setdefault(m, set()).add(pipe)
            try:
                if self._still_member(sid, participant_id) and self._still_member(*guest[3]):
                    await self._pipe(reader, writer, guest[0], guest[1])
                else:                            # removed in the moment of pairing: no pipe
                    for w in pipe:
                        _abort(w)
            finally:
                self._count(member, -1)
                for m in (member, guest[3]):
                    pipes = self.member_pipes.get(m)
                    if pipes is not None:
                        pipes.discard(pipe)
                        if not pipes:
                            self.member_pipes.pop(m, None)
                if not guest[2].done():
                    guest[2].set_result(True)
            return
        if role == "guest":
            # Counted before waiting, so one guest can not open many connections at once and take every parked host
            # slot while none of them is counted yet. Released whatever happens.
            self._count(member, +1)
            try:
                await self._guest(reader, writer, sid, participant_id, member)
            finally:
                self._count(member, -1)
            return
        self._reply(writer, False, error="role must be host or guest")
        await _drain(writer)

    async def _guest(self, reader, writer, sid: str, participant_id: str, member: tuple[str, str]) -> None:
        # Right after the host publishes a match its relay connections are parked again (set_endpoint drops the
        # old ones), so a guest who arrives in that moment waits a little for one instead of failing.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.guest_wait_seconds
        while True:
            if not self._still_member(sid, participant_id):
                self._reply(writer, False, error="you are no longer in that room")
                await _drain(writer)
                return
            queue = self.parked.get(sid) or deque()
            found = None
            while queue:
                h_reader, h_writer, paired = queue.popleft()
                if not paired.done() and not h_writer.is_closing():
                    found = (h_reader, h_writer, paired)
                    break
            if found is not None:
                break
            if loop.time() >= deadline or reader.at_eof():
                self._reply(writer, False, error="the host's relay is not ready; ask them to launch first")
                await _drain(writer)
                return
            await asyncio.sleep(0.2)
        h_reader, h_writer, paired = found
        # No await from the check above to set_result: the host's watcher can not end the slot in between, and both
        # "paired" lines are in the buffers before the host's coroutine starts copying.
        self._reply(h_writer, True, paired=True)
        self._reply(writer, True, paired=True)
        done: asyncio.Future = loop.create_future()
        paired.set_result((reader, writer, done, member))
        await done   # the host-side coroutine runs the pipe and owns both writers

    async def handle_punch(self, request: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Hole punching used to introduce two players by telling each the other's address. It is switched off: no
        address is ever handed out (docs/canonical/SPEC.md, "Addresses"). Matches use the relay above."""
        self._reply(writer, False, error="direct connections are switched off on this server: matches go through the relay, "
                                         "which never shows anyone's address")
        await _drain(writer)

    async def _watch_parked(self, reader: asyncio.StreamReader, paired: asyncio.Future) -> None:
        """A parked host connection that hangs up (host crashed or relaunched) is dropped at once."""
        try:
            data = await reader.read(1)
        except (OSError, asyncio.CancelledError):
            return
        if not paired.done():
            paired.set_result(None)   # EOF or stray bytes: never hand this slot to a guest

    async def _pipe(self, a_r, a_w, b_r, b_w) -> None:
        self.active += 1
        try:
            await asyncio.gather(_copy(a_r, b_w, self.idle_seconds), _copy(b_r, a_w, self.idle_seconds))
        finally:
            self.active -= 1
            for w in (a_w, b_w):
                try:
                    w.close()
                except Exception:
                    pass

    def drop_session(self, sid: str) -> None:
        for _, paired in self.punch_parked.pop(sid, ()):
            if not paired.done():
                paired.set_result(None)
        for _, w, paired in self.parked.pop(sid, ()):
            if not paired.done():
                paired.set_result(None)
            w.close()


WRITE_TIMEOUT_SECONDS = 20.0     # a peer that stops reading for this long is cut off (it would pin the buffers)


def _abort(writer: asyncio.StreamWriter) -> None:
    """Close at once, dropping unsent bytes: close() alone waits for a peer that never reads."""
    try:
        writer.transport.abort()
    except Exception:
        try:
            writer.close()
        except Exception:
            pass


async def _drain(writer: asyncio.StreamWriter, timeout: float = WRITE_TIMEOUT_SECONDS) -> None:
    """drain() with a time limit; on time out (or a broken connection) the connection is aborted and an error raised."""
    try:
        await asyncio.wait_for(writer.drain(), timeout)
    except (asyncio.TimeoutError, TimeoutError):
        _abort(writer)
        raise ConnectionError("the other side stopped reading") from None


async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, idle_seconds: float = 600.0,
                first_seconds: float | None = None) -> None:
    """Copy until the reader ends. `first_seconds`: the first bytes must arrive that soon (a connection that pairs and then
    says nothing would otherwise hold its slot for the whole idle time)."""
    try:
        first = True
        while True:
            data = await asyncio.wait_for(reader.read(65536), first_seconds if first and first_seconds else idle_seconds)
            first = False
            if not data:
                break
            writer.write(data)
            await _drain(writer, min(idle_seconds, WRITE_TIMEOUT_SECONDS * 3))
    except (ConnectionError, asyncio.IncompleteReadError, OSError, TimeoutError):
        pass
    finally:
        try:
            if writer.can_write_eof():
                writer.write_eof()
        except (OSError, RuntimeError):
            pass
