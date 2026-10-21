"""Jira Cloud's REST API: finding, reading, creating, commenting on, attaching files to, moving,
assigning, linking and watching issues, linking them to web pages, and logging time on them."""

import base64
import email
import email.policy
import io
import json
import urllib.error
import urllib.request

import pytest
from cli_kit.credentials import Credential
from cli_kit.outcome import Failure, Precondition

from jira_tools import api
from jira_tools.api import (
    Forbidden,
    Issue,
    IssueType,
    Jira,
    LinkType,
    NotFound,
    Transition,
    User,
    Watchers,
)

SITE = "https://me.atlassian.net"
CREDENTIAL = Credential("me@example.com", "the-token")


class FakeJira:
    """What _send was asked, and the answers it gives in turn."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []
        self.answers: list = []
        self.auth: set[str] = set()

    def send(self, method: str, url: str, auth: str, body: dict | None) -> dict | list:
        self.sent.append((method, url, body))
        if isinstance(self.answers[0], Exception):
            raise self.answers.pop(0)
        self.auth.add(auth)
        return self.answers.pop(0)

    def upload(self, url: str, auth: str, name: str, content: bytes) -> list:
        return self.send("POST", url, auth, {"file": (name, content)})


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeJira:
    fake = FakeJira()
    monkeypatch.setattr(api, "_send", fake.send)
    monkeypatch.setattr(api, "_upload", fake.upload)
    return fake


def found(*summaries: str, next_page: str | None = None) -> dict:
    answer = {
        "issues": [
            {"key": f"WEB-{n}", "fields": {"summary": summary}}
            for n, summary in enumerate(summaries, 1)
        ]
    }
    if next_page:
        answer["nextPageToken"] = next_page
    return answer


def find(summary: str = "Scan skips symlinks", labels: tuple[str, ...] = ("deferred",)):
    return Jira(SITE, CREDENTIAL).find_open("WEB", labels, summary)


def test_searches_the_spaces_open_issues_with_every_label(fake):
    fake.answers = [found()]
    find(labels=("deferred", "review"))
    assert fake.sent == [
        (
            "POST",
            f"{SITE}/rest/api/3/search/jql",
            {
                "jql": 'project = "WEB" AND statusCategory != Done'
                ' AND labels = "deferred" AND labels = "review"',
                "fields": ["summary"],
                "maxResults": 100,
            },
        )
    ]


def test_without_labels_it_searches_all_the_spaces_open_issues(fake):
    fake.answers = [found()]
    find(labels=())
    assert fake.sent[0][2]["jql"] == 'project = "WEB" AND statusCategory != Done'


def test_quotes_in_a_label_are_escaped(fake):
    fake.answers = [found()]
    find(labels=('say "hi" \\',))
    assert fake.sent[0][2]["jql"].endswith(' AND labels = "say \\"hi\\" \\\\"')


def test_finds_the_issue_whose_summary_matches_ignoring_case_and_surrounding_space(fake):
    fake.answers = [found("Scan skips files", "  scan SKIPS symlinks ")]
    assert find() == Issue("WEB-2", f"{SITE}/browse/WEB-2")


def test_finds_nothing_when_no_summary_matches(fake):
    fake.answers = [found("Scan skips files")]
    assert find() is None


def test_reads_every_page_of_results(fake):
    fake.answers = [found("Other", next_page="p2"), found("Scan skips symlinks")]
    assert find() == Issue("WEB-1", f"{SITE}/browse/WEB-1")
    assert fake.sent[1][2]["nextPageToken"] == "p2"


def test_creates_an_issue_with_its_fields(fake):
    fake.answers = [{"id": "10001", "key": "WEB-7"}]
    description = {"type": "doc", "version": 1, "content": []}
    issue = Jira(SITE, CREDENTIAL).create("WEB", "Task", ("deferred",), "Fix it", description)
    assert issue == Issue("WEB-7", f"{SITE}/browse/WEB-7")
    assert fake.sent == [
        (
            "POST",
            f"{SITE}/rest/api/3/issue",
            {
                "fields": {
                    "project": {"key": "WEB"},
                    "issuetype": {"name": "Task"},
                    "summary": "Fix it",
                    "labels": ["deferred"],
                    "description": description,
                }
            },
        )
    ]


def test_creates_an_issue_with_more_fields(fake):
    fake.answers = [{"id": "10001", "key": "WEB-7"}]
    more = {"priority": {"name": "High"}}
    jira().create("WEB", "Task", (), "Fix it", None, more)
    assert fake.sent[0][2]["fields"]["priority"] == {"name": "High"}


def test_edits_more_fields_and_their_changes(fake):
    fake.answers = [{}]
    more = {"priority": {"name": "High"}}
    update = {"components": [{"add": {"name": "API"}}]}
    jira().edit("WEB-1", None, None, (), (), more, update)
    assert fake.sent == [
        ("PUT", f"{SITE}/rest/api/3/issue/WEB-1", {"fields": more, "update": update})
    ]


STORY_POINTS = {
    "name": "Story points",
    "required": False,
    "schema": {
        "type": "number",
        "custom": "com.atlassian.jira.plugin.system.customfieldtypes:float",
    },
}


def test_reads_the_fields_an_issues_edit_screen_can_set_by_id(fake):
    fake.answers = [{"fields": {"customfield_10016": STORY_POINTS}}]
    assert jira().edit_meta("WEB-1") == {"customfield_10016": STORY_POINTS}
    assert fake.sent == [("GET", f"{SITE}/rest/api/3/issue/WEB-1/editmeta", None)]


def test_reads_every_page_of_the_issue_types_a_space_can_create_saying_which_are_subtasks(fake):
    bug = {"id": "1", "name": "Bug", "subtask": False, "hierarchyLevel": 0}
    subtask = {"id": "3", "name": "Subtask", "subtask": True, "hierarchyLevel": -1}
    fake.answers = [
        {"issueTypes": [bug], "startAt": 0, "maxResults": 1, "total": 2},
        {"issueTypes": [subtask], "startAt": 1, "maxResults": 1, "total": 2},
    ]
    assert jira().issue_types("WEB") == [
        IssueType("1", "Bug", subtask=False),
        IssueType("3", "Subtask", subtask=True),
    ]
    base = f"{SITE}/rest/api/3/issue/createmeta/WEB/issuetypes"
    assert [url for _, url, _ in fake.sent] == [
        f"{base}?startAt=0&maxResults=50",
        f"{base}?startAt=1&maxResults=50",
    ]


def test_reads_every_page_of_the_fields_a_types_create_screen_can_set_by_id(fake):
    points = {"fieldId": "customfield_10016", **STORY_POINTS}
    summary = {"fieldId": "summary", "name": "Summary", "schema": {"type": "string"}}
    fake.answers = [
        {"fields": [points], "startAt": 0, "maxResults": 1, "total": 2},
        {"fields": [summary], "startAt": 1, "maxResults": 1, "total": 2},
    ]
    assert jira().create_meta("WEB", "10001") == {"customfield_10016": points, "summary": summary}
    base = f"{SITE}/rest/api/3/issue/createmeta/WEB/issuetypes/10001"
    assert fake.sent[1][1] == f"{base}?startAt=1&maxResults=50"


def test_reads_the_active_and_future_sprints_of_the_spaces_scrum_boards(fake):
    fake.answers = [
        {
            "values": [{"id": 1, "type": "scrum"}, {"id": 2, "type": "kanban"}],
            "isLast": False,
        },
        {"values": [{"id": 3, "type": "scrum"}], "isLast": True},
        {"values": [{"id": 37, "name": "Sprint 4", "state": "active"}], "isLast": True},
        {"values": [{"id": 38, "name": "Sprint 5", "state": "future"}], "isLast": True},
    ]
    assert jira().sprints("WEB") == [
        {"id": 37, "name": "Sprint 4", "state": "active"},
        {"id": 38, "name": "Sprint 5", "state": "future"},
    ]
    agile = f"{SITE}/rest/agile/1.0"
    assert [url for _, url, _ in fake.sent] == [
        f"{agile}/board?projectKeyOrId=WEB&startAt=0&maxResults=50",
        f"{agile}/board?projectKeyOrId=WEB&startAt=2&maxResults=50",
        f"{agile}/board/1/sprint?state=active%2Cfuture&startAt=0&maxResults=50",
        f"{agile}/board/3/sprint?state=active%2Cfuture&startAt=0&maxResults=50",
    ]


def test_signs_in_with_the_email_and_token(fake):
    fake.answers = [found()]
    find()
    expected = base64.b64encode(b"me@example.com:the-token").decode()
    assert fake.auth == {f"Basic {expected}"}


def jira() -> Jira:
    return Jira(SITE, CREDENTIAL)


def test_lists_the_open_issues_assigned_to_you_in_a_space_most_recently_updated_first(fake):
    fake.answers = [{"issues": [{"key": "WEB-3", "fields": {}}], "nextPageToken": "p2"}, found()]
    assert jira().open_assigned_to_me("WEB") == [{"key": "WEB-3", "fields": {}}]
    assert fake.sent[0][2] == {
        "jql": 'project = "WEB" AND assignee = currentUser() AND statusCategory != Done'
        " ORDER BY updated DESC",
        "fields": ["summary", "status", "issuetype"],
        "maxResults": 100,
    }
    assert fake.sent[1][2]["nextPageToken"] == "p2"


def test_reads_you_as_a_user(fake):
    fake.answers = [{"accountId": "a1", "displayName": "Ian", "emailAddress": "me@example.com"}]
    assert jira().myself() == User("a1", "Ian", "me@example.com")
    assert fake.sent == [("GET", f"{SITE}/rest/api/3/myself", None)]


def test_reads_an_issue_with_every_field_and_their_names_and_schemas(fake):
    fake.answers = [{"key": "WEB-1", "fields": {}, "names": {}, "schema": {}}]
    assert jira().issue("WEB-1") == {"key": "WEB-1", "fields": {}, "names": {}, "schema": {}}
    assert fake.sent == [
        ("GET", f"{SITE}/rest/api/3/issue/WEB-1?fields=*all&expand=names,schema", None)
    ]


def test_an_issue_that_is_not_there_is_none(fake):
    fake.answers = [NotFound("Jira answered 404.")]
    assert jira().issue("WEB-404") is None


def test_reads_every_comment_oldest_first(fake):
    fake.answers = [
        {"comments": [{"id": "1"}, {"id": "2"}], "startAt": 0, "total": 3},
        {"comments": [{"id": "3"}], "startAt": 2, "total": 3},
    ]
    assert jira().comments("WEB-1") == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    base = f"{SITE}/rest/api/3/issue/WEB-1/comment?orderBy=created&maxResults=100"
    assert [url for _, url, _ in fake.sent] == [f"{base}&startAt=0", f"{base}&startAt=2"]


def test_the_comments_of_an_issue_that_is_not_there_are_none(fake):
    fake.answers = [NotFound("Jira answered 404.")]
    assert jira().comments("WEB-404") is None


def test_adds_a_comment_and_gives_its_url(fake):
    fake.answers = [{"id": "10050"}]
    body = {"type": "doc", "version": 1, "content": []}
    url = jira().add_comment("WEB-1", body)
    assert url == f"{SITE}/browse/WEB-1?focusedCommentId=10050"
    assert fake.sent == [("POST", f"{SITE}/rest/api/3/issue/WEB-1/comment", {"body": body})]


def test_replaces_a_comments_body(fake):
    fake.answers = [{"id": "10050"}]
    body = {"type": "doc", "version": 1, "content": []}
    url = jira().edit_comment("WEB-1", "10050", body)
    assert url == f"{SITE}/browse/WEB-1?focusedCommentId=10050"
    assert fake.sent == [("PUT", f"{SITE}/rest/api/3/issue/WEB-1/comment/10050", {"body": body})]


def test_deletes_a_comment(fake):
    fake.answers = [{}]
    jira().delete_comment("WEB-1", "10050")
    assert fake.sent == [("DELETE", f"{SITE}/rest/api/3/issue/WEB-1/comment/10050", None)]


def test_attaches_a_file_and_gives_the_attachment(fake):
    attachment = {"id": "10001", "filename": "trace.txt", "size": 5}
    fake.answers = [[attachment]]
    assert jira().attach("WEB-1", "trace.txt", b"trace") == attachment
    assert fake.sent == [
        ("POST", f"{SITE}/rest/api/3/issue/WEB-1/attachments", {"file": ("trace.txt", b"trace")})
    ]


RESOLUTION = {
    "required": True,
    "schema": {"type": "resolution", "system": "resolution"},
    "name": "Resolution",
    "hasDefaultValue": False,
    "operations": ["set"],
    "allowedValues": [{"id": "1", "name": "Done"}, {"id": "2", "name": "Won't Do"}],
}


def test_lists_the_moves_an_issue_can_make_by_the_status_each_reaches(fake):
    fake.answers = [{"transitions": [{"id": "21", "name": "Start", "to": {"name": "In Progress"}}]}]
    assert jira().transitions("WEB-1") == [Transition("21", "In Progress")]
    assert fake.sent == [
        ("GET", f"{SITE}/rest/api/3/issue/WEB-1/transitions?expand=transitions.fields", None)
    ]


def test_each_move_carries_its_screens_fields_as_jira_gives_them(fake):
    fields = {"resolution": RESOLUTION}
    move = {"id": "31", "name": "Finish", "to": {"name": "Done"}, "fields": fields}
    fake.answers = [{"transitions": [move]}]
    [transition] = jira().transitions("WEB-1")
    assert transition.fields == fields


def test_a_move_without_a_screen_has_no_fields(fake):
    fake.answers = [{"transitions": [{"id": "21", "name": "Start", "to": {"name": "In Progress"}}]}]
    assert jira().transitions("WEB-1")[0].fields == {}


def test_moves_are_equal_by_their_id_and_status_whatever_their_fields(fake):
    assert Transition("31", "Done", {"resolution": RESOLUTION}) == Transition("31", "Done")


def test_moves_an_issue_by_a_transition(fake):
    fake.answers = [{}]
    jira().transition("WEB-1", Transition("21", "In Progress"))
    assert fake.sent == [
        ("POST", f"{SITE}/rest/api/3/issue/WEB-1/transitions", {"transition": {"id": "21"}})
    ]


def test_moves_an_issue_setting_fields_and_making_changes_as_it_moves(fake):
    fake.answers = [{}]
    fields = {"resolution": {"name": "Done"}}
    update = {"comment": [{"add": {"body": {"type": "doc", "version": 1, "content": []}}}]}
    jira().transition("WEB-1", Transition("31", "Done"), fields=fields, update=update)
    body = {"transition": {"id": "31"}, "fields": fields, "update": update}
    assert fake.sent == [("POST", f"{SITE}/rest/api/3/issue/WEB-1/transitions", body)]


@pytest.mark.parametrize("account", ["a1", None])
def test_assigns_an_issue_or_unassigns_it(fake, account):
    fake.answers = [{}]
    jira().assign("WEB-1", account)
    assert fake.sent == [("PUT", f"{SITE}/rest/api/3/issue/WEB-1/assignee", {"accountId": account})]


def test_lists_the_link_types_by_how_each_reads_both_ways(fake):
    blocks = {"id": "1", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"}
    fake.answers = [{"issueLinkTypes": [blocks | {"self": "..."}]}]
    assert jira().link_types() == [LinkType("1", "Blocks", "is blocked by", "blocks")]
    assert fake.sent == [("GET", f"{SITE}/rest/api/3/issueLinkType", None)]


def test_links_two_issues_by_a_link_type(fake):
    fake.answers = [{}]
    jira().link("Blocks", "WEB-9", "WEB-12")
    assert fake.sent == [
        (
            "POST",
            f"{SITE}/rest/api/3/issueLink",
            {
                "type": {"name": "Blocks"},
                "inwardIssue": {"key": "WEB-9"},
                "outwardIssue": {"key": "WEB-12"},
            },
        )
    ]


def test_removes_a_link_by_its_id(fake):
    fake.answers = [{}]
    jira().unlink("20001")
    assert fake.sent == [("DELETE", f"{SITE}/rest/api/3/issueLink/20001", None)]


def test_lists_the_priorities_a_space_has_from_every_page(fake):
    def page(*names: str, last: bool) -> dict:
        return {"values": [{"id": n, "name": n} for n in names], "isLast": last}

    fake.answers = [{"id": "10000", "key": "WEB"}, page("High", "Medium", last=False)]
    fake.answers.append(page("Low", last=True))
    assert jira().priorities("WEB") == ["High", "Medium", "Low"]
    assert [url for method, url, body in fake.sent] == [
        f"{SITE}/rest/api/3/project/WEB",
        f"{SITE}/rest/api/3/priority/search?projectId=10000&startAt=0&maxResults=50",
        f"{SITE}/rest/api/3/priority/search?projectId=10000&startAt=2&maxResults=50",
    ]


def test_lists_a_spaces_components(fake):
    fake.answers = [[{"id": "1", "name": "Scanner"}, {"id": "2", "name": "API"}]]
    assert jira().components("WEB") == ["Scanner", "API"]
    assert fake.sent == [("GET", f"{SITE}/rest/api/3/project/WEB/components", None)]


def test_lists_a_spaces_versions_but_not_those_archived(fake):
    fake.answers = [
        [
            {"id": "1", "name": "1.0", "archived": True, "released": True},
            {"id": "2", "name": "1.1", "archived": False, "released": True},
            {"id": "3", "name": "1.2", "archived": False, "released": False},
        ]
    ]
    assert jira().versions("WEB") == ["1.1", "1.2"]
    assert fake.sent == [("GET", f"{SITE}/rest/api/3/project/WEB/versions", None)]


def test_lists_an_issues_web_links(fake):
    pull = {"id": 10000, "globalId": "g", "object": {"url": "https://x/pr/1", "title": "PR 1"}}
    fake.answers = [[pull]]
    assert jira().web_links("WEB-1") == [pull]
    assert fake.sent == [("GET", f"{SITE}/rest/api/3/issue/WEB-1/remotelink", None)]


def test_adds_a_web_link_whose_global_id_is_its_url(fake):
    fake.answers = [{"id": 10000, "self": "..."}]
    jira().add_web_link("WEB-1", "https://x/pr/1", "PR 1")
    assert fake.sent == [
        (
            "POST",
            f"{SITE}/rest/api/3/issue/WEB-1/remotelink",
            {"globalId": "https://x/pr/1", "object": {"url": "https://x/pr/1", "title": "PR 1"}},
        )
    ]


def test_a_url_too_long_to_be_a_global_id_is_added_without_one(fake):
    fake.answers = [{"id": 10000, "self": "..."}]
    url = "https://x/" + "a" * 246
    jira().add_web_link("WEB-1", url, "Long")
    assert fake.sent[0][2] == {"object": {"url": url, "title": "Long"}}


def test_retitles_a_web_link_keeping_the_rest_of_it(fake):
    fake.answers = [{}]
    link = {
        "id": 10000,
        "self": f"{SITE}/rest/api/3/issue/WEB-1/remotelink/10000",
        "globalId": "github=1",
        "relationship": "mentioned in",
        "application": {"type": "com.github", "name": "GitHub"},
        "object": {"url": "https://x/pr/1", "title": "PR 1", "icon": {"url16x16": "i.png"}},
    }
    jira().retitle_web_link("WEB-1", link, "Pull request 1")
    assert fake.sent == [
        (
            "PUT",
            f"{SITE}/rest/api/3/issue/WEB-1/remotelink/10000",
            {
                "globalId": "github=1",
                "relationship": "mentioned in",
                "application": {"type": "com.github", "name": "GitHub"},
                "object": {
                    "url": "https://x/pr/1",
                    "title": "Pull request 1",
                    "icon": {"url16x16": "i.png"},
                },
            },
        )
    ]


def test_removes_a_web_link_by_its_id(fake):
    fake.answers = [{}]
    jira().remove_web_link("WEB-1", 10000)
    assert fake.sent == [("DELETE", f"{SITE}/rest/api/3/issue/WEB-1/remotelink/10000", None)]


def test_finds_the_active_people_whose_name_or_email_matches(fake):
    fake.answers = [
        [
            {"accountId": "a1", "displayName": "Alice", "accountType": "atlassian", "active": True},
            {
                "accountId": "a2",
                "displayName": "Al Gone",
                "accountType": "atlassian",
                "active": False,
            },
            {"accountId": "a3", "displayName": "Alert bot", "accountType": "app", "active": True},
        ]
    ]
    assert jira().find_users("al ice") == [User("a1", "Alice", None)]
    assert fake.sent == [("GET", f"{SITE}/rest/api/3/user/search?query=al+ice&maxResults=50", None)]


def test_reads_every_worklog_oldest_first(fake):
    fake.answers = [
        {"worklogs": [{"id": "1"}, {"id": "2"}], "startAt": 0, "total": 3},
        {"worklogs": [{"id": "3"}], "startAt": 2, "total": 3},
    ]
    assert jira().worklogs("WEB-1") == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    base = f"{SITE}/rest/api/3/issue/WEB-1/worklog?maxResults=1000"
    assert [url for _, url, _ in fake.sent] == [f"{base}&startAt=0", f"{base}&startAt=2"]


def test_the_worklogs_of_an_issue_that_is_not_there_are_none(fake):
    fake.answers = [NotFound("Jira answered 404.")]
    assert jira().worklogs("WEB-404") is None


def test_logs_work_leaving_the_remaining_estimate_to_jira_and_gives_its_url(fake):
    fake.answers = [{"id": "10070"}]
    worklog = {"timeSpent": "1h 30m", "started": "2026-10-14T09:00:00.000+0100"}
    url = jira().add_worklog("WEB-1", worklog, None)
    assert url == f"{SITE}/browse/WEB-1?focusedWorklogId=10070"
    assert fake.sent == [("POST", f"{SITE}/rest/api/3/issue/WEB-1/worklog", worklog)]


def test_logs_work_setting_the_remaining_estimate(fake):
    fake.answers = [{"id": "10070"}]
    jira().add_worklog("WEB-1", {"timeSpent": "1h"}, "2d 4h")
    assert fake.sent[0][1] == (
        f"{SITE}/rest/api/3/issue/WEB-1/worklog?adjustEstimate=new&newEstimate=2d+4h"
    )


def test_reads_the_seconds_in_each_unit_of_time_by_the_sites_working_day_and_week(fake):
    tracking = {"workingHoursPerDay": 7.5, "workingDaysPerWeek": 4.0, "timeFormat": "pretty"}
    fake.answers = [{"timeTrackingEnabled": True, "timeTrackingConfiguration": tracking}]
    day = int(7.5 * 3600)
    assert jira().time_units() == {"w": 4 * day, "d": day, "h": 3600, "m": 60}
    assert fake.sent == [("GET", f"{SITE}/rest/api/3/configuration", None)]


def test_without_time_tracking_settings_a_day_is_8_hours_and_a_week_5_days(fake):
    fake.answers = [{"timeTrackingEnabled": False}]
    assert jira().time_units() == {"w": 5 * 8 * 3600, "d": 8 * 3600, "h": 3600, "m": 60}


def test_lists_the_account_ids_of_an_issues_watchers(fake):
    fake.answers = [{"isWatching": True, "watchCount": 2, "watchers": [{"accountId": "a1"}]}]
    assert jira().watchers("WEB-1") == Watchers(("a1",), you=True)
    assert fake.sent == [("GET", f"{SITE}/rest/api/3/issue/WEB-1/watchers", None)]


def test_watchers_jira_withholds_are_none_but_it_still_says_whether_you_watch(fake):
    # Without permission to see who watches an issue, Jira leaves the list out.
    fake.answers = [{"isWatching": True, "watchCount": 2}]
    assert jira().watchers("WEB-1") == Watchers(None, you=True)


def test_the_watchers_of_an_issue_that_is_not_there_are_none(fake):
    fake.answers = [NotFound("Jira answered 404.")]
    assert jira().watchers("WEB-404") is None


def test_adds_a_watcher_by_sending_their_account_id_as_a_json_string(fake):
    fake.answers = [{}]
    jira().watch("WEB-1", "a1")
    assert fake.sent == [("POST", f"{SITE}/rest/api/3/issue/WEB-1/watchers", "a1")]


def test_removes_a_watcher_by_their_account_id(fake):
    fake.answers = [{}]
    jira().unwatch("WEB-1", "a 1")
    assert fake.sent == [("DELETE", f"{SITE}/rest/api/3/issue/WEB-1/watchers?accountId=a+1", None)]


def test_a_key_is_quoted_in_the_url(fake):
    fake.answers = [{}]
    jira().transition("WEB 1/x", Transition("1", "Done"))
    assert fake.sent[0][1] == f"{SITE}/rest/api/3/issue/WEB%201%2Fx/transitions"


# _send, with urllib replaced


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def answering(
    monkeypatch: pytest.MonkeyPatch, outcome, headers: dict[str, str] | None = None
) -> list[urllib.request.Request]:
    requests: list[urllib.request.Request] = []

    def urlopen(request: urllib.request.Request):
        requests.append(request)
        if isinstance(outcome, Exception):
            raise outcome
        response = Response(json.dumps(outcome).encode())
        response.headers = headers or {}
        return response

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return requests


def http_error(
    code: int, body: dict | str, headers: dict[str, str] | None = None
) -> urllib.error.HTTPError:
    content = body if isinstance(body, str) else json.dumps(body)
    return urllib.error.HTTPError(
        f"{SITE}/x",
        code,
        "error",
        headers or {},  # type: ignore[arg-type]
        io.BytesIO(content.encode()),  # type: ignore[arg-type]
    )


def test_sends_json_and_returns_the_answer(monkeypatch):
    requests = answering(monkeypatch, {"key": "WEB-1"})
    assert api._send("POST", f"{SITE}/x", "Basic abc", {"a": 1}) == {"key": "WEB-1"}
    request = requests[0]
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"a": 1}
    assert request.get_header("Authorization") == "Basic abc"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Accept") == "application/json"


def test_a_string_body_is_sent_as_a_json_string(monkeypatch):
    requests = answering(monkeypatch, {})
    api._send("POST", f"{SITE}/x", "Basic abc", "a1")
    assert requests[0].data == b'"a1"'
    assert requests[0].get_header("Content-type") == "application/json"


def test_a_refused_token_is_a_precondition(monkeypatch):
    answering(monkeypatch, http_error(401, ""))
    with pytest.raises(Precondition) as raised:
        api._send("POST", f"{SITE}/x", "Basic abc", {})
    assert raised.value.message == "Jira refused the API token."


def test_a_forbidden_request_is_a_failure_of_its_own_kind_with_jiras_messages(monkeypatch):
    # Jira answers 403 to a signed-in user who isn't allowed to do something, such as attach a
    # file larger than the site allows: the token is fine.
    body = {"errorMessages": ["You do not have permission to create attachments for this issue."]}
    answering(monkeypatch, http_error(403, body))
    with pytest.raises(Forbidden) as raised:
        api._send("POST", f"{SITE}/x", "Basic abc", {})
    assert [raised.value.message, *raised.value.details] == [
        "Jira answered 403.",
        "You do not have permission to create attachments for this issue.",
        "Your account isn't allowed to do this, or the site has it turned off.",
    ]


# When Jira can't sign a request in, it often doesn't answer 401: it carries on as an anonymous
# user and says so in this header. A search then finds nothing, and a create is refused as if the
# space didn't exist.
SIGN_IN_FAILED = {"X-Seraph-LoginReason": "AUTHENTICATED_FAILED"}


def test_an_answer_given_without_signing_in_is_a_refused_token(monkeypatch):
    answering(monkeypatch, {"issues": []}, SIGN_IN_FAILED)
    with pytest.raises(Precondition) as raised:
        api._send("POST", f"{SITE}/x", "Basic abc", {})
    assert raised.value.message == "Jira refused the API token."


def test_an_error_given_without_signing_in_is_a_refused_token(monkeypatch):
    body = {"errors": {"project": "The target project doesn't exist."}}
    answering(monkeypatch, http_error(400, body, SIGN_IN_FAILED))
    with pytest.raises(Precondition) as raised:
        api._send("POST", f"{SITE}/x", "Basic abc", {})
    assert raised.value.message == "Jira refused the API token."


def test_another_error_is_a_failure_with_jiras_messages(monkeypatch):
    body = {"errorMessages": ["Bad JQL."], "errors": {"issuetype": "Specify a valid type."}}
    answering(monkeypatch, http_error(400, body))
    with pytest.raises(Failure) as raised:
        api._send("POST", f"{SITE}/x", "Basic abc", {})
    assert [raised.value.message, *raised.value.details] == [
        "Jira answered 400.",
        "Bad JQL.",
        "issuetype: Specify a valid type.",
    ]


def form(request: urllib.request.Request) -> list[email.message.Message]:
    """The parts of request's multipart/form-data body, as a mail reader parses them."""
    head = f"Content-Type: {request.get_header('Content-type')}\r\n\r\n".encode()
    message = email.message_from_bytes(head + request.data, policy=email.policy.HTTP)
    assert message.is_multipart()
    return list(message.iter_parts())


