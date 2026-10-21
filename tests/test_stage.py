"""jira stage: where an issue is in our process, or moving it to a stage, against a fake Jira
site."""

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf
from jira_tools.__main__ import main
from jira_tools.commands.stage import stage
from jira_tools.config import Config

SITE = "https://me.atlassian.net"


@pytest.fixture
def mapped(site):
    site.settings = Config("me.atlassian.net", "WEB", stages={"ready-for-agent": "Ready"})
    return site


def test_without_a_stage_it_says_where_the_issue_is(site):
    site.add("WEB-12", labels=["stage-needs-codebase"])
    result = stage("WEB-12")
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 is at needs-codebase."
    site.add("WEB-13", labels=[])
    assert stage("WEB-13").summary == "WEB-13 has no stage."


def test_a_stage_kept_as_a_label_is_set_by_its_label(site):
    site.add("WEB-12", labels=["scan", "stage-needs-codebase"])
    result = stage("WEB-12", "needs-developer")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Moved WEB-12 to needs-developer.",
        f"{SITE}/browse/WEB-12",
    )
    assert site.issues["WEB-12"]["labels"] == ["scan", "stage-needs-developer"]


def test_a_mapped_stage_moves_the_issue_to_its_status(mapped):
    mapped.add("WEB-12", labels=["stage-needs-developer"])
    stage("WEB-12", "ready-for-agent")
    assert mapped.issues["WEB-12"]["status"]["name"] == "Ready"
    assert mapped.issues["WEB-12"]["labels"] == []


def test_an_issue_already_at_the_stage_is_left_alone(site):
    site.add("WEB-12", labels=["stage-needs-developer"])
    result = stage("WEB-12", "needs-developer")
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 is already at needs-developer."
    assert site.writes == []


def test_an_issue_with_open_questions_is_not_made_ready_for_an_agent(site):
    description = adf.from_markdown("## Problem\n\nX.\n\n## Open questions\n\n- Which phone?")
    site.add("WEB-12", labels=["stage-needs-developer"], description=description)
    with pytest.raises(Precondition) as raised:
        stage("WEB-12", "ready-for-agent")
    assert raised.value.message == "WEB-12 has open questions."
    assert site.writes == []


def test_an_issue_that_is_not_there_is_named(site):
    with pytest.raises(Precondition) as raised:
        stage("WEB-12", "needs-developer")
    assert raised.value.message == "No issue WEB-12."


def test_the_command_line_takes_the_key_and_the_stage(site, capsys):
    site.add("WEB-12", labels=[])
    assert main(["stage", "12", "needs-developer"]) == 0
    assert capsys.readouterr().out.startswith("✅ Moved WEB-12 to needs-developer.\n")
