"""Naming an issue on the command line: by its key, by its number in the set space, or by its
URL."""

import pytest
from cli_kit.outcome import Precondition

from jira_tools.keys import issue_key


@pytest.mark.parametrize("text", ["WEB-12", "web-12", " WEB-12 ", "WEB-012"])
def test_a_key_is_taken_in_any_case(text):
    assert issue_key(text, "WEB") == "WEB-12"


def test_a_key_in_another_space_is_kept():
    assert issue_key("OPS-3", "WEB") == "OPS-3"


def test_a_number_alone_is_an_issue_in_the_set_space():
    assert issue_key("12", "web") == "WEB-12"


def test_an_issues_url_names_it():
    assert issue_key("https://me.atlassian.net/browse/WEB-12?focusedCommentId=1", "X") == "WEB-12"


@pytest.mark.parametrize("text", ["", "WEB", "WEB-", "-12", "WEB-12a", "12-WEB"])
def test_anything_else_is_refused(text):
    with pytest.raises(Precondition) as raised:
        issue_key(text, "WEB")
    assert raised.value.message == f"{text.strip()!r} isn't an issue key."
