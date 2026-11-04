"""Short server codes: one easy-to-type string that carries a server's address, port and a
fingerprint prefix, so a friend types one thing instead of three.

Addresses that do not fit in four bytes (an IPv6 address or a name such as home.duckdns.org) use a longer, checksummed
form that starts LP2- (see encode_long); the short LP- form stays for plain IPv4 addresses.

Format: LP-XXXX-XXXX-XXXX-XXXX-XX (Crockford base32 of: 4 address bytes, 2 port bytes,
5 fingerprint bytes). Only IPv4 addresses fit; for a name or IPv6 address share the long form.
Codes that carry the server key are longer: 4 address, 2 port, 10 fingerprint and 5 key bytes (34 characters), so the
80-bit fingerprint prefix checked against the server certificate on every connect can not be forged by brute force.
Older codes (40-bit fingerprint, with or without the key) still decode.

LP3- codes are what a player's own computer hands out: they hold NO address of that computer. They carry a token at a
meeting point (server/rendezvous.py), the server's certificate fingerprint and key, and the meeting point's own address
(a rented server, not a player's computer). See encode_meet.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_FIX = {"O": "0", "I": "1", "L": "1", "U": "V"}


class CodeError(ValueError):
    pass


_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MAX_HOST = 100


def _clean_host(host: str) -> str:
    host = (host or "").strip().strip("[]").rstrip(".").lower()
    if not host or len(host) > MAX_HOST:
        raise CodeError("That address is empty or too long.")
    return host


def _hex_bytes(fingerprint_hex: str) -> bytes:
    try:
        return bytes.fromhex("".join(c for c in fingerprint_hex.lower() if c in "0123456789abcdef"))
    except ValueError as exc:
        raise CodeError("Bad fingerprint.") from exc


def _fingerprint_bytes(fingerprint_hex: str, key: bytes) -> bytes:
    return _hex_bytes(fingerprint_hex)[:10].ljust(10, b"\0")


def _to_text(raw: bytes) -> str:
    value = int.from_bytes(raw, "big")
    length = -(-len(raw) * 8 // 5)
    chars = []
    for _ in range(length):
        chars.append(ALPHABET[value & 31])
        value >>= 5
    text = "".join(reversed(chars))
    return "-".join(text[i:i + 4] for i in range(0, len(text), 4))


def encode_long(host: str, port: int, fingerprint_hex: str, key_hex: str = "") -> str:
    """LP2- form: any IPv6 address or host name, with a checksum so a typo is caught before connecting."""
    host = _clean_host(host)
    if not 1 <= port <= 65535:
        raise CodeError("Port out of range.")
    key = bytes.fromhex(key_hex) if key_hex else b""
    if key and len(key) != 5:
        raise CodeError("Bad server key.")
    try:
        ip6 = ipaddress.IPv6Address(host.split("%")[0])
        kind, body = 1, ip6.packed
    except ValueError:
        try:
            ipaddress.IPv4Address(host)
            kind, body = 0, ipaddress.IPv4Address(host).packed
        except ValueError:
            if not all(_LABEL.match(part) for part in host.split(".")):
                raise CodeError("That address has characters a server code can't hold. Use letters, numbers and hyphens.") from None
            kind, body = 2, bytes([len(host)]) + host.encode("ascii")
    flags = kind | (4 if key else 0)
    raw = bytes([flags]) + body + port.to_bytes(2, "big") + _fingerprint_bytes(fingerprint_hex, key) + key
    raw += hashlib.sha256(raw).digest()[:2]
    return "LP2-" + _to_text(raw)


def _decode_long(text: str) -> dict:
    text = "".join(_FIX.get(c, c) for c in text)
    if any(c not in ALPHABET for c in text) or len(text) < 20:
        raise CodeError("That server code does not look right. It should be LP2- followed by letters and numbers.")
    size = len(text) * 5 // 8
    value = 0
    for c in text:
        value = value << 5 | ALPHABET.index(c)
    if value >> (size * 8):
        raise CodeError("That server code does not look right.")
    raw = value.to_bytes(size, "big")
    body, check = raw[:-2], raw[-2:]
    if hashlib.sha256(body).digest()[:2] != check:
        raise CodeError("That server code has a typo in it. Check it against the one you were sent.")
    flags, rest = body[0], body[1:]
    kind, has_key = flags & 3, bool(flags & 4)
    try:
        if kind == 0:
            host, rest = str(ipaddress.IPv4Address(rest[:4])), rest[4:]
        elif kind == 1:
            host, rest = str(ipaddress.IPv6Address(rest[:16])), rest[16:]
        elif kind == 2:
            n = rest[0]
            host, rest = rest[1:1 + n].decode("ascii"), rest[1 + n:]
            if not host or not all(_LABEL.match(part) for part in host.split(".")):
                raise ValueError
        else:
            raise ValueError
    except (ValueError, IndexError, UnicodeDecodeError, ipaddress.AddressValueError) as exc:
        raise CodeError("That server code does not look right.") from exc
    if len(rest) != 2 + 10 + (5 if has_key else 0):
        raise CodeError("That server code does not look right.")
    port = int.from_bytes(rest[:2], "big")
    if not port:
        raise CodeError("That server code does not look right.")
    out = {"host": host, "port": port, "fingerprint": rest[2:12].hex()}
    if has_key:
        out["key"] = rest[12:17].hex()
    return out


def encode(host: str, port: int, fingerprint_hex: str, key_hex: str = "") -> str:
    host = _clean_host(host)
    try:
        ip = ipaddress.IPv4Address(host)
    except ValueError:
        return encode_long(host, port, fingerprint_hex, key_hex)       # IPv6 or a name
    if not 1 <= port <= 65535:
        raise CodeError("Port out of range.")
    key = bytes.fromhex(key_hex) if key_hex else b""
    if key and len(key) != 5:
        raise CodeError("Bad server key.")
    try:
        full = bytes.fromhex("".join(c for c in fingerprint_hex.lower() if c in "0123456789abcdef"))
    except ValueError as exc:
        raise CodeError("Bad fingerprint.") from exc
    width = 10 if key and len(full) >= 10 else 5       # the long form only when the certificate fingerprint is long enough
    fp = full[:width].ljust(width, b"\0")
    raw = ip.packed + port.to_bytes(2, "big") + fp + key
    value = int.from_bytes(raw, "big")
    length = {11: 18, 16: 26, 21: 34}[len(raw)]   # base32 characters for 11 (no key), 16 (old, with key) and 21 (with key) bytes
    chars = []
    for _ in range(length):
        chars.append(ALPHABET[value & 31])
        value >>= 5
    text = "".join(reversed(chars))
    return "LP-" + "-".join(text[i:i + 4] for i in range(0, length - 2, 4)) + "-" + text[length - 2:]


def _host_body(host: str) -> tuple[int, bytes]:
    host = _clean_host(host)
    try:
        return 1, ipaddress.IPv6Address(host.split("%")[0]).packed
    except ValueError:
        pass
    try:
        return 0, ipaddress.IPv4Address(host).packed
    except ValueError:
        pass
    if not all(_LABEL.match(part) for part in host.split(".")):
        raise CodeError("That address has characters a server code can't hold. Use letters, numbers and hyphens.")
    return 2, bytes([len(host)]) + host.encode("ascii")


def encode_meet(token_hex: str, fingerprint_hex: str, key_hex: str, meet: dict) -> str:
    """LP3- form: a player's server reached through a meeting point. Holds the token, the player's server fingerprint
    (80 bits) and key, and the meeting point (its address, port and fingerprint). Never the player's address."""
    try:
        token, key = bytes.fromhex(token_hex), bytes.fromhex(key_hex)
    except ValueError as exc:
        raise CodeError("Bad token or key.") from exc
    if len(token) != 12 or len(key) != 5:
        raise CodeError("Bad token or key.")
    if len(_hex_bytes(fingerprint_hex)) < 10:
        # the code pins the player's server by these 80 bits; zero padding would make it a much weaker pin
        raise CodeError("The server's certificate fingerprint is too short for a code.")
    port = int(meet.get("port") or 0)
    if not 1 <= port <= 65535:
        raise CodeError("Port out of range.")
    kind, body = _host_body(str(meet.get("host", "")))
    raw = (bytes([kind | 0x10]) + token + _fingerprint_bytes(fingerprint_hex, b"") + key
           + body + port.to_bytes(2, "big") + _fingerprint_bytes(str(meet.get("fingerprint", "")), b""))
    raw += hashlib.sha256(raw).digest()[:2]
    return "LP3-" + _to_text(raw)


