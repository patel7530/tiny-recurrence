"""Core recurrence expansion logic.

This module implements a small, predictable subset of RFC 5545 RRULE:
FREQ, INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY and WKST.

WHY a subset rather than full RFC 5545:
Full RRULE has dozens of interacting parts (BYxxx expansion order, RDATE,
EXDATE, negative month days, second-level precision). Supporting all of them
requires a state machine that is hard to verify. This library supports the
three most common patterns — daily, weekly with BYDAY, and monthly with
BYMONTHDAY — and handles the genuinely awkward edge cases (month length,
week boundaries, count/until termination) deterministically.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

__all__ = ["expand", "RRuleError"]

# RFC 5545 weekday mapping: SU=0 ... SA=6.
# Python's datetime.weekday() is Mon=0..Sun=6, so we convert.
_WEEKDAY_MAP = {"SU": 6, "MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5}
_VALID_BYDAY = set(_WEEKDAY_MAP)
_VALID_MONTHDAYS = set(range(1, 32))


class RRuleError(ValueError):
    """Raised for an invalid or unsupported RRULE string."""


def expand(rule: str, dtstart: date, limit: int = 100) -> list[date]:
    """Expand an RRULE string into a list of occurrence dates.

    Args:
        rule: An RRULE string, e.g. "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,FR;COUNT=5".
        dtstart: The first occurrence (anchor for all calculations).
        limit: Maximum number of occurrences to return. Acts as a safety net
            so a rule with neither COUNT nor UNTIL cannot loop forever.

    Returns:
        A list of datetime.date objects (or datetime.datetime if dtstart
        is a datetime — the time component is preserved). The list always
        includes dtstart as the first element when dtstart satisfies the
        rule; if it does not, the first satisfying date is used as the
        anchor instead (see _generate_weekly for details).

    Raises:
        RRuleError: If the rule is malformed or uses unsupported features.
    """
    if limit < 1:
        raise RRuleError("limit must be >= 1")
    params = _parse_rule(rule)
    freq = params["FREQ"]
    interval = params["INTERVAL"]
    count = params["COUNT"]
    until = params["UNTIL"]

    total_cap = min(count if count is not None else limit, limit)

    occurrences: list[date] = []
    if freq == "DAILY":
        gen = _generate_daily(dtstart, interval)
    elif freq == "WEEKLY":
        gen = _generate_weekly(dtstart, interval, params.get("BYDAY"), params.get("WKST"))
    elif freq == "MONTHLY":
        gen = _generate_monthly(dtstart, interval, params.get("BYMONTHDAY"))
    else:
        # _parse_rule validates FREQ, so this should be unreachable.
        raise RRuleError(f"Unsupported FREQ: {freq}")

    for occ in gen:
        if until is not None and occ > until:
            break
        occurrences.append(occ)
        if len(occurrences) >= total_cap:
            break
    return occurrences


def _parse_rule(rule: str) -> dict:
    """Parse an RRULE string into a validated parameter dict."""
    if not isinstance(rule, str):
        raise RRuleError("rule must be a string")
    rule = rule.strip()
    if rule.upper().startswith("RRULE:"):
        rule = rule[6:]
    if not rule:
        raise RRuleError("empty rule string")

    params: dict = {}
    for part in rule.split(";"):
        if "=" not in part:
            raise RRuleError(f"malformed rule part: {part!r}")
        key, val = part.split("=", 1)
        key = key.strip().upper()
        val = val.strip()
        if not key or not val:
            raise RRuleError(f"empty key or value in part: {part!r}")
        params[key] = val

    if "FREQ" not in params:
        raise RRuleError("FREQ is required")

    freq = params["FREQ"].upper()
    if freq not in ("DAILY", "WEEKLY", "MONTHLY"):
        raise RRuleError(f"FREQ must be DAILY, WEEKLY, or MONTHLY (got {freq})")
    params["FREQ"] = freq

    # Default interval is 1 per RFC 5545.
    if "INTERVAL" in params:
        try:
            interval = int(params["INTERVAL"])
        except ValueError:
            raise RRuleError(f"INTERVAL must be an integer (got {params['INTERVAL']!r})")
        if interval < 1:
            raise RRuleError(f"INTERVAL must be >= 1 (got {interval})")
        params["INTERVAL"] = interval
    else:
        params["INTERVAL"] = 1

    if "COUNT" in params:
        try:
            count = int(params["COUNT"])
        except ValueError:
            raise RRuleError(f"COUNT must be an integer (got {params['COUNT']!r})")
        if count < 1:
            raise RRuleError(f"COUNT must be >= 1 (got {count})")
        params["COUNT"] = count
    else:
        params["COUNT"] = None

    params["UNTIL"] = _parse_until(params.get("UNTIL"), freq)

    if freq == "WEEKLY":
        params["WKST"] = _parse_wkst(params.get("WKST"))
        params["BYDAY"] = _parse_byday(params.get("BYDAY"))
    elif "BYDAY" in params:
        raise RRuleError("BYDAY is only supported with FREQ=WEEKLY")
    elif "WKST" in params:
        raise RRuleError("WKST is only supported with FREQ=WEEKLY")

    if freq == "MONTHLY":
        params["BYMONTHDAY"] = _parse_bymonthday(params.get("BYMONTHDAY"))
    elif "BYMONTHDAY" in params:
        raise RRuleError("BYMONTHDAY is only supported with FREQ=MONTHLY")

    return params


def _parse_until(until_str: str | None, freq: str) -> date | None:
    """Parse and validate the UNTIL value.

    Per RFC 5545, UNTIL for DATE-TIME rules must be UTC. This library's
    expand() only returns date objects (datetime is treated as date for
    comparison purposes), so UNTIL must be a DATE to avoid ambiguity.
    """
    if until_str is None:
        return None
    s = until_str.strip()
    if "T" in s:
        raise RRuleError("UNTIL must be a DATE (YYYYMMDD); DATE-TIME is not supported")
    if len(s) != 8 or not s.isdigit():
        raise RRuleError(f"UNTIL must be YYYYMMDD (got {until_str!r})")
    try:
        return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        raise RRuleError(f"UNTIL is not a valid date: {until_str!r}")


def _parse_wkst(wkst_str: str | None) -> int:
    """Parse WKST into a Python weekday (Mon=0..Sun=6).

    Defaults to Monday per RFC 5545 default. WKST affects which dates fall
    into the same week for INTERVAL > 1.
    """
    if wkst_str is None:
        return 0  # MO
    wkst_str = wkst_str.strip().upper()
    if wkst_str not in _WEEKDAY_MAP:
        raise RRuleError(f"WKST must be a valid weekday (got {wkst_str!r})")
    return _WEEKDAY_MAP[wkst_str]


def _parse_byday(byday_str: str | None) -> list[int] | None:
    """Parse BYDAY into a list of Python weekdays, or None.

    Returns None to mean 'use dtstart's weekday', per RFC 5545.
    This subset does not support prefixed rules like '2MO' (second Monday).
    """
    if byday_str is None:
        return None
    parts = [p.strip().upper() for p in byday_str.split(",")]
    weekdays: list[int] = []
    for p in parts:
        if p not in _VALID_BYDAY:
            raise RRuleError(f"BYDAY entry {p!r} is not a valid weekday")
        weekdays.append(_WEEKDAY_MAP[p])
    if not weekdays:
        return None
    return weekdays


def _parse_bymonthday(bymonthday_str: str | None) -> list[int] | None:
    """Parse BYMONTHDAY into a sorted list of positive day numbers, or None.

    Returns None to mean 'use dtstart's day-of-month'.
    Negative days (e.g. -1 for last day) are not supported to keep the
    month-length logic tractable and well-defined.
    """
    if bymonthday_str is None:
        return None
    parts = [p.strip() for p in bymonthday_str.split(",")]
    days: list[int] = []
    for p in parts:
        try:
            day = int(p)
        except ValueError:
            raise RRuleError(f"BYMONTHDAY entry {p!r} is not an integer")
        if day not in _VALID_MONTHDAYS:
            raise RRuleError(f"BYMONTHDAY must be 1-31 (got {day})")
        days.append(day)
    if not days:
        return None
    return sorted(set(days))


def _generate_daily(dtstart: date, interval: int):
    """Yield dates spaced 'interval' days apart, starting at dtstart."""
    current = dtstart
    step = timedelta(days=interval)
    while True:
        yield current
        current = current + step


def _generate_weekly(
    dtstart: date,
    interval: int,
    byday: list[int] | None,
    wkst: int,
):
    """Yield dates for a weekly recurrence.

    Algorithm:
    - If BYDAY is None, the rule means 'every interval weeks on the same
      weekday as dtstart', which reduces to daily-style stepping.
    - If BYDAY is given, we generate week-by-week. A 'week' starts on WKST.
      Within each qualifying week (every INTERVAL weeks), we yield the
      BYDAY weekdays in chronological order.

    Anchor alignment:
    We align to the WKST start of dtstart's week. The anchor week is week 0.
    Only weeks at (anchor + n*interval) are eligible.
    dtstart itself is yielded if it falls on a BYDAY weekday within the
    anchor week; otherwise generation begins from the anchor week.
    """
    if byday is None:
        yield from _generate_daily(dtstart, interval * 7)
        return

    weekdays = sorted(set(byday))
    anchor_week_start = _week_start(dtstart, wkst)
    current_week_start = anchor_week_start

    while True:
        for wd in weekdays:
            # Offset from week start to the target weekday.
            delta_days = (wd - current_week_start.weekday()) % 7
            occ = current_week_start + timedelta(days=delta_days)
            # Only yield dates on or after dtstart (dtstart may be mid-week
            # and earlier weekdays in the anchor week should be skipped).
            if occ >= dtstart:
                yield occ
        current_week_start = current_week_start + timedelta(weeks=interval)


def _generate_monthly(
    dtstart: date,
    interval: int,
    bymonthday: list[int] | None,
):
    """Yield dates for a monthly recurrence.

    - If BYMONTHDAY is None, use dtstart's day-of-month.
    - If BYMONTHDAY is given, within each month yield all matching days
      that exist, in ascending order.

    Months shorter than the target day are skipped entirely — e.g.,
    BYMONTHDAY=31 in February yields nothing for February.
    """
    days = bymonthday if bymonthday is not None else [dtstart.day]
    year, month = dtstart.year, dtstart.month

    while True:
        month_len = calendar.monthrange(year, month)[1]
        for day in days:
            if day <= month_len:
                occ = _replace_date(dtstart, year, month, day)
                if occ >= dtstart:
                    yield occ
        # Advance month by interval, rolling over years.
        month += interval
        while month > 12:
            month -= 12
            year += 1
        while month < 1:
            month += 12
            year -= 1


def _week_start(d: date, wkst: int) -> date:
    """Return the date of the week containing 'd' that starts on 'wkst'."""
    delta = (d.weekday() - wkst) % 7
    return d - timedelta(days=delta)


def _replace_date(dtstart: date, year: int, month: int, day: int) -> date:
    """Create a new date/datetime preserving time if dtstart is a datetime."""
    if isinstance(dtstart, datetime):
        return dtstart.replace(year=year, month=month, day=day)
    return date(year, month, day)
