# Friends service: security and privacy

The friends service (`server/social`) is optional. It gives players friend codes, presence, room invites, messages and
group chats. This page says what it can and cannot see, how messages are encrypted, how reports stay honest, and how
the moderation console is protected. Code: `server/social/` (service), `launcher/friends.py` (the app's side).

## What the service can see, and what it can't

| The service stores and can read | The service stores but **cannot** read | The service never has |
|---|---|---|
| Display names, friend codes, friend lists, pending requests, blocks | Message text (one-to-one and group) | Players' private encryption keys |
| Each app's **public** encryption key | The per-message keys | Addresses (none are written to disk; per-address limits live only in memory) |
| Presence: online or not, a status line ("playing X") and, if the player shares it, the room's invite code | The server code of a shared room (sealed for the friends online) | Game traffic |
| Room invites (game name, invite code) | The server code in an invite (sealed for that one friend) | |
| Group chats: name, members, who made it | | |
| When each message was sent, by whom, to whom (needed to deliver it) | | |
| Reports, including the text of reported messages (see below) | | |

Messages are kept a week (200 per conversation, 300 per group). Idle players are forgotten after 60 days; "Leave the
friends service" deletes everything about a player at once. Older versions stored plain-text messages: they are dropped
when the service starts.

Who sees what among players: only **mutual friends** see each other's presence, status, room and public key. A pending
friend request shows the requester's name to the person asked, but the requester only sees the code they typed until
the other person says yes. Friend codes are 12 characters (about 60 bits), so they cannot be found by guessing; code
attempts, requests, messages, invites, new group chats, reports and new identities per address are all rate-limited.
The service does not answer "who is this id?" questions: names come only with a friendship, a conversation or a group.

## Where the service runs

By default (no friends link set) the friends list lives on the **multiplayer server the player is connected to**: the
host's game server (`server/api/json_server.py`) answers `{"operation": "friends", "friends": {...}}` on its own TLS
port with the same rules as the stand-alone service, run in-process (`server/social/inserver.py`) with its own folder
(`<server data>/social`). A friend who joined with the server code reaches it through the same certificate pin, router
port, relay and fallback paths as the game, so friends work wherever the game does. A new identity there needs the
server code's key (like browsing or joining a room) and is limited per address; later calls are authenticated by the
player's own id and secret, so a fresh server code does not cut friends off. The host moderates it from the app's
Moderation tab through the server's local admin channel (this computer only). Each player has one key pair; they get
one identity per service they use, and friends lists belong to one service. A separate service (a friends link, or
one this computer runs) stays available as the advanced option.

Server codes are never stored in plain text: an invite's server code is sealed end to end for the invited friend
(conversation `i:<sender>:<recipient>`), and a shared room's code for the friends online (conversation `r:<owner>`,
eleven friends per envelope); the service checks each envelope is from the sender's key and wrapped only for mutual
friends, and gives each friend only the envelope sealed for them. On a game server's own friends list no code is sent
at all: the room is on that same server. A plain server code from an older app is dropped.

## End-to-end encrypted messages

Pure Python, standard library only (`server/social/purecrypto.py`, checked against the RFC test vectors in
`tests/test_friends_crypto.py`):

- **X25519** key agreement (RFC 7748), **ChaCha20-Poly1305** authenticated encryption (RFC 8439), **HKDF-SHA256** (RFC 5869).

Each Legacy Player app has one long-term X25519 key pair. The private key is in `friends_identity.key` in the app's
data folder (owner-only permissions; on Windows the file's permissions are reduced to the current user) and never
leaves the computer. The public key is sent with hello and every heartbeat.

For every message (`server/social/e2e.py`):

1. The app picks a random 32-byte message key **K** and encrypts the text: `ChaCha20-Poly1305(K, nonce, text)`, with the
   conversation, the sender's id and the message id as associated data (a message can't be moved to another
   conversation or attributed to someone else).
2. It stores a **commitment** `SHA-256("LP-E2E-commit-v1" | K | message id)`, so exactly one K opens the message.
3. K is **wrapped** for every recipient and for the sender's own copy: `X25519(sender private, recipient public)` →
   HKDF → ChaCha20-Poly1305 over K. Because the wrap uses the sender's long-term key, the recipient knows which app sent it.

The service checks that an envelope is well formed, comes from the authenticated sender, belongs to that
conversation, and is wrapped for exactly the current members with the keys it has for them; it refuses anything else,
including plain text.

**Pinning and safety codes.** The app pins a friend's public key the first time it sees it. If a friend's key changes
later (a new computer, a reinstall, "Make a new key", or someone in the middle), the conversation shows a warning until
the player confirms they checked it. Every conversation and group has a short **safety code** (four groups of five
digits) computed from both people's ids and keys; if it is the same on both screens, nobody swapped a key in between.
The first contact relies on this check: until it is compared, a dishonest service could have handed out its own key.

**Filtering.** The service can't filter what it can't read. The service-wide word filter applies to names, statuses,
group names and invites; message text is filtered by each player's own app after decryption (Settings > Friends,
on by default).

**Old apps.** An app from before encryption has no public key. Newer apps show "Update Legacy Player to message
<name>" instead of a message box, the service refuses plain text, and old apps see "(an encrypted message: update
Legacy Player to read it)".

## Honest reports

