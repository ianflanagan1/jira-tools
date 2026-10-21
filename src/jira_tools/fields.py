"""Setting any field by name: Name=value, given on the command line, as Jira's JSON for the field.

What a field takes comes from its metadata, as a screen gives it: an issue's edit screen, a type's
create screen, or a transition's screen. Each is the fields it can set, by id, each with its name,
its schema and any values it allows, so nothing here depends on which screen it came from.
"""

import difflib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cli_kit.outcome import Precondition

from jira_tools import adf, api, choices, durations, people

# The field --estimate sets, by its id.
ESTIMATE = "timetracking"
CUSTOM = "com.atlassian.jira.plugin.system.customfieldtypes:"
SPRINT = "com.pyxis.greenhopper.jira:gh-sprint"

# The fields Jira's API v3 takes as ADF rather than text: multi-line custom fields, and the
# system fields that are rich text.
RICH_TEXT_SYSTEM = {"description", "environment"}

# The kinds of value chosen by name from a field's allowed values, and the key each is named by.
CHOSEN = {
    "option": "value",
    "version": "name",
    "component": "name",
    "priority": "name",
    "resolution": "name",
}

# The fields commands set with options of their own, which --field mustn't fight, and how each is
# given instead.
RESERVED = {
    "summary": "Give it with --summary.",
    "description": "Give it as Markdown on stdin.",
    "labels": "Give them with --label, and on jira edit --unlabel.",
    "issuetype": "Give it with --type.",
    "project": "Give it with --space.",
}

# The kinds of value a field can take several of.
LISTED = {"option", "string", "user", "version", "component"}


@dataclass(frozen=True)
class Changes:
    """The fields to set, by id, as Jira's JSON has them; and the ids of the fields to clear."""

    fields: dict
    clears: tuple[str, ...]

    def json(self) -> dict:
        """The changes as an edit's fields: each cleared one set to null."""
        return {**self.fields, **dict.fromkeys(self.clears)}

    def differing_from(self, current: dict, units: dict[str, int] | None = None) -> "Changes":
        """These changes without those that would leave a field as it is in current, an issue's
        fields. units are the seconds in each unit of a duration on the site, to compare an
        original estimate by, since Jira rewrites one, such as 8h as 1d; without them, an
        estimate is compared as written."""
        differing = {}
        for field, value in self.fields.items():
            if field == "timetracking" and units is not None:
                same = _same_estimate(value, current.get(field), units)
            else:
                same = _same(value, current.get(field))
            if not same:
                differing[field] = value
        return Changes(differing, tuple(f for f in self.clears if not _empty(current.get(f))))


def convert(meta: dict, given: list[str], jira: api.Jira, *, space: str, screen: str) -> Changes:
    """The changes given asks for, each Name=value: the field named, by its name ignoring case or
    by its id, set to value, read as the field's schema in meta says; or cleared, for an empty
    value. A field that takes several values takes one each time it's given. space is the space
    whose sprints a sprint is named among, and screen what meta is, for saying a field isn't on it.

    Raises Precondition for a field meta doesn't have, or has more than one of, one in RESERVED,
    and for a value the field can't take."""
    values: dict[str, list[str]] = {}
    for name, value in pairs(given):
        field = _field(meta, name, screen)
        if field in RESERVED:
            raise Precondition(
                f"{meta[field].get('name', field)} can't be set with --field.", RESERVED[field]
            )
        values.setdefault(field, []).append(value)
    fields: dict = {}
    clears: list[str] = []
    for field, given_values in values.items():
        value = _value(meta[field], [v for v in given_values if v], jira, space)
        if value is None:
            clears.append(field)
        else:
            fields[field] = value
    return Changes(fields, tuple(clears))


