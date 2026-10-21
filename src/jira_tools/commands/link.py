"""jira link <key> <relation> <other>

Links the issue to the other one by relation, as Jira reads links from the issue: such as
"is blocked by", "blocks", "relates to", "duplicates" or "is cloned by". The relation is matched
ignoring case against how each of the site's link types reads both ways. Issues already linked
so are left alone.

<key> and <other> are each an issue's key, such as WEB-12, its number alone for one in the set
space, or its URL.
"""

from dataclasses import dataclass

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import api, config, keys, session


@dataclass(frozen=True)
class Relation:
    """How a link type reads from one of its issues: outward, as the issue that blocks, or
    inward, as the one that is blocked."""

    type: api.LinkType
    outward: bool

    @property
    def reads(self) -> str:
        return self.type.outward if self.outward else self.type.inward


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "link",
        help='link an issue to another, such as "is blocked by" it',
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("relation", help='how it relates to the other, such as "is blocked by"')
    parser.add_argument("other", help="the other issue's key")
    parser.set_defaults(run=lambda args: link(args.key, args.relation, args.other))


def link(key: str, relation: str, other: str) -> Done | NothingToDo:
    jira, key, other, fields = linking(key, other)
    found = relation_named(jira, relation)
    stated = f"{key} {found.reads} {other}"
    if existing(fields, found, other) is not None:
        return NothingToDo(f"Already linked: {stated}.")
    add(jira, key, found, other)
    return Done(f"Linked: {stated}.", jira.issue_link(key).url)


def add(jira: api.Jira, key: str, relation: Relation, other: str) -> None:
    """Links the issue with key to other, so that it reads relation other."""
    inward, outward = (key, other) if relation.outward else (other, key)
    jira.link(relation.type.name, inward, outward)


def linking(key: str, other: str) -> tuple[api.Jira, str, str, dict]:
    """The site, the two issues' keys, and the first one's fields. Raises Precondition when
    they're the same issue or either isn't there."""
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    other = keys.issue_key(other, settings.space)
    if key == other:
        raise Precondition(f"{key} can't be linked to itself.")
    jira = session.connect(settings)
    fields = session.fetch(jira, key)["fields"]
    session.fetch(jira, other)
    return jira, key, other, fields


def relation_named(jira: api.Jira, relation: str) -> Relation:
    """The relation that reads as relation, ignoring case. Raises Precondition when no link
    type reads so, or more than one does."""
    wanted = relation.strip().casefold()
    types = jira.link_types()
    found = [
        Relation(t, outward=t.outward.casefold() == wanted)
        for t in types
        if wanted in (t.outward.casefold(), t.inward.casefold())
    ]
    if len(found) == 1:
        return found[0]
    if found:
        names = ", ".join(r.type.name for r in found)
        raise Precondition(f"More than one link type reads {relation.strip()!r}: {names}.")
    known = dict.fromkeys(reads for t in types for reads in (t.outward, t.inward))
    raise Precondition(
        f"Jira has no relation {relation.strip()!r}.", f"It has: {', '.join(known)}."
    )


def existing(fields: dict, relation: Relation, other: str) -> dict | None:
    """The link among an issue's fields that reads relation other, or None. A link type that
    reads the same both ways matches from either side."""
    sides = {"outwardIssue" if relation.outward else "inwardIssue"}
    if relation.type.inward.casefold() == relation.type.outward.casefold():
        sides = {"outwardIssue", "inwardIssue"}
    for found in fields.get("issuelinks") or []:
        if found["type"]["id"] != relation.type.id:
            continue
        if any(found.get(side, {}).get("key") == other for side in sides):
            return found
    return None
