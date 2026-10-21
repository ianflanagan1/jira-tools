"""Naming a priority, issue type, component or version, or a date: each matched against those the
space has, against a fake Jira site."""

import pytest
from cli_kit.outcome import Precondition

from jira_tools import choices, session
from jira_tools.api import IssueType


@pytest.fixture
def jira(site):
    return session.connect(site.settings)


def test_a_priority_is_matched_ignoring_case_and_named_as_jira_names_it(jira):
    assert choices.priority(jira, "WEB", " high ") == "High"


def test_a_priority_the_space_lacks_names_those_it_has(jira):
    with pytest.raises(Precondition) as raised:
        choices.priority(jira, "WEB", "Urgent")
    assert [raised.value.message, *raised.value.details] == [
        "WEB has no priority 'Urgent'.",
        "It has: Highest, High, Medium, Low, Lowest.",
    ]


def test_an_issue_type_is_matched_ignoring_case(jira):
    assert choices.issue_type(jira, "WEB", "SUBTASK") == IssueType("10003", "Subtask", True)


def test_an_issue_type_the_space_lacks_names_those_it_has(jira):
    with pytest.raises(Precondition) as raised:
        choices.issue_type(jira, "WEB", "Sub-task")
    assert [raised.value.message, *raised.value.details] == [
        "WEB has no issue type 'Sub-task'.",
        "It has: Task, Bug, Subtask.",
    ]


def test_components_are_each_matched_and_named_once(jira):
    assert choices.components(jira, "WEB", ["api", "Scanner", "API"]) == ["API", "Scanner"]


def test_no_components_reads_nothing_from_jira(site, jira):
    site.components = None
    assert choices.components(jira, "WEB", []) == []


def test_a_component_the_space_lacks_names_those_it_has(jira):
    with pytest.raises(Precondition) as raised:
        choices.components(jira, "WEB", ["Scanner", "Parser"])
    assert [raised.value.message, *raised.value.details] == [
        "WEB has no component 'Parser'.",
        "It has: Scanner, API.",
    ]


def test_a_space_without_components_says_so(site, jira):
    site.components = []
    with pytest.raises(Precondition) as raised:
        choices.components(jira, "WEB", ["Parser"])
    assert raised.value.details == ("It has none.",)


def test_versions_are_matched_among_those_not_archived(jira):
    assert choices.versions(jira, "WEB", ["1.2"]) == ["1.2"]
    with pytest.raises(Precondition) as raised:
        choices.versions(jira, "WEB", ["1.0"])
    assert [raised.value.message, *raised.value.details] == [
        "WEB has no version '1.0'.",
        "It has: 1.1, 1.2.",
    ]


def test_a_date_is_a_day_written_year_month_day():
    assert choices.date(" 2026-10-31 ", "--due") == "2026-10-31"


@pytest.mark.parametrize("given", ["31/10/2026", "2026-02-30", "2026-1-5", "tomorrow"])
def test_anything_else_is_not_a_date(given):
    with pytest.raises(Precondition) as raised:
        choices.date(given, "--due")
    assert [raised.value.message, *raised.value.details] == [
        f"--due takes a date as YYYY-MM-DD, such as 2026-10-31, not {given!r}."
    ]
