"""tiny-recurrence: a readable subset of RRULE for daily, weekly and monthly repeats."""

from .core import expand, RRuleError

__all__ = ["expand", "RRuleError"]
