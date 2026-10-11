"""Who may open the friends service's moderation console, and how they prove it.

Accounts (owner and moderators) have a name, a password (hashlib.scrypt with a per-account salt) and a TOTP second
factor (RFC 6238: an authenticator app, 6 digits, 30 s, one step of clock drift either way, and a code is never accepted
twice). A wrong try counts against the account name and, in the HTTP layer, against the address; after 5 wrong tries in
a row the name is locked for 30 s, doubling with each further wrong try up to an hour. A good login opens a session kept
only in memory (random id, idle timeout, absolute lifetime), sent as an HttpOnly, SameSite=Strict cookie (Secure over
HTTPS), with a separate CSRF token every change must carry.

Everything is kept in the service's data folder with owner-only permissions, never in the repository:
  admins.json        accounts (password hashes, TOTP secrets, last used step), pending set-ups and moderator invites
  admin_audit.log    logins, failed logins, lockouts, logouts, set-ups, invites and moderator actions (no addresses)

The first owner is made on the computer that runs the service: in Legacy Player (Friends > Your service > Set up the
moderation console) or with   python -m server.social --dir social --create-admin <name>.  Owners invite moderators
with a one-time code; the moderator then picks their own password and sets up their own authenticator.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import purecrypto as pc

ISSUER = "Legacy Player friends"
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD = 10
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
PENDING_FOR = 30 * 60                        # a started set-up must be finished within half an hour
INVITE_FOR = 48 * 3600
FREE_TRIES = 5
LOCK_BASE = 30.0
LOCK_MAX = 3600.0
SESSION_IDLE = 30 * 60
SESSION_MAX = 12 * 3600
MAX_SESSIONS = 200
AUDIT_MAX_BYTES = 1_000_000


class AuthError(ValueError):
    """Safe to show: never says which part of a login was wrong."""


class Locked(AuthError):
    def __init__(self, seconds: float) -> None:
        self.seconds = max(1, int(seconds + 0.999))
        super().__init__(f"Too many wrong tries for this account. Wait {self.seconds} s and try again.")


def write_private(path: Path, data: bytes) -> None:
    """Write a secret file atomically, readable only by this user (chmod 600; on Windows the inherited permissions
    are replaced by the current user only, when icacls is there)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + "-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    restrict(path)


def restrict(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if sys.platform == "win32":
        user = os.environ.get("USERNAME")
        if user:
            try:
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"], capture_output=True,
                               timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.SubprocessError):
                pass


def _hash(password: str, salt: bytes, params: dict) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=params["n"], r=params["r"], p=params["p"],
                          maxmem=128 * 1024 * 1024, dklen=32)


_DUMMY_SALT = secrets.token_bytes(16)


