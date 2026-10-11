"""No friends-service data or secret ever sits in the repository: moderator keys, console accounts, sessions, players,
app identity keys or a data folder. .gitignore keeps them out, and this test fails if one was committed anyway."""
import fnmatch
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_NAMES = ("moderator.key", "*.key", "admins.json", "admin*.json", "admin_audit.log", "*sessions*.json", "players.json",
                "players.json.corrupt-*", "friends_identity.key", "key.pem", "user_data*.json")
SECRET_DIRS = ("social", "data", "LegacyPlayerData", "sessions")
IGNORE_LINES = ("/social/", "moderator.key", "*.key", "admin*.json", "admin_audit.log", "*sessions*.json", "/data/", "LegacyPlayerData/")


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        out = None
    if out is not None and out.returncode == 0 and out.stdout:
        return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]
    return [str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.rglob("*")
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts and ".claude" not in p.parts]


class NoSecretsInTheRepository(unittest.TestCase):
    def test_no_secret_files_are_tracked(self):
        bad = []
        for path in tracked_files():
            parts = path.split("/")
            name = parts[-1]
            if any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_NAMES):
                bad.append(path)
            elif parts[0] in SECRET_DIRS:                    # a data folder at the top of the checkout
                bad.append(path)
        self.assertEqual([], bad, "secrets or service data are in the repository")

    def test_gitignore_keeps_them_out(self):
        lines = {line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
        for needed in IGNORE_LINES:
            self.assertIn(needed, lines)
        # and the code of the friends service itself is never caught by those patterns
        try:
            out = subprocess.run(["git", "check-ignore", "server/social/__init__.py", "server/social/admin_auth.py"], cwd=ROOT,
                                 capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git is not available")
        if out.returncode == 128:
            self.skipTest("not a git checkout")
        self.assertEqual(b"", out.stdout.strip())


if __name__ == "__main__":
    unittest.main()
