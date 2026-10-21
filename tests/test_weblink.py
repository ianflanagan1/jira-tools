"""jira weblink: an issue linked to a web page, such as a pull request, against a fake Jira
site."""

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.weblink import weblink

SITE = "https://me.atlassian.net"
PULL = "https://github.com/me/web/pull/42"


@pytest.fixture
def issue(site):
    site.add("WEB-12")
    return site


def links(site) -> list[tuple[str, str]]:
    return [(link["object"]["url"], link["object"]["title"]) for link in site.web_links["WEB-12"]]


def test_links_the_issue_to_the_url_with_the_title_and_gives_its_url(issue):
    result = weblink("WEB-12", PULL, "Follow symlinks")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        f"Linked WEB-12 to {PULL}.",
        f"{SITE}/browse/WEB-12",
    )
    assert links(issue) == [(PULL, "Follow symlinks")]


def test_the_title_defaults_to_the_url(issue):
    weblink("WEB-12", PULL)
    assert links(issue) == [(PULL, PULL)]


@pytest.mark.parametrize("url", ["ftp://example.com/file", "example.com", "https://", "PR 42"])
def test_a_url_that_is_not_a_web_address_is_refused(issue, url):
    with pytest.raises(Precondition) as raised:
        weblink("WEB-12", url)
    assert [raised.value.message, *raised.value.details] == [
        f"{url!r} isn't a web address.",
        "Give one starting http:// or https://.",
    ]
    assert issue.writes == []


def test_a_url_already_linked_with_the_title_is_left_alone(issue):
    issue.web_link("WEB-12", PULL, "Follow symlinks")
    result = weblink("WEB-12", PULL, "Follow symlinks")
    assert isinstance(result, NothingToDo)
    assert result.summary == f"WEB-12 already links to {PULL}."
    assert issue.writes == []


def test_a_url_already_linked_with_another_title_is_retitled(issue):
    issue.web_link("WEB-12", "https://example.com", "Docs")
    issue.web_link("WEB-12", PULL, "PR 42", global_id="github=42")
    result = weblink("WEB-12", PULL, "Follow symlinks")
    assert isinstance(result, Done)
    assert result.summary == f"Retitled WEB-12's link to {PULL}: Follow symlinks."
    assert links(issue) == [("https://example.com", "Docs"), (PULL, "Follow symlinks")]
    assert issue.web_links["WEB-12"][1]["globalId"] == "github=42"


def test_an_issue_that_is_not_there_is_named(issue):
    with pytest.raises(Precondition) as raised:
        weblink("WEB-404", PULL)
    assert raised.value.message == "No issue WEB-404."
    assert issue.writes == []


@pytest.mark.parametrize("key", ["web-12", "12", f"{SITE}/browse/WEB-12"])
def test_the_issue_can_be_named_by_its_key_number_or_url(issue, key):
    assert weblink(key, PULL).summary == f"Linked WEB-12 to {PULL}."


def test_the_command_line_takes_the_key_url_and_title(issue, capsys):
    assert main(["weblink", "WEB-12", PULL, "Follow symlinks"]) == 0
    assert capsys.readouterr().out == f"✅ Linked WEB-12 to {PULL}.\n{SITE}/browse/WEB-12\n"
    assert links(issue) == [(PULL, "Follow symlinks")]