def given(values: list[str], files: list[str], estimate: str | None) -> list[str]:
    """The fields a command is given to set, each Name=value: values; files, each Name=path,
    read; and estimate, a duration, as the time tracking field's. Raises Precondition for one that
    isn't Name=value, a file that can't be read, or an estimate that isn't a duration."""
    named = [*values, *from_files(files)]
    if estimate is not None:
        named.append(f"{ESTIMATE}={durations.duration(estimate)}")
    pairs(named)
    return named


def pairs(given: list[str]) -> list[tuple[str, str]]:
    """Each of given, Name=value, as its name and value, with the space around each removed.
    Raises Precondition for one without a name."""
    split = []
    for pair in given:
        name, _, value = pair.partition("=")
        if not name.strip() or "=" not in pair:
            raise Precondition(
                f"{pair!r} isn't a field and its value.",
                "Give it as <name>=<value>, such as 'Story points=3'.",
            )
        split.append((name.strip(), value.strip()))
    return split


def from_files(given: list[str]) -> list[str]:
    """Each of given, Name=path, as Name=value, the value the file's contents. Raises Precondition
    for a file that can't be read."""
    read = []
    for name, path in pairs(given):
        try:
            read.append(f"{name}={Path(path).read_text()}")
        except OSError as error:
            raise Precondition(f"Can't read {path}.", error.strerror or str(error)) from None
    return read


def _field(meta: dict, name: str, screen: str) -> str:
    """The id of the field in meta that name names. Raises Precondition when none does, or more
    than one."""
    if name.casefold() in (field.casefold() for field in meta):
        return next(field for field in meta if field.casefold() == name.casefold())
    matches = [
        f for f, about in meta.items() if about.get("name", "").casefold() == name.casefold()
    ]
    if len(matches) > 1:
        raise Precondition(
            f"More than one field is named {name!r}: {', '.join(matches)}.",
            "Name it by its id instead.",
        )
    if not matches and name.casefold() == ESTIMATE:
        raise Precondition(
            f"--estimate can't be set on {screen}.",
            "It has no time tracking: that may be turned off, or not on the screen.",
        )
    if not matches:
        names = {about.get("name", "").casefold(): about.get("name", "") for about in meta.values()}
        close = difflib.get_close_matches(name.casefold(), names, n=3)
        hint = [f"Did you mean {' or '.join(names[c] for c in close)}?"] if close else []
        raise Precondition(f"{name!r} can't be set on {screen}.", *hint)
    return matches[0]


def _value(about: dict, values: list[str], jira: api.Jira, space: str):
    """The field's value for values, as Jira's JSON has it, or None to clear it."""
    schema = about.get("schema", {})
    kind = schema.get("type")
    name = about.get("name", "")
    if not values:
        return None
    if schema.get("custom") == SPRINT:
        return _sprint(_one(name, values), jira, space)
    if kind == "array":
        if schema.get("items") not in LISTED:
            raise _unsettable(name, f"array of {schema.get('items')}")
        items = [_item(about, schema["items"], value, jira, space) for value in values]
        # A list of people is cleared by giving it no one, not none.
        return [item for item in items if item is not None] or None
    return _item(about, kind, _one(name, values), jira, space)


def _item(about: dict, kind: str | None, value: str, jira: api.Jira, space: str):
    """The value of one of kind, as Jira's JSON has it."""
    schema = about.get("schema", {})
    name = about.get("name", "")
    match kind:
        case "string" if schema.get("custom") == CUSTOM + "textarea":
            return adf.from_markdown(value)
        case "string" if schema.get("system") in RICH_TEXT_SYSTEM:
            return adf.from_markdown(value)
        case "string":
            return value
        case "number":
            return _number(name, value)
        case "date":
            return choices.date(value, name)
        case "datetime":
            return _datetime(name, value)
        case "user":
            user = people.person(jira, value)
            return None if user is None else {"accountId": user.account_id}
        case "timetracking":
            return {"originalEstimate": durations.duration(value)}
        case kind if kind in CHOSEN:
            return _chosen(about, CHOSEN[kind], value)
    raise _unsettable(name, kind)


