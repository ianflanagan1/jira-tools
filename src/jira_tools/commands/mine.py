"""jira mine [--space <key>]

Lists the open issues assigned to you in the set space, or the one given, grouped by status:
those in progress first, then those to do. Within each, the most recently updated come first.
"""

from cli_kit import cli
from cli_kit.outcome import NothingToDo

from jira_tools import config, session

# The status categories open issues are in, in the order they're listed.
CATEGORIES = ["indeterminate", "new"]


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "mine",
        help="list the open issues assigned to you",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("--space", help="the space's key, instead of the set one")
    parser.set_defaults(run=lambda args: mine(space=args.space))


def mine(*, space: str | None = None) -> NothingToDo:
    settings = config.load()
    space = space or settings.space
    issues = session.connect(settings).open_assigned_to_me(space)
    if not issues:
        return NothingToDo(f"No open issues assigned to you in {space}.")

    groups: dict[str, list[dict]] = {}
    for issue in issues:
        groups.setdefault(issue["fields"]["status"]["name"], []).append(issue)

    def rank(status: str) -> int:
        category = groups[status][0]["fields"]["status"]["statusCategory"]["key"]
        return CATEGORIES.index(category) if category in CATEGORIES else len(CATEGORIES)

    key_width = max(len(issue["key"]) for issue in issues)
    type_width = max(len(issue["fields"]["issuetype"]["name"]) for issue in issues)
    for status in sorted(groups, key=rank):
        print(status)
        for issue in groups[status]:
            fields = issue["fields"]
            kind = fields["issuetype"]["name"]
            print(f"  {issue['key']:<{key_width}}  {kind:<{type_width}}  {fields['summary']}")
    count = f"{len(issues)} open issue{'' if len(issues) == 1 else 's'}"
    return NothingToDo(f"{count} assigned to you in {space}.")
