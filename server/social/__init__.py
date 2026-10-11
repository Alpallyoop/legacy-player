"""The friends layer: a small, separate service for finding friends, seeing who is online, inviting them into a room
and sending short messages (one to one, or in small group chats). It is not part of the lobby server and Legacy Player
works fully without it.

No sign-ups. A player's app asks the service for an identity once ("hello" with a display name and the app's public
key) and gets back a player id, a secret that only that app keeps, and a friend code (like "MK7Q-4X2P-9HTA") to give to
friends. Nothing else is ever asked: no e-mail, no password, no account. The service remembers a player for 60 days
after their last visit, then forgets them.

Messages are end-to-end encrypted (server/social/e2e.py): the service stores and forwards sealed envelopes it cannot
read, for 7 days. A player who reports a message reveals that message's key (and the few before it) so the moderators
can read the service's own stored copy; nothing else is ever readable here.

What it keeps per player: the name they chose, the friend code, their public key, their friends, pending requests, the
invites and sealed messages waiting for them, the group chats they are in, and a presence line their app refreshes
while it is open: online or not, and, if they chose to share it, the room they are in (an invite code and the server
code that reaches it) so a friend can join with one click. It never sees game traffic, addresses, or anything about
the computer.

Run it with   python -m server.social --dir social --port 8791   and put HTTPS in front of it (the app only talks to
https:// addresses, or to 127.0.0.1 while testing).
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import e2e, textfilter

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"            # no 0/O or 1/I: codes are read out loud
FORGET_AFTER = 60 * 86400
ONLINE_WINDOW = 75.0                                       # a heartbeat every 30 s keeps a player online
MESSAGE_KEEP = 7 * 86400
MESSAGES_PER_PAIR = 200
MAX_FRIENDS = 200
MAX_NAME = 24
MAX_TEXT = 500
PER_MINUTE = 120                                           # calls per player per minute
MESSAGES_PER_MINUTE = 20                                   # a friend cannot flood a conversation
REQUESTS_PER_HOUR = 20                                     # nor send friend requests to every code they can guess
REPORTS_PER_DAY = 20
REPORT_CATEGORIES = ("harassment", "hate", "threats", "spam", "scam", "sexual", "name", "cheating", "other")
TIMEOUTS = {"1h": 3600, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}
INVITES_PER_HOUR = 30
GROUPS_PER_HOUR = 10                                       # new group chats per player
GROUP_CHANGES_PER_HOUR = 60                                # adds, removals and renames per player
MAX_GROUP = 10                                             # members in one group chat, the creator included
MAX_GROUPS = 50                                            # group chats one player can be in
GROUP_MESSAGES = 300
CODE_GROUPS = 3                                            # friend codes are 3 groups of 4: about 60 bits, never guessed
MAX_PLAYERS = 100_000                                      # the whole service: hello stops making identities beyond this
SAVE_EVERY = 2.0                                           # seconds: ordinary changes are written at most this often
TIDY_EVERY = 60.0                                          # seconds (service clock) between full tidy passes


def _log(line: str) -> None:
    """One line for the service's own log. Never a player's words, ids or any address."""
    try:
        print(f"friends service: {line}", file=sys.stderr, flush=True)
    except Exception:
        pass


def _small_int(value, limit: int = 64) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(limit, number))


def _str_list(value) -> list:
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def _clean_player(p) -> dict | None:
    """A player entry as read from disk, with every field the rules rely on; None when it can't be used."""
    if not isinstance(p, dict) or not all(isinstance(p.get(k), str) and p.get(k) for k in ("code", "secret")):
        return None
    out = dict(p)
    out["name"] = clean_name(p.get("name"))
    for key in ("friends", "requests_in", "requests_out", "blocked"):
        out[key] = _str_list(p.get(key))
    seen = p.get("seen")
    out["seen"] = float(seen) if isinstance(seen, (int, float)) and not isinstance(seen, bool) else 0.0
    out["status"] = p.get("status") if isinstance(p.get("status"), str) else ""
    out["room"] = p.get("room") if isinstance(p.get("room"), dict) else None
    invites = p.get("invites") if isinstance(p.get("invites"), list) else []
    out["invites"] = [i for i in invites if isinstance(i, dict) and isinstance(i.get("at"), (int, float))]
    messages = p.get("messages") if isinstance(p.get("messages"), dict) else {}
    # only sealed (end-to-end encrypted) messages are kept: plain-text ones from older versions are dropped on load
    out["messages"] = {str(k): [m for m in v if isinstance(m, dict) and isinstance(m.get("at"), (int, float))
                                and isinstance(m.get("from"), str) and isinstance(m.get("e"), dict)]
                       for k, v in messages.items() if isinstance(v, list)}
    out["messages"] = {k: v for k, v in out["messages"].items() if v}
    out["pub"] = p.get("pub") if _pub_ok(p.get("pub")) else ""
    out["requests_open"] = bool(p.get("requests_open", True))
    return out


def _pub_ok(value) -> bool:
    """A public key as the apps send it: 32 bytes, url-safe base64."""
    try:
        return isinstance(value, str) and len(e2e.pc.b64d(value, 32)) == 32
    except ValueError:
        return False


def _clean_group(g) -> dict | None:
    if not isinstance(g, dict) or not isinstance(g.get("owner"), str):
        return None
    members = list(dict.fromkeys(_str_list(g.get("members"))))
    if not members:
        return None
    out = {"name": clean_name(g.get("name"), "Group"), "owner": g["owner"] if g["owner"] in members else members[0], "members": members,
           "at": float(g["at"]) if isinstance(g.get("at"), (int, float)) else 0.0}
    # joined / read / cleared are message numbers (each message in a group gets the next number)
    for key in ("joined", "read", "cleared"):
        raw = g.get(key) if isinstance(g.get(key), dict) else {}
        out[key] = {str(k): int(v) for k, v in raw.items() if isinstance(v, int) and not isinstance(v, bool)}
    msgs = g.get("messages") if isinstance(g.get("messages"), list) else []
    out["messages"] = [m for m in msgs if isinstance(m, dict) and isinstance(m.get("at"), (int, float)) and isinstance(m.get("from"), str)
                       and isinstance(m.get("e"), dict) and isinstance(m.get("id"), str) and isinstance(m.get("n"), int)]
    seq = g.get("seq") if isinstance(g.get("seq"), int) else 0
    out["seq"] = max([seq] + [m["n"] for m in out["messages"]])
    return out


