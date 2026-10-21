"""jira create <summary> [--type <type>] [--label <label>]... [--space <key>]
            [--priority <name>] [--parent <key>] [--assign <who>] [--reporter <who>]
            [--due <YYYY-MM-DD>] [--component <name>]... [--fix-version <name>]...
            [--affects-version <name>]... [--link <relation> <other>]...
            [--field <name>=<value>]... [--field-file <name>=<path>]... [--estimate <duration>]
            [--stage <stage>] [--workspace <file>] [--dry-run]

Files a Jira issue with summary, in the space, of the type and with the labels set in the
[tracker] table of the repository's .workspace.toml, or with --workspace, of another file: a
.workspace.toml, or a product map, whose front matter has the table. Its description is the
Markdown on stdin, if any, followed by where it was raised: the branch, commit and repository of
the current folder. The options set its other fields: its
type, priority, components and versions each matched ignoring case against those the space has;
its parent, an epic, or for a subtask type the issue it's under; and its assignee and reporter,
me, or someone's name or email. --link links it to the other issue, as jira link does, once
it's filed. --field sets any field the type's create screen has by name, such as Story points: a
field that takes several values once for each. --field-file reads the value from a file, such as
acceptance criteria in Markdown, and --estimate sets the original estimate, such as 1d 4h. A
field is set by its own option or by --field, not both. Each of these is checked before anything
is filed. --stage puts it at a stage of our process once it's filed, as jira stage does; it won't
file an issue whose description has an Open questions section at ready-for-agent.

Nothing is filed with a summary over 80 characters, a description with Markdown Jira would show
as plain text, such as a table, or a secret in either, such as a token or password.

It isn't filed again while an open issue in the space with the same summary, ignoring case,
has all of its labels, not counting a stage label; that issue gets any of the links it lacks
instead, and keeps its stage. --dry-run shows what
would be sent, without the API token or Jira.
"""

import json
import sys
from pathlib import Path
from typing import TextIO

from cli_kit import cli, outcome
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import (
    adf,
    api,
    checks,
    choices,
    config,
    context,
    fields,
    keys,
    people,
    session,
    stages,
)
from jira_tools.commands import link
from jira_tools.commands.stage import READY, has_open_questions

SECRET = "Take it out, or describe it without its value."

# The option that sets each field by name, so that --field can't set it too.
OPTIONS = {
    "priority": "--priority",
    "parent": "--parent",
    "assignee": "--assign",
    "reporter": "--reporter",
    "duedate": "--due",
    "components": "--component",
    "fixVersions": "--fix-version",
    "versions": "--affects-version",
}


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "create",
        help="file an issue, described by the Markdown on stdin",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("summary", help="the issue's one-line summary")
    parser.add_argument("--type", dest="issue_type", help="the issue type, instead of the set one")
    parser.add_argument(
        "--label", action="append", default=[], dest="labels", help="a label to add; repeatable"
    )
    parser.add_argument("--space", help="the space's key, instead of the set one")
    parser.add_argument("--priority", metavar="name", help="its priority, such as High")
    parser.add_argument(
        "--parent", metavar="key", help="its parent: an epic, or for a subtask its issue"
    )
    parser.add_argument("--assign", metavar="who", help="its assignee: me, or a name or email")
    parser.add_argument("--reporter", metavar="who", help="its reporter: me, or a name or email")
    parser.add_argument("--due", metavar="YYYY-MM-DD", help="its due date")
    for option, dest, kind in (
        ("--component", "components", "a component"),
        ("--fix-version", "fix_versions", "a version it's fixed in"),
        ("--affects-version", "affects_versions", "a version it affects"),
    ):
        parser.add_argument(
            option,
            action="append",
            default=[],
            dest=dest,
            metavar="name",
            help=f"{kind}; repeatable",
        )
    parser.add_argument(
        "--link",
        nargs=2,
        action="append",
        default=[],
        dest="links",
        metavar=("<relation>", "<other>"),
        help='an issue to link it to, such as "is blocked by" WEB-9; repeatable',
    )
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        dest="field_values",
        metavar="<name>=<value>",
        help="set a field by its name or id; repeatable",
    )
    parser.add_argument(
        "--field-file",
        action="append",
        default=[],
        dest="field_files",
        metavar="<name>=<path>",
        help="set a field to the contents of a file; repeatable",
    )
    parser.add_argument(
        "--estimate", metavar="duration", help="the original estimate, such as 1d 4h"
    )
    parser.add_argument("--stage", metavar="stage", help="the stage to file it at, as jira stage")
    parser.add_argument(
        "--workspace",
        metavar="file",
        type=Path,
        help="the .workspace.toml or product map to take the settings from",
    )
    parser.add_argument("--dry-run", action="store_true", help="show what would be sent")
    parser.set_defaults(
        run=lambda args: create(
            args.summary,
            issue_type=args.issue_type,
            labels=args.labels,
            space=args.space,
            priority=args.priority,
            parent=args.parent,
            assign=args.assign,
            reporter=args.reporter,
            due=args.due,
            components=args.components,
            fix_versions=args.fix_versions,
            affects_versions=args.affects_versions,
            links=[tuple(pair) for pair in args.links],
            field_values=args.field_values,
            field_files=args.field_files,
            estimate=args.estimate,
            stage=args.stage,
            workspace=args.workspace,
            dry_run=args.dry_run,
        )
    )