Reporting a message makes the reporter's app hand the service **that message's key and the keys of up to five
messages before it** in the same conversation, and nothing else. The service then opens **its own stored copy** of
those messages with the revealed keys and checks each key against the stored commitment and the authentication tag.

- The reporter never sends text, so a report can't put words in anyone's mouth.
- A made-up key, or the key of a different message, does not open the stored message: the report is refused.
- Moderators see the reported message (marked as checked) and the shared context; context messages without a working
  key show as "(not shared by the reporter)".
- Keys of messages after the reported one, and of other conversations, are never revealed.

The text of a reported message is then kept in the report, readable by moderators. That is the one deliberate
exception to "the service can't read messages".

## The moderation console

`https://<service address>/admin` shows a login form and nothing else until someone signs in. Every data endpoint
needs a session (or, see below, the local key from the computer running the service).

- **Accounts**: owners and moderators, each with a name, a password (hashed with `hashlib.scrypt`, n=2^14, r=8, p=1, a
  per-account salt) and a **TOTP** second factor (RFC 6238: 6 digits, 30 s, one step of clock drift either way; a code
  is never accepted twice).
- **Wrong tries**: the same answer whatever was wrong. Five wrong tries in a row lock the account name for 30 s,
  doubling with each further wrong try up to an hour; unknown names are treated the same way. Logins and invite
  set-ups are also limited per address (20 per 10 minutes, in memory only).
- **Sessions**: a random 256-bit id kept only in memory (a restart signs everyone out), idle timeout 30 minutes,
  lifetime 12 hours, cookie `HttpOnly; SameSite=Strict; Path=/admin` and `Secure` over HTTPS (directly or when a proxy
  says `X-Forwarded-Proto: https`).
- **CSRF**: every change needs the session's CSRF token in `X-CSRF-Token`, and a cross-site `Origin` is refused.
- **Logout** ends the session on the service. Removing an account ends its sessions.
- **Audit log**: `admin_audit.log` records account set-ups, logins, failed logins, lockouts, logouts, invites, filter
  changes and moderator actions, with the account name and never an address.
- **Headers**: the console is served with a strict Content-Security-Policy, `X-Frame-Options: DENY`, `no-referrer`
  and `no-store`.

**First owner account**, on the computer that runs the service:

- In Legacy Player: Friends > Your service > **Set up the moderation console** (name, password twice, then add the
  shown secret or QR code to an authenticator app and type one code to turn it on).
- On a server: `python -m server.social --dir social --create-admin <name>` (asks for the password with getpass,
  prints the secret and the `otpauth://` link, then asks for one code).

**Moderators**: an owner presses *Invite a moderator* (console > Accounts, or Your service in the app, or
`python -m server.social --dir social --invite-moderator`). The one-time code is valid 48 hours and only its hash is
stored. The moderator opens the console, chooses *I have an invite*, picks a name and password and sets up their own
authenticator. In Legacy Player elsewhere, a moderator logs in under Friends > *I help moderate this service* (the
session lives in memory only).

**The local moderator key** (`moderator.key`) is what Legacy Player on the hosting computer uses for its Moderation
tab without typing anything. The service accepts it **only from this computer** (loopback, and not when a reverse proxy
passes the request on with `X-Forwarded-For`, `Forwarded` or `X-Real-IP`). `--allow-remote-key` turns remote use back on;
leave it off. If you put a reverse proxy on the same machine, make sure it sets one of those headers (Caddy and nginx's
usual `proxy_set_header X-Forwarded-For` do), or the key would look local.

**Where the secrets live**: all in the service's data folder (`social/` next to the app's data, or the `--dir` you
chose), with owner-only permissions: `players.json`, `admins.json` (password hashes, TOTP secrets, pending set-ups,
invite hashes), `admin_audit.log` and `moderator.key` (plus the TLS key in the app's `server/tls` folder when Legacy
Player runs the service). None of them belong in the
repository: `.gitignore` covers `social/`, `*.key`, `admin*.json`, session files, `data/` and `LegacyPlayerData/`, and
`tests/test_no_secrets_in_repo.py` fails if one is ever committed.

## Keys: backup, loss and rotation

- **Back up** a player's encryption key by backing up the Legacy Player data folder (`friends_identity.key`). Treat
  the backup as private: anyone with it can read that player's future messages if they can also reach the service.
- **Lost key** (new computer without a backup): the app makes a new key; friends see "new key" and should compare the
  safety code. Messages sealed for the old key can't be opened any more.
- **Rotate** (the key may have leaked): Friends > Friends > *Your encryption key* > *Make a new key*. Same effect as a
  lost key, on purpose.
- **Console accounts**: an owner removes an account (its sessions end) and invites again. A lost authenticator is
  handled the same way; the last owner can't be removed, so on a server use `--create-admin` to add a new owner.

## Limits worth knowing

- The cryptography is pure Python: fine for chat-sized messages, not constant-time. Timing attacks would need precise
  measurements of the player's own computer doing many operations with the same key; the service never asks the app to
  decrypt anything for it.
- No forward secrecy: messages are sealed with long-term keys. Someone who steals a private key *and* the service's
  stored envelopes (kept a week) can read those messages.
- The first key of a friend is trusted on first use; compare the safety code to be sure.
- Metadata is visible to whoever runs the service: who is friends with whom, who messaged whom and when, group
  membership, presence and invites.
- There are still no player accounts: a banned player can say hello again with a new code. They start with no friends,
  and nobody can be messaged without accepting them first.
