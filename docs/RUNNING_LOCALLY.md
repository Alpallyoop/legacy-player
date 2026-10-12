# Running Legacy Player locally

For developers and people who want to run Legacy Player from its source code, run the multiplayer server or the
friends service on their own, or build the Windows app themselves. Players who just want the app: see the
[README](../README.md#install-windows) and the [user guide](USER_GUIDE.md).

## Contents

- [Requirements](#requirements)
- [Run the app from source](#run-the-app-from-source)
- [The lp command (Windows)](#the-lp-command-windows)
- [Where files go](#where-files-go)
- [Run the multiplayer server on its own](#run-the-multiplayer-server-on-its-own)
- [Run the friends service on its own](#run-the-friends-service-on-its-own)
- [Build the Windows app](#build-the-windows-app)
- [Reset permissions](#reset-permissions)
- [Uninstall](#uninstall)

## Requirements

- Python 3.13 or newer. Nothing else is needed for the app, the server or the friends service (standard library only).
- Optional: `python -m pip install -r tools/memory_probe/requirements.txt` for the Dolphin memory probe (psutil).
- For the tests: see [CONTRIBUTING.md](../CONTRIBUTING.md#run-the-tests).

Legacy Player is made for Windows. From source it also runs on Linux for development: the library, emulators that
are installed, the server, rooms and friends work; Windows-only parts (the tray icon, window placement, the firewall
rule, the Recycle Bin, Start menu shortcut) quietly do nothing.

## Run the app from source

From the repository folder:

```
python -m launcher                          # Windows (or: start_launcher.bat, or .\lp.cmd source)
python3 -m launcher                         # Linux
python -m launcher --games "D:\Games"       # also add a games folder (repeatable)
```

It starts a small local web server on `127.0.0.1` and opens the app in your browser. Options:

| Option | What it does |
|---|---|
| `--games FOLDER` | Adds a folder that holds your games. Repeat it for more folders. You can also add folders in the app. |
| `--data-dir FOLDER` | Keeps all of Legacy Player's files in that folder instead of the default (see [Where files go](#where-files-go)). Handy for a throw-away test copy. |
| `--port N` | The local page's port. Default 8780; when that is taken and no port was given, a free one is used. |
| `--no-browser` | Starts without opening a window. The address to open (with its one-time access token) is printed. |
| `--window` | Opens an app-style window (Edge or Chrome in app mode) and quits when it is closed. The built Windows app always does this. |

Only one Legacy Player runs per data folder. Starting it again shows the window of the one already running.

Set `LEGACY_PLAYER_NO_BACKGROUND=1` in the environment to switch off background work while you test: router renewals
at start-up, friends check-ins and starting a friends service you run.

## The lp command (Windows)

`lp.cmd` (which runs `lp.ps1`) is a small helper in the repository. In PowerShell type `.\lp.cmd`; in Command Prompt
`lp` is enough.

| Command | What it does |
|---|---|
| `.\lp.cmd install` | Downloads the newest release, checks its SHA-256 and installs it to `%LOCALAPPDATA%\Programs\LegacyPlayer` with a Start menu shortcut (no administrator needed). Add a tag, for example `.\lp.cmd install vX.Y.Z`, for one exact version. |
| `.\lp.cmd update` | Installs the newest release over the current one. Your saves and settings stay. |
| `.\lp.cmd run` | Starts the installed app. |
| `.\lp.cmd version` | Shows the installed version and the newest one. |
| `.\lp.cmd path` | Shows where the app is installed. |
| `.\lp.cmd uninstall` | Removes the program and its Start menu shortcut. Your `LegacyPlayerData` folder stays. |
| `.\lp.cmd source` | Runs this checkout with Python (`python -m launcher`). Its files go to the checkout's `data` folder. |
| `.\lp.cmd help` | Lists the commands. |

Options: `-Repo owner/name` for a fork, `-Token <token>` for a private repository, `-NoLaunch` to install without
starting the app.

## Where files go

Legacy Player keeps everything it writes in **one folder**. Nothing goes to your user folders. Which folder is used
(the first that applies; the full rule is in `launcher/datadir.py`):

1. `--data-dir FOLDER` on the command line.
2. The folder written in `data-location.txt` next to the program (the exe's folder, or the checkout when run from
   source). The app writes this file when you move your files with Settings > Where Legacy Player keeps its files.
3. `LegacyPlayerData` next to `LegacyPlayer.exe` for the Windows app, or `data` in the checkout when run from source
   (git ignores it).
4. `~/.legacy-player`, where version 0.7.44 and older kept files, if it still holds them. The app then offers once to
   move them.
5. If the program folder can not be written to (for example under Program Files), the app asks you to pick a folder.

Inside the data folder:

| Path | What is in it |
|---|---|
| `user_data.json` | Settings, library folders, favourites, controller profiles, and the **permissions record** (`consent`: each decision with its date and version, plus the full history). |
| `library_cache.json` | The last library scan. |
| `logs/` | `app.log`, `server.log` (your multiplayer server), `service.log` (a friends service you run), `launcher.log`, `apply.log` (updates), and `reports/` (problem reports waiting to be read or sent). Settings > Where Legacy Player keeps its files can put the logs in a folder of their own (`logs-location.txt`). |
| `tmp/` | Temporary files, emptied at start. |
| `emulators/` | Emulators Legacy Player downloaded. |
| `covers/`, `gamecards/`, `gamelists/` | Box art, game details you looked up or wrote, game lists (DAT files) you added. |
| `saves/`, `save_backups/` | Save folders Legacy Player made, and backups. |
| `server/` | Your multiplayer server: rooms, its certificate (`tls/`), the server code's access key, and its friends list (`social/`). |
| `social/` | A friends service you run on this computer (Friends > Run a friends service on this computer). |
| `friends_identity.key` | Your private friends key. It never leaves the computer. Keep it if you want to keep your friends. |
| `update/` | Downloaded updates while they are installed. |
| `window_profile/`, `overlay_profile/` | The app window's own browser profile. |

## Run the multiplayer server on its own

The app starts and stops your server for you (Servers page). To run one without the app, for example on a Linux box
or a Raspberry Pi, from the repository folder:

```
python -m server.cli start --detach          # in the background; start_server.bat does this on Windows
python -m server.cli status
python -m server.cli restart
python -m server.cli stop                    # graceful: tells players, saves rooms; stop_server.bat on Windows
```

Run one command at a time. The default listens on `127.0.0.1:8765` (this computer only) and keeps its state in
`artifacts/state` (change it with `--state-dir`).

To let friends connect:

```
python -m server.cli start --detach --share                     # encrypted, on every address; makes its own certificate
python -m server.cli code --address play.example.com            # prints the server code friends type
```

`--share` makes a certificate on the first run and keeps it in the state folder, so the server code stays the same
across restarts. Open the port (8765 by default, `--port` to change) in the firewall and router yourself. Other
options: `--tls-cert`/`--tls-key` for your own certificate, `--max-players`, `--max-rooms`, `--max-waiting`. Without
TLS the server refuses any address other than loopback unless you add `--allow-insecure-remote` (do not do that on
the internet).

The game server also answers friends requests for the players who joined it (see
[FRIENDS_SECURITY.md](FRIENDS_SECURITY.md#where-the-service-runs)); its friends data is in `social/` inside the state
folder. More: [server/README.md](../server/README.md), and for a shared public server
[HOSTING_PUBLIC_SERVER.md](HOSTING_PUBLIC_SERVER.md) and [deploy/README.md](../deploy/README.md).

## Run the friends service on its own

Usually not needed: friends work through the game server. A separate service keeps one friends list whatever server
people play on. In the app: Friends > Run a friends service on this computer. On its own:

```
python -m server.social --dir social --create-admin <your name>   # once: a console account (password + authenticator)
python -m server.social --dir social --port 8791                  # run it (127.0.0.1 by default; --host to change)
```

Serve it over HTTPS (`--tls-cert`/`--tls-key`, or a reverse proxy such as Caddy) before anyone else uses it. Keep
the `social/` folder private and out of git (`.gitignore` already leaves it out). Players paste its link under
Friends (Advanced: use a separate friends service). Details: [HOSTING_PUBLIC_SERVER.md](HOSTING_PUBLIC_SERVER.md#5-the-friends-service-optional-separate)
and [FRIENDS_SECURITY.md](FRIENDS_SECURITY.md).

## Build the Windows app

On Windows with Python 3.13+, from the repository folder:

```
.\build_exe.bat                                   # builds dist\LegacyPlayer\LegacyPlayer.exe (plus its _internal folder)
powershell -File tools\package_release.ps1        # the release zip, its .sha256 and SHA256SUMS.txt in dist\release
```

`build_exe.bat` closes a running copy, installs PyInstaller and psutil (pinned versions), builds a one-folder app
(nothing is unpacked to `%TEMP%` when it starts) and keeps a `LegacyPlayerData` folder you already had in
`dist\LegacyPlayer`. Its full output is saved in `build.log`. To sign the exe, set `LP_SIGN_PFX` and `LP_SIGN_PASS`
first. Releases on GitHub are built by the release workflow: [RELEASE.md](RELEASE.md).

## Reset permissions

- **One permission:** Account > Permissions (or Help > Privacy and permissions), then **Turn off** next to it. Its
  settings switch off and the app undoes what it can (router ports, firewall rules, the friends service it runs, your
  Dolphin pad file, the address in your server code). The page says what stays and how to remove it.
- **Everything, back to the first run:** close Legacy Player completely (tray icon > Exit), make a copy of
  `user_data.json` in the data folder, open it in a text editor and delete the `"consent"` entry (keep the file valid
  JSON), then start Legacy Player. Every permission is then undecided again. Features that are still switched on in
  Settings wait for you to look at them; nothing runs until you allow it. Deleting the whole data folder resets
  everything else as well.

## Uninstall

- **In the app:** Help > Uninstall Legacy Player... The doctor asks whether to keep or delete the save folders he
  made, removes only what Legacy Player created (its data folder, its program files, the Windows Firewall rules and the
  router ports it opened) and leaves nothing running. It does not remove the Start menu shortcut that `install.ps1`
  made: run `.\lp.cmd uninstall` afterwards, or delete "Legacy Player" from the Start menu folder yourself.
- **Installed with `install.ps1` or `lp`:** `.\lp.cmd uninstall` removes the program and its shortcut but keeps
  `LegacyPlayerData`. Use the in-app uninstaller first if you want your data gone too.
- **From source:** delete the checkout's `data` folder (and any folder named in `data-location.txt`).
- A server or friends service started on its own: stop it (`python -m server.cli stop`) and delete its state folder.
