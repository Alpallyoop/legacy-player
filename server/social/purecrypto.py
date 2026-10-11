"""Small, pure-Python cryptography for the friends service and Legacy Player (standard library only).

- X25519 key agreement (RFC 7748, Montgomery ladder)
- ChaCha20-Poly1305 authenticated encryption (RFC 8439)
- HKDF-SHA256 (RFC 5869)
- HOTP / TOTP one-time codes (RFC 4226 / RFC 6238)

Every function is checked against the RFC test vectors in tests/test_friends_crypto.py.

Honest limits: this is plain Python, so it is slow next to a C library (fine for short chat messages) and it is not
constant-time. Timing leaks need an attacker who can measure this computer's work very precisely on many operations
with the same key; the private key never leaves the app and the service never asks it to compute anything on demand,
which keeps that out of reach in practice. Tags and secrets are compared with hmac.compare_digest.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
from urllib.parse import quote

# --- X25519 (RFC 7748) --------------------------------------------------------------------------------------------
_P = 2 ** 255 - 19
_A24 = 121665
BASE_POINT = b"\x09" + b"\x00" * 31


def _clamp(k: bytes) -> int:
    b = bytearray(k)
    b[0] &= 248
    b[31] &= 127
    b[31] |= 64
    return int.from_bytes(b, "little")


def x25519(scalar: bytes, u: bytes) -> bytes:
    """The X25519 function: scalar (32 bytes) times the point with u-coordinate u (32 bytes)."""
    if len(scalar) != 32 or len(u) != 32:
        raise ValueError("X25519 takes 32-byte inputs")
    k = _clamp(scalar)
    ub = bytearray(u)
    ub[31] &= 127                                     # the top bit is ignored (RFC 7748 section 5)
    x1 = int.from_bytes(ub, "little") % _P
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in range(254, -1, -1):
        kt = (k >> t) & 1
        swap ^= kt
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = kt
        a = (x2 + z2) % _P
        aa = a * a % _P
        b = (x2 - z2) % _P
        bb = b * b % _P
        e = (aa - bb) % _P
        c = (x3 + z3) % _P
        d = (x3 - z3) % _P
        da = d * a % _P
        cb = c * b % _P
        x3 = (da + cb) * (da + cb) % _P
        z3 = x1 * (da - cb) * (da - cb) % _P
        x2 = aa * bb % _P
        z2 = e * (aa + _A24 * e) % _P
    if swap:
        x2, x3, z2, z3 = x3, x2, z3, z2
    return (x2 * pow(z2, _P - 2, _P) % _P).to_bytes(32, "little")


def x25519_keypair(private: bytes | None = None) -> tuple[bytes, bytes]:
    """(private, public). A new random private key unless one is given."""
    private = private if private is not None else secrets.token_bytes(32)
    return private, x25519(private, BASE_POINT)


def shared_secret(private: bytes, their_public: bytes) -> bytes:
    """X25519 agreement; refuses the all-zero result a small-order (malicious) public key gives."""
    out = x25519(private, their_public)
    if not any(out):
        raise ValueError("unusable public key")
    return out


# --- ChaCha20 and Poly1305 (RFC 8439) -----------------------------------------------------------------------------
_MASK = 0xFFFFFFFF


def _rotl(v: int, c: int) -> int:
    return ((v << c) & _MASK) | (v >> (32 - c))


def _block_words(key_words: tuple, counter: int, nonce_words: tuple) -> list:
    state = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574, *key_words, counter & _MASK, *nonce_words]
    x = list(state)
    for _ in range(10):
        for a, b, c, d in ((0, 4, 8, 12), (1, 5, 9, 13), (2, 6, 10, 14), (3, 7, 11, 15),
                           (0, 5, 10, 15), (1, 6, 11, 12), (2, 7, 8, 13), (3, 4, 9, 14)):
            x[a] = (x[a] + x[b]) & _MASK
            x[d] = _rotl(x[d] ^ x[a], 16)
            x[c] = (x[c] + x[d]) & _MASK
            x[b] = _rotl(x[b] ^ x[c], 12)
            x[a] = (x[a] + x[b]) & _MASK
            x[d] = _rotl(x[d] ^ x[a], 8)
            x[c] = (x[c] + x[d]) & _MASK
            x[b] = _rotl(x[b] ^ x[c], 7)
    return [(x[i] + state[i]) & _MASK for i in range(16)]


def chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    if len(key) != 32 or len(nonce) != 12:
        raise ValueError("ChaCha20 takes a 32-byte key and a 12-byte nonce")
    return struct.pack("<16I", *_block_words(struct.unpack("<8I", key), counter, struct.unpack("<3I", nonce)))


def chacha20_xor(key: bytes, counter: int, nonce: bytes, data: bytes) -> bytes:
    """ChaCha20 encryption (and decryption): data XOR the keystream starting at block `counter`."""
    if len(key) != 32 or len(nonce) != 12:
        raise ValueError("ChaCha20 takes a 32-byte key and a 12-byte nonce")
    kw, nw = struct.unpack("<8I", key), struct.unpack("<3I", nonce)
    out = bytearray()
    for i in range(0, len(data), 64):
        stream = struct.pack("<16I", *_block_words(kw, counter + i // 64, nw))
        chunk = data[i:i + 64]
        out += (int.from_bytes(chunk, "little") ^ int.from_bytes(stream[:len(chunk)], "little")).to_bytes(len(chunk), "little")
    return bytes(out)


def poly1305(key: bytes, message: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("Poly1305 takes a 32-byte one-time key")
    r = int.from_bytes(key[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:], "little")
    p = (1 << 130) - 5
    acc = 0
    for i in range(0, len(message), 16):
        acc = (acc + int.from_bytes(message[i:i + 16] + b"\x01", "little")) * r % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _pad16(n: int) -> bytes:
    return b"\x00" * (-n % 16)


def _aead_tag(key: bytes, nonce: bytes, aad: bytes, ciphertext: bytes) -> bytes:
    otk = chacha20_block(key, 0, nonce)[:32]
    mac_data = aad + _pad16(len(aad)) + ciphertext + _pad16(len(ciphertext)) + struct.pack("<QQ", len(aad), len(ciphertext))
    return poly1305(otk, mac_data)


def aead_encrypt(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AEAD_CHACHA20_POLY1305: ciphertext followed by the 16-byte tag."""
    ciphertext = chacha20_xor(key, 1, nonce, plaintext)
    return ciphertext + _aead_tag(key, nonce, aad, ciphertext)


