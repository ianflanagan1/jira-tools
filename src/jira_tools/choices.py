"""Naming a priority, issue type, component or version on the command line, matched ignoring case
against those the space has and named as Jira names them; and a date, as YYYY-MM-DD."""

import datetime
import re

from cli_kit.outcome import Precondition

from jira_tools import api

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def priority(jira: api.Jira, space: str, given: str) -> str:
    return _one(space, "priority", given, jira.priorities(space))


def issue_type(jira: api.Jira, space: str, given: str) -> api.IssueType:
    types = jira.issue_types(space)
    name = _one(space, "issue type", given, [t.name for t in types])
    return next(t for t in types if t.name == name)


def components(jira: api.Jira, space: str, given: list[str]) -> list[str]:
    """Each component given, once, in the order given."""
    if not given:
        return []
    names = jira.components(space)
    return list(dict.fromkeys(_one(space, "component", one, names) for one in given))


def versions(jira: api.Jira, space: str, given: list[str]) -> list[str]:
    """Each version given, once, in the order given."""
    if not given:
        return []
    names = jira.versions(space)
    return list(dict.fromkeys(_one(space, "version", one, names) for one in given))


def date(given: str, name: str) -> str:
    """given, a day as YYYY-MM-DD. Raises Precondition, saying name, the option or field it's
    for, takes one, when it's anything else."""
    given = given.strip()
    try:
        if DATE.match(given):
            datetime.date.fromisoformat(given)
            return given
    except ValueError:
        pass
    raise Precondition(f"{name} takes a date as YYYY-MM-DD, such as 2026-10-31, not {given!r}.")


def _one(space: str, kind: str, given: str, names: list[str]) -> str:
    """The name among names that is given, ignoring case. Raises Precondition, listing names,
    when none is."""
    wanted = given.strip().casefold()
    for name in names:
        if name.casefold() == wanted:
            return name
    raise Precondition(
        f"{space} has no {kind} {given.strip()!r}.",
        f"It has: {', '.join(names)}." if names else "It has none.",
    )