def create(
    summary: str,
    *,
    issue_type: str | None = None,
    labels: list[str] | None = None,
    space: str | None = None,
    priority: str | None = None,
    parent: str | None = None,
    assign: str | None = None,
    reporter: str | None = None,
    due: str | None = None,
    components: list[str] | None = None,
    fix_versions: list[str] | None = None,
    affects_versions: list[str] | None = None,
    links: list[tuple[str, str]] | None = None,
    field_values: list[str] | None = None,
    field_files: list[str] | None = None,
    estimate: str | None = None,
    stage: str | None = None,
    workspace: Path | None = None,
    dry_run: bool = False,
    stdin: TextIO | None = None,
) -> Done | NothingToDo:
    summary = summary.strip()
    if not summary:
        raise Precondition("The summary is empty.")
    if problem := checks.summary(summary):
        raise Precondition(problem)
    if found := checks.secret(summary):
        raise Precondition(f"The summary looks like it has {found}.", SECRET)
    for option, who in (("assign", assign), ("reporter", reporter)):
        if who is not None and who.strip().casefold() == "none":
            raise Precondition(f"--{option} needs someone: me, or a name or email.")
    due = choices.date(due, "--due") if due is not None else None
    by_name = fields.given(field_values or [], field_files or [], estimate)
    for name, value in fields.pairs(by_name):
        if not value:
            raise Precondition(f"{name} is empty.", "A new issue has no value to clear.")
    stage = stage.strip() if stage is not None else None
    if stage is not None and stage not in stages.STAGES:
        raise Precondition(f"No stage {stage}.", f"The stages are: {', '.join(stages.STAGES)}.")
    stdin = stdin or sys.stdin
    given_markdown = "" if stdin.isatty() else stdin.read().strip()
    if found := checks.secret(given_markdown):
        raise Precondition(f"The description looks like it has {found}.", SECRET)
    if found := checks.markdown(given_markdown):
        raise Precondition(
            f"The description has {found}, which Jira would show as plain text.",
            "Use only paragraphs, headings, - and 1. lists, code blocks, `code`, **bold** and "
            "[links](url).",
        )
    settings = config.load(workspace)
    space = space or settings.space
    all_labels = tuple(dict.fromkeys([*settings.labels, *(labels or [])]))
    kept_as_label = stage is not None and stage not in settings.stages
    new_labels = (*all_labels, stages.label(stage)) if kept_as_label else all_labels
    given = {
        "priority": priority,
        "parent": keys.issue_key(parent, space) if parent is not None else None,
        "assignee": assign,
        "reporter": reporter,
        "duedate": due,
        "components": components or [],
        "fixVersions": fix_versions or [],
        "versions": affects_versions or [],
    }
    wanted = [(relation, keys.issue_key(other, space)) for relation, other in links or []]

    parts = [given_markdown, context.where(Path.cwd()) or ""]
    markdown = "\n\n".join(part for part in parts if part)
    description = adf.from_markdown(markdown) if markdown else None
    if stage == READY and has_open_questions({"description": description}):
        raise Precondition(
            "The issue has open questions.", f"File it at another stage, not {READY}."
        )

    if dry_run:
        sent = {
            "project": {"key": space},
            "issuetype": {"name": issue_type or settings.issue_type},
            "summary": summary,
            "labels": list(new_labels),
            "description": description,
            **_fields(None, space, given),
        }
        shown: dict = {"site": settings.base_url, "fields": sent}
        if stage:
            shown["stage"] = stage
        if by_name:
            shown["set_by_name"] = by_name
        if wanted:
            shown["links"] = [{"relation": r, "other": other} for r, other in wanted]
        print(json.dumps(shown, indent=2))
        return NothingToDo("Dry run: nothing filed.")

    jira = session.connect(settings)
    kind = None
    if issue_type is not None or by_name:
        kind = choices.issue_type(jira, space, issue_type or settings.issue_type)
    more = _fields(jira, space, given)
    if by_name:
        meta = jira.create_meta(space, kind.id)
        screen = f"the create screen for a {kind.name} in {space}"
        set_by_name = fields.convert(meta, by_name, jira, space=space, screen=screen).fields
        if both := set(more) & set(set_by_name):
            field = sorted(both)[0]
            raise Precondition(
                f"{OPTIONS[field]} and --field both set {meta[field].get('name', field)}.",
                "Give it once.",
            )
        more |= set_by_name
    relations = []
    for relation, other in wanted:
        relations.append((link.relation_named(jira, relation), other))
        session.fetch(jira, other)

    if existing := jira.find_open(space, all_labels, summary):
        has = session.fetch(jira, existing.key)["fields"] if relations else {}
        if linked := _link(jira, existing.key, has, relations):
            return Done(f"Already filed as {existing.key}; linked it to {linked}.", existing.url)
        return NothingToDo(f"Already filed as {existing.key}.")
    type_name = kind.name if kind else settings.issue_type
    issue = jira.create(space, type_name, new_labels, summary, description, more)
    filed = f"Filed {issue.key} at {stage}" if stage else f"Filed {issue.key}"
    if stage and not kept_as_label:
        outcome.changed(f"Filed {issue.key}.")
        fields_now = session.fetch(jira, issue.key)["fields"]
        move = stages.plan(jira, issue.key, fields_now, settings.stages, stage, "create")
        stages.apply(jira, issue.key, move)
    if not relations:
        return Done(f"{filed}.", issue.url)
    outcome.changed(f"{filed}.")
    return Done(f"{filed}, linked to {_link(jira, issue.key, {}, relations)}.", issue.url)


