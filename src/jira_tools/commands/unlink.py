"""jira unlink <key> <relation> <other>

Removes the link that reads, from the issue, relation the other one, such as "is blocked by",
from both issues. It's matched as jira link matches it. Issues not linked so are left alone.

<key> and <other> are each an issue's key, such as WEB-12, its number alone for one in the set
space, or its URL.
"""

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo

from jira_tools.commands.link import existing, linking, relation_named


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "unlink",
        help='remove a link between two issues, such as "is blocked by"',
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("relation", help='how it relates to the other, such as "is blocked by"')
    parser.add_argument("other", help="the other issue's key")
    parser.set_defaults(run=lambda args: unlink(args.key, args.relation, args.other))


def unlink(key: str, relation: str, other: str) -> Done | NothingToDo:
    jira, key, other, fields = linking(key, other)
    found = relation_named(jira, relation)
    stated = f"{key} {found.reads} {other}"
    link = existing(fields, found, other)
    if link is None:
        return NothingToDo(f"Not linked: {stated}.")
    jira.unlink(link["id"])
    return Done(f"Unlinked: {stated}.", jira.issue_link(key).url)
