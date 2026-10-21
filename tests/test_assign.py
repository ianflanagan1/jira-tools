"""jira assign: an issue assigned to you, to someone else, or to no one, against a fake Jira
site."""

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.assign import assign

SITE = "https://me.atlassian.net"


def assignee(site) -> str | None:
    person = site.issues["WEB-12"]["assignee"]
    return person and person["accountId"]


def test_assigns_the_issue_to_you_by_default_and_gives_its_url(site):
    site.add("WEB-12")
    result = assign("WEB-12")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == ("Assigned WEB-12 to you.", f"{SITE}/browse/WEB-12")
    assert assignee(site) == "me-1"


def test_assigns_it_to_the_one_person_whose_name_or_email_matches(site):
    site.person("a-1", "Alice Smith", "alice@example.com")
    site.person("b-1", "Bob Jones", "bob@example.com")
    site.add("WEB-12")
    assert assign("WEB-12", "alice@").summary == "Assigned WEB-12 to Alice Smith."
    assert assignee(site) == "a-1"


def test_among_several_matches_one_whose_name_or_email_is_exactly_it_is_chosen(site):
    site.person("a-1", "Al", "al@example.com")
    site.person("a-2", "Alice Smith", "alice@example.com")
    site.add("WEB-12")
    assert assign("WEB-12", "al").summary == "Assigned WEB-12 to Al."


def test_several_matches_with_none_exact_are_named(site):
    site.person("a-1", "Alice Smith")
    site.person("a-2", "Alison Brown")
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        assign("WEB-12", "ali")
    assert [raised.value.message, *raised.value.details] == [
        "More than one person matches 'ali': Alice Smith, Alison Brown.",
        "Give more of their name, or their email.",
    ]
    assert site.writes == []


def test_no_match_is_said(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        assign("WEB-12", "zed")
    assert raised.value.message == "No one in Jira matches 'zed'."


def test_none_unassigns_it(site):
    site.add("WEB-12", assignee=site.me)
    assert assign("WEB-12", "none").summary == "Unassigned WEB-12."
    assert assignee(site) is None


def test_an_issue_already_assigned_so_is_left_alone(site):
    site.add("WEB-12", assignee=site.me)
    result = assign("WEB-12", "ME")
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 is already assigned to you."
    assert site.writes == []


def test_an_issue_already_unassigned_is_left_alone(site):
    site.add("WEB-12")
    assert assign("WEB-12", "none").summary == "WEB-12 is already unassigned."
    assert site.writes == []


def test_an_issue_that_is_not_there_is_named(site):
    with pytest.raises(Precondition) as raised:
        assign("WEB-404")
    assert raised.value.message == "No issue WEB-404."


def test_the_command_line_takes_the_key_and_who(site, capsys):
    site.person("a-1", "Alice Smith", "alice@example.com")
    site.add("WEB-12")
    assert main(["assign", "WEB-12", "alice@example.com"]) == 0
    assert capsys.readouterr().out.startswith("✅ Assigned WEB-12 to Alice Smith.\n")
