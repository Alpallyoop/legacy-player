"""End-to-end encrypted messages for the friends service: what is sealed, how, and how a report is checked.

Each Legacy Player app has a long-term X25519 key pair; the public half goes to the friends service with hello and every
heartbeat, and friends' apps pin it the first time they see it. A message is sealed like this:

    K      = 32 random bytes, used for this one message only
    c      = ChaCha20-Poly1305(K, nonce, text, aad = "LP-E2E-v1|<conversation>|<sender id>|<message id>")
    kc     = SHA-256("LP-E2E-commit-v1" | K | message id)       a commitment: exactly one K opens this message
    for each recipient R, the sender included:
      wk_R = HKDF-SHA256(X25519(sender private, R public), salt "LP-E2E-wrap-v1",
                         info = sender public | R public | message id | conversation)
      w_R  = ChaCha20-Poly1305(wk_R, random nonce, K, aad = "LP-E2E-key|<message id>")

The service stores only the envelope (ciphertext, commitment, wrapped keys and the public keys used), never the text
or K. Only the sender and the recipients can unwrap K, and because the wrap key comes from the sender's long-term key,
a recipient knows the message came from that sender's app.

Honest reports: a player who reports a message hands the service that message's K (and the K of the few before it).
The service checks K against the commitment and decrypts *its own stored copy* with it, so moderators read exactly what
was sent and a report cannot put words in anyone's mouth: a made-up K or a made-up text does not verify.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import purecrypto as pc

VERSION = 1
MAX_TEXT_BYTES = 2400                       # 500 characters of any script fit
MAX_RECIPIENTS = 12
_MID = re.compile(r"^[0-9a-f]{16,32}$")


class E2EError(ValueError):
    pass


def direct_conv(a: str, b: str) -> str:
    x, y = sorted((str(a), str(b)))
    return f"d:{x}:{y}"


def group_conv(gid: str) -> str:
    return f"g:{gid}"


def new_message_id() -> str:
    return pc.random_bytes(12).hex()


def _aad(conv: str, sender: str, mid: str) -> bytes:
    return f"LP-E2E-v1|{conv}|{sender}|{mid}".encode("utf-8")


def commitment(key: bytes, mid: str) -> bytes:
    return hashlib.sha256(b"LP-E2E-commit-v1" + key + mid.encode("ascii")).digest()


def _wrap_key(shared: bytes, spub: bytes, rpub: bytes, mid: str, conv: str) -> bytes:
    return pc.hkdf(shared, b"LP-E2E-wrap-v1", spub + rpub + mid.encode("ascii") + conv.encode("utf-8"), 32)


def seal(private: bytes, public: bytes, sender: str, conv: str, recipients: dict, text: str, mid: str | None = None) -> dict:
    """The envelope for `text`, readable by every id in `recipients` ({id: public key bytes}; include the sender)."""
    data = str(text).encode("utf-8")
    if not data or len(data) > MAX_TEXT_BYTES:
        raise E2EError("message too long or empty")
    if sender not in recipients or len(recipients) > MAX_RECIPIENTS:
        raise E2EError("bad recipients")
    mid = mid or new_message_id()
    key, nonce = pc.random_bytes(32), pc.random_bytes(12)
    keys = {}
    for rid, rpub in recipients.items():
        shared = pc.shared_secret(private, rpub)
        wn = pc.random_bytes(12)
        keys[str(rid)] = {"p": pc.b64e(rpub), "n": pc.b64e(wn),
                          "w": pc.b64e(pc.aead_encrypt(_wrap_key(shared, public, rpub, mid, conv), wn, key, b"LP-E2E-key|" + mid.encode()))}
    return {"v": VERSION, "mid": mid, "conv": conv, "from": sender, "spub": pc.b64e(public), "n": pc.b64e(nonce),
            "c": pc.b64e(pc.aead_encrypt(key, nonce, data, _aad(conv, sender, mid))), "kc": pc.b64e(commitment(key, mid)),
            "keys": keys}


def unwrap(env: dict, my_id: str, private: bytes, public: bytes, cache: dict | None = None) -> bytes:
    """K for this envelope, as wrapped for me; checked against the commitment. `cache` keeps X25519 results per
    sender key, so a long conversation costs one key agreement, not one per message."""
    try:
        entry = env["keys"][my_id]
        rpub, spub = pc.b64d(entry["p"], 32), pc.b64d(env["spub"], 32)
        if rpub != public:
            raise E2EError("sealed for another key of mine (the key was replaced)")
        shared = cache.get(spub) if cache is not None else None
        if shared is None:
            shared = pc.shared_secret(private, spub)
            if cache is not None:
                cache[spub] = shared
        key = pc.aead_decrypt(_wrap_key(shared, spub, rpub, env["mid"], env["conv"]), pc.b64d(entry["n"], 12),
                              pc.b64d(entry["w"], 48), b"LP-E2E-key|" + env["mid"].encode())
    except E2EError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise E2EError("this message could not be opened") from exc
    if not _commit_ok(env, key):
        raise E2EError("this message's key does not match its commitment")
    return key


def _commit_ok(env: dict, key: bytes) -> bool:
    try:
        import hmac
        return hmac.compare_digest(commitment(key, env["mid"]), pc.b64d(env["kc"], 32))
    except (KeyError, TypeError, ValueError):
        return False


def open_with_key(env: dict, key: bytes, conv: str | None = None, sender: str | None = None) -> str:
    """The text, given K. `conv` and `sender` (when given) are what the *caller* knows, not what the envelope says."""
    try:
        conv = env["conv"] if conv is None else conv
        sender = env["from"] if sender is None else sender
        if len(key) != 32 or not _commit_ok(env, key):
            raise E2EError("that key does not belong to this message")
        data = pc.aead_decrypt(key, pc.b64d(env["n"], 12), pc.b64d(env["c"], limit=8192), _aad(conv, sender, env["mid"]))
        return data.decode("utf-8")
    except E2EError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise E2EError("this message could not be opened") from exc


def open_envelope(env: dict, my_id: str, private: bytes, public: bytes, cache: dict | None = None) -> tuple[str, bytes]:
    key = unwrap(env, my_id, private, public, cache)
    return open_with_key(env, key), key


def check_shape(env, sender: str, conv: str, sender_pub: str, member_pubs: dict) -> dict:
    """What the service checks before storing an envelope: well formed, from the authenticated sender, for this
    conversation, sealed with the sender's published key, and wrapped for exactly the current members with the keys
    the service has for them. Returns a clean copy (unknown fields dropped)."""
    if not isinstance(env, dict) or env.get("v") != VERSION:
        raise E2EError("Update Legacy Player: this friends service only takes end-to-end encrypted messages.")
    mid = env.get("mid")
    if not isinstance(mid, str) or not _MID.match(mid):
        raise E2EError("bad message id")
    if env.get("conv") != conv or env.get("from") != sender:
        raise E2EError("message sealed for another conversation")
    if env.get("spub") != sender_pub:
        raise E2EError("Your app's key does not match the one the service has. Refresh and try again.")
    try:
        pc.b64d(env.get("n"), 12)
        pc.b64d(env.get("kc"), 32)
        c = pc.b64d(env.get("c"), limit=8192)
    except ValueError as exc:
        raise E2EError("bad message") from exc
    if not 17 <= len(c) <= MAX_TEXT_BYTES + 16:
        raise E2EError("message too long")
    keys = env.get("keys")
    if not isinstance(keys, dict) or set(keys) != set(member_pubs):
        raise E2EError("The people in this conversation changed. Refresh and send again.")
    clean_keys = {}
    for rid, entry in keys.items():
        if not isinstance(entry, dict) or entry.get("p") != member_pubs[rid]:
            raise E2EError("Someone in this conversation has a new key. Refresh and send again.")
        try:
            pc.b64d(entry.get("n"), 12)
            pc.b64d(entry.get("w"), 48)
        except ValueError as exc:
            raise E2EError("bad message") from exc
        clean_keys[rid] = {"p": entry["p"], "n": entry["n"], "w": entry["w"]}
    return {"v": VERSION, "mid": mid, "conv": conv, "from": sender, "spub": env["spub"], "n": env["n"], "c": env["c"],
            "kc": env["kc"], "keys": clean_keys}


def safety_code(id_a: str, pub_a: bytes, id_b: str, pub_b: bytes) -> str:
    """A short code both people see the same way round; equal codes mean nobody swapped a key in between."""
    parts = sorted([(str(id_a), bytes(pub_a)), (str(id_b), bytes(pub_b))])
    digest = json.dumps([[i, p.hex()] for i, p in parts]).encode()
    for _ in range(1024):
        digest = hashlib.sha256(b"LP-safety-v1" + digest).digest()
    groups = [str(int.from_bytes(digest[i * 5:i * 5 + 5], "big") % 100000).zfill(5) for i in range(4)]
    return " ".join(groups)


def group_safety_code(members: dict) -> str:
    """The same idea for a group: every member's id and key ({id: public key bytes})."""
    digest = json.dumps(sorted([str(i), bytes(p).hex()] for i, p in members.items())).encode()
    for _ in range(1024):
        digest = hashlib.sha256(b"LP-group-safety-v1" + digest).digest()
    return " ".join(str(int.from_bytes(digest[i * 5:i * 5 + 5], "big") % 100000).zfill(5) for i in range(4))