def _fields(jira: api.Jira | None, space: str, given: dict) -> dict:
    """The fields given by their own options, as Jira's JSON names them: each matched against
    what space has, or for a dry run, with no jira, as given, with people as named. Raises
    Precondition when the space has no such priority, component or version, or there's no such
    issue or person."""
    sent: dict = {}
    if given["priority"] is not None:
        name = given["priority"].strip()
        sent["priority"] = {"name": choices.priority(jira, space, name) if jira else name}
    if given["parent"] is not None:
        if jira:
            session.fetch(jira, given["parent"])
        sent["parent"] = {"key": given["parent"]}
    for field in ("assignee", "reporter"):
        if (who := given[field]) is not None:
            person = people.person(jira, who.strip()) if jira else None
            sent[field] = {"accountId": person.account_id} if person else who.strip()
    if given["duedate"] is not None:
        sent["duedate"] = given["duedate"]
    for field in ("components", "fixVersions", "versions"):
        if names := [name.strip() for name in given[field]]:
            if jira:
                match = choices.components if field == "components" else choices.versions
                names = match(jira, space, names)
            sent[field] = [{"name": name} for name in names]
    return sent


def _link(jira: api.Jira, key: str, has: dict, relations: list) -> str:
    """Links the issue with key, whose fields are has, by each relation it doesn't already have,
    and names the issues it linked it to, such as "WEB-3 and WEB-5", or "" for none."""
    linked = []
    for relation, other in relations:
        if link.existing(has, relation, other) is None:
            link.add(jira, key, relation, other)
            outcome.changed(f"Linked: {key} {relation.reads} {other}.")
            linked.append(other)
    return " and ".join(", ".join(linked).rsplit(", ", 1))
