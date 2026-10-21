"""jira unweblink: an issue's web links to a URL removed, against a fake Jira site."""

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.unweblink import unweblink

SITE = "https://me.atlassian.net"
PULL = "https://github.com/me/web/pull/42"


@pytest.fixture
def issue(site):
    site.add("WEB-12")
    return site


def urls(site) -> list[str]:
    return [link["object"]["url"] for link in site.web_links["WEB-12"]]


def test_removes_the_issues_link_to_the_url_and_gives_its_url(issue):
    issue.web_link("WEB-12", PULL, "PR 42")
    issue.web_link("WEB-12", "https://example.com", "Docs")
    result = unweblink("WEB-12", PULL)
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        f"Removed WEB-12's link to {PULL}.",
        f"{SITE}/browse/WEB-12",
    )
    assert urls(issue) == ["https://example.com"]


def test_removes_every_link_to_the_url(issue):
    issue.web_link("WEB-12", PULL, "PR 42")
    issue.web_link("WEB-12", PULL, "Pull request", global_id="github=42")
    result = unweblink("WEB-12", PULL)
    assert result.summary == f"Removed WEB-12's 2 links to {PULL}."
    assert urls(issue) == []


def test_an_issue_without_a_link_to_the_url_is_left_alone(issue):
    issue.web_link("WEB-12", "https://example.com", "Docs")
    result = unweblink("WEB-12", PULL)
    assert isinstance(result, NothingToDo)
    assert result.summary == f"WEB-12 has no link to {PULL}."
    assert issue.writes == []


def test_an_issue_that_is_not_there_is_named(issue):
    with pytest.raises(Precondition) as raised:
        unweblink("WEB-404", PULL)
    assert raised.value.message == "No issue WEB-404."


@pytest.mark.parametrize("key", ["web-12", "12", f"{SITE}/browse/WEB-12"])
def test_the_issue_can_be_named_by_its_key_number_or_url(issue, key):
    issue.web_link("WEB-12", PULL, "PR 42")
    assert isinstance(unweblink(key, PULL), Done)


def test_the_command_line_takes_the_key_and_url(issue, capsys):
    issue.web_link("WEB-12", PULL, "PR 42")
    assert main(["unweblink", "WEB-12", PULL]) == 0
    assert capsys.readouterr().out.startswith(f"✅ Removed WEB-12's link to {PULL}.\n")
