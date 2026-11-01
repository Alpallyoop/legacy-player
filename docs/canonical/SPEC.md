# Legacy Player: specification

**Status:** Canonical. Approved 2026-11-01 (`docs/decisions/ADR-0002_LAUNCHER_SCOPE_AND_ADDRESS_PRIVACY.md`).
**Scope:** both tracks. The **launcher** has requirements LP-LR-xxx, and the **research runtime** has LP-FR-xxx and
LP-NFR-xxx. Every requirement, with its code, tests and status, is in `docs/REQUIREMENTS_TRACEABILITY.md`. The research
track's detail is in `docs/PROJECT_SPEC.md`. This file sets the rules that every part has to keep.

## 1. Trust boundaries

| Boundary | Who is on the other side | What protects it |
|---|---|---|
| Local web UI (`launcher/web.py`) | Other programs on this computer | Loopback only; `Host` header checked; a per-run token compared in constant time; the page is served only to the window the app opened |
| Lobby server (`server/api/json_server.py`) | Friends, through a meeting point or on the home network | TLS with the app's own certificate, pinned by fingerprint (80 bits) in the server code; the access key (40 bits) for new people, throttled per address; room credentials; per-address connection limits; admin operations from this computer only, and never from a connection that came through a meeting point |
| Relay (`server/relay/`) | The other players in a room | Room credentials; the match's own TLS-PSK key (256 bits), handed out by the lobby only to room members; the relay only copies bytes it can not read |
| Meeting point (`server/rendezvous.py`) | Whoever runs it, and anyone on the internet | TLS pinned to its fingerprint (from its own server code); parking needs the secret behind the token; joining needs the 96-bit token; everything inside is the friend's TLS to the player's server, end to end |
| Friends (`server/social/`) | The friends service and its moderators | Messages sealed end to end (X25519, ChaCha20-Poly1305, HKDF); invites sealed for the invited friend; moderation behind scrypt passwords and TOTP |
| Downloads and self-update (`launcher/installer.py`, `launcher/selfupdate.py`) | GitHub release hosts | HTTPS to allow-listed hosts only; size limits; SHA-256 checked against the release (fail closed); safe zip extraction |

## 2. Addresses (invariant)

No player's address (internet, IPv6, Tailscale or other routable address) is ever shown to another player, through any
code, endpoint, invite, event, message, log, report or screen.

1. A server code made for a player's own computer is either:
   - **LP3-** (`launcher/servercode.encode_meet`): a 96-bit token at a meeting point, the server's 80-bit certificate
     fingerprint, its 40-bit access key, and the meeting point's own address, port and fingerprint. It holds no
     address of the player's computer. The player's server then listens on `127.0.0.1` only.
   - **LP-/LP2- with a home-network address** (RFC 1918, or `fd00::/8`), when no meeting point is set. Never a public,
     shared (CGNAT), loopback or documentation address.
   LP-/LP2- codes with a public address are only for servers on rented machines (`python -m server.cli code`).
2. **A fresh code changes the token and the key.** Every older code stops working at once. Players already
   connected stay connected.
3. **Matches are relayed only.** The only endpoint a server accepts is `{"kind": "relay"}`. Direct addresses, Dolphin
   host codes and hole punching are refused by the server and by the app. RetroArch runs over TCP through the TLS-PSK
   tunnel. Dolphin NetPlay runs as UDP datagrams, each with a 2-byte length in front, inside the tunnel. Each player's
   emulator connects to `127.0.0.1` on its own computer.
