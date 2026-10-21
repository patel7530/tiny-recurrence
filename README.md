# tiny-recurrence

A readable subset of RRULE for daily, weekly, and monthly repeats.

## Installation

    pip install tiny-recurrence

## Usage

    from tiny_recurrence import expand
    from datetime import date

    # Daily, 5 occurrences
    expand("FREQ=DAILY;COUNT=5", date(2025, 6, 1))
    # [date(2025, 6, 1), date(2025, 6, 2), date(2025, 6, 3), date(2025, 6, 4), date(2025, 6, 5)]

    # Weekly on Mondays and Fridays, every 2 weeks
    expand("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,FR;COUNT=4", date(2025, 6, 2))
    # [date(2025, 6, 2), date(2025, 6, 6), date(2025, 6, 16), date(2025, 6, 20)]

    # Monthly on the 31st (short months are skipped)
    expand("FREQ=MONTHLY;BYMONTHDAY=31;COUNT=2", date(2025, 1, 31))
    # [date(2025, 1, 31), date(2025, 3, 31)]

## Why this exists

Full RFC 5545 RRULE is complex enough that correct implementations are rare and heavy. This library covers the three patterns most applications actually need — daily, weekly with named weekdays, and monthly with fixed days — with zero third-party dependencies and deterministic behaviour. It does not support BYxxx expansion chains, RDATE, EXDATE, negative month days, or second-precision UNTIL. Every rule has a `limit` cap (default 100) so open-ended rules cannot loop forever.

## Edge cases

- **Month length**: `BYMONTHDAY=31` silently skips February (and other short months). This matches common expectations for "last day" style rules, though a dedicated `BYMONTHDAY=-1` would be more explicit (and is not supported here).
- **Weekly anchor**: if `dtstart` is not in the `BYDAY` set, the first occurrence is the earliest matching weekday on or after `dtstart` within its week.
- **UNTIL**: must be a `YYYYMMDD` date string. `DATE-TIME` UNTIL values are rejected because this library only produces dates, and mixing precision levels is a common source of off-by-one bugs.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

