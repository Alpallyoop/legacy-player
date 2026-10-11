"""The Legacy Player World themes: eight places and four holiday towns, each with a day and a night look. The colours
and the pixel scenes live in the page (launcher/ui/index.html, BIOMES); this file only knows their names, the holiday
calendar and whether it is day, so the parts of the app outside the page (the tray menu) can follow along."""
from __future__ import annotations

import time

BIOMES = {
    "meadow": "Martin's Meadow", "harbor": "Pixel Harbor", "ember": "Ember Peaks", "frost": "Frostfall",
    "dunes": "Mirage Dunes", "glimmer": "Glimmerwood", "neon": "Neon Arcade", "cloudtop": "Cloudtop Isles",
    "spooky": "Spooky Hollow", "pumpkin": "Pumpkin Town", "winterlights": "Winter Lights", "newyear": "New Year",
}
HOLIDAY_BIOMES = ("spooky", "pumpkin", "winterlights", "newyear")
DAY_START, DAY_END = 7 * 60, 19 * 60            # "Follow my clock": day from 07:00 to 19:00 local time
TIMES = ("auto", "day", "night")

# The holiday calendar by this computer's local date: (month, day), both ends included. The page keeps the same table
# (HOLIDAYS and holidayFor() in launcher/ui/index.html); tests/test_world.py checks that the two agree day by day.
# Spooky season only counts when the player turned on "Seasonal themes"; the others follow "Holiday themes" (on by default).
HOLIDAYS = (
    {"id": "halloween", "theme": "pumpkin", "start": (10, 24), "end": (11, 1), "seasonal": False},
    {"id": "spooky", "theme": "spooky", "start": (10, 1), "end": (10, 23), "seasonal": True},
    {"id": "winter", "theme": "winterlights", "start": (12, 18), "end": (12, 30), "seasonal": False},
    {"id": "newyear", "theme": "newyear", "start": (12, 31), "end": (1, 1), "seasonal": False},
)


def time_now(choice: str, now: float | None = None) -> str:
    """'day' or 'night' for a time-of-day setting ('auto' reads this computer's clock)."""
    if choice in ("day", "night"):
        return choice
    t = time.localtime(now if now is not None else time.time())
    minutes = t.tm_hour * 60 + t.tm_min
    return "day" if DAY_START <= minutes < DAY_END else "night"


def holiday_for(month: int, day: int, seasonal: bool = False) -> dict | None:
    """The holiday on this calendar day, or None. Spooky season only counts when seasonal themes are on."""
    md = month * 100 + day
    for h in HOLIDAYS:
        if h["seasonal"] and not seasonal:
            continue
        a, b = h["start"][0] * 100 + h["start"][1], h["end"][0] * 100 + h["end"][1]
        if (a <= md <= b) if a <= b else (md >= a or md <= b):
            return h
    return None


def shown_theme(settings: dict, now: float | None = None) -> str:
    """The theme the app shows: a holiday town during its holiday (unless the player turned that off), otherwise the
    player's own. A holiday never changes the saved theme."""
    theme = settings.get("theme", "dark")
    t = time.localtime(now if now is not None else time.time())
    h = holiday_for(t.tm_mon, t.tm_mday, bool(settings.get("seasonal_themes")))
    if h is None or (not h["seasonal"] and not settings.get("holiday_themes", True)):
        return theme
    return h["theme"]


def looks_light(settings: dict, now: float | None = None) -> bool:
    """Is the app light right now? The Light theme always is; a World theme is light by day and dark by night."""
    theme = shown_theme(settings, now)
    if theme == "light":
        return True
    return theme in BIOMES and time_now(settings.get("time_of_day", "auto"), now) == "day"
