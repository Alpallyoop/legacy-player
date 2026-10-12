"""Permissions: everything Legacy Player does that reaches outside this computer or changes something on it, each with
its own yes or no.

Every item says, in plain words, what happens, what is sent and to whom, what changes on this computer, which settings
it controls, and whether (and how) it can be undone. Each item has a VERSION: when what an item does changes, its
version goes up and an earlier yes no longer counts ("needs a new look").

The record lives in the settings file (catalog data["consent"]):

    {"decisions": {item id: {"decision": "granted" | "declined", "version": n, "at": epoch, "scope": text}},
     "history":   [{"item", "decision", "version", "at", "how", "scope"}, ...]}      append-only

A yes counts only when it was given for the item's current version (and, for the friends service and problem reports,
for the same address it was given for). Turning a setting on in Settings is NOT a yes: the yes comes only from the
permission dialog (LauncherApp.api_consent), after the player was shown the item's text.

The app checks this record before acting (LauncherApp._need / _allowed); see tests/test_consent.py."""
from __future__ import annotations

import time

POLICY_VERSION = "2026-10-12"        # the date the texts below were last changed as a whole

# Every item. `settings`: setting -> the value that means "on" (turned on when the player allows the item, if
# `switch_on` is true, and turned off when they turn the item off). `requires_setting`: the gated action also needs that
# setting on. `undo`: what turning it off undoes; `stays`: what can not be undone by the app and how to remove it.
ITEMS: list[dict] = [
    {"id": "downloads", "version": 2, "group": "Downloads and updates", "title": "Internet downloads and updates",
     "what": "Lets Legacy Player download emulators, RetroArch and its cores, and new versions of Legacy Player, and check "
             "whether newer versions exist. Each download or check still waits for you to press its button.",
     "sends": "Which file or release it wants, to GitHub (api.github.com, github.com and GitHub's file hosts), "
              "buildbot.libretro.com (RetroArch and its cores) and the emulator makers' own download sites. Like any web "
              "request, those sites see your internet address. Nothing about you or your games is sent.",
     "changes": "Downloaded emulators go into Legacy Player's own folder. An update replaces Legacy Player's program files "
                "after you press Restart.",
     "settings": {"allow_internet": True},
     "undo": "Nothing is downloaded or checked any more.",
     "stays": "Emulators already downloaded stay. Remove them from the Engines page, or with Uninstall Legacy Player."},
    {"id": "covers", "version": 1, "group": "Downloads and updates", "title": "Box art",
     "what": "When you press Get box art (for all games, or one game), Legacy Player fetches a cover picture for each game.",
     "sends": "Each game's name and console to thumbnails.libretro.com. For a Steam game, its store number to Steam's picture "
              "servers (shared.akamai.steamstatic.com, cdn.cloudflare.steamstatic.com, steamcdn-a.akamaihd.net); for an Epic "
              "game, the picture address the Epic launcher already listed (cdn1.epicgames.com, cdn2.epicgames.com, "
              "cdn1.unrealengine.com, cdn2.unrealengine.com) or its name to the Steam store search (store.steampowered.com). "
              "Those sites see your internet address. Steam and Epic pictures already on this computer are used first.",
     "changes": "Pictures are saved in Legacy Player's covers folder.",
     "settings": {},
     "undo": "No more pictures are fetched.",
     "stays": "Pictures already fetched stay. Pick another picture on a game's page, or delete the covers folder in "
              "Legacy Player's data folder."},
    {"id": "game_info", "version": 2, "group": "Downloads and updates", "title": "Look up game details (Wikipedia)",
     "what": "On a game's card, 'Look it up online' fills in the description, release date, makers and player count.",
     "sends": "That game's name and console to en.wikipedia.org and www.wikidata.org, only when you press the button "
              "(or Look up all games). Those sites see your internet address.",
     "changes": "The answers are kept in Legacy Player's data folder.",
     "settings": {"allow_game_info": True},
     "undo": "Nothing is looked up any more.",
     "stays": "Details already looked up stay on the cards. Press Forget on a card to remove them."},
    {"id": "network_test", "version": 2, "group": "Playing online", "title": "Network test",
     "what": "Checks whether this computer is better at hosting or joining, when you press Test my network (or, with "
             "'Test my network when Legacy Player opens' on, by itself at start-up).",
     "sends": "Small timing messages to the multiplayer server you use (your own on this computer, or a friend's you "
              "connected to with their server code). Nothing about you.",
     "changes": "The result is kept in Legacy Player's settings file.",
     "settings": {"auto_network_test": True}, "switch_on": False, "requires_setting": False,
     "undo": "The test does not run, by itself or by button.", "stays": ""},
    {"id": "router", "version": 1, "group": "Your server", "title": "Open my router for friends (UPnP)",
     "what": "When you start your server with 'Let friends connect' (or run a friends service), Legacy Player asks your "
             "home router to forward that port to this computer, keeps it open while it runs and closes it when it stops. "
             "'Test my router' opens a port for a moment and closes it again. At start-up, a port left open by a run that "
             "crashed is closed (or kept, if your server is still running).",
     "sends": "Requests to your own router only (UPnP, on your home network). There is no Windows prompt for this. The "
              "router tells Legacy Player your public internet address, which then goes into your server code.",
     "changes": "Your router forwards one port (the server's, and the friends service's if you run one) to this computer "
                "while they run. Anyone on the internet can then reach that port; the server only lets in people with "
                "your server code.",
     "settings": {"server_auto_open": True},
     "undo": "Every port Legacy Player opened on your router is closed now, and none is opened again.",
     "stays": "If your router was switched off when you turned this off, its forward expires by itself within an hour."},
    {"id": "firewall", "version": 1, "group": "Your server", "title": "Windows Firewall rule",
     "what": "Adds a Windows Firewall rule so friends on other networks can reach your server (and your friends service, "
             "if you run one). Windows shows its own approval box each time.",
     "sends": "Nothing.",
     "changes": "One inbound rule named 'Legacy Player server' (and 'Legacy Player friends service') for that port.",
     "settings": {},
     "undo": "The rules are removed. Windows asks you to approve that.",
     "stays": "If you say no to Windows' box, remove them yourself: Windows Defender Firewall > Advanced settings > "
              "Inbound Rules, the ones starting with 'Legacy Player'."},
    {"id": "fallback", "version": 1, "group": "Your server", "title": "Shared server when mine can't be reached",
     "what": "If your router can't be opened, Legacy Player moves you and your friends to a shared server instead "
             "(only one set under Settings > Your server, or built into this copy).",
     "sends": "Your rooms, the name you show other players, and encrypted game traffic go through that server. Whoever "
              "runs it sees your internet address, as with any server.",
     "changes": "Nothing on this computer.",
     "settings": {"server_use_fallback": True},
     "undo": "You leave the shared server and go back to your own.", "stays": ""},
    {"id": "name_tag", "version": 1, "group": "Playing online", "title": "Ask servers for my name tag",
     "what": "When you host, join or press 'Ask my server for my tag', Legacy Player asks that server for a #tag nobody "
             "active there shares with your name.",
     "sends": "Your display name, the tag you had, and a random number made for that one server (so it can give you the "
              "same tag next time). The number is different for every server, so servers can't link you.",
     "changes": "The tag is kept in Legacy Player's settings file.",
     "settings": {},
     "undo": "Legacy Player forgets its tag and random numbers and uses a tag made on this computer.",
     "stays": "A server forgets your tag by itself once you have not used it for a while."},
    {"id": "friends", "version": 1, "group": "Friends", "title": "Friends service",
     "what": "Friend codes, friend requests, who is online, messages and group chats, through the friends service whose "
             "link you pasted (or the one you run).",
     "sends": "To that service: the name you show, your public encryption key, your friend code and friends list, "
              "requests, and your messages sealed end to end (the service can't read them). Every 12 to 30 seconds while "
              "Legacy Player is open it asks for news, so the service sees that you are online and your internet address. "
              "Reporting a message shares that message and the few before it with the service's moderators.",
     "changes": "Your friends key is kept in Legacy Player's data folder.",
     "settings": {}, "scope": "friends_server",
     "undo": "Legacy Player stops contacting the service and forgets its link (it remembers it in case you allow this again).",
     "stays": "The service keeps your name, friend code, key, friends and sealed messages until you have not used it for 60 "
              "days. To remove them now, press 'Leave this friends service' on the Friends page before turning this off."},
    {"id": "friends_presence", "version": 1, "group": "Friends", "title": "Show friends what I'm playing",
     "what": "Your friends see 'playing <game>' or 'in a room' next to your name.",
     "sends": "The name of the game you are playing, or that you are in a room, to the friends service, which shows it to "
              "your friends.",
     "changes": "Nothing on this computer.",
     "settings": {},
     "undo": "Friends see only that you are online.", "stays": ""},
    {"id": "friends_share_room", "version": 1, "group": "Friends", "title": "Share my room with friends",
     "what": "While you host a room, friends see it and can join with one click, and you can send them invites.",
     "sends": "Your room's game, invite code and your server code to the friends service, for your friends. A server code "
              "contains your server's internet address, so friends who get it (and the service, which stores invites) "
              "can read that address.",
     "changes": "Nothing on this computer.",
     "settings": {"friends_share_room": True},
     "undo": "Your room is no longer shown to friends.",
     "stays": "Invites already sent stay in your friends' lists until they dismiss them or they expire."},
    {"id": "friends_host", "version": 1, "group": "Friends", "title": "Run a friends service on this computer",
     "what": "Starts a friends service on this computer for the people you give your friends link to. You are its moderator.",
     "sends": "Nothing to anywhere else. It answers the people who have your friends link. That link contains this "
              "computer's internet address, so they know it.",
     "changes": "A background program runs while Legacy Player runs and keeps names, friend codes, friend lists, invites, "
                "sealed messages (7 days), reports and moderator accounts in Legacy Player's data folder.",
     "settings": {},
     "undo": "The friends service stops; nobody can connect to it.",
     "stays": "Its data stays in the data folder (social folder) until you start it again or uninstall Legacy Player."},
    {"id": "direct", "version": 2, "group": "Playing online", "title": "Direct connections in matches",
     "what": "Lets matches connect computer to computer (faster; Dolphin needs it). Each match still asks you first.",
     "sends": "Your internet address, to the other players in that match. Game traffic goes straight between you.",
     "changes": "Nothing on this computer.",
     "settings": {"allow_direct_connections": True},
     "undo": "Matches always go through the server's relay, so nobody learns your address. Dolphin online play can't start.",
     "stays": "Players you already played with directly may have seen your address."},
    {"id": "private_link", "version": 2, "group": "Playing online", "title": "Tailscale private link for Dolphin",
     "what": "Plays Dolphin matches over Tailscale when every player has it.",
     "sends": "Your Tailscale address (a 100.x address, not your home address) to the server and the players in your room.",
     "changes": "Nothing on this computer.",
     "settings": {"use_private_link": True},
     "undo": "Your Tailscale address is no longer shared; Dolphin uses its normal connection.", "stays": ""},
    {"id": "code_address", "version": 1, "group": "Your server", "title": "Put my IPv6 or Tailscale address in my server code",
     "what": "Makes your server code carry this computer's IPv6 address or Tailscale address, so friends can reach you "
             "without opening the router.",
     "sends": "Nothing by itself. Every server code contains an address of this computer (normally your public address "
              "or home-network address); with this, it is your IPv6 or Tailscale address instead. Anyone you give the code "
              "to can read it.",
     "changes": "Changes 'Address friends use to reach your server' in Settings.",
     "settings": {},
     "undo": "Your server code goes back to your normal address.",
     "stays": "Codes you already sent still contain that address. Press 'Make a fresh code' so old codes stop working."},
    {"id": "tailscale", "version": 1, "group": "Playing online", "title": "Install and sign in to Tailscale",
     "what": "Installs Tailscale (a separate free program) with Windows' package manager, opens its sign-in, and lets "
             "Update everything update it.",
     "sends": "winget downloads Tailscale from Microsoft's package list and Tailscale's servers. Signing in happens in "
              "Tailscale's own window, with Tailscale.",
     "changes": "Installs the Tailscale program and its background service on this computer.",
     "settings": {},
     "undo": "Legacy Player no longer installs, updates or opens Tailscale.",
     "stays": "Tailscale stays installed and signed in. Remove it in Windows Settings > Apps > Installed apps > Tailscale."},
    {"id": "dolphin_config", "version": 1, "group": "This computer", "title": "Change Dolphin's settings files",
     "what": "Adds the folders your GameCube and Wii games are in to Dolphin's game list (when you press Fix, or start a "
             "Dolphin match), and, with 'Set up Dolphin's GameCube controller for me' on, writes your controllers into "
             "Dolphin's GameCube pad file before Dolphin starts.",
     "sends": "Nothing.",
     "changes": "Dolphin's Dolphin.ini (game folders) and GCPadNew.ini (pads). Your own pad file is saved once as "
                "GCPadNew.ini.legacy-player-backup.",
     "settings": {"dolphin_manage_pads": True}, "switch_on": False, "requires_setting": False,
     "undo": "Your own Dolphin pad file is put back.",
     "stays": "Game folders added to Dolphin's list stay. Remove them in Dolphin: Config > Paths."},
    {"id": "reports", "version": 2, "group": "Help", "title": "Send problem reports automatically",
     "what": "When something breaks, a cleaned-up report is sent to the people who make Legacy Player without asking you "
             "each time.",
     "sends": "The error, the app and Windows version, and the names of your last few actions, to the report address set "
              "in Settings (or built into this copy). Names, addresses, paths and codes are removed first. The receiver "
              "sees your internet address while it receives the report but keeps no record of it.",
     "changes": "Reports wait in Legacy Player's logs folder until sent.",
     "settings": {"error_reports": "auto"}, "off": {"error_reports": "ask"}, "scope": "report_url",
     "undo": "Reports wait for you to read and approve each one.",
     "stays": "Reports already sent can't be called back. Waiting ones can be deleted in Settings > Problem reports."},
]