def test_uploads_a_file_as_a_form_part_named_file_and_returns_the_answer(monkeypatch):
    requests = answering(monkeypatch, [{"id": "10001"}])
    content = bytes(range(256)) + b"\r\n--"
    assert api._upload(f"{SITE}/x", "Basic abc", "trace.txt", content) == [{"id": "10001"}]
    request = requests[0]
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Basic abc"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("X-atlassian-token") == "no-check"
    [part] = form(request)
    assert part.get_param("name", header="content-disposition") == "file"
    assert part.get_filename() == "trace.txt"
    assert part.get_content_type() == "text/plain"
    assert part.get_payload(decode=True) == content


def test_an_uploaded_files_name_is_sent_as_a_browser_sends_it(monkeypatch):
    requests = answering(monkeypatch, [{"id": "10001"}])
    api._upload(f"{SITE}/x", "Basic abc", 'say "café"\n.bin', b"x")
    disposition = 'form-data; name="file"; filename="say %22café%22%0A.bin"'
    assert f"Content-Disposition: {disposition}\r\n".encode() in requests[0].data
    [part] = form(requests[0])
    assert part.get_content_type() == "application/octet-stream"


def test_an_upload_has_the_same_errors_as_any_other_request(monkeypatch):
    answering(monkeypatch, http_error(401, ""))
    with pytest.raises(Precondition):
        api._upload(f"{SITE}/x", "Basic abc", "a.txt", b"")
    answering(monkeypatch, http_error(404, {"errorMessages": ["Issue does not exist."]}))
    with pytest.raises(NotFound):
        api._upload(f"{SITE}/x", "Basic abc", "a.txt", b"")


