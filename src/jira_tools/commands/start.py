"""jira start <key>

Starts work on the issue, in the git repository in the current folder:

1. Assigns it to you.
2. Moves it to the being-worked-on stage: the status .workspace.toml's [tracker.stages] keeps
   it in, In Progress unless set, in one move, or its stage-being-worked-on label. When its
   workflow has no move there from its status, it stops before changing anything and says which
   statuses it can move to; when the move needs fields filled in, it says which, to fill them in
   with jira move.
3. Switches to its branch: the one named by its key, as in WEB-12 or WEB-12-anything, here or
   on origin. When there's none, it creates one from the current commit, named for the key and
   summary, as in WEB-12-scan-skips-symlinks.

An issue assigned to someone else or done is left alone. Each step is skipped when it's done, so
running it again after a failure is safe.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

import re
from pathlib import Path

from cli_kit import cli, outcome
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import config, git, keys, session, stages

# A new branch's name is the key and at most this many characters of the summary.
SLUG_LENGTH = 40
WORKING = "being-worked-on"


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "start",
        help="assign an issue to you, move it in progress and switch to its branch",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.set_defaults(run=lambda args: start(args.key))


def start(key: str, directory: Path | None = None) -> Done | NothingToDo:
    directory = directory or Path.cwd()
    if not git.is_repository(directory):
        raise Precondition(
            "Not in a git repository.", "Run it from the repository you'll work on the issue in."
        )
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    jira = session.connect(settings)
    fields = session.fetch(jira, key)["fields"]
    me = jira.myself()

    status = fields["status"]
    if status["statusCategory"]["key"] == "done":
        raise Precondition(
            f"{key} is {status['name']}.",
            f"If there's more to do, move it back first: jira move {key} '<status>'",
        )
    assignee = fields.get("assignee")
    if assignee and assignee["accountId"] != me.account_id:
        raise Precondition(
            f"{key} is assigned to {assignee.get('displayName', 'someone else')}.",
            f"If you're taking it over, assign it to yourself first: jira assign {key}",
        )
    # The move comes after start assigns the issue to you, so it has an assignee by then.
    assigned = {**fields, "assignee": assignee or {"accountId": me.account_id}}
    move = stages.plan(jira, key, assigned, settings.stages, WORKING, "start")

    local = git.local_branch_for(directory, key)
    remote = None if local else git.remote_branch_for(directory, key)
    branch = local or remote or branch_name(key, fields.get("summary", ""))

    changes = 0

    def changed(description: str) -> None:
        nonlocal changes
        outcome.changed(description)
        changes += 1

    if not assignee:
        jira.assign(key, me.account_id)
        changed(f"Assigned {key} to you.")
    if move:
        stages.apply(jira, key, move)
        changed(f"Moved {key} to {move.transition.status if move.transition else WORKING}.")
    if git.current_branch(directory) != branch:
        if local:
            git.switch(directory, branch)
            changed(f"Switched to branch {branch}.")
        elif remote:
            git.create(directory, branch, tracking=f"origin/{remote}")
            changed(f"Created branch {branch}, following origin/{remote}.")
        else:
            git.create(directory, branch)
            changed(f"Created branch {branch}.")

    if not changes:
        return NothingToDo(f"{key} is already started, on branch {branch}.")
    return Done(f"Started {key}.", jira.issue_link(key).url)


def branch_name(key: str, summary: str) -> str:
    """A new branch's name: key, then the summary's words in lower case, joined by hyphens,
    cut at a word to fit SLUG_LENGTH."""
    slug = ""
    for word in re.findall(r"[a-z0-9]+", summary.lower()):
        if len(slug) + len(word) + 1 > SLUG_LENGTH:
            break
        slug = f"{slug}-{word}" if slug else word
    return f"{key}-{slug}" if slug else key
