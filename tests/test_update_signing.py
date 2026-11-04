"""Update signing (audit 2026-11-04, open item 1): Ed25519 matches RFC 8032, and once launcher/version.py lists a key an
update needs a valid signature over its tag, name and SHA-256. Without a key nothing changes."""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import ed25519, selfupdate
from launcher import version as lpversion
from tests.test_selfupdate import fake_release

ROOT = Path(__file__).resolve().parents[1]

RFC8032 = [   # (secret, public, message, signature), section 7.1 tests 1-3
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


class Ed25519Vectors(unittest.TestCase):
    def test_rfc8032(self):
        for sk, pk, msg, sig in RFC8032:
            sk, pk, msg, sig = map(bytes.fromhex, (sk, pk, msg, sig))
            self.assertEqual(pk, ed25519.public_key(sk))
            self.assertEqual(sig, ed25519.sign(sk, msg))
            self.assertTrue(ed25519.verify(pk, msg, sig))
            self.assertFalse(ed25519.verify(pk, msg + b"!", sig))
            self.assertFalse(ed25519.verify(pk, msg, sig[:-1] + bytes([sig[-1] ^ 1])))
            self.assertFalse(ed25519.verify(pk, msg, b"\0" * 64))
            self.assertFalse(ed25519.verify(b"\x01" * 31, msg, sig))


class SignedUpdates(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.up = selfupdate.SelfUpdate(self.tmp / "data")
        self.up.mode = lambda: "exe"
        (self.tmp / "app").mkdir()
        self.secret = os.urandom(32)
        self.public = ed25519.public_key(self.secret).hex()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _release(self, sig: str | None, tag="v99.0.0"):
        rel, opener = fake_release(self.tmp)
        if sig is not None:
            rel["assets"].append({"name": "LegacyPlayer-99.0.0-win64.zip.sig", "url": "https://github.com/g", "size": 129, "sha256": ""})

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener2(url, hosts, allow_http=False, timeout=30):
            return Resp(sig.encode()) if url.endswith("/g") else opener(url, hosts, allow_http, timeout)
        return rel, opener2

    def _zip_sha(self, rel, opener):
        with opener(rel["assets"][0]["url"], ()) as r:
            return hashlib.sha256(r.read()).hexdigest()

    def _prepare(self, rel, opener, keys):
        with mock.patch.object(selfupdate, "_open", opener), mock.patch.object(selfupdate.sys, "platform", "win32"), \
             mock.patch.object(selfupdate.sys, "executable", str(self.tmp / "app" / "LegacyPlayer.exe")), \
             mock.patch.object(lpversion, "UPDATE_SIGNING_KEYS", keys):
            return self.up.prepare({"mode": "exe", "newer": True, "latest": rel["tag"], "release": rel, "message": ""})

    def test_no_key_listed_means_no_signature_needed(self):
        rel, opener = self._release(None)
        self.assertEqual("ready", self._prepare(rel, opener, ())["state"])

    def test_a_listed_key_needs_a_signature(self):
        rel, opener = self._release(None)
        with self.assertRaises(selfupdate.InstallError) as caught:
            self._prepare(rel, opener, (self.public,))
        self.assertIn("not signed", str(caught.exception))

    def test_a_good_signature_installs(self):
        rel, _ = self._release("")
        sha = self._zip_sha(rel, fake_release(self.tmp)[1])
        sig = ed25519.sign(self.secret, selfupdate.signed_message("v99.0.0", "LegacyPlayer-99.0.0-win64.zip", sha)).hex()
        rel, opener = self._release(sig)
        self.assertEqual("ready", self._prepare(rel, opener, ("00" * 32, self.public))["state"])

    def test_a_wrong_key_tag_or_name_is_refused(self):
        rel, _ = self._release("")
        sha = self._zip_sha(rel, fake_release(self.tmp)[1])
        other = os.urandom(32)
        for secret, tag, name in ((other, "v99.0.0", "LegacyPlayer-99.0.0-win64.zip"),           # someone else's key
                                  (self.secret, "v1.0.0", "LegacyPlayer-99.0.0-win64.zip"),       # an old release's signature
                                  (self.secret, "v99.0.0", "LegacyPlayer-1.0.0-win64.zip")):
            with self.subTest(tag=tag, name=name):
                sig = ed25519.sign(secret, selfupdate.signed_message(tag, name, sha)).hex()
                rel, opener = self._release(sig)
                with self.assertRaises(selfupdate.InstallError):
                    self._prepare(rel, opener, (self.public,))
                self.assertFalse((self.tmp / "data" / "update" / "new").exists())


class SignTool(unittest.TestCase):
    def test_sign_tool_writes_a_signature_the_app_accepts(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            secret = os.urandom(32)
            public = ed25519.public_key(secret).hex()
            z = tmp / "LegacyPlayer-9.9.9-win64.zip"
            z.write_bytes(b"package bytes")
            with mock.patch.dict(os.environ, {"LP_UPDATE_SIGNING_KEY": secret.hex()}), \
                 mock.patch.object(lpversion, "UPDATE_SIGNING_KEYS", (public,)):
                sys.path.insert(0, str(ROOT / "tools"))
                import importlib
                tool = importlib.import_module("sign_release")
                with mock.patch.object(tool, "UPDATE_SIGNING_KEYS", (public,)):
                    self.assertEqual(0, tool.sign("v9.9.9", tmp))
                    self.assertTrue(selfupdate.signature_ok((public,), "v9.9.9", z.name, hashlib.sha256(z.read_bytes()).hexdigest(),
                                                            (tmp / (z.name + ".sig")).read_text()))
                with mock.patch.object(tool, "UPDATE_SIGNING_KEYS", ("11" * 32,)):
                    self.assertEqual(1, tool.sign("v9.9.9", tmp))            # a key the app doesn't list is refused
            with mock.patch.dict(os.environ, {"LP_UPDATE_SIGNING_KEY": ""}):
                with mock.patch.object(tool, "UPDATE_SIGNING_KEYS", (public,)):
                    self.assertEqual(1, tool.sign("v9.9.9", tmp))            # a listed key but no secret: the release fails
                with mock.patch.object(tool, "UPDATE_SIGNING_KEYS", ()):
                    self.assertEqual(0, tool.sign("v9.9.9", tmp))            # not set up yet: unsigned, as before
            out = subprocess.run([sys.executable, str(ROOT / "tools" / "sign_release.py"), "new-key", "--out", str(ROOT / "k.txt")],
                                 capture_output=True, text=True)
            self.assertEqual(2, out.returncode)                              # never inside the repository
            self.assertFalse((ROOT / "k.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_key_ships_by_default(self):
        self.assertEqual((), tuple(lpversion.UPDATE_SIGNING_KEYS))


if __name__ == "__main__":
    unittest.main()