def _one(name: str, values: list[str]) -> str:
    if len(values) > 1:
        raise Precondition(f"{name} takes one value, and was given {len(values)}.")
    return values[0]


def _number(name: str, value: str) -> int | float:
    try:
        number = float(value)
    except ValueError:
        raise Precondition(f"{name} takes a number, not {value!r}.") from None
    return int(number) if number.is_integer() else number


def _datetime(name: str, value: str) -> str:
    """value, a date and time, in ISO 8601 with or without its offset, as Jira writes one: with
    its offset, the local one when it has none."""
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        raise Precondition(
            f"{name} takes a date and time, such as 2026-10-20T14:30, not {value!r}."
        ) from None
    when = when.astimezone() if when.tzinfo is None else when
    return when.strftime("%Y-%m-%dT%H:%M:%S.000%z")


def _chosen(about: dict, key: str, value: str) -> dict:
    """The one of the field's allowed values that value names, by its key, ignoring case, or its
    id; or value by key, when meta gives no allowed values."""
    allowed = about.get("allowedValues")
    if allowed is None:
        return {key: value}
    for choice in allowed:
        if value.casefold() == str(choice.get(key, "")).casefold() or value == choice.get("id"):
            return {"id": choice["id"]}
    raise Precondition(
        f"{about.get('name', '')} can't be {value!r}.",
        f"It can be: {', '.join(str(choice.get(key)) for choice in allowed)}.",
    )


def _sprint(value: str, jira: api.Jira, space: str) -> int:
    """The id of the sprint value names: by its id, or by its name, ignoring case, among the
    space's active and future sprints."""
    if value.isdigit():
        return int(value)
    sprints = {sprint["id"]: sprint for sprint in jira.sprints(space)}
    matches = [s["id"] for s in sprints.values() if s["name"].casefold() == value.casefold()]
    if len(matches) > 1:
        raise Precondition(
            f"More than one sprint is named {value!r}: {', '.join(map(str, matches))}.",
            "Name it by its id instead.",
        )
    if not matches:
        named = ", ".join(f"{s['name']} ({s['id']})" for s in sprints.values())
        raise Precondition(
            f"{space} has no active or future sprint named {value!r}.",
            *([f"It has: {named}."] if named else []),
        )
    return matches[0]


def _unsettable(name: str, kind: str | None) -> Precondition:
    return Precondition(f"{name} is a field of type {kind}, which jira can't set.")


def _same(sent, current) -> bool:
    """Whether sent, a field's value as it would be sent, is already current, its value as an
    issue gives it: with more in it, such as an option's name as well as its id."""
    if isinstance(sent, dict) and sent.get("type") == "doc":
        return isinstance(current, dict) and adf.to_markdown(sent) == adf.to_markdown(current)
    if isinstance(sent, dict):
        return isinstance(current, dict) and all(_same(v, current.get(k)) for k, v in sent.items())
    if isinstance(sent, list):
        return (
            isinstance(current, list)
            and len(sent) == len(current)
            and all(any(_same(s, c) for c in current) for s in sent)
        )
    if isinstance(sent, int | float) and isinstance(current, list):
        # A sprint is sent as its id, and an issue has its sprints.
        return any(isinstance(s, dict) and s.get("id") == sent for s in current)
    if isinstance(sent, int | float):
        return isinstance(current, int | float) and float(sent) == float(current)
    if sent == current:
        return True
    return _instant(sent) is not None and _instant(sent) == _instant(current)


def _same_estimate(sent: dict, current: dict | None, units: dict[str, int]) -> bool:
    """Whether sent, an original estimate as it would be sent, is current's, an issue's time
    tracking, in seconds by units."""
    seconds = (current or {}).get("originalEstimateSeconds")
    return seconds is not None and durations.seconds(sent["originalEstimate"], units) == seconds


def _instant(value) -> datetime | None:
    """value as an instant, for a date and time with its offset, or None."""
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    return when if when.tzinfo else None


def _empty(value) -> bool:
    return value is None or value in ("", [], {})