BY_ID = {it["id"]: it for it in ITEMS}

# The privacy_ok record of 0.7.46 and older: item id there -> item id here.
OLD_IDS = {"downloads": "downloads", "game_info": "game_info", "friends": "friends", "friends_host": "friends_host",
           "reports": "reports", "direct": "direct", "private_link": "private_link", "network_test": "network_test"}


class UnknownItem(KeyError):
    pass


def item(item_id: str) -> dict:
    try:
        return BY_ID[item_id]
    except KeyError as exc:
        raise UnknownItem(item_id) from exc


def off_values(it: dict) -> dict:
    """The value of each setting the item controls when it is off."""
    out = {k: (False if isinstance(v, bool) else "") for k, v in it["settings"].items()}
    out.update(it.get("off") or {})
    return out


def scope_of(it: dict, settings: dict) -> str:
    """What a yes is tied to besides the version: the friends service's or the report receiver's address."""
    key = it.get("scope")
    return str(settings.get(key) or "").strip() if key else ""


def record(data: dict) -> dict:
    """The consent record inside the settings data, made (and the old privacy_ok record moved over) on first use."""
    rec = data.get("consent")
    if not isinstance(rec, dict):
        rec = data["consent"] = {}
    rec.setdefault("decisions", {})
    rec.setdefault("history", [])
    if "privacy_ok" in data:
        migrate(data, rec)
    return rec


