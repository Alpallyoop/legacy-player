"""What Legacy Player sends over the network and changes on this computer, in plain words.

Legacy Player collects nothing: there is no analytics, no tracking, no account and nothing is sold. Everything that
reaches outside this computer, or changes something on it, is a permission of its own (launcher/consent.py): it says
where it goes, what it carries and what it changes, it is off until the player allows it in the permission dialog, and
the app checks the player's yes before each action (LauncherApp._need). This module keeps the short "never sent" text
and an older view of the same list for callers that still use it."""
from __future__ import annotations

from . import consent

NEVER = ("Legacy Player does not collect data: no analytics, no tracking, no account, nothing sold. Never sent by any of "
         "these: your Windows user name or computer name, your files or folder names, a list of your games, or anything "
         "for advertising. Be aware of three things that do carry an address: every web request (downloads, box art, game "
         "details, reports, the friends service) shows that site your internet address, as any web request does; a "
         "server code contains your server's address (anyone you give it to can read it, even though the app hides it "
         "on screen); and a direct connection shows your address to the other players in that match.")


def items(settings: dict, data: dict) -> list[dict]:
    """Every permission, in the shape older pages used: id, title, what, sends, the settings it controls, whether it is
    on (switched on in the settings) and whether the player said yes to it for what it does now."""
    out = []
    for it in consent.view(data, settings):
        out.append({**it, "setting": (it["settings"] or [""])[0], "contacts": [it["sends"]], "off_means": it["undo"],
                    "confirmed": it["allowed"], "needs_look": it["needs_review"]})
    return out


OFF_VALUES = {k: v for it in consent.ITEMS for k, v in consent.off_values(it).items()}
