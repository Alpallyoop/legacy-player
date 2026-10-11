"""Legacy Player's side of the friends service (server/social): one identity per app, kept in the catalog, small JSON
calls over https, and end-to-end encryption of every message.

Encryption (server/social/e2e.py): this app has one long-term X25519 key pair. The private key stays in a file in the
data folder (`friends_identity.key`, owner-only permissions) and never leaves this computer; the public key goes to the
service with hello and every heartbeat. Friends' keys are pinned the first time they are seen; a later change is shown
as a warning in the conversation, and both people can compare a short safety code. Messages are sealed here and opened
here; the service only ever stores envelopes it cannot read. Reporting a message hands the service that message's key
(and the few before it), so moderators can read exactly that, from the service's own copy.

A friends link may carry the service's certificate fingerprint:  https://203.0.113.5:8791/#pin=<sha256 hex>. Services run by
Legacy Player use a self-signed certificate, so instead of a certificate authority the app checks that fingerprint
(the same way server codes work). Links without a pin are checked the normal way."""
from __future__ import annotations

import hashlib
import http.client
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from server.social import e2e
from server.social import purecrypto as pc

from .version import VERSION

KEY_FILE = "friends_identity.key"
REPORT_CONTEXT = 5


class FriendsError(ValueError):
    pass


def split_link(link: str) -> tuple[str, str]:
    """('https://host:port', 'PIN') from a friends link; the pin is '' when the link has none."""
    base, _, frag = str(link or "").strip().partition("#")
    pin = re.sub(r"[^0-9a-fA-F]", "", (parse_qs(frag).get("pin") or [""])[0]).lower()
    return base.rstrip("/"), pin if len(pin) == 64 else ""


def make_link(host: str, port: int, pin: str) -> str:
    host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"https://{host}:{int(port)}/#pin={pin.lower()}"


def pinned_request_full(url: str, pin: str, body: bytes | None, headers: dict, timeout: float, method: str = "POST",
                        limit: int = 512_000) -> tuple[int, bytes, dict]:
    """One HTTPS request that only goes ahead when the server's certificate has the expected SHA-256 fingerprint.
    Returns (status, body, headers) with header names in lower case."""
    u = urlsplit(url)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE                    # the fingerprint below is the check
    conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=timeout, context=context)
    try:
        conn.connect()
        der = conn.sock.getpeercert(binary_form=True) or b""
        if hashlib.sha256(der).hexdigest() != pin:
            raise FriendsError("That friends service is not the one your link is for (its certificate changed). "
                               "Ask whoever runs it for the link again.")
        conn.request(method, (u.path or "/") + (f"?{u.query}" if u.query else ""), body=body, headers=headers)
        response = conn.getresponse()
        return response.status, response.read(limit), {k.lower(): v for k, v in response.getheaders()}
    finally:
        conn.close()


def pinned_request(url: str, pin: str, body: bytes | None, headers: dict, timeout: float, method: str = "POST",
                   limit: int = 512_000) -> tuple[int, bytes]:
    status, raw, _ = pinned_request_full(url, pin, body, headers, timeout, method, limit)
    return status, raw