def test_a_request_without_a_body_sends_none(monkeypatch):
    requests = answering(monkeypatch, {"accountId": "a1"})
    assert api._send("GET", f"{SITE}/x", "Basic abc", None) == {"accountId": "a1"}
    assert requests[0].get_method() == "GET"
    assert requests[0].data is None
    assert requests[0].get_header("Content-type") is None


def test_an_empty_answer_is_an_empty_object(monkeypatch):
    def urlopen(request):
        response = Response(b"")
        response.headers = {}
        return response

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert api._send("PUT", f"{SITE}/x", "Basic abc", {"accountId": None}) == {}


def test_not_found_is_a_failure_of_its_own_kind(monkeypatch):
    body = {"errorMessages": ["Issue does not exist or you do not have permission to see it."]}
    answering(monkeypatch, http_error(404, body))
    with pytest.raises(NotFound) as raised:
        api._send("GET", f"{SITE}/x", "Basic abc", None)
    assert isinstance(raised.value, Failure)
    assert raised.value.details == (body["errorMessages"][0],)


def test_an_error_whose_body_is_not_json_shows_the_body(monkeypatch):
    answering(monkeypatch, http_error(502, "Bad gateway"))
    with pytest.raises(Failure) as raised:
        api._send("POST", f"{SITE}/x", "Basic abc", {})
    assert raised.value.details == ("Bad gateway",)