def _decode_meet(text: str) -> dict:
    text = "".join(_FIX.get(c, c) for c in text)
    if any(c not in ALPHABET for c in text) or len(text) < 60:
        raise CodeError("That server code does not look right. It should be LP3- followed by letters and numbers.")
    size = len(text) * 5 // 8
    value = 0
    for c in text:
        value = value << 5 | ALPHABET.index(c)
    if value >> (size * 8):
        raise CodeError("That server code does not look right.")
    raw = value.to_bytes(size, "big")
    body, check = raw[:-2], raw[-2:]
    if hashlib.sha256(body).digest()[:2] != check:
        raise CodeError("That server code has a typo in it. Check it against the one you were sent.")
    flags = body[0]
    if flags & 0xF0 != 0x10:
        raise CodeError("That server code is from a newer Legacy Player. Update the app.")
    kind, rest = flags & 3, body[1:]
    token, fp, key, rest = rest[:12], rest[12:22], rest[22:27], rest[27:]
    try:
        if kind == 0:
            host, rest = str(ipaddress.IPv4Address(rest[:4])), rest[4:]
        elif kind == 1:
            host, rest = str(ipaddress.IPv6Address(rest[:16])), rest[16:]
        elif kind == 2:
            n = rest[0]
            host, rest = rest[1:1 + n].decode("ascii"), rest[1 + n:]
            if not host or not all(_LABEL.match(part) for part in host.split(".")):
                raise ValueError
        else:
            raise ValueError
    except (ValueError, IndexError, UnicodeDecodeError, ipaddress.AddressValueError) as exc:
        raise CodeError("That server code does not look right.") from exc
    if len(token) != 12 or len(key) != 5 or len(rest) != 12:
        raise CodeError("That server code does not look right.")
    port = int.from_bytes(rest[:2], "big")
    if not port:
        raise CodeError("That server code does not look right.")
    # A meeting point named by a short LP- code without a key carries only 40 bits of its fingerprint, padded with zeros
    # here; the padding is dropped so the pin is the prefix that was really known (at least 40 bits).
    meet_fp = rest[2:12].rstrip(b"\0")
    if len(meet_fp) < 5:
        meet_fp = rest[2:7]
    return {"token": token.hex(), "fingerprint": fp.hex(), "key": key.hex(),
            "meet": {"host": host, "port": port, "fingerprint": meet_fp.hex()}}


