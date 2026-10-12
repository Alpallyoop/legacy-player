from __future__ import annotations

import asyncio
import secrets
import time


class ServerControl:
    """Local-only admin channel so stop/status work the same on Windows, Linux and a Pi."""

    def __init__(self, token: str, shutdown: asyncio.Event, service, store=None) -> None:
        self._token = token
        self.store = store
        self.shutdown = shutdown
        self.service = service
        self.started_at = time.time()
        self.friends = None               # the in-process friends service (server/social/inserver.py), when it started

    def is_admin_operation(self, operation) -> bool:
        return isinstance(operation, str) and operation.startswith("admin_")

    def handle(self, request: dict, *, peer_is_loopback: bool) -> dict:
        token = request.get("admin_token")
        if not peer_is_loopback:
            raise PermissionError("admin operations are only accepted from this machine")
        # bytes on both sides: compare_digest raises TypeError for a str with non-ASCII characters
        if not isinstance(token, str) or not secrets.compare_digest(token.encode("utf-8", "replace"),
                                                                    self._token.encode("utf-8", "replace")):
            raise PermissionError("invalid admin token")
        operation = request["operation"]
        if operation == "admin_status":
            sessions = self.service.sessions
            live = [s for s in sessions.values() if s.state.value not in {"completed", "failed"}]
            return {
                "running": True,
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "sessions_total": len(sessions),
                "sessions_live": len(live),
                "players_in_live_sessions": sum(len(s.participants) for s in live),
                "open_rooms": sum(1 for s in live if self.service.options.get(s.session_id, {}).get("open")),
                "waiting_total": sum(len(self.service._live_waiting(s.session_id)) for s in live),
                "limits": self.service.limits(),
            }
        if operation == "admin_shutdown":
            self.shutdown.set()
            return {"stopping": True}
        if operation == "admin_rotate_key":
            if self.store is None:
                raise PermissionError("this server cannot change its key")
            key = self.store.rotate_access_key()
            self.service.access_key = key
            return {"key": key}
        if operation == "admin_friends":
            # moderation of this server's friends list, by whoever runs the server, from this computer only
            if self.friends is None:
                raise PermissionError("friends are not available on this server")
            from server.social import SocialError
            try:
                return self.friends.admin(request)
            except SocialError as exc:
                raise PermissionError(str(exc)) from exc
        raise PermissionError(f"unsupported admin operation: {operation}")
