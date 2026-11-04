# Legacy Player: identity

**Status:** Canonical. Approved 2026-11-01 (`docs/decisions/ADR-0002_LAUNCHER_SCOPE_AND_ADDRESS_PRIVACY.md`).
**Changes:** only through a proposal under `docs/proposals` and a decision record. The ecosystem copy of the service's
role and ownership (`docs/canonical/ECOSYSTEM_INTEGRATION.md`, Constellation's registry) is managed by Constellation.

## What Legacy Player is

Legacy Player is a local-first player for the games people already own. It is a library, a launcher, controllers,
saves, private online play with friends, and TV mode, all in one app on the player's own computer. Emulators do the
emulating: Legacy Player finds or installs the official upstream programs, starts them and keeps them in step. Beneath
the player sits a research runtime: memory authority, normalized game state, semantic events, replay verification and
lockstep sync. It reads supported games through versioned game packs and talks to emulators through adapters. Mario
Party 4 on Dolphin is the first of these.

Canonical role (as registered with Constellation): *local-first compatibility, instrumentation, state-understanding,
replay-verification, and multiplayer-orchestration runtime for legacy games; integrates emulators through adapters and
games through versioned game packs.* The launcher is how that runtime reaches players, and it is part of this service.

## Who it is for

Players on their own Windows PCs, the owner and friends first. Small private groups play together. Anyone who wants to
can run a server or a meeting point on Windows, Linux or a Raspberry Pi.

## What it owns

- **Library:** a read-only scan of the player's own folders (18 consoles, plus Steam and Epic PC games), covers,
  collections, favorites, filters, and game details on request. Game files are never copied, changed or sent.
- **Emulator integration:** finding emulators, and installing or updating them from official releases only after a
  yes. Starting, supervising and configuring them through adapters, and an in-game overlay.
- **Controllers and saves:** layouts per console for up to four players, save folders, backups and restores.
- **Private-group play:** the lobby server (rooms, invite codes, approval, waiting lines), the relay that carries every
  match encrypted, server codes, and the meeting point that lets friends reach a player's own server without anyone
  learning an address.
- **Friends:** friends on the game server, with codes, requests, presence, invites, end-to-end encrypted messages,
  reports and moderation. Also the stand-alone friends service package, for people who run one on a rented server.
- **TV mode:** a full-screen home that a controller can drive.
- **Self-update and uninstall:** updating from this repository's releases, checked against their SHA-256, and an
  uninstall that removes only what the app created.
- **Consent:** a permission, with what it sends and to whom, for every network contact, download, system change and
  data share. Each yes is recorded with its version, enforced before the action runs, and can be withdrawn with undo.
- **Opt-in problem reports**, scrubbed of names, addresses, paths and codes, and their receiver.
- **The research runtime:** adapter contracts, game packs, memory authority, state, events, replay packages and
  lockstep sync (`docs/PROJECT_SPEC.md`).

## What it does not own (non-goals)

- Emulator implementation. The engines stay the upstream projects, under their own licenses.
- Distributing games, BIOS or firmware, or downloading them. Each player brings their own.
- Public matchmaking with accounts, or internet-scale abuse handling. Groups are private, with names like `Name#tag`
  and no accounts.
- A server that every player is required to rent or use. Hosting stays optional and replaceable.
- An in-process libretro frontend. It needs a proposal of its own (proposal 0003).
- Volunteer relay nodes (proposal 0005: declined).

## Core principles

1. **Local-first.** Everything a player has stays on their computer. Play on one computer or on a home network needs
   no third party. A meeting point or server only carries encrypted bytes and keeps nothing about players.
2. **No player's address is ever shown to another player.** Server codes for a player's computer hold no address, and
   every match goes through the relay. See `SPEC.md`, "Addresses".
3. **The player's yes comes first.** Nothing goes online, changes the computer or shares data before the matching
   permission is allowed. See `SPEC.md`, "Consent".
4. **No game content is shipped.**
5. **Fail closed.** A bad checksum, an unreadable code, a wrong certificate or a missing yes stops the action with a
   plain reason. Nothing falls back silently to a weaker path.
6. **Standalone-first.** The repository builds, tests and releases on its own. Ecosystem integrations add to it and
   never replace standalone correctness (`ECOSYSTEM_INTEGRATION.md`).

## Relationship to Constellation

`legacy-player` is a service in the `chronicle` family of the Constellation ecosystem, layer `platform.legacy-runtime`,
with no required upstream service. Its registered role and ownership lists are kept by Constellation. Updating them
to match this file is open work there (`CURRENT_STATE.md`).
