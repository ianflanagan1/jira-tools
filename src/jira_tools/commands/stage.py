"""jira stage <key> [<stage>]

Says which stage of our process the issue is at, or moves it to stage:

    needs-codebase    a report no one has compared with the code
    needs-developer   a developer answers, decides or approves
    ready-for-agent   approved, with no open questions: an agent may work on it
    being-worked-on   work has started
    awaiting-review   the work is up for review

Each stage is kept in the status [stages] in .config/ianf-tracker.toml maps it to, or, with none,
as a stage-<name> label; a done status is done. It won't move an issue whose description has an Open
questions section to ready-for-agent, or a done one anywhere. An issue already at the stage is
left alone.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

import re

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf, config, keys, session, stages

READY = "ready-for-agent"


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "stage",
        help="say which stage an issue is at, or move it to one",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("stage", nargs="?", help="the stage to move it to")
    parser.set_defaults(run=lambda args: stage(args.key, args.stage))


def stage(key: str, wanted: str | None = None) -> Done | NothingToDo:
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    jira = session.connect(settings)
    fields = session.fetch(jira, key)["fields"]
    now = stages.current(fields, settings.stages)
    if wanted is None:
        return NothingToDo(f"{key} is at {now}." if now else f"{key} has no stage.")
    wanted = wanted.strip()
    if wanted == READY and has_open_questions(fields):
        raise Precondition(
            f"{key} has open questions.",
            "Answer them and take the Open questions section out of its description first.",
        )
    move = stages.plan(jira, key, fields, settings.stages, wanted, "stage")
    if not move:
        return NothingToDo(f"{key} is already at {wanted}.")
    stages.apply(jira, key, move)
    return Done(f"Moved {key} to {wanted}.", jira.issue_link(key).url)


def has_open_questions(fields: dict) -> bool:
    """Whether the issue's description has an Open questions section."""
    markdown = adf.to_markdown(fields.get("description") or {})
    return re.search(r"^#+\s+Open questions\s*$", markdown, re.M | re.I) is not None
