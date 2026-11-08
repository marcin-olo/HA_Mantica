"""Failure-handling rules and new-item detection (no Home Assistant imports)."""
from __future__ import annotations

from typing import Any

# Version of the grade-ID format kept in storage. Bump when IDs change so
# stored IDs are re-seeded instead of every grade looking "new".
ID_FORMAT = 2

# More "new" items than this in a single update is treated as suspicious
# (layout/ID change, semester switch) -> one bulk event instead of N events.
MAX_EVENTS_PER_UPDATE = 5

ACTION_RETRY = "retry"
ACTION_ISSUE = "issue"
ACTION_REAUTH = "reauth"


class FailurePolicy:
    """Counts consecutive failures per kind and decides what to do.

    auth   - the server answered with the login form again after we sent the
             password. Could be a changed password *or* a changed login form,
             so ask the user only after several attempts in a row (~1.5 h).
    layout - logged-in page with unrecognised structure. Deterministic, so a
             Repairs issue after 2 attempts (filters out one truncated page).
    conn   - network errors, HTTP errors, maintenance / unknown pages.
             Usually transient; Repairs issue only after ~2 h.
    Any successful update resets everything.
    """

    LIMITS = {"auth": 3, "layout": 2, "conn": 4}

    def __init__(self) -> None:
        self.counts = {k: 0 for k in self.LIMITS}

    def record(self, kind: str) -> str:
        for k in self.counts:
            if k != kind:
                self.counts[k] = 0
        self.counts[kind] += 1
        if self.counts[kind] < self.LIMITS[kind]:
            return ACTION_RETRY
        return ACTION_REAUTH if kind == "auth" else ACTION_ISSUE

    def success(self) -> None:
        self.counts = {k: 0 for k in self.LIMITS}


def find_new(
    items: list[dict[str, Any]], seen: set[str] | None
) -> tuple[list[dict[str, Any]], bool]:
    """Return (new_items, is_bulk). seen=None means first run: nothing is new."""
    if seen is None:
        return [], False
    new = [i for i in items if i["id"] not in seen]
    return new, len(new) > MAX_EVENTS_PER_UPDATE


# The calendar is read for a 3-month window, so when it moves on, entries of
# the newly visible month were not "added" just now. Only entries the school
# added recently (per their "Data dodania") count as new.
NEW_EVENT_MAX_AGE_DAYS = 7


def recently_added(events: list[dict[str, Any]], today_iso: str) -> list[dict[str, Any]]:
    from datetime import date, timedelta

    cutoff = (date.fromisoformat(today_iso) - timedelta(days=NEW_EVENT_MAX_AGE_DAYS)).isoformat()
    return [e for e in events if not e.get("added") or e["added"] >= cutoff]


def next_poll_delay(now: Any, interval_min: int, start_h: int, end_h: int) -> Any:
    """Time until the next portal read.

    Reads happen every `interval_min` minutes between start_h:00 and
    end_h:00 (local time); at night the next read is at start_h:00.
    `now` is a timezone-aware datetime; returns a timedelta.
    """
    from datetime import timedelta

    if start_h <= 0 and end_h >= 24:
        return timedelta(minutes=interval_min)
    nxt = now + timedelta(minutes=interval_min)
    mins = nxt.hour * 60 + nxt.minute
    if nxt.date() == now.date() and start_h * 60 <= mins <= end_h * 60:
        return timedelta(minutes=interval_min)
    # Next window opening: later today if still before it, otherwise tomorrow.
    opening = now.replace(hour=start_h, minute=0, second=0, microsecond=0)
    if opening <= now:
        opening += timedelta(days=1)
    return opening - now
