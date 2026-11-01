"""Guided launch for Dolphin's built-in NetPlay (GameCube and Wii).

Dolphin has no command-line option to start or join NetPlay, so this adapter does
not pretend to drive it. It opens Dolphin with the game ready (a visible window,
not batch mode), then gives the player exact, ordered steps with the room's
address or host code already filled in. Everyone must use the same Dolphin
version, the same game file (region and revision) and the same settings.
"""
from __future__ import annotations

DEFAULT_PORT = 2626
SUPPORTED_CONSOLES = {"gamecube", "wii"}


class DolphinNetplayError(RuntimeError):
    pass


def build_open_command(exe: str, rom: str = "") -> list[str]:
    """Open Dolphin's normal window WITHOUT starting the game. Dolphin refuses to start or join NetPlay ("can't start a NetPlay
    session while a game is running"); NetPlay itself starts the game once everyone is in. `rom` is kept for callers, unused."""
    return [exe]


def steps(role: str, *, mode: str = "relay", address: str | None = None, port: int | None = None, code: str | None = None,
          game_folder: str | None = None, private: bool = False) -> list[str]:
    """The player's steps. Only the relay exists: every Dolphin connects to this computer (127.0.0.1) and Legacy Player
    carries the match through the server's relay, so no player sees another's address (adapters/dolphin/udp_relay.py).
    Dolphin's traversal server and direct connections between players are not offered: both show addresses."""
    if mode != "relay":
        raise DolphinNetplayError("Dolphin online play goes through the relay only; direct and traversal connections "
                                  "show addresses to the other players")
    # NetPlay lists games from Dolphin's own game folders, so a game outside them is "not found" for everyone.
    ready = [f"Legacy Player added the game's folder to Dolphin. If the game is still missing from Dolphin's list: Config > Paths > Add… and choose {game_folder}." if game_folder
             else "Legacy Player added the game's folder to Dolphin. If the game is still missing from Dolphin's list: Config > Paths > Add… and choose its folder.",
             "Do not start the game yourself: NetPlay starts it for everyone."]
    if role == "host":
        return ready + [
            "In Dolphin, choose Tools > Start NetPlay… and open the Host tab.",
            "Pick this game in the list.",
            f"Set Connection to 'Direct Connection' and the port to {port or DEFAULT_PORT}. Nothing needs opening on your "
            "router: friends come in through Legacy Player's relay, which never shows your address.",
            "Click Host. Your friends are notified.",
            "When everyone appears in Dolphin's NetPlay window, start the game from there.",
        ]
    if role == "guest":
        if not port:
            raise DolphinNetplayError("the host has not launched yet")
        return ready + [
            "In Dolphin, choose Tools > Start NetPlay… and open the Connect tab.",
            "Set Connection to 'Direct Connection'.",
            f"Enter the address {address or '127.0.0.1'} and port {port}. That is this computer: Legacy Player carries the "
            "connection to the host through the relay, so neither of you sees the other's address.",
            "Click Connect, then wait for the host to start the game.",
        ]
    raise DolphinNetplayError("role must be host or guest")
