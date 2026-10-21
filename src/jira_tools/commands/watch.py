"""jira watch <key> [<who>]

Adds who to the issue's watchers, whom Jira tells of its changes: me, the default, or someone
else, by their name or email, matched as jira assign matches them. Someone already watching it is
left alone.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

from dataclasses import dataclass

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import api, config, keys, people, session


@dataclass(frozen=True)
class Watching:
    """The issue, the person named, and whether they're among its watchers."""

    jira: api.Jira
    key: str
    person: api.User
    you: bool
    watches: bool

    @property
    def is_(self) -> str:
        """The person and is, to begin a sentence: You're, or Alice Smith is."""
        return "You're" if self.you else f"{self.person.name} is"


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "watch",
        help="add you, or someone else, to an issue's watchers",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("who", nargs="?", default="me", help="me (the default), or a name or email")
    parser.set_defaults(run=lambda args: watch(args.key, args.who))


def watch(key: str, who: str = "me") -> Done | NothingToDo:
    found = watching(key, who)
    if found.watches:
        return NothingToDo(f"{found.is_} already watching {found.key}.")
    found.jira.watch(found.key, found.person.account_id)
    return Done(f"{found.is_} watching {found.key}.", found.jira.issue_link(found.key).url)


def watching(key: str, who: str) -> Watching:
    """The issue with key and the person who names, me or a name or email. Raises Precondition
    when there's no such issue, or who names no one."""
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    jira = session.connect(settings)
    person = people.person(jira, who.strip())
    if person is None:
        raise Precondition(
            "None isn't a person.", "Name me, the default, or someone by their name or email."
        )
    watchers = jira.watchers(key)
    if watchers is None:
        raise session.missing(key)
    you = who.strip().casefold() == "me"
    if you:
        return Watching(jira, key, person, you, watchers.you)
    if watchers.ids is None:
        raise Precondition(
            f"Jira won't say who watches {key}.",
            "Your account isn't allowed to see an issue's watchers, only whether you watch it.",
        )
    return Watching(jira, key, person, you, person.account_id in watchers.ids)
