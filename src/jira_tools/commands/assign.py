"""jira assign <key> [<who>]

Assigns the issue to who: me, the default; none, to unassign it; or someone else, by their name
or email. Someone else must match one person in Jira, or among several, one whose name or email
is exactly who. An issue already assigned so is left alone.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo

from jira_tools import config, keys, people, session


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "assign",
        help="assign an issue to you, to someone else, or to no one",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument(
        "who", nargs="?", default="me", help="me (the default), none, or a name or email"
    )
    parser.set_defaults(run=lambda args: assign(args.key, args.who))


def assign(key: str, who: str = "me") -> Done | NothingToDo:
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    jira = session.connect(settings)
    current = (session.fetch(jira, key)["fields"].get("assignee") or {}).get("accountId")

    person = people.person(jira, who.strip())
    if person is None:
        if current is None:
            return NothingToDo(f"{key} is already unassigned.")
        jira.assign(key, None)
        return Done(f"Unassigned {key}.", jira.issue_link(key).url)

    name = "you" if who.strip().casefold() == "me" else person.name
    if current == person.account_id:
        return NothingToDo(f"{key} is already assigned to {name}.")
    jira.assign(key, person.account_id)
    return Done(f"Assigned {key} to {name}.", jira.issue_link(key).url)