4. **Room statistics are numbers only.** An address sent in them (such as an older app's `private_address`) is
   dropped and never stored or shown.
5. **A connection that came through a meeting point has no address** inside the player's server. It is never treated
   as this computer.
6. **What does see an address:** whoever runs a meeting point or server sees the addresses that connect to it, as
   with any server. They are never logged or stored (`json_server._log`, `server/rendezvous.py`). Every web request
   shows the site the player's address. The app and `PRIVACY.md` say both plainly.
7. **Removed for good, because they show addresses:** opening the router (UPnP), putting an IPv6 or Tailscale address
   in a code, the Tailscale private link, direct matches, hole punching, Dolphin's traversal server, and a friends
   service on the player's computer. Their permissions are retired (`launcher/consent.RETIRED`). An older yes is
   withdrawn at start-up and recorded, and what it did is undone (ports it opened are closed).

## 3. Consent (invariant)

1. Every network contact, download, change to the computer and data share has a permission item
   (`launcher/consent.ITEMS`). Each item says what happens, what is sent and to whom, what changes, what turning it off
   undoes, and what stays.
2. A yes is recorded with the time and the item's version, plus its scope (an address, for the friends service and
   reports). A changed text, version or scope asks again. The history only grows.
3. The yes is enforced in Python before the action (`LauncherApp._need` / `_allowed`). A setting turned on by itself
   is not a yes. Without a yes, the action is refused or quietly skipped in the background.
4. Everything is off by default. A withdrawn yes switches the feature off and undoes what can be undone.
5. Tests check that each action is refused without its yes (`tests/test_consent.py`).

## 4. Public schemas and contracts

| Contract | Where it is defined | Version rule |
|---|---|---|
| Lobby wire protocol (JSON lines over TLS) | `docs/WIRE_PROTOCOL_v1.md`, `server/lobby/service.py` | Additive; refusals are plain-language `error` strings |
| Meeting point protocol | `server/rendezvous.py`: `{"operation":"rv_park","token","secret"}` gives `parked`, then `paired`, then the server sends `{"go":true}`, then bytes; `{"operation":"rv_join","token"}` gives `paired`, then bytes | Token = first 12 bytes of SHA-256(`legacy-player-meeting-point:` + secret) |
| Server codes LP-, LP2-, LP3- | `launcher/servercode.py` | Crockford base32. LP2/LP3 carry a 2-byte SHA-256 check. LP3 flags `0x10` + host kind; a newer flag is refused with "update the app" |
| Match tunnel | `adapters/retroarch/tunnel.py`, `adapters/dolphin/udp_relay.py` | TLS 1.2 PSK (identity `legacy-player`, 256-bit key per match); UDP framing: 2-byte big-endian length |
| Friends API | `server/social/__init__.py`, `launcher/friends.py` | Sealed payloads; versioned with the app |
| Game packs and adapters | `docs/GAME_PACK_SPEC_v1.md`, `docs/ADAPTER_INTERFACE_v1.md` | Versioned files (`*_v1`) |
| Settings | `launcher/catalog.SETTINGS_SCHEMA` | Keys not in the schema are ignored, so a removed setting has no effect |
| Replay packages and receipts | `runtime/replay/REPLAY_PACKAGE_v1.md`, `docs/EVIDENCE_AND_RECEIPTS.md` | Canonical JSON; SHA-256; see `.constellation/SHARED_INVARIANTS.md` |

## 5. Failure semantics

- Fail closed with a reason a player can act on. A wrong fingerprint, a stale code, a missing yes, a bad checksum
  or a missing TLS-PSK are all refused. A match is never downgraded to an unencrypted or direct path.
- A wrong code never leaves the app pointed at a dead server: the change is undone.
- The meeting point's or relay's errors never name an address.

## 6. Release criteria

`docs/DEFINITION_OF_DONE.md` and `docs/RELEASE.md`: releases are built only from tested commits on `main` (`docs/CODE_SIGNING_POLICY.md`),
with SHA-256 sums and a build attestation. Every change runs the full test suite (`python -m unittest discover -s
tests`), `tools/validate_repository.py` and `tools/check_links.py`. One green run is not release readiness: the Windows
checks in `docs/WINDOWS_CHECKLIST.md` and two-network play in `docs/MULTIPLAYER_TEST_PLAN.md` are part of it.
