# Proposal: make IDENTITY.md principle 2 match SPEC.md about home-network codes

**Status:** proposed (needs the owner's decision and a decision record; canonical files are not changed here).
**Found by:** the security stress test of 2026-11-06 (`docs/audits/AUDIT_2026-11-06.md`, "Still open", 5).

## The mismatch

- `docs/canonical/IDENTITY.md`, principle 2: "No player's address is ever shown to another player. Server codes for a
  player's computer hold no address, and every match goes through the relay."
- `docs/canonical/SPEC.md`, "Addresses", 1: a server code for a player's own computer is either an `LP3-` code (no
  address of the computer) or an `LP-`/`LP2-` code **with a home-network address** (RFC 1918 or `fd00::/8`) when no
  meeting point is set. Never a public, shared (CGNAT), loopback or documentation address.

The code follows SPEC.md. When a player shares their server without a meeting point, their friend's app receives the
sharer's home-network address, and shows it in its settings.

## Options

1. **Change the wording of IDENTITY.md** to "hold no internet address (a code made without a meeting point holds only a
   home-network address, usable on that home network)". Matches what is built and tested.
2. **Change the code** so a home-network code is never made unless the player is told that it shows their home-network
   address to whoever gets the code, and hide `server_host` in the friend's settings when it came from a code.
3. **Both.**

Recommendation: option 3. The address is not reachable from outside the home, so the risk is small, but the principle
says "never", and a plain notice costs one dialog.
