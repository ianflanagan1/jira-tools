"""jira log: time logged on an issue as you, against a fake Jira site, in London's time."""

import io
import json
import os
import time
from datetime import datetime

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf
from jira_tools.__main__ import main
from jira_tools.commands.log import log

SITE = "https://me.atlassian.net"
NOW = datetime(2026, 10, 14, 16, 45, 31)


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def london():
    was = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/London"
    time.tzset()
    yield
    if was is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = was
    time.tzset()


def logs(duration: str = "1h 30m", markdown: str = "", key: str = "WEB-12", **options):
    stdin = io.StringIO(markdown) if markdown else Terminal()
    return log(key, duration, stdin=stdin, now=NOW, **options)


def test_logs_the_time_as_you_from_now_to_the_minute_and_gives_its_url(site):
    site.add("WEB-12")
    result = logs("1h30m")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Logged 1h 30m on WEB-12.",
        f"{SITE}/browse/WEB-12?focusedWorklogId=10000",
    )
    [logged] = site.worklogs["WEB-12"]
    assert logged["author"] == site.me
    assert (logged["timeSpent"], logged["started"]) == ("1h 30m", "2026-10-14T16:45:00.000+0100")
    assert "comment" not in logged


def test_the_markdown_on_stdin_is_its_comment(site):
    site.add("WEB-12")
    logs(markdown="Wrote the **fix**.\n")
    assert site.worklogs["WEB-12"][0]["comment"] == adf.from_markdown("Wrote the **fix**.")


@pytest.mark.parametrize("started", ["2026-10-01 09:00", "2026-10-01T09:00"])
def test_it_started_when_given_in_local_time(site, started):
    site.add("WEB-12")
    logs(started=started)
    assert site.worklogs["WEB-12"][0]["started"] == "2026-10-01T09:00:00.000+0100"


def test_a_start_in_winter_time_has_winter_times_offset(site):
    site.add("WEB-12")
    logs(started="2026-12-01 09:00")
    assert site.worklogs["WEB-12"][0]["started"] == "2026-12-01T09:00:00.000+0000"


def test_the_remaining_estimate_is_set_when_given(site):
    site.add("WEB-12")
    logs(remaining="2d 4h")
    assert site.issues["WEB-12"]["timetracking"] == {"remainingEstimate": "2d 4h"}


def test_without_a_remaining_estimate_jira_adjusts_it(site):
    site.add("WEB-12")
    logs()
    assert "timetracking" not in site.issues["WEB-12"]


def test_your_worklog_with_the_same_time_start_and_comment_is_not_logged_again(site):
    site.add("WEB-12")
    site.worklog("WEB-12", "1h 30m", "2026-10-14T09:00:00.000+0100", adf.from_markdown("Fix"))
    result = logs(markdown="Fix", started="2026-10-14 09:00")
    assert isinstance(result, NothingToDo)
    assert result.summary == "Already logged 1h 30m on WEB-12 from 2026-10-14 09:00."
    assert site.writes == []


def test_the_same_time_is_matched_however_jira_writes_it(site):
    site.time_tracking = {"workingHoursPerDay": 7.0, "workingDaysPerWeek": 5.0}
    site.add("WEB-12")
    site.worklog("WEB-12", "1d 3h", "2026-10-14T08:00:00.000+0000")
    assert isinstance(logs("10h", started="2026-10-14 09:00"), NothingToDo)


def test_the_same_start_is_matched_to_the_minute(site):
    site.add("WEB-12")
    site.worklog("WEB-12", "1h 30m", "2026-10-14T16:45:12.000+0100")
    assert isinstance(logs(), NothingToDo)


@pytest.mark.parametrize(
    ("duration", "started", "markdown", "author"),
    [
        ("1h", "2026-10-14 09:00", "Fix", None),
        ("1h 30m", "2026-10-14 09:01", "Fix", None),
        ("1h 30m", "2026-10-14 09:00", "Other", None),
        ("1h 30m", "2026-10-14 09:00", "", None),
        ("1h 30m", "2026-10-14 09:00", "Fix", "a-1"),
    ],
)
def test_a_worklog_that_differs_in_time_start_comment_or_author_does_not_stop_yours(
    site, duration, started, markdown, author
):
    other = site.person("a-1", "Alice")
    site.add("WEB-12")
    site.worklog(
        "WEB-12",
        duration,
        started.replace(" ", "T") + ":00.000+0100",
        adf.from_markdown(markdown) if markdown else None,
        other if author else None,
    )
    assert isinstance(logs(markdown="Fix", started="2026-10-14 09:00"), Done)


@pytest.mark.parametrize("duration", ["90", "1.5h", "an hour"])
def test_a_time_that_is_not_a_duration_is_refused_before_the_token_is_read(site, duration):
    with pytest.raises(Precondition) as raised:
        logs(duration)
    assert raised.value.message == f"{duration!r} isn't a duration."
    assert site.tokens_read == 0


def test_no_time_is_refused(site):
    with pytest.raises(Precondition) as raised:
        logs("0h")
    assert [raised.value.message, *raised.value.details] == [
        "No time to log.",
        "Give a duration, such as 1h 30m.",
    ]


def test_a_remaining_estimate_that_is_not_a_duration_is_refused(site):
    with pytest.raises(Precondition) as raised:
        logs(remaining="soon")
    assert raised.value.message == "'soon' isn't a duration."


@pytest.mark.parametrize("started", ["yesterday", "2026-10-14", "14/10/2026 09:00", "09:00"])
def test_a_start_that_is_not_a_time_is_refused_before_the_token_is_read(site, started):
    with pytest.raises(Precondition) as raised:
        logs(started=started)
    assert [raised.value.message, *raised.value.details] == [
        f"{started!r} isn't a time.",
        "Give it as YYYY-MM-DD HH:MM, in local time, such as 2026-10-14 09:00.",
    ]
    assert site.tokens_read == 0


def test_an_issue_that_is_not_there_is_named(site):
    with pytest.raises(Precondition) as raised:
        logs()
    assert raised.value.message == "No issue WEB-12."


def test_a_dry_run_shows_the_worklog_and_reads_no_token_and_sends_nothing(site, capsys):
    result = logs("2h", "Fix", started="2026-10-14 09:00", remaining="1d", dry_run=True)
    assert isinstance(result, NothingToDo)
    assert result.summary == "Dry run: nothing logged."
    assert json.loads(capsys.readouterr().out) == {
        "issue": "WEB-12",
        "worklog": {
            "timeSpent": "2h",
            "started": "2026-10-14T09:00:00.000+0100",
            "comment": adf.from_markdown("Fix"),
        },
        "remaining": "1d",
    }
    assert site.tokens_read == 0


def test_the_command_line_takes_the_key_duration_and_options(site, monkeypatch, capsys):
    site.add("WEB-12")
    monkeypatch.setattr("sys.stdin", io.StringIO("Fix"))
    argv = ["log", "12", "45m", "--started", "2026-10-14 09:00", "--remaining", "1h"]
    assert main(argv) == 0
    assert capsys.readouterr().out.startswith("✅ Logged 45m on WEB-12.\n")
    [logged] = site.worklogs["WEB-12"]
    assert logged["started"] == "2026-10-14T09:00:00.000+0100"
    assert site.issues["WEB-12"]["timetracking"] == {"remainingEstimate": "1h"}
