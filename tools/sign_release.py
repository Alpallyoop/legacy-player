"""Sign a release so installed apps can tell it came from the maintainers (docs/RELEASE.md, "Update signing").

    python tools/sign_release.py new-key --out <file outside the repository>
        Makes a signing key. Prints the public half to paste into UPDATE_SIGNING_KEYS in launcher/version.py; the
        private half is written to --out (only you can read it). Put the private half in the repository secret
        LP_UPDATE_SIGNING_KEY, keep an offline copy, and never commit it.

    python tools/sign_release.py sign --tag vX.Y.Z --folder dist/release
        Run by the release workflow. Signs LegacyPlayer-*-win64.zip with the key in the environment variable
        LP_UPDATE_SIGNING_KEY, writing <zip>.sig. Without that variable it signs nothing, which is an error once
        launcher/version.py lists a key (apps would then refuse the update).

The signature covers the release tag, the zip's file name and its SHA-256 (launcher.selfupdate.signed_message), so a
signed old release can't be passed off as a newer one.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launcher import ed25519  # noqa: E402
from launcher.selfupdate import signed_message  # noqa: E402
from launcher.version import UPDATE_SIGNING_KEYS  # noqa: E402


def new_key(out: Path) -> int:
    out = out.resolve()
    if ROOT in out.parents or out == ROOT:
        print("Write the key outside the repository, so it can't be committed by mistake.", file=sys.stderr)
        return 2
    if out.exists():
        print(f"{out} already exists; pick another name.", file=sys.stderr)
        return 2
    secret = secrets.token_bytes(32)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secret.hex() + "\n")
    print("Private key written to", out)
    print("Public key (add it to UPDATE_SIGNING_KEYS in launcher/version.py):")
    print(ed25519.public_key(secret).hex())
    return 0


def sign(tag: str, folder: Path) -> int:
    raw = os.environ.get("LP_UPDATE_SIGNING_KEY", "").strip()
    zips = sorted(folder.glob("LegacyPlayer-*-win64.zip"))
    if len(zips) != 1:
        print(f"Expected one LegacyPlayer-*-win64.zip in {folder}, found {len(zips)}.", file=sys.stderr)
        return 1
    if not raw:
        if UPDATE_SIGNING_KEYS:
            print("launcher/version.py lists an update signing key but LP_UPDATE_SIGNING_KEY is not set: installed apps "
                  "would refuse this release. Add the secret (docs/RELEASE.md).", file=sys.stderr)
            return 1
        print("No update signing key is set up yet; the release is not signed (docs/RELEASE.md, Update signing).")
        return 0
    try:
        secret = bytes.fromhex(raw)
    except ValueError:
        secret = b""
    if len(secret) != 32:
        print("LP_UPDATE_SIGNING_KEY is not a 64-character hex key.", file=sys.stderr)
        return 1
    public = ed25519.public_key(secret).hex()
    if public not in UPDATE_SIGNING_KEYS:
        print("The signing key in LP_UPDATE_SIGNING_KEY is not one of UPDATE_SIGNING_KEYS in launcher/version.py, so "
              "apps would refuse it. Add its public half there first.", file=sys.stderr)
        return 1
    z = zips[0]
    digest = hashlib.sha256(z.read_bytes()).hexdigest()
    sig = ed25519.sign(secret, signed_message(tag, z.name, digest))
    (z.parent / (z.name + ".sig")).write_text(sig.hex() + "\n", encoding="ascii")
    print(f"Signed {z.name} for {tag}.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("new-key")
    k.add_argument("--out", required=True, type=Path)
    s = sub.add_parser("sign")
    s.add_argument("--tag", required=True)
    s.add_argument("--folder", required=True, type=Path)
    a = ap.parse_args(argv)
    return new_key(a.out) if a.cmd == "new-key" else sign(a.tag, a.folder)


if __name__ == "__main__":
    raise SystemExit(main())
