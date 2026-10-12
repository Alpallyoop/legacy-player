# Privacy policy

Legacy Player runs on your own computer. This page says exactly what it does with information. It applies to the app,
the optional server you can run, and the optional shared server and report receiver.

## What the app collects
**Nothing is sent to the maintainers by default.** There is no account, no analytics, no advertising and no tracking.
Your library, settings, saves and controller profiles stay on your computer, in the `LegacyPlayerData` folder inside the
Legacy Player folder, or in a folder you choose (Settings > Where Legacy Player keeps its files). Logs and temporary files
are kept there too; nothing is written to your user folders.

## Permissions: nothing goes out, and nothing on your PC changes, until you allow it
Everything Legacy Player does that reaches outside your computer, or changes something on it, is a **permission** of
its own (the full list, with the exact words the app shows, is in `launcher/consent.py`). Each one is off until you
allow it: in the box that opens the first time you use the feature, on the welcome screen (nothing is ticked there), or
on the Permissions page (Account menu). The app checks your yes before every such action, not just the setting: turning
a setting on by itself is not a yes. Each permission has a version; when what it does changes, your earlier yes no
longer counts and the app asks again ("needs a new look"). Every decision is kept with its date and version in an
append-only history on the Permissions page. Turning a permission off switches its settings off and undoes what it did
where it can (it closes router ports, removes the firewall rules, stops the friends service it runs, puts your own
Dolphin pad file back, takes the IPv6 or Tailscale address out of your server code); the page tells you what stays and
how to remove it. If you used an older version, anything that was switched on waits for you to look at it again.

Every web request below shows the site your internet address, as any web request does.

- **Internet downloads and updates.** GitHub (`api.github.com`, `github.com` and GitHub's file hosts, for Legacy Player
  and emulator updates), `buildbot.libretro.com` (RetroArch and its cores) and the emulator makers' own sites, only when
  you press a button that downloads or checks something.
- **Box art.** The game's name and console to `thumbnails.libretro.com`. For Steam and Epic games the app first uses
  the pictures those launchers keep on your computer (nothing is sent); otherwise a Steam game's store number goes to
  Steam's picture servers (`shared.akamai.steamstatic.com`, `cdn.cloudflare.steamstatic.com`, `steamcdn-a.akamaihd.net`),
  and an Epic game's picture address (already listed by the Epic launcher) to Epic's servers (`cdn1/cdn2.epicgames.com`,
  `cdn1/cdn2.unrealengine.com`) or its name to the Steam store search (`store.steampowered.com`).
- **Game details.** The game's title and console to Wikipedia (`en.wikipedia.org`) and Wikidata (`www.wikidata.org`),
  when you press Look it up.
- **Network test.** Small timing messages to the multiplayer server you use (your own, or a friend's).
- **Open my router for friends (UPnP).** The app asks your home router to forward your server's port (and the friends
  service's, if you run one) while they run, renews it, and closes it when they stop. **There is no Windows prompt for
  this.** The router tells the app your public address. At start-up the app closes a port a crashed run left open.
- **Windows Firewall rule.** An inbound rule for your server's port (and the friends service's). Windows shows its own
  approval box.
- **Shared server when yours can't be reached.** Only a shared server set in Settings or built into your copy (none is
  built in today). Your rooms, display name and encrypted game traffic then go through it, and whoever runs it sees your
  address.
- **Name tags.** Your display name, your previous tag and a random number made for that one server go to the server you
  host or join on, so it can give you a #tag nobody active there shares. The number differs per server; no install id is
  sent any more.
- **Friends service, what I'm playing, sharing my room, running a friends service.** See the next section.
- **Direct connections.** Your address goes to the other players in a match. Each match asks again, including for "hole
  punching" (trying a direct route next to the relay).
- **Tailscale private link.** Your Tailscale (100.x) address goes to the server and the players in your room.
- **IPv6 or Tailscale address in the server code.** See "Your address and the server code" below.
- **Installing and signing in to Tailscale.** Windows' package manager (winget) downloads Tailscale; signing in happens
  in Tailscale's own window.
