# Private link for Dolphin online play (retired)

**Removed on 2026-11-01** (`docs/decisions/ADR-0002_LAUNCHER_SCOPE_AND_ADDRESS_PRIVACY.md`).

The private link ran Dolphin NetPlay over a Tailscale network. It shared each player's Tailscale (`100.x`) address with
the server and with the other players in the room. Legacy Player no longer shows any player's address to another, so the
private link, Tailscale set-up from inside the app, and putting a Tailscale or IPv6 address in a server code are all gone.

## What replaces it

Dolphin online play now goes through the room's relay, like every other match (`adapters/dolphin/udp_relay.py`):

- Each player's Dolphin connects to `127.0.0.1` on its own computer. The host uses "Direct Connection" with port 2626
  in Dolphin's Host tab; a guest enters the address and port the app shows (`127.0.0.1` and a local port).
- Legacy Player carries Dolphin's UDP datagrams inside the match's TLS-PSK tunnel through the server's relay. It is
  encrypted, needs no router set-up, and nobody sees anybody's address.
- Friends outside your home reach your server through a meeting point (`docs/HOSTING_PUBLIC_SERVER.md`).

## If you used it before

At start-up the app withdraws an earlier yes for "Tailscale private link", "Install and sign in to Tailscale" and
"Put my IPv6 or Tailscale address in my server code", and records that in the permission history as "retired".
Tailscale itself stays installed if you installed it; Legacy Player leaves it alone (Update everything no longer
updates it). Uninstall it from Windows Settings if you no longer want it.
