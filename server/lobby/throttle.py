"""Per-address failure throttle: after a few wrong guesses an address is locked out for a while.

Used for invite codes and the server access key so one address cannot guess them, without letting that
address lock everyone else out. The table is bounded so a flood of fake addresses cannot grow it forever.
"""
from __future__ import annotations

import ipaddress
import time

MAX_TRACKED = 4096
MAX_LOCKED = 16384      # addresses locked out at once (each needs max_failures wrong tries to get here)


# The peer key of every connection that came through a meeting point. Never an address, never "this computer".
FORWARDED = "via-meeting-point"


def key_for(peer: str | None) -> str | None:
    """The address to count against, or None for this computer / unknown (never throttled per address)."""
    if not peer:
        return None
    if peer == FORWARDED:
        return FORWARDED                       # friends through a meeting point share one bucket (no address is known)
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return None
    if ip.is_loopback:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        # A household is given a /56 (or a /48) by its provider, not just a /64. Counting per /64 would hand whoever holds a
        # /48 65,536 separate budgets of wrong guesses; per /56 it is 256.
        return str(ipaddress.ip_network(f"{ip}/56", strict=False).network_address)
    return str(ip)


class FailureThrottle:
    """`max_failures` wrong tries within `window` seconds lock one address out for `lockout` seconds.

    Friends who come through a meeting point all share the FORWARDED key (their addresses are not known here). Locking
    that key would let one stranger lock every meeting-point friend out, so it is never locked: it gets a larger rolling
    budget instead (`forwarded_factor` x `max_failures` per `window`), and once that is used up further tries wait only
    until the oldest failure leaves the window. Guess rates through the meeting point stay far too low to matter: for
    the server access key (40 bits, 8 x 10 = 80 tries a minute) that is about 2**40 / 80 minutes, over 26,000 years;
    for invite codes (50 bits, 5 x 10 = 50 a minute, and the global cap in invites.py) longer still, while a code
    lives at most a day.
    """

    def __init__(self, *, max_failures: int = 5, window: float = 60.0, lockout: float = 300.0, clock=time.monotonic,
                 forwarded_factor: int = 10, max_locked: int = MAX_LOCKED) -> None:
        self.max_failures, self.window, self.lockout, self.clock = max_failures, window, lockout, clock
        self.forwarded_budget = max(1, max_failures * forwarded_factor)
        self.max_locked = max_locked
        self._fails: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}

    def _forwarded_wait(self, now: float) -> float:
        recent = [t for t in self._fails.get(FORWARDED, ()) if now - t <= self.window]
        if len(recent) < self.forwarded_budget:
            return 0.0
        return max(0.001, self.window - (now - recent[-self.forwarded_budget]))

    def blocked(self, peer: str | None) -> float:
        """Seconds left on a lockout (0 when the address may try)."""
        key = key_for(peer)
        if key is None:
            return 0.0
        now = self.clock()
        if key == FORWARDED:
            return self._forwarded_wait(now)
        until = self._locked.get(key, 0.0)
        if until <= now:
            self._locked.pop(key, None)
            return 0.0
        return until - now

    def fail(self, peer: str | None) -> None:
        key = key_for(peer)
        if key is None:
            return
        now = self.clock()
        if len(self._fails) + len(self._locked) > MAX_TRACKED:
            self._sweep(now)
        recent = [t for t in self._fails.get(key, []) if now - t <= self.window]
        recent.append(now)
        if key == FORWARDED:                      # shared by every meeting-point friend: a budget, never a lockout
            self._fails[key] = recent[-self.forwarded_budget:]
            return
        if len(recent) >= self.max_failures:
            self._lock(key, now)
            recent = []
        self._fails[key] = recent

    def _lock(self, key: str, now: float) -> None:
        """Bounded: when the table is full, expired locks go first; if it is still full, the lock closest to running out
        on its own goes. Pushing out one real lockout that way means creating `max_locked` fresh ones (max_failures
        wrong tries each, from that many different addresses) within the lockout time, and it gains at most the few
        seconds that lock had left."""
        self._locked.pop(key, None)
        if len(self._locked) >= self.max_locked:
            for k in [k for k, t in self._locked.items() if t <= now]:
                del self._locked[k]
            if len(self._locked) >= self.max_locked:
                del self._locked[min(self._locked, key=self._locked.__getitem__)]
        self._locked[key] = now + self.lockout

    def ok(self, peer: str | None) -> None:
        key = key_for(peer)
        if key is not None and key != FORWARDED:  # one friend's success must not reset a budget everyone shares
            self._fails.pop(key, None)

    def _sweep(self, now: float) -> None:
        for k in [k for k, t in self._locked.items() if t <= now]:
            del self._locked[k]
        for k in [k for k, ts in self._fails.items() if not ts or now - ts[-1] > self.window]:
            del self._fails[k]
        while len(self._fails) > MAX_TRACKED:
            self._fails.pop(next(iter(self._fails)))


def wait_text(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    return f"Too many wrong tries from this address. Try again in about {minutes} minute{'s' if minutes != 1 else ''}."
