"""jira log <key> <duration> [--started <when>] [--remaining <duration>] [--dry-run]

Logs time on the issue as you: duration, such as 1h 30m, 2d or 45m, in weeks, days, hours and
minutes, started now unless --started gives when, as YYYY-MM-DD HH:MM in local time. The
Markdown on stdin, if any, is the worklog's comment. --remaining sets the issue's remaining
estimate; without it, Jira takes the time spent off it. It isn't logged again while the issue has
a worklog of yours with the same time, start, to the minute, and comment, so running it again
after a failure is safe when you gave --started: now moves on. --dry-run shows what would be
sent, without the API token or Jira.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

import json
import sys
from datetime import datetime
from typing import TextIO

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf, config, durations, keys, session

STARTED = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M")


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "log",
        help="log time on an issue, with the Markdown on stdin as its comment",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("duration", help="the time spent, such as 1h 30m")
    parser.add_argument(
        "--started", metavar="when", help="when it started, as YYYY-MM-DD HH:MM; now by default"
    )
    parser.add_argument(
        "--remaining", metavar="duration", help="set the remaining estimate, such as 2d"
    )
    parser.add_argument("--dry-run", action="store_true", help="show what would be sent")
    parser.set_defaults(
        run=lambda args: log(
            args.key,
            args.duration,
            started=args.started,
            remaining=args.remaining,
            dry_run=args.dry_run,
        )
    )


def log(
    key: str,
    duration: str,
    *,
    started: str | None = None,
    remaining: str | None = None,
    dry_run: bool = False,
    stdin: TextIO | None = None,
    now: datetime | None = None,
) -> Done | NothingToDo:
    stdin = stdin or sys.stdin
    markdown = "" if stdin.isatty() else stdin.read().strip()
    spent = durations.duration(duration)
    if spent == "0m":
        raise Precondition("No time to log.", "Give a duration, such as 1h 30m.")
    if remaining is not None:
        remaining = durations.duration(remaining)
    start = (_started(started) if started else (now or datetime.now())).astimezone()
    start = start.replace(second=0, microsecond=0)
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    worklog: dict = {"timeSpent": spent, "started": start.strftime("%Y-%m-%dT%H:%M:%S.000%z")}
    if markdown:
        worklog["comment"] = adf.from_markdown(markdown)

    if dry_run:
        print(json.dumps({"issue": key, "worklog": worklog, "remaining": remaining}, indent=2))
        return NothingToDo("Dry run: nothing logged.")

    jira = session.connect(settings)
    worklogs = jira.worklogs(key)
    if worklogs is None:
        raise session.missing(key)
    me = jira.myself().account_id
    # Jira rewrites the time spent in its largest units, 10h as 1d 2h, so it's compared in
    # seconds, by the site's working day and week.
    seconds = durations.seconds(spent, jira.time_units())
    reads = adf.to_markdown(worklog.get("comment") or {})
    if any(
        w.get("author", {}).get("accountId") == me
        and w.get("timeSpentSeconds") == seconds
        and _minute(w["started"]) == start
        and adf.to_markdown(w.get("comment") or {}) == reads
        for w in worklogs
    ):
        return NothingToDo(f"Already logged {spent} on {key} from {start:%Y-%m-%d %H:%M}.")
    return Done(f"Logged {spent} on {key}.", jira.add_worklog(key, worklog, remaining))


def _started(text: str) -> datetime:
    """The local time text names, as YYYY-MM-DD HH:MM or YYYY-MM-DDTHH:MM. Raises Precondition
    when it names none."""
    for form in STARTED:
        try:
            return datetime.strptime(text.strip(), form)
        except ValueError:
            pass
    raise Precondition(
        f"{text!r} isn't a time.",
        "Give it as YYYY-MM-DD HH:MM, in local time, such as 2026-10-14 09:00.",
    )


def _minute(started: str) -> datetime:
    """The time Jira wrote, such as 2026-10-14T09:00:00.000+0100, to the minute."""
    return datetime.fromisoformat(started).replace(second=0, microsecond=0)
