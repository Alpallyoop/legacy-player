> The ready-to-run kit (Docker, HTTPS proxy, systemd unit, deployment checker) is in `deploy/README.md`. This page explains the pieces.

# Hosting the meeting point (and the report receiver)

Players share their own server with friends outside their home through a **meeting point**: a server on a machine with
a public address. A player's server listens on their own computer only and keeps a few connections open to the meeting
point, made outward; friends connect to the meeting point with the player's `LP3-` server code and are passed on
(`server/rendezvous.py`). Nothing needs opening at home, and nobody learns anybody's address: the player's code holds no
address of their computer, only a token, and everything inside is TLS between the friend's app and the player's server,
which the meeting point cannot read. The same machine is also a normal shared server: players can make rooms on it
directly, and matches go through `server/relay`, encrypted between the players (TLS-PSK). It only needs a machine with a
public address and one open TCP port (a small VPS is enough).

Whoever runs it sees the addresses that connect to it, as with any server. It keeps no record of them: the server's
log never names an address, and the meeting point stores nothing about players.

## The built-in meeting point

Since 2026-11-01 the maintainers run one, and `PUBLIC_SERVER_CODE` in `launcher/version.py` names it
(`LP2-0068-CM2R-WH3T-FKHH-T89M-3379-YSSQ-WYM`):

- **Machine:** AWS Lightsail, `us-east-1`, the smallest Linux plan with a public IPv4 address (about USD 5 a month),
  with a static address. Instance `legacy-player-meeting-point-v2`, static address `legacy-player-meeting-point-ip`.
- **Service:** `deploy/legacy-player-server.service` (`start --share`, which makes it a meeting point too). Its
  certificate was made once and is pinned by the code above, so replacing the machine keeps the same code as long as
  the certificate and the static address are reused.
- **Updates:** a timer (`legacy-player-update.timer`) pulls the release branch every 30 minutes and restarts the
  server only when something changed.
- **Firewall:** TCP 8765 open to everyone. SSH only through Lightsail's browser console.

If you replace it with a server of your own, run the steps below and change `PUBLIC_SERVER_CODE`.

## 1. Run the server
```
python -m server.cli start --share --port 8765
```
`--share` listens on every address over TLS (it makes its certificate on first start and keeps it in the state folder)
and makes the server a meeting point too. Open TCP 8765 in the machine's firewall / cloud security group. Run
Legacy Player's own "Let friends connect" on a player's computer instead, and it becomes a *user* of a meeting point,
not one.

## 2. Make its server code
`python -m server.cli code --address <its public name or IP>`. It looks like `LP-0108-1G8J-AD18-3N2A-AAMD-YWSA-NX49-19F4-9D`
(nine groups after `LP`). A server reached by a host name or an IPv6 address gets a longer code that starts with `LP2-`.

