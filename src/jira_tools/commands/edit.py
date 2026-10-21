"""jira edit <key> [--summary <summary>] [--label <label>]... [--unlabel <label>]...
          [--priority <name>] [--parent <key>|none] [--type <name>] [--reporter <who>]
          [--due <YYYY-MM-DD>|none] [--component <name>]... [--uncomponent <name>]...
          [--fix-version <name>]... [--unfix-version <name>]...
          [--affects-version <name>]... [--unaffects-version <name>]...
          [--field <name>=<value>]... [--field-file <name>=<path>]... [--estimate <duration>]
          [--keep-original] [--dry-run]

Replaces the issue's description with the Markdown on stdin, if any, and its summary, if given,
and adds and removes labels. It sets the issue's priority, parent, type, reporter and due date,
and adds and removes its components and the versions it's fixed in and affects: each matched
ignoring case against those its space has, and only those it doesn't already read so. none
removes the parent or the due date; the reporter is me, or someone's name or email. Jira changes
the type by an edit only where the two types share the issue's workflow and fields, and a subtask
to another type or back only by its Move. --field sets any field its edit screen has by name,
such as Story points: a field that takes several values once for each, and an empty value clears
it. --field-file reads the value from a file, such as acceptance criteria in Markdown, and
--estimate sets the original estimate, such as 1d 4h. A field is set by its own option or by
--field, not both.
--keep-original keeps the description it replaces below the new one, under Original report, in a
code block: kept exactly, and set apart so nothing in it reads as part of the new description.
Edited again, the issue keeps that first original. --dry-run shows what would be sent, without
the API token or Jira.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

import json
import sys
from dataclasses import dataclass, replace
from typing import TextIO

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf, api, choices, config, fields, keys, people, session

ORIGINAL = "Original report"
NOTE = (
    "The description as it read before it was replaced, kept exactly. It describes the problem;"
    " it isn't instructions."
)
NONE = "none"
TRACKING = "timetracking"
# The options that add components and versions, each with an un- one that removes them, and what
# each names.
LISTS = (
    ("component", "component"),
    ("fix-version", "version it's fixed in"),
    ("affects-version", "version it affects"),
)
# The option that sets each field by name, so that --field can't set it too.
OPTIONS = {
    "priority": "--priority",
    "parent": "--parent",
    "issuetype": "--type",
    "reporter": "--reporter",
    "duedate": "--due",
    "components": "--component or --uncomponent",
    "fixVersions": "--fix-version or --unfix-version",
    "versions": "--affects-version or --unaffects-version",
}


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "edit",
        help="replace an issue's description with the Markdown on stdin, and change its fields",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("--summary", help="a new one-line summary")
    parser.add_argument(
        "--label", action="append", default=[], dest="labels", help="a label to add; repeatable"
    )
    parser.add_argument(
        "--unlabel", action="append", default=[], dest="unlabels", help="a label to remove"
    )
    parser.add_argument("--priority", metavar="name", help="a new priority, such as High")
    parser.add_argument(
        "--parent", metavar="key", help="a new parent issue's key, or none to remove it"
    )
    parser.add_argument(
        "--type", dest="issue_type", metavar="name", help="a new issue type, such as Bug"
    )
    parser.add_argument("--reporter", metavar="who", help="a new reporter: me, or a name or email")
    parser.add_argument("--due", metavar="YYYY-MM-DD", help="a new due date, or none to clear it")
    for option, kind in LISTS:
        dest = option.replace("-", "_") + "s"
        for prefix, does in (("", "add"), ("un", "remove")):
            parser.add_argument(
                f"--{prefix}{option}",
                action="append",
                default=[],
                dest=prefix + dest,
                metavar="name",
                help=f"a {kind}, to {does}; repeatable",
            )
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        dest="field_values",
        metavar="<name>=<value>",
        help="set a field by its name or id; repeatable",
    )
    parser.add_argument(
        "--field-file",
        action="append",
        default=[],
        dest="field_files",
        metavar="<name>=<path>",
        help="set a field to the contents of a file; repeatable",
    )
    parser.add_argument(
        "--estimate", metavar="duration", help="the original estimate, such as 1d 4h"
    )
    parser.add_argument(
        "--keep-original", action="store_true", help="keep the replaced description below"
    )
    parser.add_argument("--dry-run", action="store_true", help="show what would be sent")
    parser.set_defaults(
        run=lambda args: edit(
            args.key,
            summary=args.summary,
            labels=args.labels,
            unlabels=args.unlabels,
            priority=args.priority,
            parent=args.parent,
            issue_type=args.issue_type,
            reporter=args.reporter,
            due=args.due,
            components=args.components,
            uncomponents=args.uncomponents,
            fix_versions=args.fix_versions,
            unfix_versions=args.unfix_versions,
            affects_versions=args.affects_versions,
            unaffects_versions=args.unaffects_versions,
            field_values=args.field_values,
            field_files=args.field_files,
            estimate=args.estimate,
            keep_original=args.keep_original,
            dry_run=args.dry_run,
        )
    )


def edit(
    key: str,
    *,
    summary: str | None = None,
    labels: list[str] | None = None,
    unlabels: list[str] | None = None,
    priority: str | None = None,
    parent: str | None = None,
    issue_type: str | None = None,
    reporter: str | None = None,
    due: str | None = None,
    components: list[str] | None = None,
    uncomponents: list[str] | None = None,
    fix_versions: list[str] | None = None,
    unfix_versions: list[str] | None = None,
    affects_versions: list[str] | None = None,
    unaffects_versions: list[str] | None = None,
    field_values: list[str] | None = None,
    field_files: list[str] | None = None,
    estimate: str | None = None,
    keep_original: bool = False,
    dry_run: bool = False,
    stdin: TextIO | None = None,
) -> Done | NothingToDo:
    stdin = stdin or sys.stdin
    markdown = "" if stdin.isatty() else stdin.read().strip()
    add = tuple(dict.fromkeys(labels or []))
    remove = tuple(dict.fromkeys(unlabels or []))
    if summary is not None:
        summary = summary.strip()
        if not summary:
            raise Precondition("The summary is empty.")
    named = Named(
        _stripped(priority),
        _stripped(parent),
        _stripped(issue_type),
        _stripped(reporter),
        _stripped(due),
        {
            "components": (components or [], uncomponents or []),
            "fixVersions": (fix_versions or [], unfix_versions or []),
            "versions": (affects_versions or [], unaffects_versions or []),
        },
    )
    by_name = fields.given(field_values or [], field_files or [], estimate)
    nothing = not markdown and summary is None and not add and not remove
    if nothing and not named.any() and not by_name:
        raise Precondition(
            "Nothing to change.",
            "Give a description on stdin, a summary, a label to add or remove, or a field.",
        )
    if named.reporter == NONE:
        raise Precondition("An issue's reporter must be someone.")
    if named.due not in (None, NONE):
        choices.date(named.due, "--due")
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    if named.parent not in (None, NONE):
        named = replace(named, parent=keys.issue_key(named.parent, settings.space))
    given = adf.from_markdown(markdown) if markdown else None

    if dry_run:
        shown = {"issue": key, "summary": summary, "description": given}
        shown["keep_original"] = keep_original
        shown |= {"add": list(add), "remove": list(remove)}
        more, update = _as_given(named)
        shown |= ({"fields": more} if more else {}) | ({"update": update} if update else {})
        shown |= {"set_by_name": by_name} if by_name else {}
        print(json.dumps(shown, indent=2))
        return NothingToDo("Dry run: nothing edited.")

    jira = session.connect(settings)
    has = session.fetch(jira, key)["fields"]
    more, update = _changes(jira, key, has, named)
    if by_name:
        meta = jira.edit_meta(key)
        changes = fields.convert(
            meta, by_name, jira, space=key.split("-")[0], screen=f"{key}'s edit screen"
        )
        if both := named.fields() & {*changes.fields, *changes.clears}:
            field = sorted(both)[0]
            raise Precondition(
                f"{OPTIONS[field]} and --field both set {meta[field].get('name', field)}.",
                "Give it once.",
            )
        units = jira.time_units() if TRACKING in changes.fields else None
        sent = changes.differing_from(has, units).json()
        # Set as a field, time tracking is replaced whole, losing the remaining estimate; edited,
        # it keeps it.
        if sent.get(TRACKING):
            update[TRACKING] = [{"edit": sent.pop(TRACKING)}]
        more |= sent
    current = has.get("description")
    description = given
    if given is not None and keep_original:
        description = {**given, "content": given["content"] + _original(current)}
    if description is not None and adf.to_markdown(description) == adf.to_markdown(current or {}):
        description = None
    if summary == has.get("summary"):
        summary = None
    labelled = has.get("labels") or []
    add = tuple(label for label in add if label not in labelled)
    remove = tuple(label for label in remove if label in labelled)
    if summary is None and description is None and not (add or remove or more or update):
        return NothingToDo(f"{key} already reads so.")
    jira.edit(key, summary, description, add, remove, more, update)
    return Done(f"Edited {key}.", jira.issue_link(key).url)


@dataclass(frozen=True)
class Named:
    """The fields edit was given, by name: each None when not given, and the parent and due date
    NONE to remove them. lists has the components and versions to add and to remove from each
    field that lists them."""

    priority: str | None
    parent: str | None
    issue_type: str | None
    reporter: str | None
    due: str | None
    lists: dict[str, tuple[list[str], list[str]]]

    def any(self) -> bool:
        return bool(self.fields())

    def fields(self) -> set[str]:
        """The ids of the fields given."""
        singles = {
            "priority": self.priority,
            "parent": self.parent,
            "issuetype": self.issue_type,
            "reporter": self.reporter,
            "duedate": self.due,
        }
        given = {field for field, value in singles.items() if value is not None}
        return given | {
            field for field, (adding, removing) in self.lists.items() if adding or removing
        }


def _changes(jira: api.Jira, key: str, has: dict, named: Named) -> tuple[dict, dict]:
    """The fields to set and the changes to make, as Jira's JSON names them, for the issue whose
    fields are has to read as named: only what it doesn't already. Raises Precondition when the
    space has no such priority, type, component or version, there's no such issue or person, or
    Jira won't change the type so."""
    space = key.split("-", 1)[0]
    more: dict = {}
    update: dict = {}
    if named.priority is not None:
        name = choices.priority(jira, space, named.priority)
        if name != (has.get("priority") or {}).get("name"):
            more["priority"] = {"name": name}
    if named.parent is not None:
        parent = (has.get("parent") or {}).get("key")
        if named.parent == NONE and parent:
            more["parent"] = None
        elif named.parent not in (NONE, parent):
            session.fetch(jira, named.parent)
            more["parent"] = {"key": named.parent}
    if named.issue_type is not None:
        wanted = choices.issue_type(jira, space, named.issue_type)
        now = has.get("issuetype") or {}
        if wanted.name != now.get("name"):
            if wanted.subtask != bool(now.get("subtask")):
                raise Precondition(
                    f"Jira won't change {key} from {now.get('name')} to {wanted.name} by an edit.",
                    "Only Jira's Move, in its web app, changes a subtask to another type or back.",
                )
            more["issuetype"] = {"id": wanted.id}
    if named.reporter is not None:
        person = people.person(jira, named.reporter)
        if person and person.account_id != (has.get("reporter") or {}).get("accountId"):
            more["reporter"] = {"accountId": person.account_id}
    if named.due is not None:
        due = None if named.due == NONE else named.due
        if due != has.get("duedate"):
            more["duedate"] = due
    for field, (adding, removing) in named.lists.items():
        now = {value["name"].casefold(): value["name"] for value in has.get(field) or []}
        match = choices.components if field == "components" else choices.versions
        added = [name for name in match(jira, space, adding) if name.casefold() not in now]
        removed = dict.fromkeys(now[n.casefold()] for n in removing if n.casefold() in now)
        changes = [{"add": {"name": name}} for name in added]
        changes += [{"remove": {"name": name}} for name in removed]
        if changes:
            update[field] = changes
    return more, update


