# Contributing to Legacy Player

Thank you for helping. This page says how to set up, run the app from source, run the tests, and what every change
has to respect. Please also read the [Code of Conduct](CODE_OF_CONDUCT.md).

- Bugs and ideas: open an issue with one of the [issue templates](.github/ISSUE_TEMPLATE/).
- Security problems: do **not** open a public issue; follow [SECURITY.md](SECURITY.md).
- Questions about what leaves a player's computer: [PRIVACY.md](PRIVACY.md).

## Before you start: how this project is governed

Legacy Player is the `legacy-player` service in the Constellation ecosystem. [CLAUDE.md](CLAUDE.md) and
[AGENTS.md](AGENTS.md) (the same rules, for people and for coding agents) list what to read before planning or
changing anything. In short:

- The canonical documents ([docs/canonical/](docs/canonical/ECOSYSTEM_INTEGRATION.md) and `project.contract.json`)
  define the service's role, what it owns, its trust boundaries and its release criteria. Ordinary work does not edit
  them.
- To change any of those, write a proposal under [docs/proposals/](docs/proposals/) (see the existing ones for the
  form) and let the owner decide.
- If the code and a canonical document disagree, say so in your issue or pull request before choosing a behaviour.
  Do not silently redefine the product from the code.
- Today the launcher ships while its proposal is still open: see
  [the launcher approval proposal](docs/proposals/2026-10-12-launcher-approval-and-canonical-docs.md).

The [documentation index](docs/PROJECT_DOCUMENTATION_INDEX.md) says which document governs which question.

## Set up

You need:

- **Python 3.13 or newer** (python.org; on Windows tick "Add to PATH"). The app and server use the standard library
  only. Do not add third-party dependencies.
- **git**.
- **Node.js** (any current version), only for the UI syntax check below.
- **Playwright with Chromium**, only for the UI tests (they are skipped without it):
  `python -m pip install playwright` then `python -m playwright install chromium`.
- Optional: `python -m pip install -r tools/memory_probe/requirements.txt` (psutil, for the Dolphin memory probe and
  its tests).

Legacy Player is a Windows app, but development and the test suite also run on Linux: Windows-only pieces (the tray,
window placement, the firewall, the Recycle Bin) do nothing there instead of failing.

```
git clone https://github.com/Alpallyoop/legacy-player
cd legacy-player
```

## Run the app from source

```
python -m launcher                       # opens the app in your browser; add your games folder inside it
python -m launcher --games "D:\Games"    # or start with a games folder
```

From source the app keeps its files in the checkout's `data` folder (ignored by git). Use `--data-dir <folder>` for a
throw-away copy, `--port <n>` for another local port, and `--no-browser` to start without opening a window. Set the
environment variable `LEGACY_PLAYER_NO_BACKGROUND=1` to stop background work (router renewals, friends check-ins,
starting your friends service) while you test. On Windows, `.\lp.cmd source` does the same as `python -m launcher`.

Everything else (the multiplayer server and the friends service on their own, building the exe, where logs and
settings live, resetting permissions) is in [docs/RUNNING_LOCALLY.md](docs/RUNNING_LOCALLY.md).

## Run the tests

```
python -W ignore -m unittest tests.test_consent -q                       # one module (seconds)
python -W ignore -m unittest discover -s tests -q                         # everything: about 7 to 8 minutes
python tools/release_check.py                                             # what the release workflow runs
```

- The full suite has about 890 tests. The UI tests (`test_ui_smoke`, `test_tv_mode`, `test_world`, `test_contrast`,
  `test_friends_two_apps`) start real copies of the app and drive them with Playwright and Chromium; they are skipped
  when Playwright is not installed, so install it before you change the UI.
- A few tests use fixed local ports (for example 55480). If one fails because the port is busy, run that test alone.
- `tests/test_doc_links.py` runs [tools/check_links.py](tools/check_links.py): every relative link and `#anchor` in
  the Markdown files must point at something that exists. Run `python tools/check_links.py` to see the broken ones.
- A green suite is not proof of a live emulator, a real game, a real router or play between two networks. Say what
  you checked by hand, and on what (see [docs/WINDOWS_CHECKLIST.md](docs/WINDOWS_CHECKLIST.md) and
  [docs/MULTIPLAYER_TEST_PLAN.md](docs/MULTIPLAYER_TEST_PLAN.md)).

Add tests for what you build. Tests that need a permission give it the way a player does, through the permission
dialog's endpoint (`tests/consenthelp.py`), never by flipping a setting.

## How the code is laid out

- `launcher/app.py`: class `LauncherApp`. Every endpoint is a method `api_<name>(self, body: dict) -> dict`,
  dispatched by `launcher/web.py`. Errors meant for the player are raised as `AppError` with a plain sentence.
