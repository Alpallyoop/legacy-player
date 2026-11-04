from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

SNAPSHOT_NAME = "lobby_state.json"


def _log(line: str) -> None:
    try:
        print(f"Legacy Player server: {line}", file=sys.stderr, flush=True)
    except Exception:
        pass


class StateStore:
    """On-disk server state: snapshot, admin token, invite pepper. Owner-only files."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass  # Windows ACLs are inherited from the parent folder

    def _write_atomic(self, name: str, data: bytes) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".tmp-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.root / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _secret(self, name: str, nbytes: int) -> bytes:
        """A secret of exactly `nbytes` bytes. A file that is there but empty, cut short or too long (a crash in the
        middle of a copy, a disk that filled up) is never used as it is: an empty access key would switch the key
        check off and an empty admin token would be "". It is replaced with a fresh secret, and the log says so."""
        path = self.root / name
        if path.exists():
            try:
                value = path.read_bytes()
            except OSError:
                value = b""
            if len(value) == nbytes:
                return value
            _log(f"{name} was damaged (wrong length); made a fresh one")
        value = secrets.token_bytes(nbytes)
        self._write_atomic(name, value)
        return value

    def pepper(self) -> bytes:
        return self._secret("invite_pepper.bin", 32)

    def access_key(self) -> str:
        """The key a server code carries. New people need the current one to create or join rooms and browse;
        players already inside a room use their own credentials and are not affected when it changes."""
        return self._secret("access_key.bin", 5).hex()

    def rotate_access_key(self) -> str:
        value = secrets.token_bytes(5)
        self._write_atomic("access_key.bin", value)
        return value.hex()

    def meet_secret(self) -> str:
        """The secret behind this server's meeting-point token (server/rendezvous.py). Only this server knows it."""
        return self._secret("meet_secret.bin", 32).hex()

    def rotate_meet_secret(self) -> str:
        value = secrets.token_bytes(32)
        self._write_atomic("meet_secret.bin", value)
        return value.hex()

    def admin_token(self) -> str:
        return self._secret("admin_token.bin", 32).hex()

    def save_snapshot(self, snapshot: dict) -> None:
        self._write_atomic(SNAPSHOT_NAME, json.dumps(snapshot, sort_keys=True).encode())

    def load_snapshot(self) -> dict | None:
        path = self.root / SNAPSHOT_NAME
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_bytes().decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a lobby snapshot")
            return data
        except (OSError, ValueError, RecursionError):     # ValueError covers bad JSON and bytes that are not UTF-8
            # A corrupt snapshot must not stop the server from starting.
            self.quarantine_snapshot()
            return None

    def quarantine_snapshot(self) -> None:
        """Move a snapshot that can't be used aside (kept for a look, never loaded again) so the server starts empty."""
        path = self.root / SNAPSHOT_NAME
        try:
            path.replace(self.root / (SNAPSHOT_NAME + ".corrupt"))
        except OSError:
            try:
                path.unlink()
            except OSError:
                pass

    def write_info(self, info: dict) -> None:
        self._write_atomic("server_info.json", json.dumps(info).encode())

    def read_info(self) -> dict | None:
        path = self.root / "server_info.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
