"""jira view: an issue as Markdown, with everything needed to work on it, against a fake Jira
site."""

import pytest
from cli_kit.outcome import NothingToDo, Precondition

from jira_tools import adf
from jira_tools.__main__ import main
from jira_tools.commands.view import view

SITE = "https://me.atlassian.net"


def linked(key: str, summary: str, status: str) -> dict:
    return {"key": key, "fields": {"summary": summary, "status": {"name": status}}}


def test_shows_the_issue_with_its_fields_rich_text_relations_web_links_files_and_comments(
    site, capsys
):
    alice = site.person("a-1", "Alice Smith")
    site.names = {"customfield_10050": "Acceptance criteria", "description": "Description"}
    site.add(
        "WEB-12",
        "Scan skips symlinks",
        status="In Progress",
        issuetype={"name": "Bug"},
        priority={"name": "High"},
        assignee=site.me,
        reporter=alice,
        labels=["deferred", "scan"],
        components=[{"name": "Scanner"}],
        fixVersions=[{"name": "1.2"}],
        versions=[{"name": "1.0"}, {"name": "1.1"}],
        parent=linked("WEB-3", "Symlink support", "In Progress"),
        created="2026-10-01T10:22:33.000+0100",
        updated="2026-10-12T08:00:00.000+0100",
        duedate="2026-10-20",
        description=adf.from_markdown("## Problem\n\n`scan()` skips links."),
        customfield_10050=adf.from_markdown("- follows links\n- no loops"),
        customfield_10051="0|i0000f:",
        subtasks=[linked("WEB-13", "Add a test", "To Do")],
        issuelinks=[
            {
                "type": {"inward": "is blocked by", "outward": "blocks"},
                "outwardIssue": linked("WEB-20", "Release 1.2", "To Do"),
            },
            {
                "type": {"inward": "is blocked by", "outward": "blocks"},
                "inwardIssue": linked("WEB-9", "Fix paths", "Done"),
            },
        ],
        attachment=[
            {
                "filename": "trace.txt",
                "mimeType": "text/plain",
                "size": 2048,
                "content": f"{SITE}/rest/api/3/attachment/content/1",
            }
        ],
    )
    site.web_link("WEB-12", "https://github.com/me/web/pull/42", "Follow symlinks")
    site.web_link("WEB-12", "https://example.com/spec", "https://example.com/spec")
    site.comment(
        "WEB-12", adf.from_markdown("Seen on macOS too."), alice, "2026-10-02T09:00:00.000+0100"
    )
    site.comment("WEB-12", adf.from_markdown("### Plan\n\nFollow them."))

    result = view("WEB-12")
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 is In Progress."
    assert capsys.readouterr().out == "\n".join(
        [
            "# WEB-12: Scan skips symlinks",
            "",
            "- Type: Bug",
            "- Status: In Progress",
            "- Priority: High",
            "- Assignee: Ian Flanagan",
            "- Reporter: Alice Smith",
            "- Labels: deferred, scan",
            "- Components: Scanner",
            "- Fix versions: 1.2",
            "- Affects versions: 1.0, 1.1",
            "- Parent: WEB-3 (In Progress): Symlink support",
            "- Due: 2026-10-20",
            "- Created: 2026-10-01",
            "- Updated: 2026-10-12",
            f"- URL: {SITE}/browse/WEB-12",
            "",
            "## Description",
            "",
            "#### Problem",
            "",
            "`scan()` skips links.",
            "",
            "## Acceptance criteria",
            "",
            "- follows links",
            "- no loops",
            "",
            "## Subtasks",
            "",
            "- WEB-13 (To Do): Add a test",
            "",
            "## Linked issues",
            "",
            "- blocks WEB-20 (To Do): Release 1.2",
            "- is blocked by WEB-9 (Done): Fix paths",
            "",
            "## Web links",
            "",
            "- [Follow symlinks](https://github.com/me/web/pull/42)",
            "- [https://example.com/spec](https://example.com/spec)",
            "",
            "## Attachments",
            "",
            f"- [trace.txt]({SITE}/rest/api/3/attachment/content/1) (text/plain, 2 KB)",
            "",
            "## Comments",
            "",
            "### Alice Smith, 2026-10-02 (comment 10000)",
            "",
            "Seen on macOS too.",
            "",
            "### Ian Flanagan, 2026-10-13 (comment 10001)",
            "",
            "###### Plan",
            "",
            "Follow them.",
            "",
        ]
    )


def test_a_bare_issue_shows_only_what_it_has(site, capsys):
    site.add("WEB-12", "Scan skips symlinks")
    view("WEB-12")
    assert capsys.readouterr().out == "\n".join(
        [
            "# WEB-12: Scan skips symlinks",
            "",
            "- Type: Task",
            "- Status: To Do",
            "- Assignee: Unassigned",
            f"- URL: {SITE}/browse/WEB-12",
            "",
            "## Description",
            "",
            "None.",
            "",
        ]
    )


