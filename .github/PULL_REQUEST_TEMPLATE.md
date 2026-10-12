## Summary

What changes, in a few plain sentences.

## Why

The issue, audit finding or need this answers.

## Scope

Select the main area touched by this pull request:

- [ ] launcher (backend, `launcher/`)
- [ ] UI (`launcher/ui/index.html`)
- [ ] TV mode
- [ ] online play (server, rooms, server codes, relay)
- [ ] friends and messages
- [ ] permissions and privacy
- [ ] runtime / adapter / game pack (research track)
- [ ] tools, build or release
- [ ] docs

## Checklist

- [ ] Tests added or updated, and `python -W ignore -m unittest discover -s tests -q` passes (UI tests need
      Playwright and Chromium; say so if they were skipped).
- [ ] If `launcher/ui/index.html` changed: `node tools/check_ui_syntax.js` prints `ok`.
- [ ] **Permissions:** anything new that contacts the network, shares data or changes the computer has an item in
      `launcher/consent.py`, goes through `_need` (or `_allowed`) in Python, is undone when turned off, has a test that
      it is refused without the permission, and is described in `PRIVACY.md`. Changed an item's behaviour? Its
      `version` is raised. (Not applicable: [ ])
- [ ] **TV mode:** if players can reach this from TV mode, it was tested there with a controller (D-pad, A, B) and
      nothing needs a mouse or keyboard. (Not applicable: [ ])
- [ ] Words players see are plain, short and friendly, and never show a server address.
- [ ] Docs updated (user guide, README, PRIVACY, or the right spec) and `python tools/check_links.py` passes.
- [ ] A line added under **Unreleased** in `CHANGELOG.md`.
- [ ] No version bump (the maintainer does that), no new third-party dependency, no game files, keys or data folders.
- [ ] No canonical file (`docs/canonical/`, `project.contract.json`) changed; a needed change is a proposal under
      `docs/proposals/`.

## How it was checked

Automated tests, and anything checked by hand (on Windows? with a real emulator, router or second network?).

## Notes

Follow-ups, risks, or anything the reviewer should look at first.
