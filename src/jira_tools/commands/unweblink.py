"""jira unweblink <key> <url>

Removes the issue's web links to the URL, every one there is. An issue without one is left
alone.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo

from jira_tools.commands.weblink import web_links_to


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "unweblink",
        help="remove an issue's link to a web page",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("url", help="the page's URL")
    parser.set_defaults(run=lambda args: unweblink(args.key, args.url))


def unweblink(key: str, url: str) -> Done | NothingToDo:
    url = url.strip()
    jira, key, found = web_links_to(key, url)
    if not found:
        return NothingToDo(f"{key} has no link to {url}.")
    for link in found:
        jira.remove_web_link(key, link["id"])
    links = "link" if len(found) == 1 else f"{len(found)} links"
    return Done(f"Removed {key}'s {links} to {url}.", jira.issue_link(key).url)