def is_meet_code(code: str) -> bool:
    return "".join(c for c in str(code).upper() if c not in "- _\t\r\n").startswith("LP3")


def decode(code: str) -> dict:
    squeezed = "".join(c for c in code.upper() if c not in "- _\t\r\n")
    head = code.strip().upper()
    # "LP3-" and "LP2-" name the form. Without the dash, an LP- code whose text starts with 3 or 2 looks the same, so
    # the checksummed long forms are tried first and the short form is the fallback.
    for prefix, decoder in (("LP3", _decode_meet), ("LP2", _decode_long)):
        if head.startswith(prefix + "-"):
            return decoder(squeezed[3:])
        if squeezed.startswith(prefix) and not head.startswith("LP-"):
            try:
                return decoder(squeezed[3:])
            except CodeError:
                break
    text = "".join(c for c in code.upper() if c not in "- _")
    if text.startswith("LP") and len(text) in (20, 28, 36):
        text = text[2:]
    text = "".join(_FIX.get(c, c) for c in text)
    if len(text) not in (18, 26, 34) or any(c not in ALPHABET for c in text):
        raise CodeError("That server code does not look right. It should be LP- followed by letters and numbers.")
    size = {18: 11, 26: 16, 34: 21}[len(text)]
    value = 0
    for c in text:
        value = value << 5 | ALPHABET.index(c)
    if value >> (size * 8):
        raise CodeError("That server code does not look right.")
    raw = value.to_bytes(size, "big")
    host = str(ipaddress.IPv4Address(raw[:4]))
    port = int.from_bytes(raw[4:6], "big")
    if not port:
        raise CodeError("That server code does not look right.")
    fp_end = 16 if size == 21 else 11
    out = {"host": host, "port": port, "fingerprint": raw[6:fp_end].hex()}
    if size in (16, 21):
        out["key"] = raw[fp_end:fp_end + 5].hex()
    return out
