"""jira view <key>

Prints the issue as Markdown: its summary, type, status, resolution, people, labels, dates and
time; its description and any other rich-text fields, such as acceptance criteria; any other
custom field that's set, such as story points; its parent, subtasks and linked issues; its web
links; its attachments; and its comments, oldest first, each with its id. It's all someone needs
to work on the issue, so it's also what to give Claude to work on it.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

from cli_kit import cli
from cli_kit.outcome import NothingToDo

from jira_tools import adf, config, keys, session

# The kinds of custom field shown under Other fields, as their schemas name them: those whose
# values read as a word or two. The rest, such as an issue's rank, are Jira's own workings.
SIMPLE = {"string", "number", "date", "datetime", "option", "user", "version", "component"}
SPRINT = "com.pyxis.greenhopper.jira:gh-sprint"


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "view",
        help="show an issue as Markdown, with its comments",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.set_defaults(run=lambda args: view(args.key))


def view(key: str) -> NothingToDo:
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    jira = session.connect(settings)
    issue = session.fetch(jira, key)
    comments = jira.comments(key) or []
    web_links = jira.web_links(key)
    print(markdown(issue, comments, jira.issue_link(key).url, web_links))
    return NothingToDo(f"{key} is {issue['fields']['status']['name']}.")


def markdown(
    issue: dict, comments: list[dict], url: str, web_links: list[dict] | None = None
) -> str:
    """The issue, with its comments and web links, as a Markdown document."""
    fields = issue["fields"]
    names = issue.get("names", {})
    sections = [f"# {issue['key']}: {fields.get('summary', '')}", _facts(fields, url)]

    description = adf.to_markdown(fields.get("description") or {}, heading_offset=2)
    sections.append(f"## Description\n\n{description or 'None.'}")
    for field, value in fields.items():
        if field != "description" and _is_document(value):
            if text := adf.to_markdown(value, heading_offset=2):
                sections.append(f"## {names.get(field, field)}\n\n{text}")
    schemas = issue.get("schema", {})
    others = [
        f"- {names.get(field, field)}: {text}"
        for field, value in fields.items()
        if field.startswith("customfield_")
        and _is_simple(schemas.get(field, {}))
        and not _is_document(value)
        and (text := _plain(value))
    ]
    if others:
        sections.append("## Other fields\n\n" + "\n".join(others))

    subtasks = [f"- {_summary(task)}" for task in fields.get("subtasks") or []]
    links = [
        f"- {link['type']['outward']} {_summary(link['outwardIssue'])}"
        if "outwardIssue" in link
        else f"- {link['type']['inward']} {_summary(link['inwardIssue'])}"
        for link in fields.get("issuelinks") or []
    ]
    web = [f"- [{link['object']['title']}]({link['object']['url']})" for link in web_links or []]
    files = [
        f"- [{file['filename']}]({file['content']}) ({file['mimeType']}, {_size(file['size'])})"
        for file in fields.get("attachment") or []
    ]
    for heading, lines in (
        ("Subtasks", subtasks),
        ("Linked issues", links),
        ("Web links", web),
        ("Attachments", files),
    ):
        if lines:
            sections.append(f"## {heading}\n\n" + "\n".join(lines))

    if comments:
        sections.append("## Comments")
        for comment in comments:
            author = comment.get("author", {}).get("displayName", "Someone")
            body = adf.to_markdown(comment.get("body") or {}, heading_offset=3)
            heading = f"{author}, {comment.get('created', '')[:10]} (comment {comment['id']})"
            sections.append(f"### {heading}\n\n{body}")
    return "\n\n".join(sections)


def _facts(fields: dict, url: str) -> str:
    def name(value: dict | None) -> str:
        return (value or {}).get("name") or (value or {}).get("displayName") or ""

    def names(values: list) -> str:
        return ", ".join(value if isinstance(value, str) else name(value) for value in values or [])

    facts = [
        ("Type", name(fields.get("issuetype"))),
        ("Status", name(fields.get("status"))),
        ("Resolution", name(fields.get("resolution"))),
        ("Priority", name(fields.get("priority"))),
        ("Assignee", name(fields.get("assignee")) or "Unassigned"),
        ("Reporter", name(fields.get("reporter"))),
        ("Labels", names(fields.get("labels"))),
        ("Components", names(fields.get("components"))),
        ("Fix versions", names(fields.get("fixVersions"))),
        ("Affects versions", names(fields.get("versions"))),
        ("Parent", _summary(fields["parent"]) if fields.get("parent") else ""),
        ("Due", fields.get("duedate") or ""),
        *_tracked(fields),
        ("Created", (fields.get("created") or "")[:10]),
        ("Updated", (fields.get("updated") or "")[:10]),
        ("URL", url),
    ]
    return "\n".join(f"- {label}: {value}" for label, value in facts if value)


def _tracked(fields: dict) -> list[tuple[str, str]]:
    """The time estimated, spent and remaining on the issue, as Jira writes it, and how many
    people watch it."""
    time = fields.get("timetracking") or {}
    return [
        ("Original estimate", time.get("originalEstimate") or ""),
        ("Time spent", time.get("timeSpent") or ""),
        ("Remaining", time.get("remainingEstimate") or ""),
        ("Watchers", str((fields.get("watches") or {}).get("watchCount") or "")),
    ]


def _summary(issue: dict) -> str:
    """Another issue in one line: its key, status and summary."""
    fields = issue.get("fields", {})
    return (
        f"{issue['key']} ({fields.get('status', {}).get('name', '')}): {fields.get('summary', '')}"
    )


def _is_simple(schema: dict) -> bool:
    if schema.get("type") == "array":
        return schema.get("items") in SIMPLE or schema.get("custom") == SPRINT
    return schema.get("type") in SIMPLE


def _plain(value: object) -> str:
    """A simple field's value as text: an option, version, sprint or person by its name, a list
    of them joined, and a whole number without its decimal point."""
    if isinstance(value, list):
        return ", ".join(text for item in value if (text := _plain(item)))
    if isinstance(value, dict):
        return str(value.get("value") or value.get("name") or value.get("displayName") or "")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


def _is_document(value: object) -> bool:
    return isinstance(value, dict) and value.get("type") == "doc"


def _size(size: int) -> str:
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
