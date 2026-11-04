# ADR-0002: The launcher is part of Legacy Player, and no player's address is ever shown to another

**Date:** 2026-11-01
**Status:** Accepted
**Decided by:** the repository owner. On 2026-11-01 the owner asked for every open decision to be made and closed, and
for addresses to be visible to no one. The choices below were made on that instruction; the owner can reverse any of
them with a new decision record.
**Closes:** `docs/proposals/2026-10-12-launcher-approval-and-canonical-docs.md`,
`docs/proposals/2026-10-10-governance-name.md` (Constellation is the governing ecosystem; Atlas Systems is a different
family), and the open status of proposals 0001 to 0004.

## Context

The 12 October audit found three open governance points (`docs/audits/AUDIT_2026-10-12.md`, section 4, and the
proposal above):

1. The launcher ships, but proposal 0002, on which it rests, was never approved; 0001 (classification), 0003 and 0004
   were also only proposed.
2. `docs/canonical/` held only `ECOSYSTEM_INTEGRATION.md`. `IDENTITY.md`, `SPEC.md` and `CURRENT_STATE.md` were missing.
3. A server code held the host's internet address, so anyone given a code could read it (audit 3.5). Direct matches,
   hole punching, Dolphin's traversal server, the Tailscale private link and a self-hosted friends link also showed
   addresses to other players.

## Decision

### 1. Scope: option A, the launcher is part of `legacy-player`

- **Proposal 0001 is approved.** Legacy Player is a standalone-first service in layer `platform.legacy-runtime`.
- **Proposal 0002 is approved, with this amendment.** Beyond what 0002 listed, Legacy Player owns:
  - friends on the game server (friend codes, requests, presence, invites, end-to-end encrypted messages, reports and
    moderation of that server's friends list), and the stand-alone friends service package (`server/social/`) for
    people who run one on a rented server;
  - self-update from this repository's GitHub releases, which installs nothing unless the release's SHA-256 checks out;
  - PC games (Steam and Epic) in the library, read-only;
  - TV mode;
  - opt-in, scrubbed problem reports and their receiver (`server/report_receiver.py`);
  - the meeting point (section 2).
  Still **not owned**: emulator implementation, distributing games or BIOS files, public matchmaking with accounts,
  internet-scale abuse handling, and any rented server a player is required to use.
- **Proposal 0003 is approved as shipped:** the shell launches and supervises upstream engines as separate programs.
  An in-process libretro frontend is not approved; it needs a proposal of its own.
- **Proposal 0004 is approved as shipped.** Game (ROM) downloads stay out of scope.
- **Proposal 0005 is unchanged:** volunteer relay nodes stay declined. The meeting point is not a volunteer node. It
  is a server run by the maintainers or by a player for themselves, and it stores nothing.

### 2. Addresses: no player's address is ever shown to another player

This is a canonical invariant (`docs/canonical/SPEC.md`, "Addresses"):

- A server code made by Legacy Player for a player's own computer holds **no address of that computer**. The code is
  an LP3- code: it holds a random token, the server's certificate fingerprint and key, and the meeting point's address.
  The player's server listens on that computer only. It keeps a few connections open to the meeting point, made outward,
  and friends are passed through to it (`server/rendezvous.py`). A fresh code changes the token, so every older code
  stops working at once.
- Without a meeting point, sharing reaches the home network only. That code holds a home-network address (RFC 1918 or
  a local IPv6 address), never a public one.
- **Every match goes through the server's relay**, inside its own TLS-PSK tunnel. RetroArch uses TCP. Dolphin NetPlay
  uses UDP datagrams carried inside the tunnel (`adapters/dolphin/udp_relay.py`); each player's emulator connects to
  its own computer. Direct matches, hole punching, Dolphin's traversal server and host codes are removed. Servers
  refuse to pass on a direct address or a host code, so an older app can not publish one.
- These are removed because they show addresses: opening the router (UPnP), putting an IPv6 or Tailscale address in
  a code, the Tailscale private link, and running a friends service on the player's computer (its link held the
  address). An older yes for any of them is withdrawn at start-up and recorded in the consent history as "retired".
  Ports the app opened earlier are closed.
- **What still sees an address**, said plainly in the app and in `PRIVACY.md`: the person who runs a meeting point or
  a server sees the addresses that connect to it, as with any server. The meeting point and the server never log or
  store them. Every web request (downloads, box art and so on) shows that site the player's address.

### 3. Local-first is kept

Nothing about a player's games, rooms, friends or messages is stored on the meeting point. It only copies encrypted
bytes. Play on one computer or on a home network needs no third party. Play with friends elsewhere needs a meeting
point: the one built into a release (`PUBLIC_SERVER_CODE`, once the maintainers run one), or any the player sets under
Settings. Anyone can run one with `python -m server.cli start --share` (`docs/HOSTING_PUBLIC_SERVER.md`).

### 4. Consent is a canonical invariant

Every network contact, download, change to the computer and data share needs the player's recorded, versioned yes
before it runs. The yes is enforced in Python (`LauncherApp._need`), and a no or a withdrawn yes undoes what can be
undone (`docs/canonical/SPEC.md`, "Consent").

## Consequences

- `docs/canonical/IDENTITY.md`, `SPEC.md` and `CURRENT_STATE.md` now exist.
- `docs/canonical/ECOSYSTEM_INTEGRATION.md`, `project.contract.json` and `.constellation/` are managed by Constellation
  and were **not** edited. The "owns" list (`UNCLASSIFIED`) has to be updated in Constellation's
  `registry/services.json` and re-published, following that file's change-governance steps. Until then, the
  ecosystem copy lags this decision. Integration rules 1-8 still hold.
- Internet play needs a meeting point that is running. Until the maintainers run one and set `PUBLIC_SERVER_CODE`,
  each player sets one under Settings (or runs their own).
- An older app that offers a direct match can not publish it through a server of this version, and this version will
  not join one. Relayed matches work between versions, but a host on an older version should update.