- `launcher/catalog.py`: every setting, with its type, default, group and help text.
- `launcher/consent.py`: every permission (see the consent rule below).
- `launcher/ui/index.html`: the whole UI (see below).
- `server/`: the lobby, relay and TLS game server (`server/api/json_server.py`, `server/lobby`, `server/relay`); the
  friends service in `server/social/` (stand-alone, and in-process on the game server through
  `server/social/inserver.py`).
- `adapters/`, `runtime/`, `frontend/`, `game_packs/`, `tools/`: emulator adapters, the research runtime, input
  delivery, per-game data and tools. The [README](README.md#repository-layout) has the full layout.

## UI conventions

- **One file.** The UI is `launcher/ui/index.html`: plain JavaScript, no framework and no build step. Use its helpers:
  `h(tag, attrs, ...children)` builds elements, `api(name, body)` calls the backend, `act(fn, okMsg)` runs with an
  error toast, `ask(text, okLabel)` is a confirm dialog, `toast(msg, kind)`, `nav(page)` / `go()` draw pages, `S` is
  the page state.
- **No eval.** The page's Content-Security-Policy forbids `eval`, `new Function` at run time and scripts from
  elsewhere. A syntax error in the page only shows when the app is opened, so after **every** edit to `index.html` run:

  ```
  node tools/check_ui_syntax.js
  ```

  It compiles each `<script>` block without running it and prints `ok <n>`, or `ERR <block> <message>` and exits 1.
- **Plain words.** Players are not technical. Short, friendly sentences that say what happens and why. Never print
  a server's address in a message.
- **Controllers.** Anything reachable from TV mode must work with only a controller: D-pad or stick to move, A to
  press, B to go back. Check it in TV mode (F11) with a controller, or with the keyboard (arrows, Enter, Esc).
- **Contrast.** Text must stay readable in every theme. `python tools/contrast_check.py` measures it in a running
  copy (needs Playwright).
- Keep edits focused. Do not reformat or reorder unrelated parts of `index.html` or `app.py`; prefer a new function or
  module over a sprawling edit.

## The consent rule

Legacy Player does nothing outside the player's computer, and changes nothing on it, without a yes. Every **new**
action that contacts the network, shares data with someone else, or changes something on the computer (files outside
Legacy Player's own folder, router, firewall, other programs' settings, installs) must:

1. have an item in `launcher/consent.py` `ITEMS` (or use the existing one that truly covers it) with plain words for
   `what`, `sends`, `changes`, `undo` and `stays`. If you change what an existing item does, raise its `version` so
   players are asked again;
2. call `self._need("<item id>")` before acting (or `self._allowed(...)` for quiet background work, which then does
   nothing), in Python, not only in the page. A setting being on is not a yes;
3. undo what it can in `LauncherApp._consent_undo` when the item is turned off;
4. come with a test that the action is **refused, and does nothing**, without the permission (see
   `tests/test_consent.py` for the pattern);
5. be described in [PRIVACY.md](PRIVACY.md).

Things the player does themselves with a click (opening a link in their browser, joining a server with a code they
were given, hosting a room, starting their own server) need no permission.

## Documentation

- Change the docs in the same pull request as the behaviour. Players read [docs/USER_GUIDE.md](docs/USER_GUIDE.md);
  check every claim against the code and the words in the UI.
- Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
- Put a version number in `README.md` only if it equals `launcher/version.py` (a test checks this).
- New documents go into [the documentation index](docs/PROJECT_DOCUMENTATION_INDEX.md).
- Dated audits are added, never rewritten.

## Branches, commits and releases

- Work on a branch of your own and open a pull request against the default branch. Fill in the
  [pull request template](.github/PULL_REQUEST_TEMPLATE.md).
- Commit messages: a short first line that says what changed for the player or the code ("TV mode: one press is one
  press"), then the details. One topic per commit where you can.
- Do not change the version number; the maintainer does that when releasing.
- **Only the maintainer pushes to `main` and tags releases.** A release is a tag `vX.Y.Z` on a commit that is on
  `main` and equals `VERSION` in `launcher/version.py`. The release workflow refuses anything else, runs every test
  before it builds, smoke-tests the built exe and only then publishes. Installed copies update themselves to the newest
  release, so only tested work is tagged. The full steps are in [docs/RELEASE.md](docs/RELEASE.md).
- `.github/workflows/release.yml` and `tools/release.workflow.yml` must stay identical (a test checks this). Changes to
  the release workflow go through the maintainer.
- Before a push, the maintainer checks what goes in and what stays out
  ([docs/GITHUB_PUSH_CHECKLIST_v1.md](docs/GITHUB_PUSH_CHECKLIST_v1.md)): no probe exports, data folders, keys,
  friends-service data or scratch files (`tests/test_no_secrets_in_repo.py` and `.gitignore` help).

## License

By contributing you agree that your contribution is licensed under the project's [MIT License](LICENSE). Do not add
game data, ROMs, ISOs, BIOS files or anything else copyrighted (see
[docs/LEGAL_POSITION.md](docs/LEGAL_POSITION.md)).
