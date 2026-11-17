"""The athlete's local training day: one rule for which calendar day a stored timestamp belongs to.

Stored timestamps are instants. The logger saves them in UTC, so an 11:35 pm Eastern workout on
15 November is stored as 2026-11-16T04:35:00Z, and imported Hevy start times are naive UTC. Cutting
the first ten characters of such a value gives the UTC date, which moves an evening workout to the
next day. Ask this module instead.

The zone is TZ when it names an IANA zone (America/New_York in Docker). Without it, or when TZ is
not an IANA name, the server's own local zone is used, the same zone date.today() reads. Pure: no
database or network access. Host modules import it as rackbook.local_day, the logger as .local_day.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@lru_cache(maxsize=8)
def _named_zone(name: str) -> tzinfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def zone() -> tzinfo | None:
    """The configured zone, or None for the server's own local zone (what astimezone(None) uses)."""
    name = (os.environ.get("TZ") or "").strip()
    return _named_zone(name) if name else None


def instant(value) -> datetime | None:
    """An aware datetime for a stored timestamp. Naive values are UTC, as stored by the importer."""
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if len(text) <= 10:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def local_day(value) -> date | None:
    """The local calendar day of a timestamp. A plain date (or YYYY-MM-DD text) is already a day."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    moment = instant(value)
    if moment is not None:
        return moment.astimezone(zone()).date()
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def local_day_text(value) -> str | None:
    """local_day as YYYY-MM-DD, for JSON and for SQL comparisons with ISO date parameters."""
    day = local_day(value)
    return day.isoformat() if day else None


def local_today(now: datetime | None = None) -> date:
    """Today in the local zone. now (aware, or naive UTC) is for tests."""
    moment = instant(now) if now is not None else datetime.now(timezone.utc)
    return moment.astimezone(zone()).date()


def register(conn) -> None:
    """Make local_day(column) available in SQL on a sqlite3 connection, read-only ones included."""
    conn.create_function("local_day", 1, local_day_text, deterministic=True)
