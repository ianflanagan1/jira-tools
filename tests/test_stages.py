"""Where an issue is in our process, and the changes that move it on: each stage kept in the
status .config/ianf-tracker.toml maps it to, or, with none, as a stage-<name> label, against a
fake Jira site."""

import pytest
from cli_kit.outcome import Precondition

from jira_tools import session, stages
from jira_tools.config import Config

MAPPED = {"being-worked-on": "In Progress", "ready-for-agent": "Ready"}


@pytest.fixture
def jira(site):
    site.settings = Config("me.atlassian.net", "WEB", stages=MAPPED)
    return session.connect(site.settings)


def fields(site, key="WEB-12"):
    return {**site.issues[key], "labels": site.issues[key].get("labels", [])}


def test_a_mapped_status_is_its_stage():
    issue = {"status": {"name": "in progress", "statusCategory": {"key": "indeterminate"}}}
    assert stages.current(issue, MAPPED) == "being-worked-on"


def test_in_an_unmapped_status_the_stage_label_says_where_it_is():
    issue = {
        "status": {"name": "To Do", "statusCategory": {"key": "new"}},
        "labels": ["scan", "stage-needs-developer"],
    }
    assert stages.current(issue, MAPPED) == "needs-developer"


def test_a_mapped_status_wins_over_a_stale_label():
    # People move issues on the board; only our commands touch labels.
    issue = {
        "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
        "labels": ["stage-needs-developer"],
    }
    assert stages.current(issue, MAPPED) == "being-worked-on"


def test_any_done_status_is_done_and_no_stage_is_none():
    done = {"status": {"name": "Closed", "statusCategory": {"key": "done"}}, "labels": []}
    none = {"status": {"name": "To Do", "statusCategory": {"key": "new"}}}
    assert stages.current(done, MAPPED) == "done"
    assert stages.current(none, MAPPED) is None


def test_a_mapped_stage_is_a_move_and_clears_stage_labels(site, jira):
    site.add("WEB-12", labels=["scan", "stage-needs-codebase"])
    move = stages.plan(jira, "WEB-12", fields(site), MAPPED, "ready-for-agent", "stage")
    assert (move.transition.status, move.add, move.remove) == (
        "Ready",
        (),
        ("stage-needs-codebase",),
    )


def test_an_unmapped_stage_swaps_its_label_for_any_other(site, jira):
    site.add("WEB-12", labels=["stage-needs-codebase"])
    move = stages.plan(jira, "WEB-12", fields(site), MAPPED, "needs-developer", "stage")
    assert (move.transition, move.add, move.remove) == (
        None,
        ("stage-needs-developer",),
        ("stage-needs-codebase",),
    )


def test_an_unmapped_stage_moves_it_out_of_a_mapped_status_to_an_unmapped_to_do_one(site, jira):
    site.add("WEB-12", status="In Progress")
    move = stages.plan(jira, "WEB-12", fields(site), MAPPED, "needs-developer", "stage")
    assert move.transition.status == "To Do"
    assert move.add == ("stage-needs-developer",)


def test_with_no_unmapped_to_do_status_to_move_to_it_stops(site, jira):
    site.add("WEB-12", status="In Progress")
    site.moves = {"In Progress": ["Ready", "Done"]}
    with pytest.raises(Precondition) as raised:
        stages.plan(jira, "WEB-12", fields(site), MAPPED, "needs-developer", "stage")
    assert raised.value.message == "WEB-12 can't leave In Progress for needs-developer."


def test_an_issue_already_there_needs_no_change(site, jira):
    site.add("WEB-12", status="Ready")
    assert not stages.plan(jira, "WEB-12", fields(site), MAPPED, "ready-for-agent", "stage")
    site.add("WEB-13", labels=["stage-needs-developer"])
    assert not stages.plan(jira, "WEB-13", fields(site, "WEB-13"), MAPPED, "needs-developer", "x")


def test_a_done_issue_and_an_unknown_stage_are_refused(site, jira):
    site.add("WEB-12", status="Done")
    with pytest.raises(Precondition) as raised:
        stages.plan(jira, "WEB-12", fields(site), MAPPED, "needs-developer", "stage")
    assert raised.value.message == "WEB-12 is Done."
    site.add("WEB-13")
    with pytest.raises(Precondition) as raised:
        stages.plan(jira, "WEB-13", fields(site, "WEB-13"), MAPPED, "triage", "stage")
    assert raised.value.message == "No stage triage."
    assert "needs-codebase, needs-developer, ready-for-agent" in raised.value.details[0]


def test_a_move_that_needs_fields_is_refused_before_any_change(site, jira):
    site.add("WEB-12")
    site.screens["Ready"] = {"resolution": site.resolution}
    with pytest.raises(Precondition) as raised:
        stages.plan(jira, "WEB-12", fields(site), MAPPED, "ready-for-agent", "stage")
    assert (
        raised.value.message
        == "Moving WEB-12 to Ready needs: Resolution (Done, Won't Do, Duplicate)."
    )
    assert site.writes == []


def test_applying_a_move_makes_it(site, jira):
    site.add("WEB-12", status="In Progress", labels=["stage-awaiting-review"])
    move = stages.plan(jira, "WEB-12", fields(site), MAPPED, "needs-developer", "stage")
    stages.apply(jira, "WEB-12", move)
    assert stages.current(fields(site), MAPPED) == "needs-developer"
    assert site.issues["WEB-12"]["labels"] == ["stage-needs-developer"]