def migrate(data: dict, rec: dict) -> None:
    """privacy_ok (0.7.46 and older) said 'the player kept this on', with no time and no version. It becomes a yes at
    version 0, which is never current: the player is asked to look again, because the texts changed."""
    old = data.pop("privacy_ok", None) or {}
    if not isinstance(old, dict):
        return
    for old_id, signature in old.items():
        new_id = OLD_IDS.get(old_id)
        if not new_id or new_id in rec["decisions"]:
            continue
        scope = str(signature or "")
        if new_id == "reports":
            scope = scope.split("|", 1)[1] if "|" in scope else ""
        elif new_id != "friends":
            scope = ""
        rec["decisions"][new_id] = {"decision": "granted", "version": 0, "at": None, "scope": scope, "migrated": True}
        rec["history"].append({"item": new_id, "decision": "granted", "version": 0, "at": None, "how": "migrated", "scope": scope})


def state(data: dict, item_id: str, settings: dict) -> str:
    """allowed | declined | changed (a yes for an older version or another address) | undecided"""
    it = item(item_id)
    d = record(data)["decisions"].get(item_id)
    if not d:
        return "undecided"
    if d.get("decision") != "granted":
        return "declined"
    if d.get("version") != it["version"]:
        return "changed"
    if it.get("scope") and str(d.get("scope") or "") != scope_of(it, settings):
        return "changed"
    return "allowed"


