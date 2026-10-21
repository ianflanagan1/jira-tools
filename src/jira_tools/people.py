"""Naming a person on the command line: me, none, or someone in Jira by their name or email."""

from cli_kit.outcome import Precondition

from jira_tools import api


def person(jira: api.Jira, who: str) -> api.User | None:
    """The person who names: you for me, no one for none, or the one person in Jira that
    matches. Raises Precondition when no one does, or more than one."""
    match who.casefold():
        case "me":
            return jira.myself()
        case "none":
            return None
    matches = jira.find_users(who)
    exact = [
        p for p in matches if who.casefold() in (p.name.casefold(), (p.email or "").casefold())
    ]
    if len(matches) == 1:
        return matches[0]
    if len(exact) == 1:
        return exact[0]
    if not matches:
        raise Precondition(f"No one in Jira matches {who!r}.")
    names = ", ".join(p.name for p in matches)
    raise Precondition(
        f"More than one person matches {who!r}: {names}.",
        "Give more of their name, or their email.",
    )
