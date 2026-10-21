"""jira unwatch: you, or someone else, removed from an issue's watchers, against a fake Jira
site."""

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.unwatch import unwatch

SITE = "https://me.atlassian.net"


def test_removes_you_from_the_watchers_by_default_and_gives_the_issues_url(site):
    site.person("a-1", "Alice Smith")
    site.add("WEB-12")
    site.watchers["WEB-12"] = ["a-1", "me-1"]
    result = unwatch("WEB-12")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "You're no longer watching WEB-12.",
        f"{SITE}/browse/WEB-12",
    )
    assert site.watchers["WEB-12"] == ["a-1"]


def test_removes_the_one_person_whose_name_or_email_matches(site):
    site.person("a-1", "Alice Smith", "alice@example.com")
    site.add("WEB-12")
    site.watchers["WEB-12"] = ["a-1"]
    assert unwatch("WEB-12", "alice").summary == "Alice Smith is no longer watching WEB-12."
    assert site.watchers["WEB-12"] == []


def test_someone_not_watching_is_left_alone(site):
    site.person("a-1", "Alice Smith")
    site.add("WEB-12")
    site.watchers["WEB-12"] = ["me-1"]
    result = unwatch("WEB-12", "Alice Smith")
    assert isinstance(result, NothingToDo)
    assert result.summary == "Alice Smith isn't watching WEB-12."
    assert site.writes == []


def test_you_not_watching_are_left_alone(site):
    site.add("WEB-12")
    assert unwatch("WEB-12").summary == "You aren't watching WEB-12."


def test_none_is_refused(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        unwatch("WEB-12", "none")
    assert raised.value.message == "None isn't a person."
    assert site.writes == []


def test_an_issue_that_is_not_there_is_named(site):
    with pytest.raises(Precondition) as raised:
        unwatch("WEB-404")
    assert raised.value.message == "No issue WEB-404."


def test_the_command_line_takes_the_key_and_who(site, capsys):
    site.add("WEB-12")
    site.watchers["WEB-12"] = ["me-1"]
    assert main(["unwatch", "WEB-12", "me"]) == 0
    assert capsys.readouterr().out.startswith("✅ You're no longer watching WEB-12.\n")


def test_you_are_removed_when_jira_withholds_who_else_watches(site):
    site.add("WEB-12")
    site.watchers["WEB-12"] = ["me-1"]
    site.watchers_hidden = True
    assert isinstance(unwatch("WEB-12"), Done)
    assert site.watchers["WEB-12"] == []


def test_someone_else_cannot_be_judged_when_jira_withholds_who_watches(site):
    site.person("a-1", "Alice Smith", "alice@example.com")
    site.add("WEB-12")
    site.watchers_hidden = True
    with pytest.raises(Precondition) as raised:
        unwatch("WEB-12", "alice@example.com")
    assert raised.value.message == "Jira won't say who watches WEB-12."
    assert site.writes == []
