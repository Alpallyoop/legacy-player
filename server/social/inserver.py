"""The friends service, served by the multiplayer server itself.

A player who joins a friend's server with its server code already has an encrypted (TLS), certificate-pinned
connection that reaches it, through the same router, relay and fallback paths the game uses. So the game server also
answers friends requests on that same port: a request line {"operation": "friends", "friends": {"op": ..., ...}} is
handled here with the very same rules as the stand-alone service (server/social): end-to-end encrypted messages the
server can't read, rate limits, size limits, block lists and moderation. Its players are kept in their own folder
next to the server's other files (<server data>/social), never mixed with the stand-alone service's.

What the server code's key guards: making a new identity here ("hello") needs the server code's key, like browsing or
joining a room, so only people the host gave the code to can sign up. Everything after that is authenticated by the
player's own id and secret, so a fresh server code (the host rotated the key) does not cut off friends already here.

Moderation is for whoever runs the server, from that computer only: the admin channel (server/api/control.py,
loopback plus the server's admin token) passes "admin_friends" calls to `admin`.
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path

from server.http_guard import AddressWindow

from . import SocialError, SocialService

HELLO_PER_HOUR = 10                    # new identities per address per hour (this computer itself is not limited)
OPERATION = "friends"


class InServerFriends:
    def __init__(self, folder: Path | None, clock=time.time) -> None:
        self.service = SocialService(folder, clock)
        self.hello_limit = AddressWindow(HELLO_PER_HOUR, 3600.0)

    def handle(self, request: dict, lobby=None) -> dict:
        """One friends call. Raises SocialError (a message for the player) or PermissionError (the server code's key)."""
        from .__main__ import dispatch                     # the same operations, word for word, as the stand-alone service
        body = request.get("friends")
        if not isinstance(body, dict):
            raise SocialError("bad friends request")
        peer = request.get("_peer")
        if body.get("op") == "hello":
            self._check_key(request, lobby)
            if not self.hello_limit.allow(peer):
                raise SocialError("Too many new identities from this address; try again in an hour.")
        return dispatch(self.service, body)

    @staticmethod
    def _check_key(request: dict, lobby) -> None:
        key = getattr(lobby, "access_key", None)
        if not key:
            return
        throttle = getattr(lobby, "key_throttle", None)
        peer = request.get("_peer")
        if throttle is not None:
            wait = throttle.blocked(peer)
            if wait:
                from server.lobby.throttle import wait_text
                raise PermissionError(wait_text(wait))
        given = request.get("access_key")
        if not isinstance(given, str) or not secrets.compare_digest(given.encode("utf-8", "replace"), key.encode("utf-8", "replace")):
            if throttle is not None:
                throttle.fail(peer)
            raise PermissionError("This server code is out of date or not right. Ask the host for a fresh one.")

    # --- the server owner's moderation (admin channel only) ---------------------------------------------------------
    def admin(self, request: dict) -> dict:
        """what: reports (status) | players (q) | act (action, player, report, length, reason) | filter (on, words)."""
        what = str(request.get("what") or "reports")
        s = self.service
        if what == "reports":
            return s.admin_reports(str(request.get("status") or ""))
        if what == "players":
            return s.admin_players(str(request.get("q") or ""))
        if what == "act":
            return s.admin_act(str(request.get("action") or ""), str(request.get("player") or ""), str(request.get("report") or ""),
                               str(request.get("length") or ""), str(request.get("reason") or ""), by="server owner")
        if what == "filter":
            on = request.get("on")
            words = request.get("words")
            return s.admin_filter(None if on is None else bool(on), None if words is None else str(words))
        raise SocialError("unknown moderation call")

    def tidy(self) -> None:
        with self.service.lock:
            self.service._tidy()
            self.service._changed()

    def flush(self) -> None:
        self.service.flush()
