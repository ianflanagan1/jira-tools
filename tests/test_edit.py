"""jira edit: an issue's description replaced by the Markdown on stdin, keeping the original
report on request, its labels changed and any field set by name, against a fake Jira site."""

import io
import json

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf
from jira_tools.__main__ import main
from jira_tools.commands.edit import edit

SITE = "https://me.atlassian.net"


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def run(markdown: str | None, key: str = "WEB-12", **options):
    stdin = Terminal() if markdown is None else io.StringIO(markdown)
    return edit(key, stdin=stdin, **options)


FIELDS = {
    "customfield_10016": {"name": "Story points", "schema": {"type": "number"}},
    "customfield_10011": {
        "name": "Acceptance criteria",
        "schema": {
            "type": "string",
            "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
        },
    },
    "timetracking": {"name": "Time tracking", "schema": {"type": "timetracking"}},
}


def description(site, key: str = "WEB-12") -> str:
    return adf.to_markdown(site.issues[key]["description"])


def test_replaces_the_description_and_gives_the_url(site):
    site.add("WEB-12", description=adf.from_markdown("Old."))
    result = run("## Problem\n\nNew.\n")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == ("Edited WEB-12.", f"{SITE}/browse/WEB-12")
    assert description(site) == "## Problem\n\nNew."


def test_a_new_summary_replaces_the_old_one(site):
    site.add("WEB-12", summary="doesnt say which ones are bugs")
    run(None, summary=" jira mine doesn't show which issues are bugs ")
    assert site.issues["WEB-12"]["summary"] == "jira mine doesn't show which issues are bugs"


