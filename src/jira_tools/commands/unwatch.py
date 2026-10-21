"""jira unwatch <key> [<who>]

Removes who from the issue's watchers: me, the default, or someone else, by their name or email,
matched as jira assign matches them. Someone not watching it is left alone.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo

from jira_tools.commands.watch import watching


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "unwatch",
        help="remove you, or someone else, from an issue's watchers",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("who", nargs="?", default="me", help="me (the default), or a name or email")
    parser.set_defaults(run=lambda args: unwatch(args.key, args.who))


def unwatch(key: str, who: str = "me") -> Done | NothingToDo:
    found = watching(key, who)
    if not found.watches:
        isnt = "You aren't" if found.you else f"{found.person.name} isn't"
        return NothingToDo(f"{isnt} watching {found.key}.")
    found.jira.unwatch(found.key, found.person.account_id)
    return Done(
        f"{found.is_} no longer watching {found.key}.", found.jira.issue_link(found.key).url
    )
