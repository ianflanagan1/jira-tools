"""jira unlink: a link between two issues removed, against a fake Jira site."""

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.unlink import unlink

SITE = "https://me.atlassian.net"


@pytest.fixture
def issues(site):
    site.add("WEB-12")
    site.add("WEB-9")
    return site


def test_removes_the_link_from_both_issues_and_gives_its_url(issues):
    issues.link("Blocks", "WEB-9", "WEB-12")
    result = unlink("WEB-12", "is blocked by", "WEB-9")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Unlinked: WEB-12 is blocked by WEB-9.",
        f"{SITE}/browse/WEB-12",
    )
    assert issues.linked("WEB-12") == []
    assert issues.linked("WEB-9") == []


def test_only_the_link_named_is_removed(issues):
    issues.link("Blocks", "WEB-9", "WEB-12")
    issues.link("Blocks", "WEB-12", "WEB-9")
    issues.link("Relates", "WEB-12", "WEB-9")
    unlink("WEB-12", "Blocks", "WEB-9")
    assert issues.linked("WEB-12") == ["is blocked by WEB-9", "relates to WEB-9"]


def test_a_relation_that_reads_the_same_both_ways_is_removed_from_either_side(issues):
    issues.link("Relates", "WEB-9", "WEB-12")
    unlink("WEB-12", "relates to", "WEB-9")
    assert issues.linked("WEB-12") == []


def test_issues_not_linked_so_are_left_alone(issues):
    issues.link("Blocks", "WEB-12", "WEB-9")
    result = unlink("WEB-12", "is blocked by", "WEB-9")
    assert isinstance(result, NothingToDo)
    assert result.summary == "Not linked: WEB-12 is blocked by WEB-9."
    assert issues.writes == []


def test_a_relation_jira_has_no_link_type_for_is_refused(issues):
    with pytest.raises(Precondition) as raised:
        unlink("WEB-12", "depends on", "WEB-9")
    assert raised.value.message == "Jira has no relation 'depends on'."


def test_an_issue_that_is_not_there_is_named(issues):
    with pytest.raises(Precondition) as raised:
        unlink("WEB-404", "blocks", "WEB-9")
    assert raised.value.message == "No issue WEB-404."


def test_the_command_line_takes_the_key_relation_and_other_key(issues, capsys):
    issues.link("Blocks", "WEB-12", "WEB-9")
    assert main(["unlink", "WEB-12", "blocks", "WEB-9"]) == 0
    assert capsys.readouterr().out.startswith("✅ Unlinked: WEB-12 blocks WEB-9.\n")