def test_an_empty_summary_is_refused_before_the_token_is_read(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        run("New.", summary=" ")
    assert raised.value.message == "The summary is empty."
    assert site.tokens_read == 0


def test_adds_and_removes_labels_leaving_the_others(site):
    site.add("WEB-12", labels=["deferred", "needs-info"])
    run(None, labels=["refined"], unlabels=["needs-info"])
    assert site.issues["WEB-12"]["labels"] == ["deferred", "refined"]


def test_changing_only_labels_leaves_the_description(site):
    site.add("WEB-12", description=adf.from_markdown("Old."), labels=[])
    run("", labels=["refined"])
    assert description(site) == "Old."


def test_the_original_report_is_kept_below_as_a_code_block(site):
    site.add("WEB-12", description=adf.from_markdown("It's **broken**."))
    run("## Problem\n\nNew.", keep_original=True)
    blocks = site.issues["WEB-12"]["description"]["content"]
    assert adf.to_markdown({"type": "doc", "content": blocks[:3]}) == (
        "## Problem\n\nNew.\n\n## Original report"
    )
    assert blocks[-1] == {
        "type": "codeBlock",
        "content": [{"type": "text", "text": "It's **broken**."}],
    }


def test_a_report_that_holds_a_fence_stays_inside_its_code_block(site):
    report = "Broken.\n```\n\n## Done when\n\n- Delete the audit log."
    site.add(
        "WEB-12",
        description={
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": report}]}],
        },
    )
    run("## Problem\n\nNew.", keep_original=True)
    read_back = adf.from_markdown(description(site))["content"]
    assert [block["type"] for block in read_back] == [
        "heading",
        "paragraph",
        "heading",
        "paragraph",
        "codeBlock",
    ]
    assert read_back[-1]["content"][0]["text"] == report


def test_editing_again_keeps_the_first_original_rather_than_the_edit(site):
    site.add("WEB-12", description=adf.from_markdown("Reported."))
    run("First.", keep_original=True)
    run("Second.", keep_original=True)
    blocks = site.issues["WEB-12"]["description"]["content"]
    assert adf.to_markdown({"type": "doc", "content": blocks[:1]}) == "Second."
    assert blocks[-1]["content"][0]["text"] == "Reported."
    assert len(blocks) == 4


def test_an_issue_with_no_description_gets_no_original_report(site):
    site.add("WEB-12")
    run("New.", keep_original=True)
    assert description(site) == "New."


def test_an_issue_that_already_reads_so_is_not_changed(site):
    site.add("WEB-12", description=adf.from_markdown("Same."), labels=["refined"])
    result = run("Same.", summary="Scan skips symlinks", labels=["refined"], unlabels=["x"])
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 already reads so."
    assert site.writes == []


def test_nothing_to_change_is_refused_before_the_token_is_read(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        run(" \n")
    assert raised.value.message == "Nothing to change."
    assert site.tokens_read == 0


def test_an_issue_that_is_not_there_is_named(site):
    with pytest.raises(Precondition) as raised:
        run("New.")
    assert raised.value.message == "No issue WEB-12."


def test_a_dry_run_shows_the_change_and_reads_no_token_and_sends_nothing(site, capsys):
    result = run(
        "New.", labels=["refined"], unlabels=["needs-info"], keep_original=True, dry_run=True
    )
    assert isinstance(result, NothingToDo)
    assert result.summary == "Dry run: nothing edited."
    assert json.loads(capsys.readouterr().out) == {
        "issue": "WEB-12",
        "summary": None,
        "description": adf.from_markdown("New."),
        "keep_original": True,
        "add": ["refined"],
        "remove": ["needs-info"],
    }
    assert site.tokens_read == 0


def test_the_command_line_takes_the_key_labels_and_stdin(site, monkeypatch, capsys):
    site.add("WEB-12", labels=["needs-info"])
    monkeypatch.setattr("sys.stdin", io.StringIO("New."))
    argv = ["edit", "12", "--keep-original", "--label", "refined", "--unlabel", "needs-info"]
    assert main([*argv, "--summary", "Better"]) == 0
    assert capsys.readouterr().out.startswith("✅ Edited WEB-12.\n")
    assert site.issues["WEB-12"]["labels"] == ["refined"]
    assert site.issues["WEB-12"]["summary"] == "Better"


def test_sets_a_field_by_its_name(site):
    site.add("WEB-12")
    site.fields = FIELDS
    result = run(None, field_values=["story points=3"])
    assert isinstance(result, Done)
    assert site.issues["WEB-12"]["customfield_10016"] == 3


def test_a_field_file_gives_a_field_the_markdown_in_the_file(site, tmp_path):
    site.add("WEB-12")
    site.fields = FIELDS
    (tmp_path / "ac.md").write_text("- follows links\n- no loops\n")
    run(None, field_files=[f"Acceptance criteria={tmp_path / 'ac.md'}"])
    criteria = site.issues["WEB-12"]["customfield_10011"]
    assert adf.to_markdown(criteria) == "- follows links\n- no loops"


def test_an_estimate_sets_the_original_estimate(site):
    site.add("WEB-12")
    site.fields = FIELDS
    run(None, estimate="1h30m")
    assert site.issues["WEB-12"]["timetracking"]["originalEstimate"] == "1h 30m"


def test_an_empty_value_clears_a_field(site):
    site.add("WEB-12", customfield_10016=5)
    site.fields = FIELDS
    run(None, field_values=["Story points="])
    assert site.issues["WEB-12"]["customfield_10016"] is None


def test_fields_that_already_have_their_values_are_not_changed(site):
    criteria = adf.from_markdown("- follows links")
    site.add("WEB-12", customfield_10016=3.0, customfield_10011=criteria)
    site.fields = FIELDS
    result = run(None, field_values=["Story points=3", "Acceptance criteria=- follows links"])
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 already reads so."
    assert site.writes == []


def test_only_the_fields_that_change_are_sent(site):
    site.add("WEB-12", customfield_10016=3)
    site.fields = FIELDS
    run(None, field_values=["Story points=3"], estimate="2d")
    assert site.writes[0][2]["update"] == {"timetracking": [{"edit": {"originalEstimate": "2d"}}]}


def test_a_field_the_edit_screen_does_not_have_is_refused_before_anything_is_written(site):
    site.add("WEB-12")
    site.fields = FIELDS
    with pytest.raises(Precondition) as raised:
        run("New.", field_values=["Sprint=37"])
    assert raised.value.message == "'Sprint' can't be set on WEB-12's edit screen."
    assert site.writes == []


def test_a_bad_estimate_or_field_is_refused_before_the_token_is_read(site):
    site.add("WEB-12")
    for options in ({"estimate": "soon"}, {"field_values": ["Story points"]}):
        with pytest.raises(Precondition):
            run(None, **options)
    assert site.tokens_read == 0


def test_a_dry_run_shows_the_fields_as_given_without_the_token(site, capsys, tmp_path):
    (tmp_path / "ac.md").write_text("- follows links\n")
    run(
        None,
        field_values=["Story points=3"],
        field_files=[f"Acceptance criteria={tmp_path / 'ac.md'}"],
        estimate="2d",
        dry_run=True,
    )
    assert json.loads(capsys.readouterr().out)["set_by_name"] == [
        "Story points=3",
        "Acceptance criteria=- follows links\n",
        "timetracking=2d",
    ]
    assert site.tokens_read == 0


def test_the_command_line_takes_fields_field_files_and_an_estimate(site, tmp_path, monkeypatch):
    site.add("WEB-12")
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    site.fields = FIELDS
    (tmp_path / "ac.md").write_text("Done when it follows links.")
    argv = ["edit", "WEB-12", "--field", "Story points=5", "--estimate", "3d"]
    argv += ["--field-file", f"Acceptance criteria={tmp_path / 'ac.md'}"]
    assert main(argv) == 0
    fields = site.issues["WEB-12"]
    assert fields["customfield_10016"] == 5
    assert fields["timetracking"]["originalEstimate"] == "3d"
    assert adf.to_markdown(fields["customfield_10011"]) == "Done when it follows links."


def sent(site) -> dict:
    """The body of the one edit sent."""
    [body] = [body for method, path, body in site.writes if method == "PUT"]
    return body


def test_changes_the_priority_matched_ignoring_case(site):
    site.add("WEB-12", priority={"name": "Medium"})
    assert isinstance(run(None, priority="high"), Done)
    assert sent(site)["fields"] == {"priority": {"name": "High"}}
    assert site.issues["WEB-12"]["priority"] == {"name": "High"}


def test_a_priority_the_space_lacks_names_those_it_has_and_changes_nothing(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        run("New.", priority="Urgent")
    assert [raised.value.message, *raised.value.details] == [
        "WEB has no priority 'Urgent'.",
        "It has: Highest, High, Medium, Low, Lowest.",
    ]
    assert site.writes == []


def test_sets_the_parent_and_none_removes_it(site):
    site.add("WEB-3")
    site.add("WEB-12")
    run(None, parent="3")
    assert site.issues["WEB-12"]["parent"] == {"key": "WEB-3"}
    site.writes.clear()
    run(None, parent="None")
    assert sent(site)["fields"] == {"parent": None}
    assert site.issues["WEB-12"]["parent"] is None


def test_a_parent_that_is_not_there_is_named_and_nothing_changes(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        run(None, parent="WEB-404")
    assert raised.value.message == "No issue WEB-404."
    assert site.writes == []


def test_changes_the_type_by_its_id(site):
    site.add("WEB-12")
    run(None, issue_type="bug")
    assert sent(site)["fields"] == {"issuetype": {"id": "10002"}}
    assert site.issues["WEB-12"]["issuetype"]["name"] == "Bug"


def test_a_type_the_space_lacks_names_those_it_has(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        run(None, issue_type="Story")
    assert raised.value.details == ("It has: Task, Bug, Subtask.",)
    assert site.writes == []


@pytest.mark.parametrize("now, to", [("Task", "Subtask"), ("Subtask", "Bug")])
def test_a_subtask_and_another_type_are_not_swapped_by_an_edit(site, now, to):
    site.add("WEB-12", issuetype=site.issue_type({"name": now}))
    with pytest.raises(Precondition) as raised:
        run(None, issue_type=to)
    assert [raised.value.message, *raised.value.details] == [
        f"Jira won't change WEB-12 from {now} to {to} by an edit.",
        "Only Jira's Move, in its web app, changes a subtask to another type or back.",
    ]
    assert site.writes == []


def test_changes_the_reporter_to_the_person_named(site):
    site.person("a-1", "Alice Smith", "alice@example.com")
    site.add("WEB-12", reporter=site.me)
    run(None, reporter="alice")
    assert sent(site)["fields"] == {"reporter": {"accountId": "a-1"}}


def test_the_reporter_cannot_be_no_one(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        run(None, reporter="none")
    assert raised.value.message == "An issue's reporter must be someone."
    assert site.tokens_read == 0


def test_sets_the_due_date_and_none_clears_it(site):
    site.add("WEB-12")
    run(None, due="2026-10-31")
    assert site.issues["WEB-12"]["duedate"] == "2026-10-31"
    run(None, due="none")
    assert site.issues["WEB-12"]["duedate"] is None


def test_a_due_date_that_is_not_a_date_is_refused_before_the_token_is_read(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        run(None, due="31/10/2026")
    assert raised.value.message == (
        "--due takes a date as YYYY-MM-DD, such as 2026-10-31, not '31/10/2026'."
    )
    assert site.tokens_read == 0


def test_adds_and_removes_components_and_versions_leaving_the_others(site):
    site.add(
        "WEB-12",
        components=[{"name": "Scanner"}],
        fixVersions=[{"name": "1.1"}],
        versions=[{"name": "1.0"}, {"name": "1.1"}],
    )
    run(
        None,
        components=["api"],
        uncomponents=["scanner"],
        fix_versions=["1.2"],
        unfix_versions=["1.1"],
        affects_versions=["1.2"],
        unaffects_versions=["1.0"],
    )
    issue = site.issues["WEB-12"]
    assert issue["components"] == [{"name": "API"}]
    assert issue["fixVersions"] == [{"name": "1.2"}]
    assert issue["versions"] == [{"name": "1.1"}, {"name": "1.2"}]


def test_a_component_or_version_the_space_lacks_names_those_it_has(site):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        run(None, components=["API"], fix_versions=["2.0"])
    assert [raised.value.message, *raised.value.details] == [
        "WEB has no version '2.0'.",
        "It has: 1.1, 1.2.",
    ]
    assert site.writes == []


def test_an_issue_that_already_has_the_fields_given_is_not_changed(site):
    site.add("WEB-3")
    site.add(
        "WEB-12",
        priority={"name": "High"},
        parent={"key": "WEB-3"},
        reporter=site.me,
        duedate="2026-10-31",
        components=[{"name": "API"}],
        fixVersions=[],
    )
    result = run(
        None,
        priority="High",
        parent="WEB-3",
        issue_type="task",
        reporter="me",
        due="2026-10-31",
        components=["api"],
        uncomponents=["Scanner"],
        unfix_versions=["1.1"],
    )
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 already reads so."
    assert site.writes == []


def test_a_dry_run_shows_the_fields_as_given_and_reads_no_token(site, capsys):
    run(
        None,
        priority="high",
        parent="3",
        issue_type="Bug",
        reporter="alice",
        due="none",
        components=["api"],
        unaffects_versions=["1.0"],
        dry_run=True,
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["fields"] == {
        "priority": {"name": "high"},
        "parent": {"key": "WEB-3"},
        "issuetype": {"name": "Bug"},
        "reporter": "alice",
        "duedate": None,
    }
    assert shown["update"] == {
        "components": [{"add": {"name": "api"}}],
        "versions": [{"remove": {"name": "1.0"}}],
    }
    assert site.tokens_read == 0


def test_the_command_line_takes_the_fields(site, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    site.add("WEB-3")
    site.add("WEB-12", components=[{"name": "Scanner"}])
    argv = ["edit", "12", "--priority", "Low", "--parent", "WEB-3", "--type", "Bug"]
    argv += ["--reporter", "me", "--due", "2026-10-31", "--component", "API"]
    argv += ["--uncomponent", "Scanner", "--fix-version", "1.2", "--affects-version", "1.1"]
    argv += ["--unfix-version", "1.0", "--unaffects-version", "1.0"]
    assert main(argv) == 0
    assert capsys.readouterr().out.startswith("✅ Edited WEB-12.\n")
    issue = site.issues["WEB-12"]
    assert issue["priority"] == {"name": "Low"}
    assert issue["parent"] == {"key": "WEB-3"}
    assert issue["issuetype"]["name"] == "Bug"
    assert issue["reporter"] == {"accountId": "me-1"}
    assert issue["duedate"] == "2026-10-31"
    assert issue["components"] == [{"name": "API"}]
    assert issue["fixVersions"] == [{"name": "1.2"}]
    assert issue["versions"] == [{"name": "1.1"}]


PRIORITY = {"name": "Priority", "schema": {"type": "priority", "system": "priority"}}


def test_fields_set_by_their_own_options_and_by_name_are_sent_together(site):
    site.add("WEB-12", priority={"name": "Medium"}, components=[])
    site.fields = {**FIELDS, "priority": PRIORITY}
    run(None, priority="high", components=["API"], field_values=["Story points=3"])
    assert sent(site)["fields"] == {"priority": {"name": "High"}, "customfield_10016": 3}
    assert sent(site)["update"] == {"components": [{"add": {"name": "API"}}]}


@pytest.mark.parametrize(
    "option, field, message",
    [
        ({"priority": "High"}, "Priority=Low", "--priority and --field both set Priority."),
        ({"due": "none"}, "duedate=2026-10-31", "--due and --field both set Due date."),
        (
            {"uncomponents": ["API"]},
            "Components=Scanner",
            "--component or --uncomponent and --field both set Components.",
        ),
    ],
)
def test_a_field_set_by_its_own_option_and_by_name_changes_nothing(site, option, field, message):
    site.add("WEB-12", components=[{"name": "API"}])
    site.fields = {
        "priority": PRIORITY,
        "duedate": {"name": "Due date", "schema": {"type": "date", "system": "duedate"}},
        "components": {
            "name": "Components",
            "schema": {"type": "array", "items": "component", "system": "components"},
            "allowedValues": [{"id": "1", "name": "Scanner"}, {"id": "2", "name": "API"}],
        },
    }
    with pytest.raises(Precondition) as raised:
        run(None, **option, field_values=[field])
    assert [raised.value.message, *raised.value.details] == [message, "Give it once."]
    assert site.writes == []


def test_a_dry_run_shows_fields_set_by_name_beside_those_set_by_their_own_options(site, capsys):
    run(None, priority="high", field_values=["Story points=3"], estimate="2d", dry_run=True)
    shown = json.loads(capsys.readouterr().out)
    assert shown["fields"] == {"priority": {"name": "high"}}
    assert shown["set_by_name"] == ["Story points=3", "timetracking=2d"]
    assert site.tokens_read == 0


@pytest.mark.parametrize("given", ["Labels=c", "Summary=Other", "Description=Other."])
def test_a_field_with_its_own_option_given_by_name_changes_nothing(site, given):
    site.add("WEB-12")
    site.fields = {
        "labels": {"name": "Labels", "schema": {"type": "array", "items": "string"}},
        "summary": {"name": "Summary", "schema": {"type": "string", "system": "summary"}},
        "description": {
            "name": "Description",
            "schema": {"type": "string", "system": "description"},
        },
    }
    with pytest.raises(Precondition) as raised:
        run("New.", labels=["b"], field_values=[given])
    assert raised.value.message == f"{given.split('=')[0]} can't be set with --field."
    assert site.writes == []


def test_an_estimate_is_sent_as_an_edit_of_time_tracking_keeping_the_remaining_estimate(site):
    tracking = {"originalEstimate": "1d", "originalEstimateSeconds": 28800}
    site.add("WEB-12", timetracking=tracking | {"remainingEstimate": "4h"})
    site.fields = FIELDS
    run(None, estimate="2d")
    assert sent(site)["update"] == {"timetracking": [{"edit": {"originalEstimate": "2d"}}]}
    assert "timetracking" not in sent(site)["fields"]
    assert site.issues["WEB-12"]["timetracking"]["remainingEstimate"] == "4h"


@pytest.mark.parametrize("estimate", ["8h", "1d", "480m"])
def test_an_estimate_jira_already_has_however_written_is_not_set_again(site, estimate):
    site.add("WEB-12")
    site.fields = FIELDS
    run(None, estimate="1d")
    site.writes.clear()
    result = run(None, estimate=estimate)
    assert isinstance(result, NothingToDo)
    assert site.writes == []
