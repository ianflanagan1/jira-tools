"""jira move <key> <status> [--resolution <name>] [--field <name>=<value>]...
          [--field-file <name>=<path>]...

Moves the issue to status, such as "In Review", by the move its workflow has from its status
to that one. The status is matched ignoring case. An issue already there is left alone.

Some moves have a screen of fields to fill in, such as the resolution on a move to Done. When one
it needs isn't given, it stops before changing anything and says which, with the values each can
take. --resolution gives the resolution, matched ignoring case, and --field and --field-file any
other field on the move's screen, as jira edit takes them. The Markdown on stdin, if any, is
added as a comment as it moves.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

import sys
from typing import TextIO

from cli_kit import cli, outcome
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf, api, config, keys, session
from jira_tools import fields as named

# What fills in each field a move can ask for.
HINTS = {
    "resolution": "Give the resolution with --resolution <name>.",
    "comment": "Give the comment as Markdown on stdin.",
}


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "move",
        help="move an issue to a status, such as In Review",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("status", help="the status to move it to")
    parser.add_argument("--resolution", help="the resolution to set, such as Done")
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        dest="fields",
        metavar="name=value",
        help="another field the move asks for; repeatable",
    )
    parser.add_argument(
        "--field-file",
        action="append",
        default=[],
        dest="files",
        metavar="name=path",
        help="a field, its value read from a file; repeatable",
    )
    parser.set_defaults(
        run=lambda args: move(
            args.key,
            args.status,
            resolution=args.resolution,
            fields=args.fields,
            files=args.files,
        )
    )


def move(
    key: str,
    status: str,
    *,
    resolution: str | None = None,
    fields: list[str] | None = None,
    files: list[str] | None = None,
    stdin: TextIO | None = None,
) -> Done | NothingToDo:
    given_fields = named.given(fields or [], files or [], None)
    stdin = stdin or sys.stdin
    markdown = "" if stdin.isatty() else stdin.read().strip()
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    jira = session.connect(settings)
    issue = session.fetch(jira, key)["fields"]
    current = issue["status"]["name"]
    transition = transition_to(jira, key, current, status)
    if transition is None:
        return NothingToDo(f"{key} is already {current}.")

    screen = f"the move to {transition.status}"
    changes = named.convert(
        transition.fields, given_fields, jira, space=settings.space, screen=screen
    )
    sent = changes.json()
    if resolution is not None:
        if "resolution" in sent:
            name = transition.fields["resolution"].get("name", "Resolution")
            raise Precondition(f"--resolution and --field both set {name}.", "Give it once.")
        sent["resolution"] = {"name": _resolution(key, transition, resolution)}
    comment = adf.from_markdown(markdown) if markdown else None
    given = set(sent) | ({"comment"} if comment else set())
    if needs := fields_needed(key, transition, given, issue):
        raise needs

    # Jira takes a comment with a move only when the move's screen has it, so without one the
    # comment is added after moving.
    with_move = comment is not None and "comment" in transition.fields
    update = {"comment": [{"add": {"body": comment}}]} if with_move else None
    jira.transition(key, transition, sent, update)
    moved = f"Moved {key} to {transition.status}"
    if comment is None:
        return Done(f"{moved}.", jira.issue_link(key).url)
    if with_move:
        return Done(f"{moved}, with the comment.", jira.issue_link(key).url)
    outcome.changed(f"{moved}.")
    return Done(f"Commented on {key}.", jira.add_comment(key, comment))


def transition_to(jira: api.Jira, key: str, current: str, status: str) -> api.Transition | None:
    """The move from current, the issue's status, to status, matched ignoring case; None when
    it's already there. Raises Precondition when its workflow has no such move."""
    wanted = status.strip().casefold()
    if current.casefold() == wanted:
        return None
    transitions = jira.transitions(key)
    if found := next((t for t in transitions if t.status.casefold() == wanted), None):
        return found
    # A workflow that lets every status move to every other offers a move to current too.
    reachable = [t.status for t in transitions if t.status.casefold() != current.casefold()]
    if reachable:
        detail = f"From {current} it can move to: {', '.join(dict.fromkeys(reachable))}."
    else:
        detail = f"Its workflow has no moves from {current}."
    raise Precondition(f"{key} can't move from {current} to {status.strip()}.", detail)


def fields_needed(
    key: str, transition: api.Transition, given: set[str], issue: dict
) -> Precondition | None:
    """The Precondition that stops a move whose screen requires fields that aren't given, have
    no default value and the issue, its fields issue, has no value for, naming them with the
    values each can take and how to fill them in; None when it needs none."""
    missing = {
        field: meta
        for field, meta in transition.fields.items()
        if meta.get("required")
        and not meta.get("hasDefaultValue")
        and field not in given
        # The issue's comment field holds its comments; a move needs a new one.
        and (field == "comment" or not issue.get(field))
    }
    if not missing:
        return None
    named = "; ".join(_named(meta) for meta in missing.values())
    hints = [
        HINTS.get(field)
        or f"Give {meta.get('name', field)} with --field '{meta.get('name', field)}=<value>'."
        for field, meta in missing.items()
    ]
    return Precondition(f"Moving {key} to {transition.status} needs: {named}.", *hints)


def check_no_fields_needed(key: str, transition: api.Transition, issue: dict, command: str) -> None:
    """For command, which moves issues without filling in fields: raises Precondition when the
    move needs some, saying to make it with jira move and run command again."""
    if needs := fields_needed(key, transition, set(), issue):
        again = (
            f"Move it with jira move {key} '{transition.status}' and its options, then run"
            f" {command} again."
        )
        raise Precondition(needs.message, again, *needs.details)


def _resolution(key: str, transition: api.Transition, name: str) -> str:
    """The resolution the move allows that's name, ignoring case, as Jira names it. Raises
    Precondition when the move doesn't take a resolution, or not that one."""
    field = transition.fields.get("resolution")
    if field is None:
        raise Precondition(
            f"Moving {key} to {transition.status} can't set a resolution.",
            "Its workflow doesn't ask for one on that move.",
        )
    allowed = _allowed(field)
    wanted = name.strip().casefold()
    if found := next((value for value in allowed if value.casefold() == wanted), None):
        return found
    raise Precondition(
        f"Moving {key} to {transition.status} can't resolve it as {name.strip()}.",
        f"It can be resolved as: {', '.join(allowed)}.",
    )


def _named(field: dict) -> str:
    """A field a move needs, with the values it can take when Jira lists them."""
    allowed = _allowed(field)
    return f"{field.get('name')} ({', '.join(allowed)})" if allowed else field.get("name", "")


def _allowed(field: dict) -> list[str]:
    """The names of the values field can take: a resolution's or a version's name, or an
    option's value."""
    values = (value.get("name") or value.get("value") for value in field.get("allowedValues") or [])
    return [value for value in values if value]