def test_an_unreachable_site_is_a_failure(monkeypatch):
    answering(monkeypatch, urllib.error.URLError("nodename nor servname provided"))
    with pytest.raises(Failure) as raised:
        api._send("POST", f"{SITE}/x", "Basic abc", {})
    assert [raised.value.message, *raised.value.details] == [
        "Can't reach me.atlassian.net.",
        "nodename nor servname provided",
    ]


@pytest.mark.parametrize(
    "refusal", [Forbidden("Jira answered 403."), NotFound("Jira answered 404.")]
)
def test_web_links_jira_will_not_show_are_none(fake, refusal):
    # A site with issue linking turned off refuses its web links.
    fake.answers = [refusal]
    assert jira().web_links("WEB-1") is None


def test_finds_every_issue_in_a_space_with_a_label_with_its_links(fake):
    fake.answers = [found("Checkout fails", next_page="2"), found("Search is slow")]
    issues = Jira(SITE, CREDENTIAL).with_label("WEB", "production-failure")
    assert [issue["fields"]["summary"] for issue in issues] == ["Checkout fails", "Search is slow"]
    method, url, body = fake.sent[0]
    assert (method, url) == ("POST", f"{SITE}/rest/api/3/search/jql")
    assert body["jql"] == 'project = "WEB" AND labels = "production-failure" ORDER BY created DESC'
    assert {"created", "status", "issuelinks"} <= set(body["fields"])


def test_a_space_the_token_can_see_has_its_name(fake):
    fake.answers = [{"key": "WEB", "name": "Website"}]
    assert Jira(SITE, CREDENTIAL).space_name("WEB") == "Website"
    assert fake.sent[0][:2] == ("GET", f"{SITE}/rest/api/3/project/WEB")


def test_a_space_the_token_cannot_see_has_no_name(fake):
    fake.answers = [NotFound("Jira answered 404.")]
    assert Jira(SITE, CREDENTIAL).space_name("NOPE") is None


def test_lists_the_names_of_the_sites_fields(fake):
    fake.answers = [
        [{"id": "summary", "name": "Summary"}, {"id": "customfield_1", "name": "Detected"}]
    ]
    assert Jira(SITE, CREDENTIAL).field_names() == ["Summary", "Detected"]
    assert fake.sent[0][:2] == ("GET", f"{SITE}/rest/api/3/field")
