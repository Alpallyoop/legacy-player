"""Friends in the background: the check-in that keeps a player online for their friends, and the notices for what is new.

The friends service marks a player offline when their app has not checked in for 75 seconds. The Friends page checks
in while it is open, but a player who closed the window (Legacy Player keeps running in the tray) or is on another page
should still show as online and still hear about a new message. So a small thread checks in every 30 seconds while
friends are in use, and stops when the app closes.

`FriendsNotices` decides what is new since the last look (a friend request, an invite to play, a message), so each one
is announced once, even across restarts: the keys of what was already announced are kept, per friends service, in the
catalog (ids and times only, never names or words)."""
from __future__ import annotations

import threading

INTERVAL = 30.0
KEEP = 300                       # announced keys remembered per service


class FriendsPulse:
    """Calls `beat()` now and then every `interval` seconds until stopped. `beat` decides itself whether there is
    anything to do (friends not in use: it returns at once without touching the network)."""

    def __init__(self, beat, interval: float = INTERVAL) -> None:
        self.beat, self.interval = beat, interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.beats = 0

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        with self._lock:
            if self.running():
                return False
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self._run, args=(self._stop,), daemon=True, name="friends-pulse")
            self._thread.start()
            return True

    def stop(self, wait: float = 2.0) -> None:
        with self._lock:
            self._stop.set()
            thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(wait)

    def _run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.beat()
            except Exception:
                pass                      # offline, server stopped, a hiccup: try again next time, quietly
            self.beats += 1
            if stop.wait(self.interval):
                return


class FriendsNotices:
    """What is new in an inbox, each thing once."""

    def __init__(self, catalog) -> None:
        self.catalog = catalog
        self._lock = threading.Lock()

    def _store(self) -> dict:
        seen = self.catalog.data.setdefault("friends_announced", {})
        if not isinstance(seen, dict):
            seen = self.catalog.data["friends_announced"] = {}
        return seen

    def news(self, service: str, inbox: dict | None) -> list[dict]:
        """[{kind, title, text}] for what was not announced yet. kind: request | invite | message."""
        if not isinstance(inbox, dict) or not service:
            return []
        me = (inbox.get("me") or {}).get("id", "")
        current: list[tuple[str, dict]] = []
        for r in inbox.get("requests") or []:
            current.append((f"r:{r.get('id')}", {"kind": "request", "title": "Friend request",
                                                  "text": f"{r.get('name') or 'Someone'} wants to be your friend."}))
        for i in inbox.get("invites") or []:
            game = i.get("game") or "a game"
            current.append((f"i:{i.get('from')}:{i.get('at')}", {"kind": "invite", "title": "Invite to play",
                                                                  "text": f"{i.get('name') or 'A friend'} invited you to play {game}."}))
        for c in inbox.get("conversations") or []:
            if c.get("unread") and not c.get("mine") and c.get("last_id"):
                current.append((f"m:{c['last_id']}", {"kind": "message", "title": f"Message from {c.get('name') or 'a friend'}",
                                                      "text": _preview(c.get("last"))}))
        for g in inbox.get("groups") or []:
            if g.get("unread") and g.get("last_id") and g.get("last_from") != me:
                who = g.get("last_name") or "Someone"
                current.append((f"g:{g['last_id']}", {"kind": "message", "title": f"{g.get('name') or 'Group'}",
                                                      "text": f"{who}: {_preview(g.get('last'))}"}))
        with self._lock:
            store = self._store()
            known = set(store.get(service) or [])
            fresh = [event for key, event in current if key not in known]
            keys = [key for key, _ in current]
            if set(keys) != known:
                # only what is still there is kept: a request declined and sent again later is announced again
                store[service] = keys[-KEEP:]
                try:
                    self.catalog.save()
                except Exception:
                    pass
        return fresh


def _preview(text) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= 80 else text[:79] + "…"


def summary(events: list[dict]) -> tuple[str, str]:
    """One notification for a batch: (title, text)."""
    if len(events) == 1:
        return events[0]["title"], events[0]["text"]
    kinds = {e["kind"] for e in events}
    parts = []
    for kind, one, many in (("message", "a new message", "new messages"), ("request", "a friend request", "friend requests"),
                            ("invite", "an invite to play", "invites to play")):
        n = sum(1 for e in events if e["kind"] == kind)
        if n:
            parts.append(one if n == 1 else f"{n} {many}")
    text = (", ".join(parts[:-1]) + " and " + parts[-1]) if len(parts) > 1 else parts[0]
    return "Friends", f"You have {text}." + (" " + events[0]["text"] if len(kinds) == 1 and kinds == {"message"} else "")
