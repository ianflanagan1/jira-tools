"""The stages our process takes an issue through, by what has to happen next:

    needs-codebase    a report no one has compared with the code: a developer runs /jira-refine
    needs-developer   a developer answers, decides or approves
    ready-for-agent   approved, with no open questions: an agent may work on it
    being-worked-on   work has started
    awaiting-review   the work is up for review

and done, which is any status in the workflow's done category.

Each stage is kept in the status .workspace.toml maps it to, or, with none, as a stage-<name> label.
A mapped status is where the issue is, whatever its labels say, since people move issues on the
board but only our commands touch the labels; a stage label counts only in a status no stage is
mapped to.
"""

from dataclasses import dataclass

from cli_kit.outcome import Precondition

from jira_tools import api

STAGES = (
    "needs-codebase",
    "needs-developer",
    "ready-for-agent",
    "being-worked-on",
    "awaiting-review",
)
DONE = "done"
PREFIX = "stage-"


@dataclass(frozen=True)
class Move:
    """The changes that put an issue at a stage: a move to another status, and labels to add
    and remove."""

    transition: api.Transition | None
    add: tuple[str, ...]
    remove: tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.transition or self.add or self.remove)


def label(stage: str) -> str:
    return PREFIX + stage


def current(fields: dict, mapped: dict[str, str]) -> str | None:
    """The issue's stage, from its status and labels, or None when it has none."""
    status = fields["status"]
    if status.get("statusCategory", {}).get("key") == "done":
        return DONE
    if stage := _mapped_to(status["name"], mapped):
        return stage
    return next((name for name in _stage_labels(fields) if name in STAGES), None)


def plan(
    jira: api.Jira, key: str, fields: dict, mapped: dict[str, str], stage: str, command: str
) -> Move:
    """The changes that put the issue, with fields, at stage. Raises Precondition, for command,
    when there's no such stage, the issue is done, or its workflow can't get it there in one move
    that needs no fields filled in."""
    from jira_tools.commands.move import check_no_fields_needed, transition_to

    if stage not in STAGES:
        raise Precondition(f"No stage {stage}.", f"The stages are: {', '.join(STAGES)}.")
    status = fields["status"]
    if status.get("statusCategory", {}).get("key") == "done":
        raise Precondition(
            f"{key} is {status['name']}.", f"Move it back first: jira move {key} '<status>'"
        )
    labels = [label(name) for name in _stage_labels(fields)]
    if stage in mapped:
        transition = transition_to(jira, key, status["name"], mapped[stage])
        add: tuple[str, ...] = ()
        remove = tuple(labels)
    else:
        transition = None
        if _mapped_to(status["name"], mapped):
            transition = _to_do(jira, key, status["name"], mapped, stage)
        add = () if label(stage) in labels else (label(stage),)
        remove = tuple(name for name in labels if name != label(stage))
    if transition:
        check_no_fields_needed(key, transition, fields, command)
    return Move(transition, add, remove)


def apply(jira: api.Jira, key: str, move: Move) -> None:
    if move.transition:
        jira.transition(key, move.transition)
    if move.add or move.remove:
        jira.edit(key, None, None, move.add, move.remove)


def _mapped_to(status: str, mapped: dict[str, str]) -> str | None:
    wanted = status.casefold()
    return next((stage for stage, name in mapped.items() if name.casefold() == wanted), None)


def _stage_labels(fields: dict) -> list[str]:
    """The stages the issue's stage labels name."""
    labels = fields.get("labels") or []
    return [name.removeprefix(PREFIX) for name in labels if name.startswith(PREFIX)]


def _to_do(
    jira: api.Jira, key: str, status: str, mapped: dict[str, str], stage: str
) -> api.Transition:
    """The move out of status, which a stage is mapped to, to a to-do status none is: where an
    issue goes whose stage is kept as a label."""
    taken = {name.casefold() for name in mapped.values()}
    for transition in jira.transitions(key):
        if transition.category == "new" and transition.status.casefold() not in taken:
            return transition
    raise Precondition(
        f"{key} can't leave {status} for {stage}.",
        f"{stage} is kept as a label, in a to-do status no stage is mapped to, and its workflow"
        f" has no move from {status} to one. Map {stage} to a status in .workspace.toml's"
        " [tracker.stages].",
    )
