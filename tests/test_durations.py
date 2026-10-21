"""Durations as Jira writes them, such as 1h 30m: read from the command line, and in seconds."""

import pytest
from cli_kit.outcome import Precondition

from jira_tools.durations import duration, seconds

UNITS = {"w": 5 * 8 * 3600, "d": 8 * 3600, "h": 3600, "m": 60}


@pytest.mark.parametrize(
    ("given", "read"),
    [
        ("1h 30m", "1h 30m"),
        ("1h30m", "1h 30m"),
        ("  2D ", "2d"),
        ("45m", "45m"),
        ("1w 2d 3h 4m", "1w 2d 3h 4m"),
        ("1h 0m", "1h"),
        ("0m", "0m"),
    ],
)
def test_a_duration_is_read_in_weeks_days_hours_and_minutes_and_written_as_jira_writes_it(
    given, read
):
    assert duration(given) == read


@pytest.mark.parametrize("given", ["", "90", "1.5h", "1x", "30m 1h", "1h 1h", "h", "an hour"])
def test_anything_else_is_not_a_duration(given):
    with pytest.raises(Precondition) as raised:
        duration(given)
    assert [raised.value.message, *raised.value.details] == [
        f"{given!r} isn't a duration.",
        "Give it as Jira does, in weeks, days, hours and minutes, such as 1h 30m or 2d.",
    ]


def test_a_duration_in_seconds_counts_days_and_weeks_by_the_units_given():
    assert seconds("1w 2d 3h 4m", UNITS) == 7 * 8 * 3600 + 3 * 3600 + 4 * 60
    assert seconds("1d", UNITS | {"d": 7 * 3600}) == 7 * 3600