- **Dolphin's settings files.** The app adds your GameCube/Wii game folders to Dolphin's game list and, if you choose,
  writes your controllers into Dolphin's GameCube pad file (your own file is kept as a backup and put back when you
  turn this off).
- **Problem reports sent automatically.** Reports have three settings: off (the default), ask each time (you read the
  report before deciding to send that one), and automatic, which only works with this permission, for the report
  address it was given for. A report is a short note about a failed action: the app version, Windows version, the kind
  of error and a scrubbed trace. Before anything is sent the app removes your user and PC names, folder paths, IP
  addresses, host names, e-mail addresses, server codes, invite codes and keys. The report receiver
  (`server/report_receiver.py`) keeps no record of who sent a report: no address, no headers, no request log.
- **Nothing else.** The maintainers receive no list of your games, no files and no identifiers.

Things you do yourself with a click need no permission: opening a link in your browser, joining a friend's server with
the code they gave you, hosting a room, and starting your own server.

## Your address and the server code
If you press Start with "Let friends connect", your computer runs a server and shows you a server code. **A server code
contains your server's address** (your public address, your home-network address, or the IPv6/Tailscale address you
chose), its port, its certificate fingerprint and an access key. The app hides the address on screen, but anyone who has
the code can decode it, so give it only to people you trust ("Make a fresh code" stops old codes from letting new people
in). Friends connect to *your* computer over an encrypted connection whose certificate is checked against the code. The
server keeps room state (names you chose, rooms, invite code hashes) on your computer. Matches go through the server's
relay by default, so the other players do not learn each other's address unless you allow a direct connection.

The installer (`install.ps1`) puts a Start menu shortcut named "Legacy Player" in your Start menu folder; `lp uninstall`
or the in-app uninstaller removes it.

## Friends service (optional)
Friends (friend codes, who is online, room invites, messages and group chats) work only if you connect to a friends
service; Legacy Player works fully without one, and none of it is contacted before you allow it. Players make no account and give no e-mail or password. Whoever runs the
service you connect to stores, on their computer: the display name you chose, your friend code, your app's public
encryption key, your friends and pending requests, your group chats, invites, a presence line (online or not; the game you are playing
only with the "Show friends what I'm playing" permission; the room you host, with its invite code and your server code,
only with "Share my room with friends"), and your messages, kept for 7 days. While the app is open it asks the service
for news every 12 to 30 seconds, so the service sees that you are online and your internet address. Invites (with the
server code they carry, and so your server's address) are stored by the service for up to an hour, or until dismissed. **Messages are end-to-end encrypted**: they are sealed on your computer and opened on your friends' computers, and
the service stores them in a form it cannot read. Your private key stays in your data folder and never leaves your
computer. A player who has not used the service for 60 days is forgotten.

If you report a message, your app shares the keys of that message and the few before it (and nothing else) with the
service, so its moderators can read exactly those messages from the service's own copy; the report keeps them. If
someone reports a message of yours, the same happens. Moderators can time players out, ban them and filter names.

Legacy Player can run a friends service on your own computer (Friends > Run a friends service on this computer). Then
you are the one running it: everything above is stored on your computer (it cannot read the messages either), and you
see and handle the reports. The friends link you give your friends contains your computer's address, so anyone you give
it to learns that address. Its moderation console needs an account with a password and a code from an authenticator
app; the accounts and the console's sign-in log (names and times, never addresses) stay on your computer.
Details: [docs/FRIENDS_SECURITY.md](docs/FRIENDS_SECURITY.md).

## Who can see what
- Players in the same room see the display name you chose (with a short tag) and your controller inputs during a game.
- The person running a server can see who is connected to it and from which network address, as with any server.
  Their server is theirs; this project does not run one for you.

## Your control
Turn any permission off on the Permissions page (Account menu), and uninstall at any time: the doctor (Uninstall Legacy Player) asks whether to
keep or delete the save folders it made, removes only what Legacy Player created and leaves nothing running. Delete
the `LegacyPlayerData` folder (or the folder you chose) to remove your data.

## Changes and contact
Changes to this policy are made in this file and visible in the repository history. Questions: open an issue at
https://github.com/Alpallyoop/legacy-player/issues.