class SocialError(ValueError):
    """A message safe to show the player."""


NO_SUCH_CODE = "No player has that friend code. Check it with your friend (it looks like MK7Q-4X2P-9HTA)."


def make_code() -> str:
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(CODE_GROUPS))


def norm_code(code) -> str:
    """A friend code as it is looked up: letters and digits only, upper case (people type them any way)."""
    return re.sub(r"[^A-Z0-9]", "", str(code or "").upper())[:16]


def clean_name(name, empty: str = "Player") -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", "", str(name or "")).strip()[:MAX_NAME]
    return text or empty


def clean_text(text, limit: int = MAX_TEXT) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(text or "")).strip()[:limit]


class SocialService:
    """All the rules, no network. The HTTP layer in server/social/__main__.py is a thin wrapper."""

    def __init__(self, folder: Path | None, clock=time.time) -> None:
        self.folder = Path(folder) if folder else None
        self.clock = clock
        self.lock = threading.RLock()
        self.players: dict[str, dict] = {}     # id -> {name, secret, code, friends: [ids], requests_in: [ids], requests_out: [ids],
        #                                           seen, status, room, invites: [..], messages: {friend_id: [..]}, minute: [window, count]}
        self.codes: dict[str, str] = {}        # friend code (letters and digits only, see norm_code) -> player id
        self.groups: dict[str, dict] = {}      # group id -> {name, owner, members, joined, read, cleared, at, messages}
        # moderation: bans and timeouts by player id, reports from players, and the service-wide word filter
        self.mod: dict = {"bans": {}, "mutes": {}, "reports": [], "filter": {"on": False, "words": []}, "log": []}
        self._dirty = False
        self._last_save = float("-inf")       # time.monotonic() of the last write
        self._timer: threading.Timer | None = None
        self._tidied = float("-inf")          # service clock of the last full tidy
        self._load()

    # --- storage --------------------------------------------------------------------------------------------------
    def _load(self) -> None:
        if self.folder is None:
            return
        path = self.folder / "players.json"
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return
        except OSError as exc:
            # Unreadable right now (locked, permissions): never start empty, or the next save would wipe the bans.
            raise RuntimeError(f"could not read {path.name} ({type(exc).__name__}); not starting so it is not overwritten") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("players", {}), dict) or not isinstance(data.get("mod", {}), dict):
                raise ValueError("not a players file")
        except (ValueError, RecursionError) as exc:
            kept = path.with_name(f"players.json.corrupt-{int(time.time())}")
            try:
                os.replace(path, kept)
                where = f"kept it as {kept.name}"
            except OSError:
                where = "could not move it aside"
            _log(f"players.json could not be read ({type(exc).__name__}); {where} and started with an empty list. "
                 "The bans and reports in it are not active until it is repaired and put back.")
            return
        skipped = upgraded = 0
        for pid, p in (data.get("players") or {}).items():
            clean = _clean_player(p)
            if clean is None or norm_code(clean["code"]) in self.codes:
                skipped += 1
                continue
            if len(norm_code(clean["code"])) < 4 * CODE_GROUPS:
                clean["code"] = self._fresh_code()          # short codes from older versions could be guessed: a new one
                upgraded += 1
            self.players[pid] = clean
            self.codes[norm_code(clean["code"])] = pid
        for gid, g in (data.get("groups") or {}).items() if isinstance(data.get("groups"), dict) else []:
            clean = _clean_group(g)
            if clean is not None:
                clean["members"] = [m for m in clean["members"] if m in self.players]
                if clean["members"]:
                    clean["owner"] = clean["owner"] if clean["owner"] in clean["members"] else clean["members"][0]
                    self.groups[str(gid)] = clean
        if upgraded:
            _log(f"gave {upgraded} player(s) a longer friend code")
            self._changed()
        mod = data.get("mod") or {}
        for key, kind in (("bans", dict), ("mutes", dict), ("reports", list), ("filter", dict), ("log", list)):
            if isinstance(mod.get(key), kind):
                self.mod[key] = mod[key]
        self.mod["bans"] = {str(k): (v if isinstance(v, dict) else {}) for k, v in self.mod["bans"].items()}
        self.mod["mutes"] = {str(k): v for k, v in self.mod["mutes"].items()
                             if isinstance(v, dict) and isinstance(v.get("until"), (int, float))}
        self.mod["reports"] = [r for r in self.mod["reports"] if isinstance(r, dict) and isinstance(r.get("id"), str)
                               and isinstance(r.get("target"), dict) and isinstance(r["target"].get("id"), str)
                               and isinstance(r.get("status"), str)]
        self.mod["log"] = [entry for entry in self.mod["log"] if isinstance(entry, dict)]
        f = self.mod["filter"]
        self.mod["filter"] = {"on": bool(f.get("on")), "words": _str_list(f.get("words"))}
        if skipped:
            _log(f"skipped {skipped} unreadable player entr{'y' if skipped == 1 else 'ies'} in players.json")

    def save(self) -> None:
        """Write everything now: a whole new file, flushed to disk, then swapped in, so a crash or a power cut leaves
        either the old file or the new one, never half of one."""
        if self.folder is None:
            return
        with self.lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            data = json.dumps({"players": self.players, "mod": self.mod, "groups": self.groups}).encode("utf-8")
            fd, tmp = tempfile.mkstemp(prefix=".players-", suffix=".tmp", dir=self.folder)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                try:
                    os.chmod(tmp, 0o600)
                except OSError:
                    pass
                os.replace(tmp, self.folder / "players.json")
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            if hasattr(os, "O_DIRECTORY"):                 # make the rename itself durable (POSIX)
                try:
                    dfd = os.open(self.folder, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(dfd)
                    finally:
                        os.close(dfd)
                except OSError:
                    pass
            self._dirty = False
            self._last_save = time.monotonic()

    def _changed(self, urgent: bool = False) -> None:
        """Something changed. Moderation and leaving are written at once; everything else at most every SAVE_EVERY
        seconds (the first change after a quiet spell is written at once, later ones are gathered into one write)."""
        if self.folder is None:
            return
        with self.lock:
            self._dirty = True
            wait = SAVE_EVERY - (time.monotonic() - self._last_save)
            if urgent or wait <= 0:
                try:
                    self.save()
                except OSError as exc:
                    _log(f"could not save players.json ({type(exc).__name__}); trying again shortly")
                    self._schedule(SAVE_EVERY)
                return
            self._schedule(wait)

    def _schedule(self, delay: float) -> None:
        if self._timer is not None:
            return
        self._timer = threading.Timer(max(0.05, delay), self._timer_fired)
        self._timer.daemon = True
        self._timer.start()

    def _timer_fired(self) -> None:
        with self.lock:
            self._timer = None
            if self._dirty:
                try:
                    self.save()
                except OSError as exc:
                    _log(f"could not save players.json ({type(exc).__name__}); trying again shortly")
                    self._schedule(SAVE_EVERY)

    def flush(self) -> None:
        """Write anything not written yet (called when the service stops)."""
        with self.lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._dirty:
                self.save()

    # --- helpers ------------------------------------------------------------------------------------------------
    def _maybe_tidy(self) -> None:
        """The full pass is O(players): run it at most once a minute, not on every call."""
        if self.clock() - self._tidied >= TIDY_EVERY:
            self._tidy()

    def _tidy(self) -> None:
        now = self.clock()
        self._tidied = now
        for pid in [p for p, v in self.players.items() if now - v.get("seen", 0) > FORGET_AFTER and p not in self.mod["bans"]]:
            self._forget(pid)
        for pid, m in list(self.mod["mutes"].items()):
            if m.get("until", 0) <= now:
                del self.mod["mutes"][pid]
        for p in self.players.values():
            for fid, msgs in list(p.get("messages", {}).items()):
                keep = [m for m in msgs if now - m["at"] < MESSAGE_KEEP][-MESSAGES_PER_PAIR:]
                if keep:
                    p["messages"][fid] = keep
                else:
                    del p["messages"][fid]
            p["invites"] = [i for i in p.get("invites", []) if now - i["at"] < 3600]
        for gid, g in list(self.groups.items()):
            g["messages"] = [m for m in g["messages"] if now - m["at"] < MESSAGE_KEEP][-GROUP_MESSAGES:]

    def _fresh_code(self) -> str:
        code = make_code()
        while norm_code(code) in self.codes:
            code = make_code()
        return code

    def _forget(self, pid: str) -> None:
        p = self.players.pop(pid, None)
        if not p:
            return
        self.codes.pop(norm_code(p["code"]), None)
        self._leave_all_groups(pid)
        for other in self.players.values():
            for key in ("friends", "requests_in", "requests_out", "blocked"):
                if pid in other.get(key, []):
                    other[key].remove(pid)
            other.get("messages", {}).pop(pid, None)
            other["invites"] = [i for i in other.get("invites", []) if i.get("from") != pid]

    def _auth(self, pid: str, secret: str) -> dict:
        p = self.players.get(str(pid or ""))
        if p is None or not hmac.compare_digest(str(secret or "").encode("utf-8", "replace"), p["secret"].encode("utf-8", "replace")):
            raise SocialError("This app is not known to the friends service any more. Say hello again under Settings > Friends.")
        ban = self.mod["bans"].get(str(pid))
        if ban:
            raise SocialError("The moderators of this friends service banned this player" + (f": {ban.get('reason')}" if ban.get("reason") else ".")
                              + " You can't use friends, messages or invites here.")
        now = self.clock()
        window, count = p.get("minute") or [0, 0]
        if int(now // 60) != window:
            window, count = int(now // 60), 0
        if count >= PER_MINUTE:
            raise SocialError("Too many requests in a minute; wait a moment.")
        p["minute"] = [window, count + 1]
        p["seen"] = now
        return p

    def _muted(self, pid: str) -> dict | None:
        m = self.mod["mutes"].get(pid)
        return m if m and m.get("until", 0) > self.clock() else None

    def _may_talk(self, pid: str) -> None:
        m = self._muted(pid)
        if m:
            left = int(m["until"] - self.clock())
            when = f"{left // 3600} h {left % 3600 // 60} min" if left >= 3600 else f"{max(1, left // 60)} min"
            raise SocialError(f"A moderator paused your messages, invites and friend requests for another {when}"
                              + (f": {m.get('reason')}" if m.get("reason") else ".") )

    def _bump(self, p: dict, key: str, window: int, limit: int, what: str) -> None:
        now = self.clock()
        stamps = [t for t in p.get(key, []) if now - t < window]
        if len(stamps) >= limit:
            raise SocialError(f"Too many {what} in a short time; wait a little.")
        stamps.append(now)
        p[key] = stamps

    def _filtered(self, text: str) -> bool:
        f = self.mod["filter"]
        return bool(f.get("on")) and textfilter.has_bad(text, f.get("words"))

    def _online(self, p: dict) -> bool:
        return self.clock() - p.get("seen", 0) < ONLINE_WINDOW

    def _mutual(self, a: str, b: str) -> bool:
        """Friends on both sides and neither banned: a one-sided leftover never lets anything through."""
        pa, pb = self.players.get(a), self.players.get(b)
        return (pa is not None and pb is not None and b in pa.get("friends", []) and a in pb.get("friends", [])
                and a not in self.mod["bans"] and b not in self.mod["bans"])

    def _view(self, me: dict, other_id: str) -> dict:
        """A friend as I see them (only ever built for mutual friends)."""
        o = self.players.get(other_id) or {}
        room = o.get("room") if self._online(o) and o.get("room") else None
        return {"id": other_id, "name": o.get("name", "?"), "online": self._online(o), "status": o.get("status", "") if self._online(o) else "",
                "room": room, "pub": o.get("pub", ""),
                "unread": sum(1 for m in me.get("messages", {}).get(other_id, []) if not m.get("read") and m["from"] == other_id)}

    def _inbox(self, pid: str) -> dict:
        p = self.players[pid]
        friends = [self._view(p, f) for f in p.get("friends", []) if self._mutual(pid, f)]
        friends.sort(key=lambda f: (not f["online"], f["name"].lower()))
        groups = self._groups_of(pid)
        muted = self._muted(pid)
        return {"me": {"id": pid, "name": p["name"], "code": p["code"], "status": p.get("status", ""), "room": p.get("room"), "pub": p.get("pub", "")},
                "friends": friends,
                "requests": [{"id": r, "name": self.players.get(r, {}).get("name", "?")} for r in p.get("requests_in", []) if r in self.players],
                # a request I sent shows the code I typed, not their name: nobody learns a name before they say yes
                "sent": [{"id": r, "name": self.players[r]["code"], "code": self.players[r]["code"]} for r in p.get("requests_out", []) if r in self.players],
                "invites": list(p.get("invites", [])),
                "conversations": self._conversations(pid),
                "groups": groups,
                "blocked": [{"id": b, "name": self.players.get(b, {}).get("name", "?")} for b in p.get("blocked", []) if b in self.players],
                "unread": sum(f["unread"] for f in friends) + sum(g["unread"] for g in groups),
                "requests_open": p.get("requests_open", True),
                "moderation": ({"muted_until": muted["until"], "reason": muted.get("reason", "")} if muted else None),
                "online": sum(1 for f in friends if f["online"])}

    def _conversations(self, pid: str) -> list[dict]:
        p = self.players[pid]
        out = []
        for other, msgs in p.get("messages", {}).items():
            if not msgs or other not in self.players:
                continue
            last = msgs[-1]
            friend = self._mutual(pid, other)
            out.append({"id": other, "name": self.players[other]["name"], "last": "", "last_e": last["e"], "last_id": last.get("id", ""),
                        "at": last["at"], "mine": last["from"] == pid,
                        "unread": sum(1 for m in msgs if not m.get("read") and m["from"] == other),
                        "online": friend and self._online(self.players[other]),      # an ex-friend's presence is not shown
                        "friend": friend, "pub": self.players[other].get("pub", "") if friend else ""})
        out.sort(key=lambda c: -c["at"])
        return out

    def _blocks(self, a: str, b: str) -> bool:
        """True when either player has blocked the other."""
        return b in self.players.get(a, {}).get("blocked", []) or a in self.players.get(b, {}).get("blocked", [])

    # --- operations ---------------------------------------------------------------------------------------------
    def hello(self, name, pub=None) -> dict:
        """A new identity: id, secret (kept only by that app) and a friend code. `pub` is the app's public key for
        end-to-end encrypted messages (apps from before encryption send none and cannot message newer ones)."""
        with self.lock:
            self._maybe_tidy()
            if len(self.players) >= MAX_PLAYERS:
                self._tidy()
                if len(self.players) >= MAX_PLAYERS:
                    raise SocialError("This friends service is full right now. Try again later.")
            if self._filtered(clean_name(name)):
                raise SocialError("This friends service doesn't allow that name. Pick another under Settings > You.")
            pid = secrets.token_hex(8)
            code = self._fresh_code()
            self.players[pid] = {"name": clean_name(name), "secret": secrets.token_urlsafe(24), "code": code, "friends": [], "requests_in": [],
                                 "requests_out": [], "seen": self.clock(), "status": "", "room": None, "invites": [], "messages": {}, "blocked": [],
                                 "requests_open": True, "pub": pub if _pub_ok(pub) else ""}
            self.codes[norm_code(code)] = pid
            self._changed()
            return {"id": pid, "secret": self.players[pid]["secret"], "code": code, "name": self.players[pid]["name"]}

    def heartbeat(self, pid, secret, name=None, status="", room=None, requests_open=None, pub=None) -> dict:
        """The app says it is open (every 30 s), what the player is doing, the room to share and its public key, then
        gets its inbox. A new key (the player replaced theirs) is taken; friends' apps show that it changed."""
        with self.lock:
            p = self._auth(pid, secret)
            before = (p["name"], p.get("requests_open", True), p.get("pub", ""))
            if name is not None and not self._filtered(clean_name(name)):
                p["name"] = clean_name(name)
            if requests_open is not None:
                p["requests_open"] = bool(requests_open)
            if pub is not None and _pub_ok(pub):
                p["pub"] = pub
            if (p["name"], p.get("requests_open", True), p.get("pub", "")) != before:
                self._changed()        # presence itself is not written on every heartbeat (the tidy pass keeps it)
            muted = self._muted(str(pid)) is not None
            status = clean_text(status, 60)
            p["status"] = "" if muted or self._filtered(status) else status          # free text: the same rules as a message
            if isinstance(room, dict) and room.get("invite_code"):
                invite_code, server_code = clean_text(room.get("invite_code"), 14), clean_text(room.get("server_code"), 60)
                game = clean_text(room.get("game"), 80)
                p["room"] = None if self._filtered(invite_code + " " + server_code) else {
                    "invite_code": invite_code, "game": "" if muted or self._filtered(game) else game,
                    "server_code": server_code, "players": _small_int(room.get("players")),
                    "max_players": _small_int(room.get("max_players")), "at": self.clock()}
            else:
                p["room"] = None
            now = self.clock()
            p["invites"] = [i for i in p.get("invites", []) if now - i["at"] < 3600]
            self._maybe_tidy()
            return self._inbox(pid)

    def request(self, pid, secret, code) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            self._bump(p, "code_tries", 3600, 60, "friend code tries")      # codes can't be found by guessing
            other_id = self.codes.get(norm_code(code))
            if other_id is None or other_id not in self.players:
                raise SocialError(NO_SUCH_CODE)
            if other_id == pid:
                raise SocialError("That is your own code.")
            if other_id in p.get("blocked", []):
                raise SocialError("You blocked this player. Unblock them first (Friends > Blocked).")
            if pid in self.players[other_id].get("blocked", []) or other_id in self.mod["bans"]:
                raise SocialError(NO_SUCH_CODE)
            other = self.players[other_id]
            if other_id in p["friends"] and pid not in other.get("friends", []):
                p["friends"].remove(other_id)                            # a one-sided leftover is not a friendship
            if other_id not in p["friends"] and other_id not in p["requests_in"]:
                self._may_talk(pid)
                if not other.get("requests_open", True):
                    raise SocialError("That player isn't taking friend requests right now. Ask them to add your code instead.")
                self._bump(p, "req_times", 3600, REQUESTS_PER_HOUR, "friend requests")
            if other_id in p["friends"] and pid in other.get("friends", []):
                return {"ok": True, "already": True, **self._inbox(pid)}
            if len(p["friends"]) >= MAX_FRIENDS:
                raise SocialError("Your friends list is full.")
            if other_id in p["requests_in"]:                              # they asked first: this is a yes
                return self.decide(pid, secret, other_id, True)
            if other_id not in p["requests_out"]:
                p["requests_out"].append(other_id)
            if pid not in other["requests_in"]:
                other["requests_in"].append(pid)
            self._changed()
            return {"ok": True, "already": False, **self._inbox(pid)}

    def decide(self, pid, secret, other_id, accept) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            other_id = str(other_id or "")
            other = self.players.get(other_id)
            asked = other is not None and other_id in p["requests_in"]
            refused = not asked or self._blocks(pid, other_id) or other_id in self.mod["bans"]
            if accept and not refused:
                # checked before anything changes, so a full list leaves the request where it was
                if other_id not in p["friends"] and len(p["friends"]) >= MAX_FRIENDS:
                    raise SocialError("Your friends list is full.")
                if pid not in other["friends"] and len(other["friends"]) >= MAX_FRIENDS:
                    raise SocialError("That player's friends list is full.")
            if other_id in p["requests_in"]:
                p["requests_in"].remove(other_id)
            if other and pid in other.get("requests_out", []):
                other["requests_out"].remove(pid)
            if accept:
                # only a request that is really there, from someone neither side blocked, becomes a friendship
                if refused:
                    self._changed()
                    raise SocialError("That friend request is no longer here.")
                if other_id not in p["friends"]:
                    p["friends"].append(other_id)
                if pid not in other["friends"]:
                    other["friends"].append(pid)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def remove(self, pid, secret, other_id) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            other_id = str(other_id or "")
            for key in ("friends", "requests_out", "requests_in"):
                if other_id in p.get(key, []):
                    p[key].remove(other_id)
            other = self.players.get(other_id)
            if other:
                for key in ("friends", "requests_out", "requests_in"):
                    if pid in other.get(key, []):
                        other[key].remove(pid)
                other.get("messages", {}).pop(pid, None)
            p.get("messages", {}).pop(other_id, None)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def invite(self, pid, secret, to, invite_code, game, server_code="") -> dict:
        """Hand a friend the way into my room. Only friends can be invited, and only with a room invite code."""
        with self.lock:
            p = self._auth(pid, secret)
            to = str(to or "")
            if not self._mutual(str(pid), to) or self._blocks(pid, to):
                raise SocialError("You can only invite someone on your friends list.")
            self._may_talk(pid)
            self._bump(p, "inv_times", 3600, INVITES_PER_HOUR, "invites")
            code = clean_text(invite_code, 14)
            if not code:
                raise SocialError("Host a room first; the invite carries its code.")
            server_code, game = clean_text(server_code, 60), clean_text(game, 80)
            if self._filtered(code + " " + server_code):
                raise SocialError("This friends service doesn't allow some words in that invite, so it wasn't sent.")
            inv = {"from": pid, "name": p["name"], "invite_code": code, "game": "" if self._filtered(game) else game,
                   "server_code": server_code, "at": self.clock()}
            box = self.players[to]["invites"]
            box[:] = [i for i in box if i["from"] != pid]
            box.append(inv)
            del box[:-20]
            self._changed()
            return {"ok": True}

    def dismiss_invite(self, pid, secret, from_id) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            p["invites"] = [i for i in p.get("invites", []) if i["from"] != str(from_id or "")]
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def _sealed(self, p: dict, pid: str, envelope, conv: str, members: list) -> dict:
        """The checked envelope, or a SocialError saying what to do (update, refresh) in words a player understands."""
        if not isinstance(envelope, dict) or not p.get("pub"):
            raise SocialError("Update Legacy Player to send messages: this friends service only carries end-to-end encrypted messages.")
        for m in members:
            if not self.players[m].get("pub"):
                raise SocialError(f"{self.players[m]['name']} needs to update Legacy Player before you can message them.")
        try:
            return e2e.check_shape(envelope, str(pid), conv, p["pub"], {m: self.players[m]["pub"] for m in members})
        except e2e.E2EError as exc:
            raise SocialError(str(exc)) from exc

    def message(self, pid, secret, to, envelope=None) -> dict:
        """Store a sealed message for a friend. Plain text is refused: the service only ever holds envelopes it can't read
        (server/social/e2e.py), checked to be from this sender, for this conversation and for both people's keys."""
        with self.lock:
            p = self._auth(pid, secret)
            to = str(to or "")
            if not self._mutual(str(pid), to) or self._blocks(pid, to):
                raise SocialError("You can only message someone on your friends list.")
            self._may_talk(pid)
            env = self._sealed(p, pid, envelope, e2e.direct_conv(pid, to), [str(pid), to])
            if any(m.get("id") == env["mid"] for m in p.get("messages", {}).get(to, [])):
                raise SocialError("That message was already sent.")
            self._bump(p, "msg_times", 60, MESSAGES_PER_MINUTE, "messages")
            m = {"id": env["mid"], "from": pid, "to": to, "e": env, "at": self.clock()}
            for owner, other in ((pid, to), (to, pid)):
                box = self.players[owner].setdefault("messages", {}).setdefault(other, [])
                box.append(dict(m, read=(owner == pid)))
                del box[:-MESSAGES_PER_PAIR]
            self._changed()
            return {"ok": True, "messages": self._thread(pid, to)}

    def _thread(self, pid: str, other: str, legacy: bool = False) -> list[dict]:
        msgs = self.players[pid].get("messages", {}).get(other, [])
        for m in msgs:
            m["read"] = True
        out = [{"id": m.get("id", ""), "from": m["from"], "e": m["e"], "at": m["at"], "mine": m["from"] == pid} for m in msgs]
        if legacy:                                         # an app from before encryption: say why it sees nothing
            for row in out:
                row["text"] = "(an encrypted message: update Legacy Player to read it)"
        return out

    def thread(self, pid, secret, other, legacy: bool = False) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            other = str(other or "")
            # a name is only given for someone I share a conversation or a friendship with: ids are not a lookup service
            if other not in self.players or (other not in p.get("messages", {}) and not self._mutual(pid, other)):
                return {"messages": []}
            friend = self._mutual(pid, other)
            out = {"messages": self._thread(pid, other, legacy), "name": self.players[other]["name"],
                   "pub": self.players[other].get("pub", "") if friend else "", "friend": friend}
            self._changed()
            return out

    # --- group chats -------------------------------------------------------------------------------------------------
    def _groups_of(self, pid: str) -> list[dict]:
        out = []
        for gid, g in self.groups.items():
            if pid not in g["members"]:
                continue
            visible = self._group_messages(g, pid)
            last = visible[-1] if visible else None
            seen = g["read"].get(pid, 0)
            out.append({"id": gid, "name": g["name"], "owner": g["owner"], "mine": g["owner"] == pid,
                        "members": [self._member_view(pid, m) for m in g["members"]],
                        "unread": sum(1 for m in visible if m["from"] != pid and m["n"] > seen),
                        "last_e": last["e"] if last else None, "last_id": last["id"] if last else "",
                        "last_from": last["from"] if last else "", "at": last["at"] if last else g["at"]})
        out.sort(key=lambda g: -g["at"])
        return out

    def _member_view(self, me: str, other: str) -> dict:
        o = self.players.get(other) or {}
        friend = other == me or self._mutual(me, other)
        return {"id": other, "name": o.get("name", "?"), "pub": o.get("pub", ""), "friend": friend,
                "online": bool(friend and other != me and self._online(o))}      # presence only between friends

    @staticmethod
    def _group_messages(g: dict, pid: str) -> list[dict]:
        since = max(g["joined"].get(pid, 0), g["cleared"].get(pid, 0))
        return [m for m in g["messages"] if m["n"] > since]

    def _group(self, pid: str, gid) -> dict:
        g = self.groups.get(str(gid or ""))
        if g is None or pid not in g["members"]:
            raise SocialError("That group chat is no longer here.")
        return g

    def _can_join(self, members: list, newcomer: str) -> None:
        """A newcomer must be friends with every member, with no block either way between them and anyone there."""
        o = self.players.get(newcomer)
        if o is None or newcomer in self.mod["bans"]:
            raise SocialError("That player is not on the friends service.")
        for m in members:
            if m == newcomer:
                continue
            if self._blocks(m, newcomer) or not self._mutual(m, newcomer):
                raise SocialError(f"{o['name']} can only join if they are friends with everyone in the group.")
        if not o.get("pub"):
            raise SocialError(f"{o['name']} needs to update Legacy Player before they can join a group chat.")
        if sum(1 for g in self.groups.values() if newcomer in g["members"]) >= MAX_GROUPS:
            raise SocialError(f"{o['name']} is in too many group chats.")

    def group_create(self, pid, secret, name, members) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            self._may_talk(pid)
            wanted = list(dict.fromkeys(str(m) for m in (members if isinstance(members, list) else []) if str(m) != pid))
            if not wanted:
                raise SocialError("Pick at least one friend for the group.")
            if len(wanted) + 1 > MAX_GROUP:
                raise SocialError(f"A group chat has at most {MAX_GROUP} people.")
            name = clean_name(name, "Group")
            if self._filtered(name):
                raise SocialError("This friends service doesn't allow that group name.")
            if not p.get("pub"):
                raise SocialError("Update Legacy Player to use group chats.")
            if sum(1 for g in self.groups.values() if pid in g["members"]) >= MAX_GROUPS:
                raise SocialError("You are in too many group chats. Leave one first.")
            members_now = [str(pid)]
            for m in wanted:                                  # every pair must be friends: each joins a group of friends
                self._can_join(members_now, m)
                members_now.append(m)
            self._bump(p, "group_times", 3600, GROUPS_PER_HOUR, "new group chats")
            gid = secrets.token_hex(8)
            now = self.clock()
            self.groups[gid] = {"name": name, "owner": str(pid), "members": members_now, "joined": {m: 0 for m in members_now},
                                "read": {}, "cleared": {}, "at": now, "messages": [], "seq": 0}
            self._changed()
            return {"ok": True, "group": gid, **self._inbox(pid)}

    def group_add(self, pid, secret, gid, member) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            g = self._group(pid, gid)
            self._may_talk(pid)
            member = str(member or "")
            if member in g["members"]:
                return {"ok": True, **self._inbox(pid)}
            if len(g["members"]) >= MAX_GROUP:
                raise SocialError(f"A group chat has at most {MAX_GROUP} people.")
            self._can_join(g["members"], member)
            self._bump(p, "gchange_times", 3600, GROUP_CHANGES_PER_HOUR, "group changes")
            g["members"].append(member)
            g["joined"][member] = g["seq"]                    # they read from now on: earlier messages were not sealed for them
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def group_remove(self, pid, secret, gid, member) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            g = self._group(pid, gid)
            member = str(member or "")
            if g["owner"] != pid:
                raise SocialError("Only the person who made the group can remove people.")
            if member == pid:
                raise SocialError("Use Leave to leave the group.")
            if member in g["members"]:
                self._bump(p, "gchange_times", 3600, GROUP_CHANGES_PER_HOUR, "group changes")
                self._drop_member(str(gid), member)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def group_rename(self, pid, secret, gid, name) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            g = self._group(pid, gid)
            if g["owner"] != pid:
                raise SocialError("Only the person who made the group can rename it.")
            self._may_talk(pid)
            name = clean_name(name, "Group")
            if self._filtered(name):
                raise SocialError("This friends service doesn't allow that group name.")
            self._bump(p, "gchange_times", 3600, GROUP_CHANGES_PER_HOUR, "group changes")
            g["name"] = name
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def group_leave(self, pid, secret, gid) -> dict:
        with self.lock:
            self._auth(pid, secret)
            self._group(pid, gid)
            self._drop_member(str(gid), pid)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def _drop_member(self, gid: str, member: str) -> None:
        g = self.groups.get(gid)
        if g is None or member not in g["members"]:
            return
        g["members"].remove(member)
        for key in ("joined", "read", "cleared"):
            g[key].pop(member, None)
        if not g["members"]:
            del self.groups[gid]
        elif g["owner"] == member:
            g["owner"] = g["members"][0]                      # the longest-standing member takes over

    def _leave_all_groups(self, pid: str, sharing_with: str | None = None) -> None:
        for gid, g in list(self.groups.items()):
            if pid in g["members"] and (sharing_with is None or sharing_with in g["members"]):
                self._drop_member(gid, pid)

    def group_message(self, pid, secret, gid, envelope=None) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            g = self._group(pid, gid)
            self._may_talk(pid)
            env = self._sealed(p, pid, envelope, e2e.group_conv(str(gid)), list(g["members"]))
            if any(m["id"] == env["mid"] for m in g["messages"]):
                raise SocialError("That message was already sent.")
            self._bump(p, "msg_times", 60, MESSAGES_PER_MINUTE, "messages")
            g["seq"] += 1
            g["messages"].append({"id": env["mid"], "from": pid, "e": env, "at": self.clock(), "n": g["seq"]})
            del g["messages"][:-GROUP_MESSAGES]
            g["read"][pid] = g["seq"]
            self._changed()
            return {"ok": True, **self._group_thread(pid, str(gid))}

    def _group_thread(self, pid: str, gid: str) -> dict:
        g = self.groups[gid]
        visible = self._group_messages(g, pid)
        g["read"][pid] = max([g["read"].get(pid, 0)] + [m["n"] for m in visible])
        return {"group": gid, "name": g["name"], "owner": g["owner"], "members": [self._member_view(pid, m) for m in g["members"]],
                "messages": [{"id": m["id"], "from": m["from"], "name": self.players.get(m["from"], {}).get("name", "(left)"),
                              "e": m["e"], "at": m["at"], "mine": m["from"] == pid} for m in visible]}

    def group_thread(self, pid, secret, gid) -> dict:
        with self.lock:
            self._auth(pid, secret)
            self._group(pid, gid)
            out = self._group_thread(pid, str(gid))
            self._changed()
            return out

    def group_clear(self, pid, secret, gid) -> dict:
        """Hide the group's messages so far from my inbox (the others keep theirs)."""
        with self.lock:
            self._auth(pid, secret)
            g = self._group(pid, gid)
            g["cleared"][pid] = g["seq"]
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def block(self, pid, secret, other) -> dict:
        """Block a player: no friendship, requests, invites or messages either way, and they no longer see you. They are not told."""
        with self.lock:
            p = self._auth(pid, secret)
            other = str(other or "")
            if other == pid or other not in self.players or not self._met(p, pid, other):
                raise SocialError("That player is not known to the friends service.")
            o = self.players[other]
            self._leave_all_groups(pid, sharing_with=other)        # no group chat keeps a blocked person in my inbox
            for a, b in ((p, other), (o, pid)):
                for key in ("friends", "requests_in", "requests_out"):
                    if b in a.get(key, []):
                        a[key].remove(b)
                a.get("messages", {}).pop(b, None)
                a["invites"] = [i for i in a.get("invites", []) if i.get("from") != b]
            p.setdefault("blocked", [])
            if other not in p["blocked"]:
                p["blocked"].append(other)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def unblock(self, pid, secret, other) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            other = str(other or "")
            if other in p.get("blocked", []):
                p["blocked"].remove(other)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def clear_thread(self, pid, secret, other) -> dict:
        """Delete a conversation from my inbox (the other player keeps their own copy)."""
        with self.lock:
            p = self._auth(pid, secret)
            p.get("messages", {}).pop(str(other or ""), None)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def read_all(self, pid, secret) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            for msgs in p.get("messages", {}).values():
                for m in msgs:
                    m["read"] = True
            for g in self.groups.values():
                if pid in g["members"]:
                    g["read"][pid] = g["seq"]
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    # --- reports from players ------------------------------------------------------------------------------
    def _met(self, p: dict, pid: str, other: str) -> bool:
        """Only someone you have actually come across can be reported: a friend, a request either way, an invite, a
        conversation, or someone you blocked. Nobody can report a random id they never saw."""
        o = self.players.get(other, {})
        return (other in p.get("friends", []) or other in p.get("requests_in", []) or other in p.get("requests_out", [])
                or other in p.get("blocked", []) or other in p.get("messages", {}) or pid in o.get("requests_in", [])
                or any(i.get("from") == other for i in p.get("invites", []))
                or any(pid in g["members"] and other in g["members"] for g in self.groups.values()))

    def _verified(self, env: dict, conv: str, sender: str, keys: dict, mid: str) -> str | None:
        """The text of the service's own stored copy, opened with the key the reporter revealed; None when no key was
        given or it does not fit (a made-up key cannot open it, and the reporter never sends text at all)."""
        raw = keys.get(mid)
        if not isinstance(raw, str):
            return None
        try:
            return e2e.open_with_key(env, e2e.pc.b64d(raw, 32), conv=conv, sender=sender)
        except (ValueError, e2e.E2EError):
            return None

    def report(self, pid, secret, target, category, details="", message_id="", also_block=False, keys=None, group="") -> dict:
        """Tell the moderators about a player, or one of their messages. Messages are end-to-end encrypted, so the reporter
        reveals the reported message's key (and the keys of up to five before it, for context); the service opens its
        *own* stored copy with them. A report can't put words in someone's mouth: the reporter never sends the text, and
        a key that does not open the stored message is refused."""
        with self.lock:
            p = self._auth(pid, secret)
            target = str(target or "")
            if target == pid or target not in self.players or not self._met(p, pid, target):
                raise SocialError("You can only report a player you have come across here.")
            if category not in REPORT_CATEGORIES:
                raise SocialError("Pick what the report is about.")
            self._bump(p, "report_times", 86400, REPORTS_PER_DAY, "reports")
            keys = keys if isinstance(keys, dict) else {}
            o = self.players[target]
            quoted, context, where = None, [], None
            if message_id:
                if group:
                    g = self._group(pid, group)
                    msgs, conv, where = self._group_messages(g, pid), e2e.group_conv(str(group)), {"group": g["name"]}
                else:
                    msgs, conv = p.get("messages", {}).get(target, []), e2e.direct_conv(pid, target)
                idx = next((i for i, m in enumerate(msgs) if m.get("id") == message_id and m["from"] == target), None)
                if idx is None:
                    raise SocialError("That message is no longer here, so it can't be reported. You can still report the player.")
                text = self._verified(msgs[idx]["e"], conv, target, keys, message_id)
                if text is None:
                    raise SocialError("That message could not be checked against the service's copy, so it was not reported.")
                quoted = {"id": message_id, "text": text, "at": msgs[idx]["at"], "verified": True}
                for m in msgs[max(0, idx - 5):idx]:
                    shown = self._verified(m["e"], conv, m["from"], keys, m.get("id", ""))
                    who = "reported" if m["from"] == target else "reporter" if m["from"] == pid else self.players.get(m["from"], {}).get("name", "someone")
                    context.append({"from": who, "text": shown if shown is not None else "(not shared by the reporter)",
                                    "verified": shown is not None, "at": m["at"]})
            rid = secrets.token_hex(6)
            self.mod["reports"].append({"id": rid, "at": self.clock(), "status": "open", "category": category,
                                        "details": clean_text(details, 800), "reporter": {"id": pid, "name": p["name"]},
                                        "target": {"id": target, "name": o["name"], "code": o["code"]}, "message": quoted,
                                        "context": context, **(where or {})})
            del self.mod["reports"][:-5000]
            self._changed(urgent=True)
        if also_block:
            return {"ok": True, "report": rid, **self.block(pid, secret, target)}
        with self.lock:
            return {"ok": True, "report": rid, **self._inbox(pid)}

    # --- the moderators (the console in server/social/__main__.py; never reachable with a player's secret) -------
    def _player_view(self, pid: str) -> dict:
        p = self.players.get(pid) or {}
        return {"id": pid, "name": p.get("name", "?"), "code": p.get("code", ""), "seen": p.get("seen"), "friends": len(p.get("friends", [])),
                "banned": self.mod["bans"].get(pid), "muted": self._muted(pid),
                "reports": sum(1 for r in self.mod["reports"] if r["target"]["id"] == pid)}

    def admin_reports(self, status: str = "") -> dict:
        with self.lock:
            self._tidy()
            rows = [dict(r, target_state=self._player_view(r["target"]["id"])) for r in reversed(self.mod["reports"]) if not status or r["status"] == status]
            return {"reports": rows[:500], "open": sum(1 for r in self.mod["reports"] if r["status"] == "open"), "players": len(self.players),
                    "banned": len(self.mod["bans"]), "muted": len(self.mod["mutes"]), "filter": self.mod["filter"], "log": self.mod["log"][-100:][::-1]}

    def admin_players(self, query: str = "") -> dict:
        q = str(query or "").strip().lower()
        with self.lock:
            qc = norm_code(q)
            hits = [pid for pid, p in self.players.items() if not q or q in p.get("name", "").lower() or (qc and qc in norm_code(p.get("code"))) or q == pid]
            hits.sort(key=lambda pid: -(self.players[pid].get("seen") or 0))
            return {"players": [self._player_view(pid) for pid in hits[:200]]}

    def admin_act(self, action: str, player: str = "", report: str = "", length: str = "", reason: str = "", by: str = "") -> dict:
        """dismiss | resolve (a report) | timeout | untimeout | ban | unban (a player, or the player a report is about)."""
        with self.lock:
            rep = next((r for r in self.mod["reports"] if r["id"] == report), None) if report else None
            pid = str(player or (rep["target"]["id"] if rep else ""))
            reason = clean_text(reason, 200)
            if action in ("dismiss", "resolve"):
                if rep is None:
                    raise SocialError("unknown report")
                rep["status"] = "dismissed" if action == "dismiss" else "resolved"
            elif action in ("timeout", "untimeout", "ban", "unban"):
                if pid not in self.players and not (action == "unban" and pid in self.mod["bans"]):
                    raise SocialError("unknown player")
                if action == "timeout":
                    if length not in TIMEOUTS:
                        raise SocialError("pick a length: " + ", ".join(TIMEOUTS))
                    self.mod["mutes"][pid] = {"until": self.clock() + TIMEOUTS[length], "reason": reason, "length": length}
                elif action == "untimeout":
                    self.mod["mutes"].pop(pid, None)
                elif action == "ban":
                    self.mod["bans"][pid] = {"at": self.clock(), "reason": reason}
                    self.mod["mutes"].pop(pid, None)
                    for o in self.players.values():                  # a banned player disappears from everyone's lists
                        for key in ("friends", "requests_in", "requests_out"):
                            if pid in o.get(key, []):
                                o[key].remove(pid)
                        o["invites"] = [i for i in o.get("invites", []) if i.get("from") != pid]
                    self._leave_all_groups(pid)                      # and from every group chat
                    p = self.players.get(pid)
                    if p:                                            # and their own lists go too, so an unban starts afresh
                        for key in ("friends", "requests_in", "requests_out"):
                            p[key] = []
                        p["invites"], p["room"], p["status"] = [], None, ""
                else:
                    self.mod["bans"].pop(pid, None)
                if rep is not None and rep["status"] == "open":
                    rep["status"] = "resolved"
            else:
                raise SocialError("unknown action")
            self.mod["log"].append({"at": self.clock(), "action": action, "player": pid, "name": self.players.get(pid, {}).get("name", ""),
                                    "report": report or "", "length": length or "", "reason": reason, "by": clean_name(by, "")})
            del self.mod["log"][:-1000]
            self._changed(urgent=True)
            return {"ok": True, "player": self._player_view(pid) if pid else None}

    def admin_filter(self, on=None, words=None) -> dict:
        with self.lock:
            if on is not None:
                self.mod["filter"]["on"] = bool(on)
            if words is not None:
                self.mod["filter"]["words"] = textfilter.clean_words(words)
            self._changed(urgent=True)
            return {"filter": self.mod["filter"], "base": sorted(textfilter.BASE_WORDS)}

    def goodbye(self, pid, secret) -> dict:
        """The player wants out: everything about them goes."""
        with self.lock:
            self._auth(pid, secret)
            self._forget(pid)
            self._changed(urgent=True)
            return {"ok": True}
