"""Helpers for the friends tests: players with real encryption keys, talking to a SocialService directly."""
from server.social import e2e
from server.social import purecrypto as pc


def hello(service, name):
    """service.hello with a fresh key pair; the result also carries the private half (as an app would keep it)."""
    key = pc.x25519_keypair()
    out = service.hello(name, pc.b64e(key[1]))
    return {**out, "key": key}


def befriend(service, a, b):
    service.request(a["id"], a["secret"], b["code"])
    service.decide(b["id"], b["secret"], a["id"], True)


def seal_for(service, sender, conv, member_ids, text):
    recipients = {m: pc.b64d(service.players[m]["pub"], 32) for m in member_ids}
    return e2e.seal(*sender["key"], sender["id"], conv, recipients, text)


def send(service, a, b, text):
    """a messages b, sealed for both of them like the app does."""
    env = seal_for(service, a, e2e.direct_conv(a["id"], b["id"]), [a["id"], b["id"]], text)
    return service.message(a["id"], a["secret"], b["id"], env)


def send_group(service, a, gid, text):
    env = seal_for(service, a, e2e.group_conv(gid), list(service.groups[gid]["members"]), text)
    return service.group_message(a["id"], a["secret"], gid, env)


def read(service, me, other):
    """me's conversation with other, opened with me's key: [(from, text)]."""
    rows = service.thread(me["id"], me["secret"], other["id"])["messages"]
    return [(m["from"], e2e.open_envelope(m["e"], me["id"], *me["key"])[0]) for m in rows]


def key_of(me, row):
    """The message key me holds for a stored row, as a report reveals it."""
    return pc.b64e(e2e.unwrap(row["e"], me["id"], *me["key"]))
