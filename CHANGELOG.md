# Changelog

All notable changes to Legacy Player are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and version numbers follow
[Semantic Versioning](https://semver.org/) (the app is still 0.x, so any release may change behaviour).

Each release on GitHub has the downloadable app, its SHA-256 sums and a build attestation
([docs/RELEASE.md](docs/RELEASE.md)). Releases before 0.7.47 were described only in their commit messages; the
summaries below are taken from those.

## [Unreleased]

Nothing yet. Contributors: add a line here with your change ([CONTRIBUTING.md](CONTRIBUTING.md#documentation)).

## [0.7.48] - 2026-10-13

### Changed

- **Legacy Player opens on Home again.** TV mode is a start-page choice (Preferences > Home page). A saved "TV mode"
  start page from the old default is reset to Home once.
- **Martin, whole.** The TV mode intro shows Martin standing in the middle of the screen, full body, paws held at his
  chest and tail up; the TV welcome screen uses the same picture.
- **Everything in the project folder.** `lp.cmd install` installs the program into the checkout's `app\` folder (with
  its `LegacyPlayerData`) instead of AppData; `-Dest` picks another folder. `lp.cmd remove-old` removes an older copy
  from `%LOCALAPPDATA%\Programs\LegacyPlayer` once its files were moved. `lp.cmd source` and the new `lp.cmd test`
  keep temporary files and caches in `.tmp\` and `.cache\` inside the checkout.

### Fixed

- **Controller in TV mode.** One reader for every controller (every 16 ms, also when the window is covered) replaces
  six separate loops: quick taps register, held directions repeat, any connected pad works (also in dialogs), pads
  without the standard layout (hat-switch D-pads) work, a player's in-game button remap no longer changes the menus,
  lost focus comes back on the next press, and TV mode no longer runs hundreds of animations that slowed input.
  A hint appears when another window is in front. Hold Back + Y for 2 seconds (or Controllers > Input check) to see
  what the controller sends.
- **The app window no longer signs in to Microsoft Edge or syncs.** Edge signed the window's own profile in to the
  Windows account by itself ("We are now syncing your browsing data"); the window now starts with sync, sign-in and
  background networking switched off.
- Long folder paths (for example in "Moving your files") wrap instead of running out of the box.

## [0.7.47] - 2026-10-12

This release acts on the re-audit of 0.7.46 ([docs/audits/AUDIT_2026-10-12.md](docs/audits/AUDIT_2026-10-12.md)):
consent that is checked before every action, friends that work wherever the game works, and a TV mode you can run
with only a controller.

### Added

- **Permissions.** Everything Legacy Player does that reaches outside your computer or changes something on it is a
  permission of its own (18 of them, listed in `launcher/consent.py` with the exact words the app shows). Each one is
  off until you allow it. When an action needs a permission you have not given, a box opens that says what is sent,
  to whom, what changes on your computer and how to undo it, then tries again once you allow it (keyboard, mouse or
  controller; "Not now" is picked first).
- **Permissions page** (Account > Permissions, and Help > Privacy and permissions). Shows each permission, whether it
  is allowed, when you decided, Allow / Turn off, and an append-only history of every decision. Turning a permission
  off switches its settings off and undoes what it can: it closes router ports, removes the firewall rules, stops the
  friends service it runs, puts your own Dolphin pad file back, and takes an IPv6 or Tailscale address out of your
  server code. It tells you what stays and how to remove it.
- **Versioned consent.** Each permission has a version. When what it does changes, your earlier yes no longer counts
  and the app asks again ("Please review N permissions" on Home and in the doctor's check-up).
- **Friends through the host's game server, with no setup.** With no friends link set, your friends list lives on the
  multiplayer server you are connected to: your own, or the friend's server you joined with a server code. Press
  "Get my friend code" on the Friends page. Friends traffic uses the same encrypted, certificate-checked connection
  as the game, so friends work wherever the game does. The host moderates it from the Moderation tab. A separate
  friends service (a friends link, or one you run on this computer) is still there as the advanced option.
- **Friends in the background.** While friends are in use, the app checks in every 30 seconds, even with the window
  closed to the tray, so friends still see you online. A new message, friend request or invite is announced once: a
  tray notification while the window is closed (a click opens Friends), or a notice in the app.
- **TV mode controller sheets:** Get emulators (shows which consoles still need one and gets them, asking for the
  download permission first); Friends (accept or decline requests, read and answer messages and group chats with the
  on-screen keyboard; LB / RB change tabs); Join a friend's server (type their server code); and a live room lobby
  (who is in, ready, start the match, leave or close the room).
- **Controller on desktop pages.** A page opened from TV mode works with the controller: the D-pad or stick moves to
  the nearest button, A presses it, B goes back to TV mode, LB / RB scroll.
- TV mode shows more: console rows past 300 games get an "All N games" tile, the game picker pages by 120, search
  shows 60 results and a count of the rest.
- Documentation: this changelog, [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md),
  [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for players and [docs/RUNNING_LOCALLY.md](docs/RUNNING_LOCALLY.md) for
  running from source. `tools/check_links.py` checks every relative link and anchor in the Markdown files (run by
  `tests/test_doc_links.py`), and `tools/check_ui_syntax.js` syntax-checks the UI's script blocks.

### Changed

- **Console mode is merged into TV mode.** Its tab and menu entry open TV mode, and a start page of "Console mode" now
  opens TV mode. "The last page I used" can return to TV mode.
- **The Privacy page is now the Permissions page** (same place in the menus).
- Things that go online or change your computer are now off until you agree, including opening your router for
  friends (UPnP), the start-up network test, the shared-server fallback, sharing your room with friends, and writing
  Dolphin's GameCube pad file. If you used an older version, anything that was switched on waits for you to look at it
  again; nothing runs until you do.
- The welcome screen lists every permission with nothing ticked; skipping it allows nothing.
- Name tags use a random number made for each server, so servers cannot link you; the install id is no longer sent.
- Hole punching (a direct route next to the relay) asks you for every match.
- Inviting a friend is refused with a clear reason when friends can not reach the room's server.
- Home and the doctor no longer count PC games as a console; Storage says "1 game", not "1 games".
- The server controls no longer capture the whole app's output while they run.
- [PRIVACY.md](PRIVACY.md) matches the code: opening the router (UPnP) has no Windows prompt, and a server code contains
  the host's address.
- Documentation refreshed: README quick start, roadmap, launcher work packages and requirements, documentation index.

### Fixed

- TV mode's Friends opens the permission box and gets your friend code itself, instead of waiting forever or sending
  you to the desktop page.
- Saying no to a permission is an answer: it is no longer listed under "Please review" (a no for one friends address
  still asks again for another).
- Clearing a friends link no longer hides friends that live on your multiplayer server.
- The in-app uninstaller also removes the Start menu shortcut when it removes the program; the installer takes
  `-NoShortcut` to skip making one.
- Settings are written from a snapshot, so a background friends check-in can't change them half-way through a save.

- **TV mode double press.** One press is one press: the A that opens a dialog is no longer read again inside it, so
  "Quit Legacy Player" no longer quits on a single press and "More about this game" stays open. The B that closes a
  dialog no longer also closes the TV sheet under it.
- A rescan forgets the emulator list inside the scan lock, so two scans can no longer mix their results.
- Friends' pinned keys and the "run a friends service" choice now survive a restart.

### Security

- Consent is enforced in Python, not just in the page: every outbound or system-changing action goes through one
  check (`LauncherApp._need`), and turning a setting on is not a yes. A yes comes only from the permission dialog.
  Tests check that each action is refused, and does nothing, without its permission.
- Server codes are never stored in plain text on a friends service: the code in an invite is sealed end to end for the
  invited friend, a shared room's code is sealed for the friends online, and on a game server's own friends list no
  code is sent at all. Plain server codes from older apps are dropped.
- Making a new friends identity on a game server needs that server code's key and is limited per address.

### Removed

- The separate Console mode page (TV mode replaces it).
- Endpoints the app never called: `api_find_games`, `api_private_link`, `api_monitors`. `api_network_check`,
  `api_dolphin_pads` and `api_engines_scan` are now internal helpers.
- The friends moderation branches `set_key` / `forget_key`, which nothing used.
- The old `privacy_ok` record. It is moved into the new consent record as a yes for an old version, so the app asks
  you to look again.

## 0.7.38 to 0.7.46 - 2026-10-10 to 2026-10-11

- **0.7.46:** the release passes its Windows tests; the installer takes both the folder build and the older single-exe
  releases; BIOS search no longer lists a file twice; a leftover `instance.json` can no longer block startup.
- **0.7.45:** TV mode (the default start page) with a retro-TV intro; library tools (hidden games, right-click Rename
  and Open with, tags, release years, series, filters, official names); Steam and Epic detection and local art;
  DAT game lists you supply; every file kept in Legacy Player's own folder or one you pick, with a one-folder Windows
  build; friends with end-to-end encrypted messages, group chats, honest reports and a moderation console behind a
  password and authenticator code; holiday towns.
- **0.7.44:** fixes from a full audit; restart and quit close the old window; updates check in the background; the
  GitHub account is Alpallyoop.
- **0.7.43:** updates download, check their SHA-256, install and restart by themselves; run and moderate a friends
  service on your own computer with one click.
- **0.7.42:** friends moderation (reports, time-outs, bans, word filter); Server info moves to the Servers page.
- **0.7.40 and 0.7.41:** Legacy Player World themes, each place by day and by night.
- **0.7.39:** a separate switch for every online feature, a privacy check by the doctor, and a full Friends area
  with inbox and blocking.
- **0.7.38:** audit fixes.

## 0.7.26 to 0.7.37 - 2026-10-08

- Direct computer-to-computer matches with TCP hole punching and the relay as automatic fallback (0.7.27).
- Server addresses are never printed in messages; the network test says when it is done (0.7.28).
- A slim in-game overlay with server controls; tray server code; notices in the app (0.7.29).
- Background styles, the doctor's desk computer, a tray that follows server changes (0.7.30).
- Update everything: the app, engines, Tailscale and games in one go, with a checklist (0.7.31).
- Manage Steam and PC games (hide, stores, pictures) (0.7.32); background picker in the Account menu (0.7.33).
- The in-app updater updates the copy that is running and keeps its window open on failure (0.7.34).
- A "Join a friend" card first on Servers (0.7.35); the title bar takes the theme colour on Windows 11 (0.7.36, 0.7.37).

## 0.7.6 to 0.7.25 - 2026-10-07 to 2026-10-08

- The server starts itself; a live server panel with the server code; automatic join (0.7.6).
- GameCube online play fixes; Dolphin game folders added for you and checked by the doctor (0.7.8 to 0.7.11).
- An optional encrypted private link for Dolphin over Tailscale, set up from the app (0.7.12, 0.7.13, 0.7.15).
- An optional Azure Artifact Signing step in the release workflow (0.7.14).
- Much faster library and emulator lookups, colour themes and a theme picker (0.7.16, 0.7.18).
- Windows Firewall rule handling that reports Windows' real answer and accepts a rule made by hand (0.7.17, 0.7.19,
  0.7.20).
- Steam and Epic games in the library; a clear keep-or-delete choice for saves on uninstall (0.7.21).
- Reaching friends without Tailscale (IPv6, a shared-server setup script, "How friends reach me") (0.7.22).
- The full scan adds the folders that hold your games (0.7.23); separate Settings and Preferences pages (0.7.24);
  one look for form controls in every theme (0.7.25).
- Open-source release files: MIT licence, privacy policy, security policy, third-party notes, code-signing policy.

## 0.7.0 to 0.7.5 - 2026-10-07

- 0.7.0: the first Windows release: zip build, PowerShell installer and release workflow.
- 0.7.1: hover quick play, display and monitor choice, force quit.
- 0.7.2: the in-game overlay with keyboard and controller shortcuts.
- 0.7.3: fixes from a full audit; the doctor asks about the save folders he made on uninstall.
- 0.7.4: a second hardening round and the `lp install` command.
- 0.7.5: timed, renewed router mapping; a firewall rule tied to the exe; the installer checks signatures.

## Before 0.7.0

- 2026-10-06 and 2026-10-07: the launcher, the self-hosted lobby and relay server and the owned emulator shell
  (Proposal 0002, phases 1 to 4); relay mode by default with consent for direct play; the Home page, menus, doctor's
  office, TV-style Console mode, controllers, saves, covers, problem reports, router opening and the shared-server
  fallback.
- March 2026: the research track: the Dolphin memory probe, memory discovery and RAM targeting for Mario Party 4,
  and the runtime, adapter and game-pack specifications.

[0.7.47]: https://github.com/Alpallyoop/legacy-player/releases
