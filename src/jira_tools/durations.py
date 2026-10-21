"""Durations as Jira writes them, such as 1h 30m: weeks, days, hours and minutes. Jira counts a
day and a week in working time, by default 8 hours and 5 days, so a duration's length in seconds
depends on the site."""

import re

from cli_kit.outcome import Precondition

DURATION = re.compile(r"^(?:(\d+)w)?\s*(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?$")
UNITS = "wdhm"


def duration(text: str) -> str:
    """The duration text names, written as Jira writes it: 1h 30m for 1h30m. Raises Precondition
    when it names none."""
    parts = DURATION.match(text.strip().casefold())
    if not text.strip() or parts is None:
        raise Precondition(
            f"{text!r} isn't a duration.",
            "Give it as Jira does, in weeks, days, hours and minutes, such as 1h 30m or 2d.",
        )
    counts = zip(parts.groups(), UNITS, strict=True)
    written = [f"{int(n)}{unit}" for n, unit in counts if n and int(n)]
    return " ".join(written) or "0m"


def seconds(duration: str, units: dict[str, int]) -> int:
    """The seconds in duration, written as Jira writes it, with units the seconds in each unit."""
    return sum(int(n) * units[unit] for n, unit in re.findall(r"(\d+)([wdhm])", duration))
