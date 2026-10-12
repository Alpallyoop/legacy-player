> The ready-to-run kit (Docker, HTTPS proxy, systemd unit, deployment checker) is in `deploy/README.md`. This page explains the pieces.

# Hosting the shared server (and the report receiver)

Legacy Player falls back to a shared server when a player's own connection cannot be reached from outside (phone
hotspot, provider-shared address, router with UPnP off). Both players then connect *out* to it, so nothing needs opening
at home. Game traffic goes through `server/relay` and stays encrypted between the players (TLS-PSK); the shared server
cannot read it. It only needs a machine with a public address and one open TCP port (a small VPS is enough).

## 1. Run the server
```
python -m server.cli start --host 0.0.0.0 --port 8765 --tls-cert cert.pem --tls-key key.pem
```
(or run Legacy Player on that machine and press Start with "Let friends connect"). Open TCP 8765 in the machine's
firewall / cloud security group.

## 2. Make its server code
On that machine, in the app: Servers > start with "Let friends connect", then Show server code. Without the app:
`python -m server.cli code --address <its public name or IP>`. It looks like `LP-0108-1G8J-AD18-3N2A-AAMD-YWSA-NX49-19F4-9D`
(nine groups after `LP`). A server reached by a host name or an IPv6 address gets a longer code that starts with `LP2-`.

## 3. Tell the app about it
Put the code in `PUBLIC_SERVER_CODE` in `launcher/version.py` and rebuild. For a test, any player can instead paste it
into Settings > Your server > "Shared server code". Players can turn the fallback off in the same place.

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

### The easy way: from Legacy Player (no commands)
Friends > **Run a friends service on this computer**. Legacy Player then, by itself:
- starts the service in the background (it keeps running with the window closed, and starts again with the app and
  after updates);
- serves it over HTTPS with the same self-signed certificate as your multiplayer server, and gives you a **friends link**
  (`https://<your address>:8791/#pin=<fingerprint>`) to send to friends. Their app checks the fingerprint, so nobody can
  pretend to be your service;
- asks your router to open the port (when the router allows it) and offers to add a Windows Firewall rule;
- makes a local moderator key and uses it itself: you are the moderator, and Friends > **Moderation** has the reports,
  players, time-outs, bans, word filter and log. The service accepts that key from this computer only.

Friends > **Your service** has the link, **Stop**, and **Set up the moderation console**: pick an account name and a
password, add the shown secret (or scan the QR code) in an authenticator app, and type one code. Then the console at
`https://<your address>:8791/admin` works from any browser with name + password + code, and **Invite a moderator**
gives a one-time code for someone who helps you (they pick their own password and authenticator, and can then log in
in the console or in Legacy Player under Friends > *I help moderate this service*).

Everything it knows stays on that computer, in Legacy Player's data folder (`social/`): players, encrypted messages,
reports, console accounts (password hashes and authenticator secrets), the sign-in log and the local key, all readable
only by your user. The Permissions page lists it as "Run a friends service on this computer".

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
- A server code can carry an IPv4 address (short `LP-` code) or an IPv6 address / host name (longer `LP2-` code with a checksum). A host name means the address can change without a new code.
- Rotating the code (Make a fresh code) stops the old one working for new players only.
- Nothing here has been run on a real VPS yet; expect to fix small things on the first try.
