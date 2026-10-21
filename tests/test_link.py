"""jira link: one issue linked to another by a relation such as "is blocked by", against a fake
Jira site."""

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.link import link

SITE = "https://me.atlassian.net"


@pytest.fixture
def issues(site):
    site.add("WEB-12")
    site.add("WEB-9")
    return site


def test_links_the_issue_by_the_relation_and_gives_its_url(issues):
    result = link("WEB-12", "is blocked by", "WEB-9")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Linked: WEB-12 is blocked by WEB-9.",
        f"{SITE}/browse/WEB-12",
    )
    assert issues.linked("WEB-12") == ["is blocked by WEB-9"]
    assert issues.linked("WEB-9") == ["blocks WEB-12"]


def test_an_outward_relation_links_the_issue_as_its_subject(issues):
    link("WEB-12", "blocks", "WEB-9")
    assert issues.linked("WEB-12") == ["blocks WEB-9"]
    assert issues.linked("WEB-9") == ["is blocked by WEB-12"]


def test_the_relation_is_matched_ignoring_case_and_named_as_jira_names_it(issues):
    assert link("WEB-12", " Is Cloned By ", "WEB-9").summary == "Linked: WEB-12 is cloned by WEB-9."


def test_a_relation_jira_has_no_link_type_for_names_those_it_has(issues):
    with pytest.raises(Precondition) as raised:
        link("WEB-12", "depends on", "WEB-9")
    assert [raised.value.message, *raised.value.details] == [
        "Jira has no relation 'depends on'.",
        "It has: blocks, is blocked by, clones, is cloned by, duplicates, is duplicated by,"
        " relates to.",
    ]
    assert issues.writes == []


def test_a_relation_more_than_one_link_type_has_is_refused(issues):
    issues.link_types = [*issues.link_types, {**issues.link_types[0], "id": "9", "name": "Stops"}]
    with pytest.raises(Precondition) as raised:
        link("WEB-12", "blocks", "WEB-9")
    assert raised.value.message == "More than one link type reads 'blocks': Blocks, Stops."
    assert issues.writes == []


def test_issues_already_linked_so_are_left_alone(issues):
    issues.link("Blocks", "WEB-9", "WEB-12")
    result = link("WEB-12", "is blocked by", "WEB-9")
    assert isinstance(result, NothingToDo)
    assert result.summary == "Already linked: WEB-12 is blocked by WEB-9."
    assert issues.writes == []


def test_a_link_the_other_way_round_is_not_the_same_link(issues):
    issues.link("Blocks", "WEB-12", "WEB-9")
    link("WEB-12", "is blocked by", "WEB-9")
    assert issues.linked("WEB-12") == ["blocks WEB-9", "is blocked by WEB-9"]


def test_a_relation_that_reads_the_same_both_ways_is_already_linked_from_either_side(issues):
    issues.link("Relates", "WEB-9", "WEB-12")
    assert isinstance(link("WEB-12", "relates to", "WEB-9"), NothingToDo)
    assert issues.writes == []


def test_an_issue_cannot_be_linked_to_itself(issues):
    with pytest.raises(Precondition) as raised:
        link("WEB-12", "blocks", "web-12")
    assert raised.value.message == "WEB-12 can't be linked to itself."
    assert issues.writes == []


@pytest.mark.parametrize("key, other", [("WEB-404", "WEB-9"), ("WEB-12", "WEB-404")])
def test_an_issue_that_is_not_there_is_named(issues, key, other):
    with pytest.raises(Precondition) as raised:
        link(key, "blocks", other)
    assert raised.value.message == "No issue WEB-404."
    assert issues.writes == []


def test_either_issue_can_be_named_by_its_number_or_url(issues):
    result = link("12", "blocks", f"{SITE}/browse/WEB-9")
    assert result.summary == "Linked: WEB-12 blocks WEB-9."


def test_the_command_line_takes_the_key_relation_and_other_key(issues, capsys):
    assert main(["link", "WEB-12", "is blocked by", "WEB-9"]) == 0
    assert capsys.readouterr().out == (
        f"✅ Linked: WEB-12 is blocked by WEB-9.\n{SITE}/browse/WEB-12\n"
    )