class AuthError(ValueError):
    """The ciphertext, its associated data or the key is not what was sealed."""


def aead_decrypt(key: bytes, nonce: bytes, sealed: bytes, aad: bytes = b"") -> bytes:
    if len(sealed) < 16:
        raise AuthError("too short")
    ciphertext, tag = sealed[:-16], sealed[-16:]
    if not hmac.compare_digest(_aead_tag(key, nonce, aad, ciphertext), tag):
        raise AuthError("the message does not verify")
    return chacha20_xor(key, 1, nonce, ciphertext)


# --- HKDF-SHA256 (RFC 5869) -------------------------------------------------------------------------------------------
def hkdf_extract(salt: bytes, ikm: bytes, hash_name: str = "sha256") -> bytes:
    size = hashlib.new(hash_name).digest_size
    return hmac.new(salt or b"\x00" * size, ikm, hash_name).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int, hash_name: str = "sha256") -> bytes:
    size = hashlib.new(hash_name).digest_size
    if length > 255 * size:
        raise ValueError("HKDF output too long")
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hash_name).digest()
        out += block
        counter += 1
    return out[:length]


def hkdf(ikm: bytes, salt: bytes, info: bytes, length: int = 32, hash_name: str = "sha256") -> bytes:
    return hkdf_expand(hkdf_extract(salt, ikm, hash_name), info, length, hash_name)


# --- one-time codes (RFC 4226 HOTP, RFC 6238 TOTP) ---------------------------------------------------------------------
TOTP_STEP = 30


def hotp(secret: bytes, counter: int, digits: int = 6, hash_name: str = "sha1") -> str:
    mac = hmac.new(secret, struct.pack(">Q", counter), hash_name).digest()
    offset = mac[-1] & 0x0F
    code = (int.from_bytes(mac[offset:offset + 4], "big") & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp(secret: bytes, at: float, digits: int = 6, step: int = TOTP_STEP, hash_name: str = "sha1") -> str:
    return hotp(secret, int(at // step), digits, hash_name)


def totp_match(secret: bytes, code: str, at: float, window: int = 1, step: int = TOTP_STEP) -> int | None:
    """The time step the code belongs to (now, or up to `window` steps either side), or None."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6:
        return None
    now = int(at // step)
    found = None
    for s in range(now - window, now + window + 1):
        if hmac.compare_digest(hotp(secret, s), code):
            found = s                                   # no early exit: every candidate costs the same
    return found


def new_totp_secret() -> str:
    """160 random bits as base32 text (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_secret_bytes(text: str) -> bytes:
    clean = "".join(str(text or "").split()).upper().rstrip("=")
    return base64.b32decode(clean + "=" * (-len(clean) % 8))


def otpauth_uri(secret_b32: str, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}", safe="")
    return f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer, safe='')}&algorithm=SHA1&digits=6&period={TOTP_STEP}"


# --- helpers -----------------------------------------------------------------------------------------------------------------
def b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64d(text, size: int | None = None, limit: int = 1 << 20) -> bytes:
    """Decode url-safe base64 (padding optional). ValueError for anything else, or the wrong length when `size` is set."""
    if not isinstance(text, str) or len(text) > limit or not all(c.isalnum() or c in "-_" for c in text):
        raise ValueError("not base64")
    try:
        out = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError("not base64") from exc
    if size is not None and len(out) != size:
        raise ValueError("wrong length")
    return out


def random_bytes(n: int) -> bytes:
    return os.urandom(n)
