# Working on this repository remotely

For an agent working on any repository of the Constellation ecosystem from a cloud or phone session, while the
owner's home computer may be switched off. Constellation publishes this file into every registered repository as
`.constellation/REMOTE_WORK.md` (read-only copy; the source is `ecosystem/REMOTE_WORK.md` in Constellation).

If the owner asked you to "set this repository up for remote work", do **Part 2** once, then **Part 3** from then on.

## Part 1 - Where things are

- **Home:** every project lives on the owner's computers, in its family folder of the dev root
  (`<_Family-folder>/<project>`). There are two full copies of the dev root in the same layout: the owner's
  Windows PC and the owner's Mac. On either machine, the `AGENTS.md` / `CLAUDE.md` at the dev root names where
  that machine's dev root is, and the `CONSTELLATION_DEV_ROOT` environment variable points at it when the
  Constellation buttons run. Both may be off. GitHub is the meeting point of the two machines and of every
  cloud or phone session; work only from the GitHub repository.
- **Machines:** the Windows PC uses the `.cmd` buttons in Constellation's folder; the Mac uses the app buttons
  in its dev root (from Constellation's `mac/`). Both run the same `scripts/cn.ps1` commands. Sync Everything on
  either machine first brings back work pushed from elsewhere (fast-forward only), then backs everything up.
- **This repository on GitHub:** `git remote get-url origin`. The account is the owner in Constellation's
  `registry/owner.json` (currently `Alpallyoop`); a remote naming `ScrappyHub` is the same account under its former
  name and still works.
- **Where the latest work is:** run `git fetch origin` and `git branch -a`.
  - Normally the latest work is on the branch the owner works on (often `main`).
  - A branch named `backup/s-drive-<date>` (or `backup/s-drive-<date>--<branch>`) holds the home computer's work
    for a project whose GitHub history differed from the home copy. **That branch, not `main`, is the latest
    work.** Start from it. Never merge it into `main`, force-push or delete either line without the owner saying
    which one becomes `main`.
  - Constellation's `registry/remotes.json` records, for every project, the GitHub repository and the branch that
    holds the home computer's work.
- **Ecosystem rules:** this folder also has `SERVICE_MAP.md`, `registry.json`, `AGENT_POLICY.md` and
  `SHARED_INVARIANTS.md`. Read them and this repository's `AGENTS.md` / `CLAUDE.md` before changing anything;
  the stricter rule wins.

## Part 2 - Set the repository up for remote work (once)

Work on a branch, commit each step, push, and report what you did and what is left.

1. **Everything is on GitHub.** If there are local changes in the session that are not pushed, push them. If
   the latest work is on a `backup/s-drive-*` branch, tell the owner and work from that branch.
2. **No secrets in the repository.** `.gitignore` must cover dependencies and build output (`node_modules/`,
   `.venv/`, `target/`, `dist/` where it is output, ...) and secrets (`.env`, `.env.*`, `*.key`, `*.pem`,
   `*.pfx`, ...). Search the tracked files for keys, tokens and passwords. If any secret is tracked, **stop and
   tell the owner**: it has to be rotated, and removing it from history is the owner's decision.
3. **It builds and tests in a Linux cloud session.** Find the real build and test commands (README, package
   files, scripts, CI) and run them here. Fix what is needed for them to run on Linux without changing what the
   project does: paths relative to the script or repository (never a drive letter or a home folder), PowerShell
   scripts that run on PowerShell 7 as well as Windows PowerShell 5.1, no tools assumed to be at fixed
   Windows locations.
4. **Write it down.** Add or update a `## Working remotely` section in `README.md` with: prerequisites, the exact
   install / build / test commands that worked in this session, what each proves, and what only works on
   Windows or the home computer (Unity, Windows installers or signing, hardware, local services, data that
   lives only at home). Keep it short and true; only commands you actually ran.
5. **Windows-only steps.** If something must run on Windows, propose a GitHub Actions workflow on
   `windows-latest` that builds and tests it, and ask the owner before adding it (private repositories use
   paid Actions minutes).
6. **Leave Constellation's files alone.** Never edit the managed block in `AGENTS.md` / `CLAUDE.md` (between
   `ATLAS_SERVICE_MAP_BEGIN` and `ATLAS_SERVICE_MAP_END`), anything in `.constellation/`,
   `project.contract.json`, or `docs/canonical/ECOSYSTEM_INTEGRATION.md`. Canonical documents of this
   repository change only through `docs/proposals`.
7. **Report** to the owner: the branch, what now works remotely (with the commands), what still needs the home
   computer, and anything that needs a decision.

## Part 3 - Everyday remote work

- Start from the branch that holds the latest work (Part 1). Commit small, push often; the home computer pulls it
  back with `PULL_REPOS.cmd` (fast-forward only), so keep history linear: no force-push, no history rewriting.
- Run the repository's own build and tests before every push; say plainly what you could not run here.
- Changing several repositories, or Constellation's registry, service map or managed blocks, is ecosystem-wide
  work: do it from the `constellation` repository (see its `docs/WORKING_REMOTELY.md`), not by hand here.
- Never commit secrets or files over 95 MB. Never store credentials in the repository or in a workflow file.
