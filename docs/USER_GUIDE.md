# Legacy Player: a guide for players

Legacy Player is a launcher for your old games. It finds your games, starts each one in the right emulator, sets up
your controllers, backs up your saves, and lets you play online with friends. It runs on your own Windows computer:
there is no account, and nothing goes online until you allow it.

Legacy Player does not come with games, BIOS files or emulators. You use your own games. It can download emulators
from their official pages when you ask it to.

## Contents

- [Install](#install)
- [First run](#first-run)
- [Permissions: you decide](#permissions-you-decide)
- [Adding your games](#adding-your-games)
- [Getting emulators](#getting-emulators)
- [Controllers](#controllers)
- [TV mode with a controller](#tv-mode-with-a-controller)
- [Playing with a friend](#playing-with-a-friend)
- [Friends and messages](#friends-and-messages)
- [Saves](#saves)
- [Updates](#updates)
- [Troubleshooting](#troubleshooting)
- [Reporting a problem](#reporting-a-problem)
- [Uninstalling](#uninstalling)

## Install

Open PowerShell (no administrator needed) and paste:

```powershell
irm https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/install.ps1 | iex
```

It downloads the newest release, checks it has not been changed on the way (SHA-256), installs it in
`%LOCALAPPDATA%\Programs\LegacyPlayer`, adds "Legacy Player" to your Start menu and opens it. Other ways to install
(Command Prompt, git, or the zip by hand) are in the [README](../README.md#install-windows).

Windows may say "unknown publisher" the first time, because the app is not code-signed yet: press **More info**, then
**Run anyway**.

## First run

The first time, the doctor walks you through five short steps. Any step can be skipped; the rest carries on.

1. **Meet the doctor.** Pick a name and a picture. Other players see your name with a four-character tag, like
   `#4821`.
2. **Your games.** Paste the folder your games are in. Legacy Player only reads it: nothing is moved or renamed.
3. **Scan my computer.** One scan finds the emulators and BIOS files you already have. It only reads names and uses no
   internet.
4. **Permissions.** A list of everything that goes online or changes your computer. Nothing is ticked: tick only what
   you want. Skipping allows nothing.
5. **All set.**

After that, Legacy Player opens in [TV mode](#tv-mode-with-a-controller) with a short intro (any button skips it). To
open somewhere else, change Preferences > Home page > "Open Legacy Player to".

Closing the window with **X** keeps Legacy Player running in the tray (the small icons by the clock), so your server
and friends stay on. Right-click the tray icon to stop the server or exit.

## Permissions: you decide

Everything Legacy Player does that reaches outside your computer, or changes something on it, is a **permission** of
its own: downloads, box art, game details, the network test, opening your router, the firewall rule, the shared
server, name tags, friends and what they see, direct connections, Tailscale, Dolphin's settings files and automatic
problem reports. Each one is off until you allow it.

- **The first time you use something** that needs a permission, a box opens. It says what is sent, to whom, what
  changes on your computer and how to undo it. Press **Allow** to go ahead, or **Not now**.
- **The Permissions page** (Account > Permissions, or Help > Privacy and permissions) lists all of them, whether each is
  allowed, and when you decided. **Turn off** switches one off and undoes what it can: it closes router ports, removes
  firewall rules, stops a friends service you run, puts your own Dolphin controller file back. The page tells you what
  stays and how to remove it. A history at the bottom lists every decision.
- **When a permission changes** in a new version of Legacy Player, your earlier yes no longer counts. Home and the
  doctor then say "Please review N permissions", and that feature waits until you look again.

Things you do yourself with a click need no permission: joining a friend's server with the code they gave you,
hosting a room, starting your own server, opening a link in your browser.

The full list, with what each one sends: [PRIVACY.md](../PRIVACY.md).

## Adding your games

- Add a folder: in the first-run step, on the Library page ("Add your games folder"), under Settings > Library
  folders, or in TV mode (Tools > Add a games folder). Folders are only ever read.
- Keep games sorted in folders named after the console (NES, SNES, PS2 and so on). Legacy Player knows 18 consoles,
  from NES to PS3, and also lists your installed Steam and Epic games.
- **Scan this computer** (Tools menu, or in TV mode) looks for folders with games and for emulators, and adds what it
  finds.
- **Rescan my games** (Games menu) reads your folders again after you add games.
- Box art: right-click a game > **Get box art for this game…** (needs the Box art permission), or pick your own picture.
- Right-click a game for more: favourite, hide, rename, open with another emulator, properties. Hidden games are under
  Games > Hidden games.

## Getting emulators

A game needs an emulator before it can start.

- **Normal window:** Configure > Engines (get or update emulators). Press **Get** next to a console's emulator.
- **TV mode:** the "Get emulators" tile (in Get started, Ready to play or Tools) shows which consoles still need one
  and gets them, one press each.

Downloads come from each emulator's official release page and need the "Internet downloads and updates" permission.
Emulators you already have are found by the scan. BIOS files are never downloaded: some consoles need your own dump,
and the doctor tells you which ones and where to put them.

## Controllers

Configure > Controllers. Plug in your controllers, give each player one (up to four), and press buttons to see them
light up on the drawing. **Map buttons** or **Set by holding buttons** if a button is wrong; each console has its own
layout. For GameCube games in Dolphin, Legacy Player can write your controllers into Dolphin's own file for you (the
"Change Dolphin's settings files" permission; your old file is kept and put back when you turn it off).

**In-game overlay:** while a game runs, press **Ctrl+Shift+L**, or hold **Back + Start** on the controller, for a small
window over the game with Force quit, full screen or windowed, and your room code. Change both under Preferences.

## TV mode with a controller

TV mode is a full-screen home for the couch, made to be used with only a controller (an Xbox-style pad works best).

**Open it:** the TV mode tab, Games > TV mode, **F11**, **Ctrl+Shift+T**, the controller's **Guide** button, or hold
**Back + Start** for a second (not while a game runs). **Leave it:** Start menu > Exit TV mode, or the Power row.

| Controller | Keyboard | What it does |
|---|---|---|
| D-pad or left stick | Arrow keys | Move |
| A | Enter | Select |
| B | Esc | Back |
| X | O | Options for the game or tile (favourite, play with options, details) |
| Y | / | Search games |
| RT | P | Play the selected game straight away |
| LB / RB | Tab / Shift+Tab | Previous / next row (in a sheet with tabs, like Friends: change tab) |
| Start or Guide | M | Menu: Resume, Search games, Tools, Settings, Library (normal window), Exit TV mode |
| | F11 | Full screen on or off |

The rows are: what you played last (or "Jump in" picks), Favourites, Recently added, Ready to play, Play with friends,
one row per console, **Online**, **Friends**, **Tools**, **Settings** and **Power**.

With only a controller you can:

- play games, see their details, pick favourites, and search with the on-screen keyboard;
- **get emulators** (Tools > Get emulators);
- **host a room** or **join with a code** (Online row), **join a friend's server** by typing their server code, and use
  the **room lobby**: see who is in, get ready, start the match, leave or close the room;
- **friends**: accept or decline friend requests, read and answer messages and group chats, join a friend's room
  (Friends row);
- run the doctor's check-up, scan this computer, add a games folder, rescan, and change display, theme, sounds and
  start-up options.

A few things open a page of the normal window (for example "All settings" or the Library). The controller still
works there: the D-pad moves to the nearest button, **A** presses it, **LB / RB** scroll, and **B** brings you back to
TV mode. Typing into a text box on those pages needs a keyboard.

## Playing with a friend

Playing online needs **one server**. One person hosts it on their own computer; everyone else joins with the host's
**server code**. Nobody needs to rent a server.

### If you host

1. Open **Servers**. Under "Hosting? Your own server", tick **Let friends connect** and press **Start**.
2. Legacy Player asks for the permissions it needs: opening your router for friends (UPnP) and the Windows Firewall
   rule (Windows shows its own box; press Yes). Press **Show server code**, then **Copy**, and send the code
   (`LP-...`) to your friend in private.
3. Host a room: hover a game's cover and press **Online**, or Servers > Rooms, or in TV mode Online > **Host a room**.
   The room has its own **invite code**; your friend uses it to come in. You can ask to approve everyone, keep a
   waiting line, or make the room open so people on your server can see it.
4. When everyone is ready, start the match.

**What the server code reveals.** A server code contains your server's address (your public internet address, your
home-network address, or the IPv6 or Tailscale address you chose), its port, its certificate fingerprint and an access
key. The app hides the address on screen, but anyone who has the code can work it out. So give it only to people you
trust. **New code** makes a fresh one: the old code stops letting new people in, and everyone already connected stays
connected.

During a match, game traffic goes through your server's relay by default, so players do not learn each other's
address. "Direct connections" (faster; needed for Dolphin) gives your address to the other players in that match, and
asks you each match.

### If you join

1. Get the host's server code from them.
2. Servers > "Joining a friend? Paste their server code", paste it and press **Connect**. In TV mode: Online > **Join a
   friend's server** and type it.
3. Join their room with the room's invite code ("Join with a code"), or from the list of open rooms.

You do not need to start a server of your own to join.

### When friends can't reach your server

- Servers > Server info > **Test my network** says whether your computer is better at hosting or joining.
- **How friends reach me** shows the ways a friend can connect to you and which ones work on your computer.
- **Test my router** opens your server's port for a moment and closes it again. **Check Windows Firewall** checks the
  rule.
- Some connections can't be reached from outside at all (a phone hotspot, or a provider that shares one address
  between many homes). Then let the other person host, use the "Advanced: a private network with Tailscale" option on
  the Servers page, or a shared server if one is set in Settings > Your server.

More detail per console: [NETPLAY_BY_CONSOLE.md](NETPLAY_BY_CONSOLE.md).

## Friends and messages

Friends need no extra set-up: your friends list lives on the **server you are connected to** (your own, or the friend's
server you joined with a server code), and it travels over that server's encrypted connection.

1. Open **Friends** and press **Get my friend code**. Legacy Player asks for the "Friends service" permission first.
2. Give your friend code (like `MK7Q-4X2P-9HTA`) to a friend, or type theirs (**Add a friend**). They accept your
   request, and you are friends.
3. Now you can see who is online, send messages and make group chats (up to 10 people), and invite friends into your
   room. Messages are **end-to-end encrypted**: the server stores them but can't read them, and keeps them a week.

Good to know:

- A friends list belongs to one server. Your friends on your own server are not the same list as your friends on a
  friend's server.
- "Show friends what I'm playing" and "Share my room with friends" are separate permissions.
- While friends are in use, Legacy Player checks in every 30 seconds, even with the window closed to the tray, so your
  friends see you online. A new message, friend request or invite shows as a notice in the app, or as a tray
  notification when the window is closed (click it to open Friends).
- Each conversation has a **safety code**. If it is the same on both screens, nobody swapped a key in between. If a
  friend's key changes, the app warns you.
- You can **block** a player (they are not told) and **report** a player or a single message to whoever runs the
  server. The host moderates their server's friends list from the Moderation tab.
- The Friends page has "Let people with my code send me friend requests"; Settings > Friends has the word filter.
- Advanced: a separate friends service keeps one friends list whatever server you play on. Someone runs it (Friends >
  Run a friends service on this computer) and shares its link. How it is secured: [FRIENDS_SECURITY.md](FRIENDS_SECURITY.md).

## Saves

Configure > Saves and backups. Legacy Player finds each emulator's save files. **Back up all saves now** makes one zip
with the date; restoring first backs up what is there now, so you never lose progress. You can keep backups in another
folder, a USB drive or a synced folder.

## Updates

Account > **Update everything** (or **Check for updates**) downloads the newest Legacy Player, checks it, and restarts
on it after a short countdown ("Not now" keeps it for later). Update everything can also update your emulators.
Checking and downloading need the "Internet downloads and updates" permission. Your settings, saves and games stay.

## Troubleshooting

**Start with the doctor.** The **Setup** tab (Tools > Doctor's office) checks what is missing: emulators, cores, BIOS
files, Dolphin's game folders, permissions to review. Each problem has a **Fix** button where one exists. In TV mode:
Tools > Doctor check-up.

| Problem | Try this |
|---|---|
| A game won't start | Ask the doctor: it names the missing emulator, core or BIOS for that console. |
| A game opens on the wrong screen or not full screen | Configure > Where and how games open, or "Play with options…" on the game. |
| A button is wrong | Configure > Controllers > Map buttons. |
| A feature does nothing and asks for permission | That is on purpose: read the box and Allow, or turn it on under Account > Permissions. |
| "Please review N permissions" | A permission changed in an update. Open Permissions and look at it again. |
| Friends can't connect to your server | Servers > Server info: Test my network, How friends reach me, Test my router, Check Windows Firewall (see [above](#when-friends-cant-reach-your-server)). |
| Friends don't show up | You are on a different server than your friends: friends lists belong to one server. |
| The window says Legacy Player isn't answering | It was closed or restarted. Start it again from the Start menu. |

Your settings, logs and everything else Legacy Player saves are in one folder: `LegacyPlayerData` in the Legacy
Player folder, unless you chose another under Settings > Where Legacy Player keeps its files. The logs are in its
`logs` folder.

## Reporting a problem

On the Home page, press **See an issue or a problem?**. Pick what it is about and describe it. Your words go with the
app and Windows version and, if you tick it, the names of your last few actions. Your name, addresses, folders and
codes are never included.

If something fails, Legacy Player can also offer a report. Settings > Privacy > "Help fix problems by sending reports"
chooses: Off (the default), Ask me each time, or Send automatically (a permission of its own). If your copy has no
report address, the report is kept on your computer: copy it from **Settings > Problem reports** and paste it into a
[GitHub issue](https://github.com/Alpallyoop/legacy-player/issues) (the bug form asks for it).

## Uninstalling

Help > **Uninstall Legacy Player...**. The doctor asks whether to keep or delete the save folders he made, then removes
only what Legacy Player created (its folder and files, the firewall rules and router ports it opened). Your games and
emulators you installed yourself are not touched. When it removes the program it also removes the "Legacy Player" Start menu shortcut the installer
made.