def test_a_resolved_issue_shows_its_resolution_after_its_status(site, capsys):
    site.add("WEB-12", status="Done", resolution={"id": "10001", "name": "Won't Do"})
    view("WEB-12")
    assert "- Status: Done\n- Resolution: Won't Do\n" in capsys.readouterr().out


def test_shows_the_time_estimated_spent_and_remaining_and_how_many_watch_it(site, capsys):
    site.add(
        "WEB-12",
        duedate="2026-10-20",
        timetracking={
            "originalEstimate": "2d",
            "originalEstimateSeconds": 57600,
            "timeSpent": "1d 2h",
            "timeSpentSeconds": 36000,
            "remainingEstimate": "6h",
            "remainingEstimateSeconds": 21600,
        },
        watches={"watchCount": 3, "isWatching": True},
    )
    view("WEB-12")
    assert (
        "\n".join(
            [
                "- Due: 2026-10-20",
                "- Original estimate: 2d",
                "- Time spent: 1d 2h",
                "- Remaining: 6h",
                "- Watchers: 3",
            ]
        )
        in capsys.readouterr().out
    )


def test_only_the_time_tracked_is_shown_and_no_watchers_are_left_out(site, capsys):
    site.add("WEB-12", timetracking={"timeSpent": "30m"}, watches={"watchCount": 0})
    view("WEB-12")
    out = capsys.readouterr().out
    assert "- Time spent: 30m\n" in out
    assert "estimate" not in out
    assert "Remaining" not in out
    assert "Watchers" not in out


def test_an_empty_rich_text_field_other_than_the_description_is_left_out(site, capsys):
    site.names = {"customfield_1": "Acceptance criteria"}
    site.add("WEB-12", customfield_1={"type": "doc", "version": 1, "content": []})
    view("WEB-12")
    assert "Acceptance criteria" not in capsys.readouterr().out


def test_an_issue_that_is_not_there_is_named(site):
    with pytest.raises(Precondition) as raised:
        view("WEB-404")
    assert raised.value.message == "No issue WEB-404."


def test_the_command_line_takes_the_key(site, capsys):
    site.add("WEB-12")
    assert main(["view", "web-12"]) == 0
    assert capsys.readouterr().out.endswith("➖ WEB-12 is To Do.\n")


def test_set_custom_fields_of_simple_values_are_listed_under_other_fields(site, capsys):
    custom = "com.atlassian.jira.plugin.system.customfieldtypes:"
    site.names = {
        "customfield_1": "Story points",
        "customfield_2": "Severity",
        "customfield_3": "Browsers",
        "customfield_4": "Reviewer",
        "customfield_5": "Sprint",
        "customfield_6": "Team name",
        "customfield_7": "Rank",
        "customfield_8": "Start date",
        "customfield_9": "Acceptance criteria",
    }
    site.schemas = {
        "customfield_1": {"type": "number", "custom": custom + "float"},
        "customfield_2": {"type": "option", "custom": custom + "select"},
        "customfield_3": {"type": "array", "items": "option", "custom": custom + "multicheckboxes"},
        "customfield_4": {"type": "user", "custom": custom + "userpicker"},
        "customfield_5": {
            "type": "array",
            "items": "json",
            "custom": "com.pyxis.greenhopper.jira:gh-sprint",
        },
        "customfield_6": {"type": "string", "custom": custom + "textfield"},
        "customfield_7": {"type": "any", "custom": "com.pyxis.greenhopper.jira:gh-lexo-rank"},
        "customfield_8": {"type": "date", "custom": custom + "datepicker"},
        "customfield_9": {"type": "string", "custom": custom + "textarea"},
    }
    site.add(
        "WEB-12",
        customfield_1=3.0,
        customfield_2={"id": "101", "value": "High"},
        customfield_3=[{"id": "100", "value": "Chrome"}, {"id": "101", "value": "Edge"}],
        customfield_4={"accountId": "a-1", "displayName": "Alice Smith"},
        customfield_5=[{"id": 37, "name": "Sprint 4", "state": "active"}],
        customfield_6=None,
        customfield_7="0|i0000f:",
        customfield_8="2026-10-20",
        customfield_9=adf.from_markdown("Follows links."),
    )
    view("WEB-12")
    out = capsys.readouterr().out
    assert (
        "\n".join(
            [
                "## Acceptance criteria",
                "",
                "Follows links.",
                "",
                "## Other fields",
                "",
                "- Story points: 3",
                "- Severity: High",
                "- Browsers: Chrome, Edge",
                "- Reviewer: Alice Smith",
                "- Sprint: Sprint 4",
                "- Start date: 2026-10-20",
                "",
            ]
        )
        in out
    )


def test_an_issue_whose_web_links_jira_will_not_show_is_shown_without_them(site, capsys):
    site.add("WEB-12")
    site.web_links_refused = True
    view("WEB-12")
    out = capsys.readouterr().out
    assert out.startswith("# WEB-12: Scan skips symlinks")
    assert "Web links" not in out