def valid(data: dict, item_id: str, settings: dict) -> bool:
    return state(data, item_id, settings) == "allowed"


def decide(data: dict, item_id: str, granted: bool, settings: dict, how: str = "dialog", now: float | None = None) -> dict:
    """Write down a yes or a no for the item's current version. The history only ever grows."""
    it = item(item_id)
    rec = record(data)
    at = round(time.time() if now is None else now, 3)
    entry = {"decision": "granted" if granted else "declined", "version": it["version"], "at": at, "scope": scope_of(it, settings)}
    rec["decisions"][item_id] = entry
    rec["history"].append({"item": item_id, **entry, "how": how})
    return entry


def active(it: dict, settings: dict, data: dict) -> bool:
    """Is the feature switched on in the settings (so it would run if it were allowed)?"""
    if it["id"] == "friends":
        return bool(str(settings.get("friends_server") or "").strip())
    if it["id"] == "friends_host":
        return bool(data.get("friends_host_wanted"))
    if it["id"] == "router" and (data.get("router_mapped") or data.get("router_mapped_friends")):
        return True
    return any(settings.get(k) == v for k, v in it["settings"].items())


def needs_review(data: dict, settings: dict) -> list[dict]:
    """Items that are switched on but have no yes for their current version: they do not run until the player looks."""
    return [it for it in ITEMS if active(it, settings, data) and not valid(data, it["id"], settings)]


def view(data: dict, settings: dict) -> list[dict]:
    """Every item with its words and where it stands, for the Permissions page and the dialog."""
    rec = record(data)
    out = []
    for it in ITEMS:
        st = state(data, it["id"], settings)
        d = rec["decisions"].get(it["id"]) or {}
        out.append({**{k: v for k, v in it.items() if k not in ("off",)}, "settings": sorted(it["settings"]),
                    "state": st, "allowed": st == "allowed", "decided_at": d.get("at"), "decided_version": d.get("version"),
                    "on": active(it, settings, data), "needs_review": active(it, settings, data) and st != "allowed"})
    return out


def one(data: dict, item_id: str, settings: dict) -> dict:
    return next(v for v in view(data, settings) if v["id"] == item_id)


def setting_items() -> dict:
    """setting -> item id, for every setting an item controls (the page asks for permission before turning one on)."""
    out = {}
    for it in ITEMS:
        for key in it["settings"]:
            out[key] = it["id"]
    out["friends_server"] = "friends"
    return out