class AdminStore:
    """Accounts on disk (read fresh for every check, so a --create-admin run while the service is up just works)."""

    def __init__(self, folder: Path, clock=time.time) -> None:
        self.folder = Path(folder)
        self.path = self.folder / "admins.json"
        self.audit_path = self.folder / "admin_audit.log"
        self.clock = clock
        self.lock = threading.RLock()
        self._fails: dict[str, list] = {}       # account name -> [wrong tries in a row, locked until]

    # --- storage -----------------------------------------------------------------------------------------------------
    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as exc:
            raise AuthError(f"The account file could not be read ({type(exc).__name__}).") from exc
        if not isinstance(data, dict):
            data = {}
        for key in ("users", "pending", "invites"):
            if not isinstance(data.get(key), dict):
                data[key] = {}
        return data

    def _write(self, data: dict) -> None:
        write_private(self.path, json.dumps(data, indent=1).encode("utf-8"))

    def audit(self, event: str, user: str = "", detail: str = "") -> None:
        """One line per event: when, what, which account. Never an address or a password."""
        line = json.dumps({"at": round(self.clock(), 1), "event": event, "user": str(user)[:40], "detail": str(detail)[:200]}) + "\n"
        with self.lock:
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                if self.audit_path.exists() and self.audit_path.stat().st_size > AUDIT_MAX_BYTES:
                    keep = self.audit_path.read_bytes()[-AUDIT_MAX_BYTES // 2:]
                    write_private(self.audit_path, keep[keep.find(b"\n") + 1:])
                new = not self.audit_path.exists()
                with open(self.audit_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
                if new:
                    restrict(self.audit_path)
            except OSError:
                pass

    def audit_tail(self, n: int = 200) -> list[dict]:
        try:
            lines = self.audit_path.read_text(encoding="utf-8").splitlines()[-n:]
        except OSError:
            return []
        out = []
        for line in reversed(lines):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    # --- accounts ----------------------------------------------------------------------------------------------------
    def has_accounts(self) -> bool:
        with self.lock:
            return bool(self._read()["users"])

    def accounts(self) -> list[dict]:
        with self.lock:
            users = self._read()["users"]
            return [{"name": n, "role": u.get("role", "moderator"), "created": u.get("created"), "last_login": u.get("last_login")}
                    for n, u in sorted(users.items())]

    def begin(self, name: str, password: str, role: str = "owner", invite: str = "") -> dict:
        """Start an account: checked name and password, a new TOTP secret to put in an authenticator app. Nothing can log
        in with it until finish() sees one good code."""
        name = str(name or "").strip()
        if not NAME_RE.match(name):
            raise AuthError("Pick a name of 3 to 32 letters, digits, dots, dashes or underscores.")
        if len(str(password or "")) < MIN_PASSWORD:
            raise AuthError(f"Pick a password of at least {MIN_PASSWORD} characters.")
        if role not in ("owner", "moderator"):
            raise AuthError("unknown role")
        with self.lock:
            data = self._read()
            now = self.clock()
            data["pending"] = {k: v for k, v in data["pending"].items() if v.get("expires", 0) > now}
            if name.lower() in {n.lower() for n in data["users"]}:
                raise AuthError("That name is taken. Pick another.")
            salt = secrets.token_bytes(16)
            secret = pc.new_totp_secret()
            data["pending"][name] = {"salt": salt.hex(), "hash": _hash(password, salt, SCRYPT).hex(), "params": SCRYPT,
                                     "totp": secret, "role": role, "expires": now + PENDING_FOR, "invite": invite}
            self._write(data)
        return {"name": name, "secret": secret, "uri": pc.otpauth_uri(secret, name, ISSUER)}

    def finish(self, name: str, code: str) -> dict:
        """One good code from the authenticator turns the started account on."""
        with self.lock:
            data = self._read()
            pend = data["pending"].get(str(name or ""))
            now = self.clock()
            if not pend or pend.get("expires", 0) <= now:
                raise AuthError("That set-up has expired or was never started. Start again.")
            step = pc.totp_match(pc.totp_secret_bytes(pend["totp"]), code, now)
            if step is None:
                pend["tries"] = int(pend.get("tries", 0)) + 1
                if pend["tries"] >= FREE_TRIES:                 # no guessing the code: five wrong ones end the set-up
                    del data["pending"][name]
                    self._write(data)
                    raise AuthError("Too many wrong codes. Start the set-up again.")
                self._write(data)
                raise AuthError("That code is not right. Check the clock on your phone and type the newest code.")
            if pend.get("invite"):
                inv = data["invites"].get(pend["invite"])
                if not inv or inv.get("expires", 0) <= now:
                    raise AuthError("That invite has expired or was already used. Ask for a new one.")
                del data["invites"][pend["invite"]]
            if name.lower() in {n.lower() for n in data["users"]}:
                raise AuthError("That name is taken. Pick another.")
            del data["pending"][name]
            data["users"][name] = {"salt": pend["salt"], "hash": pend["hash"], "params": pend.get("params", SCRYPT),
                                   "totp": pend["totp"], "role": pend["role"], "last_step": step, "created": now}
            self._write(data)
        self.audit("account_created", name, pend["role"])
        return {"name": name, "role": pend["role"]}

    def remove(self, name: str, by: str) -> None:
        with self.lock:
            data = self._read()
            if name not in data["users"]:
                raise AuthError("No such account.")
            if data["users"][name].get("role") == "owner" and sum(1 for u in data["users"].values() if u.get("role") == "owner") <= 1:
                raise AuthError("The last owner can't be removed.")
            del data["users"][name]
            self._write(data)
        self.audit("account_removed", by, name)

    # --- invites -------------------------------------------------------------------------------------------------------
    @staticmethod
    def _invite_key(code: str) -> str:
        return hashlib.sha256(("LP-invite|" + re.sub(r"[^A-Za-z0-9]", "", str(code or "")).upper()).encode()).hexdigest()

    def create_invite(self, by: str, role: str = "moderator") -> dict:
        """A one-time code for a new moderator (only its hash is kept)."""
        raw = pc.b64e(secrets.token_bytes(15)).upper().replace("-", "X").replace("_", "Y")[:20]
        code = "LPI-" + "-".join(raw[i:i + 5] for i in range(0, 20, 5))
        with self.lock:
            data = self._read()
            now = self.clock()
            data["invites"] = {k: v for k, v in data["invites"].items() if v.get("expires", 0) > now}
            if len(data["invites"]) >= 20:
                raise AuthError("Too many open invites. Wait for some to be used or to expire.")
            data["invites"][self._invite_key(code)] = {"role": role if role in ("owner", "moderator") else "moderator",
                                                        "by": by, "expires": now + INVITE_FOR}
            self._write(data)
        self.audit("invite_created", by, role)
        return {"code": code, "expires": self.clock() + INVITE_FOR, "role": role}

    def begin_from_invite(self, code: str, name: str, password: str) -> dict:
        key = self._invite_key(code)
        with self.lock:
            inv = self._read()["invites"].get(key)
            if not inv or inv.get("expires", 0) <= self.clock():
                raise AuthError("That invite code is not valid. Check it, or ask for a new one.")
            return self.begin(name, password, inv.get("role", "moderator"), invite=key)

    # --- logging in -----------------------------------------------------------------------------------------------------
    def _check_lock(self, name: str) -> None:
        tries = self._fails.get(name.lower())
        if tries and tries[1] > self.clock():
            raise Locked(tries[1] - self.clock())

    def _failed(self, name: str) -> None:
        key = name.lower()
        if key not in self._fails and len(self._fails) > 5000:
            self._fails.clear()                             # bounded; a flood of made-up names forgets old counts
        tries = self._fails.setdefault(key, [0, 0.0])
        tries[0] += 1
        if tries[0] >= FREE_TRIES:
            tries[1] = self.clock() + min(LOCK_MAX, LOCK_BASE * 2 ** (tries[0] - FREE_TRIES))
            self.audit("locked", name[:40], f"{tries[0]} wrong tries")

    def login(self, name: str, password: str, code: str) -> dict:
        """{name, role} for the right name + password + a fresh authenticator code; AuthError otherwise (the same words
        whatever was wrong)."""
        name = str(name or "").strip()[:64]
        with self.lock:
            self._check_lock(name)
            user = self._read()["users"].get(name)
            if user is None:
                _hash(str(password or ""), _DUMMY_SALT, SCRYPT)       # the same work, so timing does not tell names apart
                ok = False
            else:
                ok = hmac.compare_digest(_hash(str(password or ""), bytes.fromhex(user["salt"]), user.get("params", SCRYPT)),
                                         bytes.fromhex(user["hash"]))
            step = pc.totp_match(pc.totp_secret_bytes(user["totp"]), code, self.clock()) if ok else None
            if ok and (step is None or step <= int(user.get("last_step", -1))):
                ok = False                                  # wrong, or a code that was already used
            if not ok:
                self._failed(name)
                self.audit("login_failed", name if user is not None else "(unknown name)")
                self._check_lock(name)
                raise AuthError("That name, password or code is not right.")
            data = self._read()
            data["users"][name]["last_step"] = step
            data["users"][name]["last_login"] = self.clock()
            self._write(data)
            self._fails.pop(name.lower(), None)
        self.audit("login", name)
        return {"name": name, "role": user.get("role", "moderator")}


class Sessions:
    """Console sessions, only in memory: a restart signs everyone out."""

    def __init__(self, clock=time.monotonic, idle: float = SESSION_IDLE, lifetime: float = SESSION_MAX) -> None:
        self.clock, self.idle, self.lifetime = clock, idle, lifetime
        self._by_id: dict[str, dict] = {}
        self.lock = threading.Lock()

    def create(self, name: str, role: str) -> dict:
        with self.lock:
            if len(self._by_id) >= MAX_SESSIONS:
                oldest = min(self._by_id, key=lambda k: self._by_id[k]["last"])
                del self._by_id[oldest]
            sid = secrets.token_urlsafe(32)
            now = self.clock()
            self._by_id[sid] = {"name": name, "role": role, "csrf": secrets.token_urlsafe(24), "made": now, "last": now}
            return {"id": sid, **self._by_id[sid]}

    def get(self, sid: str) -> dict | None:
        if not sid:
            return None
        with self.lock:
            s = self._by_id.get(sid)
            now = self.clock()
            if s is None:
                return None
            if now - s["last"] > self.idle or now - s["made"] > self.lifetime:
                del self._by_id[sid]
                return None
            s["last"] = now
            return dict(s, id=sid)

    def end(self, sid: str) -> None:
        with self.lock:
            self._by_id.pop(sid, None)

    def end_user(self, name: str) -> None:
        with self.lock:
            for sid in [k for k, v in self._by_id.items() if v["name"] == name]:
                del self._by_id[sid]
