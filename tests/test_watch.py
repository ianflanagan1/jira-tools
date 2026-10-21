"""jira watch: you, or someone else, added to an issue's watchers, against a fake Jira site."""

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.watch import watch

SITE = "https://me.atlassian.net"


def test_adds_you_to_the_watchers_by_default_and_gives_the_issues_url(site):
    site.add("WEB-12")
    result = watch("WEB-12")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == ("You're watching WEB-12.", f"{SITE}/browse/WEB-12")
    assert site.watchers["WEB-12"] == ["me-1"]


def test_adds_the_one_person_whose_name_or_email_matches(site):
    site.person("a-1", "Alice Smith", "alice@example.com")
    site.add("WEB-12")
    assert watch("WEB-12", "alice@").summary == "Alice Smith is watching WEB-12."
    assert site.watchers["WEB-12"] == ["a-1"]


def test_someone_already_watching_is_left_alone(site):
    site.add("WEB-12")
    site.watchers["WEB-12"] = ["me-1"]
    result = watch("WEB-12", "ME")
    assert isinstance(result, NothingToDo)
    assert result.summary == "You're already watching WEB-12."
    assert site.writes == []


def test_none_is_refused(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        watch("WEB-12", "none")
    assert [raised.value.message, *raised.value.details] == [
        "None isn't a person.",
        "Name me, the default, or someone by their name or email.",
    ]
    assert site.writes == []


def test_no_match_is_said(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        watch("WEB-12", "zed")
    assert raised.value.message == "No one in Jira matches 'zed'."


def test_an_issue_that_is_not_there_is_named(site):
    with pytest.raises(Precondition) as raised:
        watch("WEB-404")
    assert raised.value.message == "No issue WEB-404."


def test_the_command_line_takes_the_key_and_who(site, capsys):
    site.person("a-1", "Alice Smith", "alice@example.com")
    site.add("WEB-12")
    assert main(["watch", "12", "alice@example.com"]) == 0
    assert capsys.readouterr().out.startswith("✅ Alice Smith is watching WEB-12.\n")


def test_you_already_watching_is_seen_when_jira_withholds_who_else_watches(site):
    site.add("WEB-12")
    site.watchers["WEB-12"] = ["me-1"]
    site.watchers_hidden = True
    assert isinstance(watch("WEB-12"), NothingToDo)
    assert site.writes == []