## 3. Tell the app about it
Put the code in `PUBLIC_SERVER_CODE` in `launcher/version.py` and rebuild. For a test, any player can instead paste it
into Settings > Your server > "Meeting point code". Using a meeting point is a permission of its own ("Meeting point for
friends outside my home"); without it, a player's server is reachable on their home network only. A player's `LP3-`
code is never accepted as a meeting point code.

A player can also point their own server at a meeting point by hand: `python -m server.cli start --meet LP-...` listens
on `127.0.0.1` only, and `admin_meet_status` (the app's "How friends reach me") says whether its connections are parked.

## 4. Problem reports (optional)
```
python -m server.report_receiver --dir reports --port 8790 --token <secret>
```
Put it behind https (a reverse proxy such as Caddy), then set `REPORT_URL` in `launcher/version.py`.
Read what arrived: `python tools/read_reports.py reports`, or open the admin console.

### The admin console
Start the receiver with `--admin-token <another secret>` (or `LP_ADMIN_TOKEN`), open `https://<your address>/admin` in a
browser and paste the admin token into the form there (it is not put in the address, so it does not end up in browser
history or proxy logs). It lists everything that came in: crashes and failures
the app caught, and the reports players write themselves from Home > "See an issue or a problem?" (those carry a
category and the player's own words). Filter by kind, category and status, read each report in full, and mark it
new / looking / fixed / won't fix with a note. Triage lives in `<dir>/triage.json`; the reports are never changed. The
admin token is a different door from the report token: the app never needs it, and it never accepts a report.

## 5. The friends service (optional, separate)
Friend codes, who is online, one-click invites into a room, end-to-end encrypted messages and group chats, reporting
and blocking. Legacy Player works fully without it and players make no account: an app says hello once and gets a
friend code (like `MK7Q-4X2P-9HTA`). What the service can and can't see, and how the console is protected, is in
[`FRIENDS_SECURITY.md`](FRIENDS_SECURITY.md).

### Not on a player's computer any more
Earlier versions could run a friends service on the player's own computer (Friends > Run a friends service on this
computer). Its link held that computer's address, so it is no longer offered (`docs/canonical/SPEC.md`, "Addresses").
A player's game server already has a friends list of its own (Friends > Use my server's friends list), reached through
the meeting point like the rest of the server. A separate friends service runs on a rented server, as below.

### On a server (VPS)
```
python -m server.social --dir social --create-admin <your name>     # once: password, then the authenticator secret
python -m server.social --dir social --port 8791
```
`--create-admin` asks for the password without echoing it, prints the authenticator secret and `otpauth://` link, and
asks for one code before the account works. `--invite-moderator` prints a one-time invite code. Keep `social/` out of
any repository (the project's `.gitignore` already does) and readable only by the service's user.

Put HTTPS in front (a reverse proxy such as Caddy, or a tunnel), or pass `--tls-cert`/`--tls-key` and share the link
with its `#pin=` fingerprint. Players paste the link under Friends > Join a friends service. To moderate, open
`https://<address>/admin` and log in. The local key (`social/moderator.key`) is refused from other computers;
`--allow-remote-key` would turn that back on and is not recommended. Make sure the reverse proxy sets
`X-Forwarded-For` (Caddy does by default) so requests it passes on are never mistaken for local ones, and
`X-Forwarded-Proto: https` so console cookies are marked Secure.

The service stores names, codes, public keys, friend lists, group chats, presence and sealed messages (a week) it can't
read; never addresses or game traffic. Idle players are forgotten after 60 days, and a player can leave at any time
(everything about them is deleted).

### Who can reach whom
Only mutual friends can message or invite each other, and see each other's presence. Everyone else can only send a
friend request, and only with the player's friend code (12 characters, so codes can't be guessed); a player can close
requests altogether (Friends > "Let people with my code send me friend requests"). A group chat holds up to 10 people,
and someone can only be added if they are friends with everyone already in it and nobody there has blocked anyone.
Requests (20 an hour), code guesses (60 an hour), messages (20 a minute), invites (30 an hour), new group chats (10 an
hour), group changes (60 an hour) and reports (20 a day) are limited per player, and new identities per address (10 an
hour). Blocking hides a player from the blocker completely and takes the blocker out of group chats they share.

### Moderation
In Legacy Player (Friends > Moderation) for whoever runs the service or is logged in as a moderator, or in a browser
at `/admin` after logging in.

- **Reports:** players report a player or a single message (one-to-one or in a group), with a category (harassment,
  hate, threats, spam, scam, sexual content, offensive name, cheating, other) and optional details. Messages are
  end-to-end encrypted: the reporter's app shares the keys of the reported message and the few before it, and the
  service opens **its own copy** with them, so moderators read exactly what was sent and a report can't put words in
  someone's mouth (a made-up key is refused). The reported player is never told who reported them.
- **Time out** (1 hour, 24 hours, 7 days, 30 days): the player can still sign in and see friends but cannot message,
  invite, make group chats or send requests; they see the reason and when it ends. **End time-out** lifts it.
- **Ban:** the player is shut out (they see the reason), removed from everyone's friends, requests, invites and group
  chats, and is never forgotten by the idle clean-up. **Unban** lets them back with an empty friends list.
- **Word filter:** off by default. When on, the service refuses names, statuses, group names and invites containing
  filtered words (a built-in list of common profanity plus your own words). It can't read messages; each player has
  their own filter in Settings > Friends (on by default) that hides those words as `****` in what they read.
- **Log:** every moderator action with who did it, newest first, kept in `players.json`; console sign-ins in
  `admin_audit.log` (Accounts tab, owners only).

Limit worth knowing: players have no accounts and no addresses are kept, so a banned player can say hello again as a
new player with a new code. They start with no friends, and nobody can be messaged without accepting them first, so the
damage is small; report and block again if it happens.

## Notes
- A rented server's code carries its IPv4 address (short `LP-` code) or an IPv6 address / host name (longer `LP2-` code with a checksum). A host name means the address can change without a new code. Use the code with the access key (what `server.cli code` prints): its fingerprint is 80 bits, so players' apps pin the meeting point firmly.
- A player's code (`LP3-`) holds a token, their server's fingerprint and key, and the meeting point's code; never their own address. Making a fresh code changes the token and the key, so the old code stops working at once.
- Nothing here has been run on a real VPS yet; expect to fix small things on the first try.