def address_ok(url: str) -> bool:
    url = split_link(url)[0]
    return bool(url) and (url.startswith("https://") or re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?(/|$)", url) is not None)


class IdentityKey:
    """This app's long-term key pair for end-to-end encryption, in one owner-only file in the data folder."""

    def __init__(self, folder: Path | None) -> None:
        self.path = Path(folder) / KEY_FILE if folder else None
        self._pair: tuple[bytes, bytes] | None = None
        self._lock = threading.Lock()
        self.cache: dict = {}                              # X25519 results per peer key (memory only)

    def pair(self) -> tuple[bytes, bytes]:
        with self._lock:
            if self._pair is None:
                self._pair = self._load() or self._make()
            return self._pair

    def public_b64(self) -> str:
        return pc.b64e(self.pair()[1])

    def _load(self) -> tuple[bytes, bytes] | None:
        if self.path is None:
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            private = pc.b64d(data["private"], 32)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise FriendsError(f"This app's encryption key file ({KEY_FILE}) can't be read. Restore it from a backup, "
                               "or make a new key under Friends > Your encryption key.") from exc
        return pc.x25519_keypair(private)

    def _make(self) -> tuple[bytes, bytes]:
        pair = pc.x25519_keypair()
        self._save(pair)
        return pair

    def _save(self, pair: tuple[bytes, bytes]) -> None:
        if self.path is None:
            return
        from server.social.admin_auth import write_private
        write_private(self.path, json.dumps({"v": 1, "kind": "x25519", "private": pc.b64e(pair[0]), "public": pc.b64e(pair[1]),
                                             "made": int(time.time())}).encode("utf-8"))

    def replace(self) -> None:
        """A new key pair. Messages sealed for the old key can no longer be opened here."""
        with self._lock:
            pair = pc.x25519_keypair()
            self._save(pair)
            self._pair = pair
            self.cache = {}


class FriendsClient:
    def __init__(self, catalog, opener=urllib.request.urlopen, timeout: float = 8.0, key_dir: Path | None = None) -> None:
        self.catalog, self.opener, self.timeout = catalog, opener, timeout
        self.key = IdentityKey(key_dir if key_dir is not None else getattr(catalog, "dir", None))
        self.admin_session: dict = {}                      # a moderator's console session: memory only, never on disk
        self._pubs: dict[str, str] = {}                    # the latest public keys the service gave for friends / members

    # --- where and who ---------------------------------------------------------------------------------------
    def link(self) -> str:
        return str(self.catalog.settings().get("friends_server") or "").strip()

    def server(self) -> str:
        return split_link(self.link())[0]

    def pin(self) -> str:
        return split_link(self.link())[1]

    def enabled(self) -> bool:
        return address_ok(self.server())

    def identity(self) -> dict:
        me = self.catalog.data.get("friends") or {}
        return me if me.get("server") == self.server() and me.get("id") and me.get("secret") else {}

    def _send(self, path: str, data: bytes | None, headers: dict, method: str = "POST") -> tuple[int, bytes, dict]:
        url = self.server() + path
        headers = {"User-Agent": f"LegacyPlayer/{VERSION}", **headers}
        if self.pin():
            try:
                return pinned_request_full(url, self.pin(), data, headers, self.timeout, method)
            except FriendsError:
                raise
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                raise FriendsError(f"Could not reach the friends service ({exc}).") from exc
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                hdrs = {k.lower(): v for k, v in (response.headers.items() if getattr(response, "headers", None) else [])}
                return getattr(response, "status", 200), response.read(512_000), hdrs
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(64_000), {}
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise FriendsError(f"Could not reach the friends service ({getattr(exc, 'reason', exc)}).") from exc

    def _call(self, body: dict) -> dict:
        if not address_ok(self.server()):
            raise FriendsError("Set the friends service address under Settings > Friends first (it must start with https://).")
        status, raw, _ = self._send("/", json.dumps({**body, "e2e": 1}).encode("utf-8"), {"Content-Type": "application/json"})
        try:
            out = json.loads(raw)
        except ValueError:
            out = {}
        if status >= 400:
            raise FriendsError(out.get("error") or f"The friends service answered {status}.")
        if not out.get("ok"):
            raise FriendsError(out.get("error") or "The friends service refused that.")
        return out

    # --- the moderation console (a moderator elsewhere logs in; the hosting computer uses its local key) -------------
    def admin(self, key: str | None, path: str, body: dict | None = None) -> dict:
        """GET when body is None, otherwise POST. With `key` (only accepted from the computer that runs the service), or
        with this app's console session (admin_login)."""
        if not address_ok(self.server()):
            raise FriendsError("No friends service is set.")
        headers = {}
        if key:
            headers["X-Admin-Token"] = key
        else:
            s = self.admin_session
            if not s or s.get("server") != self.server():
                raise FriendsError("Log in to the moderation console first.")
            headers["Cookie"] = f"lp_admin={s['cookie']}"
            headers["X-CSRF-Token"] = s["csrf"]
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, raw, _ = self._send(path, data, headers, "GET" if body is None else "POST")
        try:
            out = json.loads(raw)
        except ValueError:
            out = {}
        if status == 401:
            if not key:
                self.admin_session = {}
            raise FriendsError("Your moderation login has ended. Log in again." if not key else
                               "That moderator key was not accepted by this friends service.")
        if status >= 400 or not out.get("ok"):
            raise FriendsError(out.get("error") or f"The friends service answered {status}.")
        return out

    def admin_login(self, name: str, password: str, code: str) -> dict:
        if not address_ok(self.server()):
            raise FriendsError("Join a friends service first.")
        status, raw, headers = self._send("/admin/login", json.dumps({"name": name, "password": password, "code": code}).encode(),
                                          {"Content-Type": "application/json"})
        try:
            out = json.loads(raw)
        except ValueError:
            out = {}
        if status >= 400 or not out.get("ok"):
            raise FriendsError(out.get("error") or f"The friends service answered {status}.")
        jar = SimpleCookie()
        try:
            jar.load(headers.get("set-cookie", ""))
        except Exception:
            pass
        if "lp_admin" not in jar or not jar["lp_admin"].value:
            raise FriendsError("The friends service did not open a session.")
        self.admin_session = {"server": self.server(), "cookie": jar["lp_admin"].value, "csrf": out["csrf"],
                              "name": out.get("name", ""), "role": out.get("role", "")}
        return {"name": out.get("name", ""), "role": out.get("role", "")}

    def admin_logout(self) -> None:
        if self.admin_session:
            try:
                self.admin(None, "/admin/logout", {})
            except FriendsError:
                pass
        self.admin_session = {}

    def _auth(self) -> dict:
        me = self.identity()
        if not me:
            raise FriendsError("Say hello to the friends service first (the Friends page does it with one click).")
        return {"id": me["id"], "secret": me["secret"]}

    # --- pinned keys (trust on first use) ---------------------------------------------------------------------------
    def _pins(self) -> dict:
        allp = self.catalog.data.setdefault("friends_pins", {})
        if not isinstance(allp, dict):
            allp = self.catalog.data["friends_pins"] = {}
        return allp.setdefault(self.server(), {})

    def _pin(self, pid: str, pub: str) -> bool:
        """Remember a friend's key the first time; a different key later is taken (they may have a new computer) but
        marked as changed until this player says they checked it. True when something changed."""
        if not pid or not pub:
            return False
        pins = self._pins()
        entry = pins.get(pid)
        now = int(time.time())
        if entry is None:
            pins[pid] = {"current": pub, "keys": [pub], "first": now, "changed": 0, "verified": False}
            return True
        if entry.get("current") == pub:
            return False
        keys = [k for k in entry.get("keys", []) if k != pub][-4:] + [pub]
        entry.update({"current": pub, "keys": keys, "changed": now, "verified": False})
        return True

    def pin_state(self, pid: str) -> dict:
        e = self._pins().get(pid) or {}
        return {"pinned": bool(e), "changed": e.get("changed", 0), "verified": bool(e.get("verified")), "current": e.get("current", "")}

    def mark_verified(self, pid: str) -> None:
        e = self._pins().get(pid)
        if e:
            e["verified"] = True
            e["changed"] = 0
            self.catalog.save()

    def safety_code(self, pid: str) -> str:
        me = self.identity()
        pub = self._pins().get(pid, {}).get("current")
        if not me or not pub:
            return ""
        return e2e.safety_code(me["id"], self.key.pair()[1], pid, pc.b64d(pub, 32))

    def group_safety_code(self, members: list) -> str:
        me = self.identity()
        keys = {}
        for m in members:
            pub = self.key.public_b64() if m["id"] == me.get("id") else self._pins().get(m["id"], {}).get("current") or m.get("pub")
            if not pub:
                return ""
            keys[m["id"]] = pc.b64d(pub, 32)
        return e2e.group_safety_code(keys)

    # --- opening sealed messages --------------------------------------------------------------------------------------
    def _open(self, env) -> tuple[str | None, bytes | None, str]:
        """(text, key, problem). Problem is '' when fine, 'unknown-key' when the sender's key is not one this app pinned."""
        me = self.identity()
        if not isinstance(env, dict) or not me:
            return None, None, "unreadable"
        private, public = self.key.pair()
        try:
            text, key = e2e.open_envelope(env, me["id"], private, public, self.key.cache)
        except e2e.E2EError:
            return None, None, "unreadable"
        sender = env.get("from")
        problem = ""
        if sender != me["id"]:
            known = self._pins().get(sender, {}).get("keys", [])
            if env.get("spub") not in known:
                problem = "unknown-key"
        elif env.get("spub") != self.key.public_b64():
            problem = "old-key"
        return text, key, problem

    def _open_rows(self, rows: list) -> list:
        out = []
        for m in rows:
            text, _, problem = self._open(m.get("e"))
            row = {k: v for k, v in m.items() if k != "e"}
            row["text"] = text if text is not None else "(this message can't be opened on this computer)"
            row["sealed"] = text is not None
            row["problem"] = problem if text is not None else "unreadable"
            out.append(row)
        return out

    def _decorate(self, inbox: dict) -> dict:
        """Pin keys from the inbox, open conversation previews, and say who can be messaged."""
        changed = False
        for f in inbox.get("friends", []):
            changed |= self._pin(f["id"], f.get("pub", ""))
            self._pubs[f["id"]] = f.get("pub", "")
        for g in inbox.get("groups", []):
            for m in g.get("members", []):
                if m.get("pub") and m["id"] != self.identity().get("id"):
                    changed |= self._pin(m["id"], m["pub"])
                    self._pubs[m["id"]] = m["pub"]
        if changed:
            self.catalog.save()
        for f in inbox.get("friends", []):
            st = self.pin_state(f["id"])
            f["e2e"] = bool(f.get("pub"))
            f["key_changed"] = bool(st["changed"]) and not st["verified"]
            f.pop("pub", None)
        for c in inbox.get("conversations", []):
            text, _, _ = self._open(c.pop("last_e", None))
            c["last"] = text if text is not None else "(encrypted message)"
            c["e2e"] = bool(c.pop("pub", ""))
        for g in inbox.get("groups", []):
            text, _, _ = self._open(g.pop("last_e", None))
            who = next((m["name"] for m in g.get("members", []) if m["id"] == g.get("last_from")), "")
            g["last"] = (text if text is not None else "(encrypted message)") if g.get("last_id") else ""
            g["last_name"] = who
            g["can_post"] = all(m.get("pub") for m in g.get("members", []))
            g["outdated"] = [m["name"] for m in g.get("members", []) if not m.get("pub")]
            for m in g.get("members", []):
                m.pop("pub", None)
        me = inbox.get("me") or {}
        me["e2e"] = me.pop("pub", "") == self.key.public_b64()
        return inbox

    # --- operations -------------------------------------------------------------------------------------------
    def hello(self, name: str) -> dict:
        out = self._call({"op": "hello", "name": name, "pub": self.key.public_b64()})
        self.catalog.data["friends"] = {"server": self.server(), "id": out["id"], "secret": out["secret"], "code": out["code"]}
        self.catalog.save()
        return {"code": out["code"], "name": out["name"]}

    def heartbeat(self, name: str, status: str = "", room: dict | None = None, requests_open: bool | None = None) -> dict:
        out = self._call({"op": "heartbeat", **self._auth(), "name": name, "status": status, "room": room, "requests_open": requests_open,
                          "pub": self.key.public_b64()})
        return self._decorate(out)

    def _inbox_call(self, body: dict) -> dict:
        return self._decorate(self._call({**body, **self._auth()}))

    def report(self, player: str, category: str, details: str = "", message: str = "", block: bool = False, group: str = "") -> dict:
        """A report. For a message, the keys of that message and the few before it go with it (and nothing else), so the
        moderators can open exactly those from the service's own copy."""
        keys = {}
        if message:
            raw = self._call({"op": "group_thread", **self._auth(), "group": group} if group else
                             {"op": "thread", **self._auth(), "friend": player})["messages"]
            idx = next((i for i, m in enumerate(raw) if m.get("id") == message), None)
            if idx is None:
                raise FriendsError("That message is no longer here, so it can't be reported. You can still report the player.")
            for m in raw[max(0, idx - REPORT_CONTEXT):idx + 1]:
                _, key, _ = self._open(m.get("e"))
                if key is not None:
                    keys[m["id"]] = pc.b64e(key)
        out = self._call({"op": "report", **self._auth(), "player": player, "category": category, "details": details,
                          "message": message, "block": bool(block), "keys": keys, "group": group})
        return self._decorate(out)

    def request(self, code: str) -> dict:
        return self._inbox_call({"op": "request", "code": code})

    def decide(self, other: str, accept: bool) -> dict:
        return self._inbox_call({"op": "decide", "from": other, "accept": bool(accept)})

    def remove(self, other: str) -> dict:
        return self._inbox_call({"op": "remove", "friend": other})

    def invite(self, to: str, invite_code: str, game: str, server_code: str = "") -> dict:
        return self._call({"op": "invite", **self._auth(), "to": to, "invite_code": invite_code, "game": game, "server_code": server_code})

    def dismiss_invite(self, other: str) -> dict:
        return self._inbox_call({"op": "dismiss_invite", "from": other})

    def _recipients(self, ids: list, names: dict) -> dict:
        me = self.identity()
        out = {me["id"]: self.key.pair()[1]}
        for i in ids:
            if i == me["id"]:
                continue
            pub = self._pubs.get(i)
            if not pub:
                raise FriendsError(f"Update Legacy Player to message {names.get(i, 'them')}: their app is too old for encrypted messages.")
            out[i] = pc.b64d(pub, 32)
        return out

    def message(self, to: str, text: str) -> dict:
        """Seal and send. If the service says a key changed meanwhile, refresh once and seal again."""
        text = str(text or "").strip()
        if not text:
            raise FriendsError("Type something first.")
        if len(text) > 500:
            raise FriendsError("That message is too long (500 characters at most).")
        me = self._auth()
        if to not in self._pubs:
            self.thread(to)                                  # learns (and pins) their current key
        for attempt in (0, 1):
            recipients = self._recipients([to], {})
            env = e2e.seal(*self.key.pair(), me["id"], e2e.direct_conv(me["id"], to), recipients, text)
            try:
                out = self._call({"op": "message", **me, "to": to, "envelope": env})
                break
            except FriendsError as exc:
                if attempt or "key" not in str(exc).lower():
                    raise
                self.thread(to)
        out["messages"] = self._open_rows(out.get("messages", []))
        return out

    def thread(self, other: str) -> dict:
        out = self._call({"op": "thread", **self._auth(), "friend": other})
        if out.get("pub"):
            if self._pin(other, out["pub"]):
                self.catalog.save()
            self._pubs[other] = out["pub"]
        st = self.pin_state(other)
        out["messages"] = self._open_rows(out.get("messages", []))
        out["e2e"] = bool(out.pop("pub", ""))
        out["key_changed"] = bool(st["changed"]) and not st["verified"]
        out["changed_at"] = st["changed"]
        out["safety_code"] = self.safety_code(other)
        return out

    def block(self, other: str) -> dict:
        return self._inbox_call({"op": "block", "player": other})

    def unblock(self, other: str) -> dict:
        return self._inbox_call({"op": "unblock", "player": other})

    def clear_thread(self, other: str) -> dict:
        return self._inbox_call({"op": "clear_thread", "friend": other})

    def read_all(self) -> dict:
        return self._inbox_call({"op": "read_all"})

    # --- group chats ----------------------------------------------------------------------------------------------------
    def group_create(self, name: str, members: list) -> dict:
        return self._inbox_call({"op": "group_create", "name": name, "members": list(members)})

    def group_add(self, group: str, member: str) -> dict:
        return self._inbox_call({"op": "group_add", "group": group, "member": member})

    def group_remove(self, group: str, member: str) -> dict:
        return self._inbox_call({"op": "group_remove", "group": group, "member": member})

    def group_rename(self, group: str, name: str) -> dict:
        return self._inbox_call({"op": "group_rename", "group": group, "name": name})

    def group_leave(self, group: str) -> dict:
        return self._inbox_call({"op": "group_leave", "group": group})

    def group_clear(self, group: str) -> dict:
        return self._inbox_call({"op": "group_clear", "group": group})

    def _group_out(self, out: dict) -> dict:
        changed = False
        for m in out.get("members", []):
            if m.get("pub") and m["id"] != self.identity().get("id"):
                changed |= self._pin(m["id"], m["pub"])
                self._pubs[m["id"]] = m["pub"]
        if changed:
            self.catalog.save()
        out["safety_code"] = self.group_safety_code(out.get("members", []))
        out["can_post"] = all(m.get("pub") for m in out.get("members", []))
        out["outdated"] = [m["name"] for m in out.get("members", []) if not m.get("pub")]
        for m in out.get("members", []):
            st = self.pin_state(m["id"])
            m["key_changed"] = bool(st["changed"]) and not st["verified"]
            m.pop("pub", None)
        out["messages"] = self._open_rows(out.get("messages", []))
        return out

    def group_thread(self, group: str) -> dict:
        return self._group_out(self._call({"op": "group_thread", **self._auth(), "group": group}))

    def group_message(self, group: str, text: str) -> dict:
        text = str(text or "").strip()
        if not text:
            raise FriendsError("Type something first.")
        if len(text) > 500:
            raise FriendsError("That message is too long (500 characters at most).")
        me = self._auth()
        for attempt in (0, 1):
            raw = self._call({"op": "group_thread", **me, "group": group})       # the members right now, with their keys
            names = {m["id"]: m["name"] for m in raw.get("members", [])}
            for m in raw.get("members", []):
                if m.get("pub") and m["id"] != me["id"]:
                    if self._pin(m["id"], m["pub"]):
                        self.catalog.save()
                    self._pubs[m["id"]] = m["pub"]
                elif m["id"] != me["id"]:
                    self._pubs.pop(m["id"], None)
            recipients = self._recipients([m["id"] for m in raw.get("members", [])], names)
            env = e2e.seal(*self.key.pair(), me["id"], e2e.group_conv(group), recipients, text)
            try:
                return self._group_out(self._call({"op": "group_message", **me, "group": group, "envelope": env}))
            except FriendsError as exc:
                if attempt or not ("key" in str(exc).lower() or "changed" in str(exc).lower()):
                    raise
        raise FriendsError("The group changed while sending. Try again.")

    def replace_key(self) -> dict:
        """A new key pair for this app (for example after a backup of the data folder leaked). Friends see that it
        changed; messages sealed for the old key can no longer be opened here."""
        self.key.replace()
        return {"public": self.key.public_b64()}

    def goodbye(self) -> dict:
        try:
            return self._call({"op": "goodbye", **self._auth()})
        finally:
            self.catalog.data["friends"] = {}
            pins = self.catalog.data.get("friends_pins")
            if isinstance(pins, dict):
                pins.pop(self.server(), None)                # this service's pinned keys go with the identity
            self.catalog.save()
