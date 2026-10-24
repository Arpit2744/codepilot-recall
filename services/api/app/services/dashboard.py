"""Pure dashboard aggregation logic: timezone bucketing and streaks.

Timezone semantics (ADR-0003): every source timestamp is UTC; a local
activity date is `timestamp.astimezone(tz).date()`. We never group by UTC
date and relabel it.
"""

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Heatmap range guard: large enough for a full year + margin.
MAX_HEATMAP_DAYS = 731
STREAK_WINDOW_DAYS = 400


def resolve_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise ValueError(f"Unknown timezone: {name!r}") from exc


def local_range_to_utc(from_date: date, to_date: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[from_date 00:00 local, (to_date + 1 day) 00:00 local) expressed in UTC."""
    start = datetime.combine(from_date, datetime.min.time(), tzinfo=tz).astimezone(UTC)
    end_local = to_date + timedelta(days=1)
    end = datetime.combine(end_local, datetime.min.time(), tzinfo=tz).astimezone(UTC)
    return start, end


def bucket_by_local_date(timestamps: Sequence[datetime], tz: ZoneInfo) -> Counter[date]:
    """Count timestamps per LOCAL calendar date in `tz` (midnight boundary
    evaluated in the target zone, DST-safe via zoneinfo)."""
    naive_safe = (ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts for ts in timestamps)
    return Counter(ts.astimezone(tz).date() for ts in naive_safe)


def build_continuous_days(
    counts: Counter[date], from_date: date, to_date: date
) -> list[dict]:
    """Continuous date sequence including zero-activity days."""
    days = []
    current = from_date
    while current <= to_date:
        days.append({"date": current.isoformat(), "count": counts.get(current, 0)})
        current += timedelta(days=1)
    return days


def compute_streak(active_dates: set[date], today_local: date) -> int:
    """Consecutive active days ending today (or yesterday, so a streak
    survives until the day ends). Capped at the lookup window."""
    start = today_local if today_local in active_dates else today_local - timedelta(days=1)
    streak = 0
    current = start
    for _ in range(STREAK_WINDOW_DAYS):
        if current in active_dates:
            streak += 1
            current -= timedelta(days=1)
        else:
            break
    return streak


def streak_window_utc(today_local: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC bounds for the activity lookback used by streak computation."""
    start_date = today_local - timedelta(days=STREAK_WINDOW_DAYS)
    return local_range_to_utc(start_date, today_local, tz)