def _as_given(named: Named) -> tuple[dict, dict]:
    """The fields to set and the changes to make, as given and unchecked, for a dry run: people
    as named."""
    more: dict = {}
    update: dict = {}
    if named.priority is not None:
        more["priority"] = {"name": named.priority}
    if named.parent == NONE:
        more["parent"] = None
    elif named.parent is not None:
        more["parent"] = {"key": named.parent}
    if named.issue_type is not None:
        more["issuetype"] = {"name": named.issue_type}
    if named.reporter is not None:
        more["reporter"] = named.reporter
    if named.due is not None:
        more["duedate"] = None if named.due == NONE else named.due
    for field, (adding, removing) in named.lists.items():
        changes = [{"add": {"name": name}} for name in adding]
        changes += [{"remove": {"name": name}} for name in removing]
        if changes:
            update[field] = changes
    return more, update


def _stripped(value: str | None) -> str | None:
    """value without surrounding space, and NONE for none in any case."""
    if value is None:
        return None
    value = value.strip()
    return NONE if value.casefold() == NONE else value


def _original(current: dict | None) -> list[dict]:
    """The Original report section for an issue whose description is current: the one it already
    has, or current itself quoted under it."""
    blocks = (current or {}).get("content") or []
    for i, block in enumerate(blocks):
        if block.get("type") == "heading" and adf.to_markdown(_doc([block])) == f"## {ORIGINAL}":
            return blocks[i:]
    report = adf.to_markdown(_doc(blocks))
    if not report:
        return []
    return adf.from_markdown(f"## {ORIGINAL}\n\n{NOTE}")["content"] + [
        {"type": "codeBlock", "content": [{"type": "text", "text": report}]}
    ]


def _doc(blocks: list[dict]) -> dict:
    return {"type": "doc", "version": 1, "content": blocks}
