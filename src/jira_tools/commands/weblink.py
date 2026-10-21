"""jira weblink <key> <url> [<title>]

Links the issue to a web page, such as a pull request or a document, titled <title>, or by its
URL when there's none. Jira calls these remote links, and lists them apart from linked issues.
A URL the issue already links to keeps that link: with the same title it's left alone, and with
another it's retitled.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

import urllib.parse

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import api, config, keys, session


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "weblink",
        help="link an issue to a web page, such as a pull request",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("url", help="the page's URL, http or https")
    parser.add_argument("title", nargs="?", help="what the link reads; the URL unless given")
    parser.set_defaults(run=lambda args: weblink(args.key, args.url, args.title))


def weblink(key: str, url: str, title: str | None = None) -> Done | NothingToDo:
    url = url.strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        raise Precondition(
            f"{url!r} isn't a web address.", "Give one starting http:// or https://."
        )
    title = title or url
    jira, key, found = web_links_to(key, url)
    if any(link["object"].get("title") == title for link in found):
        return NothingToDo(f"{key} already links to {url}.")
    if found:
        jira.retitle_web_link(key, found[0], title)
        return Done(f"Retitled {key}'s link to {url}: {title}.", jira.issue_link(key).url)
    jira.add_web_link(key, url, title)
    return Done(f"Linked {key} to {url}.", jira.issue_link(key).url)


def web_links_to(key: str, url: str) -> tuple[api.Jira, str, list[dict]]:
    """The site, the issue's key, and its web links to url. Raises Precondition when the issue
    isn't there."""
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    jira = session.connect(settings)
    session.fetch(jira, key)
    return (
        jira,
        key,
        [link for link in jira.web_links(key) or [] if link["object"].get("url") == url],
    )
