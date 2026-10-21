"""jira create, with the settings, the credential store, git and Jira replaced by fakes."""

import io
import json
from pathlib import Path

import pytest
from cli_kit import credentials
from cli_kit.credentials import Credential, Token
from cli_kit.outcome import Done, Failure, NothingToDo, Precondition

from jira_tools import adf, api, config, context
from jira_tools.__main__ import main
from jira_tools.commands.create import create
from jira_tools.config import Config
from jira_tools.session import TOKEN

SITE = "https://me.atlassian.net"
WHERE = "Raised on branch `main` at `abc1234` in `shop`."


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class Fakes:
    def __init__(self) -> None:
        self.settings = Config("me.atlassian.net", "WEB", "Task", ("deferred",))
        self.where: str | None = WHERE
        self.tokens_read: list[Token] = []
        self.open_summaries: list[str] = []
        self.sent: list[tuple[str, dict]] = []
        self.workspaces: list[Path | None] = []

    def send(self, method: str, url: str, auth: str, body: dict) -> dict:
        self.sent.append((url.removeprefix(SITE), body))
        if url.endswith("/search/jql"):
            issues = [
                {"key": f"WEB-{n}", "fields": {"summary": s}}
                for n, s in enumerate(self.open_summaries, 1)
            ]
            return {"issues": issues}
        if url.split("?")[0].endswith("/issuetypes"):
            types = [{"id": "1", "name": "Task"}, {"id": "2", "name": "Bug"}]
            return {"issueTypes": types, "isLast": True}
        return {"id": "10001", "key": "WEB-9"}

    def created(self) -> dict:
        """The fields of the one issue created."""
        [fields] = [body["fields"] for url, body in self.sent if url == "/rest/api/3/issue"]
        return fields


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    fakes = Fakes()

    def read(token: Token) -> Credential:
        fakes.tokens_read.append(token)
        return Credential("me@example.com", "the-token")

    def load(path: Path | None = None) -> Config:
        fakes.workspaces.append(path)
        return fakes.settings

    monkeypatch.setattr(config, "load", load)
    monkeypatch.setattr(context, "where", lambda directory: fakes.where)
    monkeypatch.setattr(credentials.Token, "read", read)
    monkeypatch.setattr(api, "_send", fakes.send)
    return fakes


def file(summary: str = "Scan skips symlinks", description: str = "", **options) -> object:
    return create(summary, stdin=io.StringIO(description), **options)


def test_files_the_issue_and_gives_its_key_and_url(fakes):
    result = file()
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == ("Filed WEB-9.", f"{SITE}/browse/WEB-9")


def test_files_it_in_the_configured_space_as_the_configured_type_and_labels(fakes):
    file()
    fields = fakes.created()
    assert fields["project"] == {"key": "WEB"}
    assert fields["issuetype"] == {"name": "Task"}
    assert fields["labels"] == ["deferred"]
    assert fields["summary"] == "Scan skips symlinks"


def test_options_choose_the_space_and_type_and_add_labels(fakes):
    file(space="OPS", issue_type="Bug", labels=["review"])
    fields = fakes.created()
    assert fields["project"] == {"key": "OPS"}
    assert fields["issuetype"] == {"name": "Bug"}
    assert fields["labels"] == ["deferred", "review"]


def test_the_description_is_the_markdown_on_stdin_then_where_it_was_raised(fakes):
    file(description="It **skips** them.\n")
    assert fakes.created()["description"]["content"] == [
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "It "},
                {"type": "text", "text": "skips", "marks": [{"type": "strong"}]},
                {"type": "text", "text": " them."},
            ],
        },
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Raised on branch "},
                {"type": "text", "text": "main", "marks": [{"type": "code"}]},
                {"type": "text", "text": " at "},
                {"type": "text", "text": "abc1234", "marks": [{"type": "code"}]},
                {"type": "text", "text": " in "},
                {"type": "text", "text": "shop", "marks": [{"type": "code"}]},
                {"type": "text", "text": "."},
            ],
        },
    ]


def test_stdin_on_a_terminal_is_not_read_as_a_description(fakes):
    fakes.where = None
    create("Scan skips symlinks", stdin=Terminal("not this"))
    assert "description" not in fakes.created()


def test_an_issue_already_open_with_the_same_summary_is_not_filed_again(fakes):
    fakes.open_summaries = ["Something else", "scan skips symlinks"]
    result = file()
    assert isinstance(result, NothingToDo)
    assert result.summary == "Already filed as WEB-2."
    assert [url for url, body in fakes.sent] == ["/rest/api/3/search/jql"]


def test_the_search_for_an_open_issue_uses_every_label_it_would_file_with(fakes):
    file(labels=["review"])
    search = fakes.sent[0][1]["jql"]
    assert 'labels = "deferred" AND labels = "review"' in search


def test_a_blank_summary_is_refused_before_anything_is_read(fakes):
    with pytest.raises(Precondition) as raised:
        file("  ")
    assert raised.value.message == "The summary is empty."
    assert fakes.tokens_read == []


def test_its_settings_are_the_repository_s_unless_a_workspace_file_is_given(fakes, tmp_path):
    file()
    file("Another", workspace=tmp_path / "shop.md")
    assert fakes.workspaces == [None, tmp_path / "shop.md"]


def test_the_command_line_takes_a_workspace_file(fakes, monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["create", "Scan skips symlinks", "--workspace", str(tmp_path / "shop.md")]) == 0
    assert fakes.workspaces == [tmp_path / "shop.md"]


def test_a_summary_over_80_characters_is_refused_before_anything_is_read(fakes):
    with pytest.raises(Precondition) as raised:
        file("x" * 81)
    assert raised.value.message == "The summary is 81 characters; it can have at most 80."
    assert fakes.workspaces == []
    assert fakes.tokens_read == []


def test_a_description_with_markdown_jira_would_not_show_is_refused(fakes):
    with pytest.raises(Precondition) as raised:
        file(description="| a | b |\n")
    assert (raised.value.message, *raised.value.details) == (
        "The description has a table, on line 1, which Jira would show as plain text.",
        "Use only paragraphs, headings, - and 1. lists, code blocks, `code`, **bold** and "
        "[links](url).",
    )
    assert fakes.tokens_read == []


@pytest.mark.parametrize(
    "summary, description, where",
    [
        ("Login fails", "Used password = hunter2hunter to log in.\n", "description"),
        ("Login fails with AKIAIOSFODNN7EXAMPLE", "", "summary"),
    ],
)
def test_a_secret_in_the_summary_or_description_is_refused(fakes, summary, description, where):
    with pytest.raises(Precondition) as raised:
        file(summary, description)
    assert raised.value.message.startswith(f"The {where} looks like it has ")
    assert raised.value.details == ("Take it out, or describe it without its value.",)
    assert "hunter2" not in raised.value.message
    assert fakes.sent == []


def test_the_token_is_the_jira_api_token_stored_under_your_atlassian_email(fakes):
    file()
    assert fakes.tokens_read == [TOKEN]
    assert TOKEN.service == "jira-api-token"
    assert TOKEN.username == "atlassian-email"


def test_a_dry_run_shows_what_it_would_send_and_reads_no_token_and_sends_nothing(fakes, capsys):
    result = file(description="Body.", dry_run=True)
    assert isinstance(result, NothingToDo)
    assert result.summary == "Dry run: nothing filed."
    shown = json.loads(capsys.readouterr().out)
    assert shown["fields"]["summary"] == "Scan skips symlinks"
    assert shown["fields"]["description"]["content"][0]["content"] == [
        {"type": "text", "text": "Body."}
    ]
    assert fakes.tokens_read == []
    assert fakes.sent == []


def test_the_command_line_takes_the_space(fakes, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["create", "Scan skips symlinks", "--space", "OPS"]) == 0
    assert fakes.created()["project"] == {"key": "OPS"}


def test_the_command_line_takes_the_summary_and_options(fakes, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("Body."))
    status = main(
        ["create", "Scan skips symlinks", "--type", "Bug", "--label", "a", "--label", "b"]
    )
    assert status == 0
    assert capsys.readouterr().out == f"✅ Filed WEB-9.\n{SITE}/browse/WEB-9\n"
    fields = fakes.created()
    assert fields["issuetype"] == {"name": "Bug"}
    assert fields["labels"] == ["deferred", "a", "b"]


def test_it_reads_where_it_was_raised_from_the_current_folder(fakes, monkeypatch, tmp_path):
    folders: list[Path] = []
    monkeypatch.setattr(context, "where", lambda directory: folders.append(directory))
    monkeypatch.chdir(tmp_path)
    file()
    assert folders == [tmp_path]


# Fields set by name, against the fake site of conftest.py, which keeps the issues it files.

FIELDS = {
    "customfield_10016": {"name": "Story points", "schema": {"type": "number"}},
    "customfield_10011": {
        "name": "Acceptance criteria",
        "schema": {
            "type": "string",
            "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
        },
    },
    "customfield_10017": {"name": "Reviewer", "schema": {"type": "user"}},
    "timetracking": {"name": "Time tracking", "schema": {"type": "timetracking"}},
}


@pytest.fixture
def on_site(site, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(context, "where", lambda directory: None)
    site.fields = FIELDS
    return site


def test_sets_fields_by_name_from_values_files_and_the_estimate(on_site, tmp_path):
    (tmp_path / "ac.md").write_text("- follows links\n- no loops\n")
    result = file(
        field_values=["Story points=3"],
        field_files=[f"acceptance criteria={tmp_path / 'ac.md'}"],
        estimate="1d 4h",
    )
    assert result.summary == "Filed WEB-1."
    fields = on_site.issues["WEB-1"]
    assert fields["customfield_10016"] == 3
    assert adf.to_markdown(fields["customfield_10011"]) == "- follows links\n- no loops"
    assert fields["timetracking"]["originalEstimate"] == "1d 4h"


def test_fields_are_those_of_the_create_screen_of_the_issues_type(on_site):
    file(issue_type="bug", field_values=["Story points=3"])
    assert on_site.issues["WEB-1"]["customfield_10016"] == 3


def test_a_type_the_space_does_not_have_is_refused_with_those_it_has(on_site):
    with pytest.raises(Precondition) as raised:
        file(issue_type="Story", field_values=["Story points=3"])
    assert raised.value.message == "WEB has no issue type 'Story'."
    assert raised.value.details == ("It has: Task, Bug, Subtask.",)
    assert on_site.issues == {}


def test_a_field_the_create_screen_does_not_have_is_refused_before_anything_is_filed(on_site):
    with pytest.raises(Precondition) as raised:
        file(field_values=["Sprint=37"])
    assert raised.value.message == "'Sprint' can't be set on the create screen for a Task in WEB."
    assert on_site.issues == {}


def test_a_field_set_to_no_one_is_left_unset(on_site):
    file(field_values=["Reviewer=none"])
    assert "customfield_10017" not in on_site.issues["WEB-1"]


def test_an_empty_field_is_refused_before_the_token_is_read(on_site):
    with pytest.raises(Precondition) as raised:
        file(field_values=["Story points="])
    assert raised.value.message == "Story points is empty."
    assert raised.value.details == ("A new issue has no value to clear.",)
    assert on_site.tokens_read == 0


def test_a_dry_run_shows_the_fields_as_given_without_the_token(fakes, capsys):
    file(field_values=["Story points=3"], estimate="2d", dry_run=True)
    shown = json.loads(capsys.readouterr().out)
    assert shown["set_by_name"] == ["Story points=3", "timetracking=2d"]
    assert fakes.tokens_read == []


def test_the_command_line_takes_fields_field_files_and_an_estimate(on_site, monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    (tmp_path / "ac.md").write_text("Done when it follows links.")
    argv = ["create", "Scan skips symlinks", "--field", "Story points=5", "--estimate", "3d"]
    argv += ["--field-file", f"Acceptance criteria={tmp_path / 'ac.md'}"]
    assert main(argv) == 0
    fields = on_site.issues["WEB-1"]
    assert fields["customfield_10016"] == 5
    assert fields["timetracking"]["originalEstimate"] == "3d"


@pytest.fixture
def filing(site, monkeypatch: pytest.MonkeyPatch):
    """The fake Jira site, for filing issues in WEB, with WEB-3 and WEB-5 to link them to."""
    monkeypatch.setattr(context, "where", lambda directory: None)
    site.person("a-1", "Alice Smith", "alice@example.com")
    site.add("WEB-3", "Symlink support")
    site.add("WEB-5", "Release 1.2")
    return site


def changes(site) -> list[str]:
    """The path of each request that changed something: every write but a search."""
    return [path for method, path, body in site.writes if path != "search/jql"]


def filed(site) -> dict:
    """The fields of the one issue filed, as sent."""
    [body] = [body for method, path, body in site.writes if path == "issue"]
    return body["fields"]


def test_files_it_with_the_fields_given_as_jira_names_them(filing):
    result = file(
        priority="high",
        parent="3",
        assign="me",
        reporter="alice",
        due="2026-10-31",
        components=["api", "Scanner"],
        fix_versions=["1.2"],
        affects_versions=["1.1", "1.2"],
    )
    assert result.summary == "Filed WEB-1."
    fields = filed(filing)
    assert fields["priority"] == {"name": "High"}
    assert fields["parent"] == {"key": "WEB-3"}
    assert fields["assignee"] == {"accountId": "me-1"}
    assert fields["reporter"] == {"accountId": "a-1"}
    assert fields["duedate"] == "2026-10-31"
    assert fields["components"] == [{"name": "API"}, {"name": "Scanner"}]
    assert fields["fixVersions"] == [{"name": "1.2"}]
    assert fields["versions"] == [{"name": "1.1"}, {"name": "1.2"}]


def test_a_subtask_is_filed_under_its_parent_as_its_type_is_named(filing):
    file(issue_type="SUBTASK", parent="WEB-3")
    fields = filed(filing)
    assert fields["issuetype"] == {"name": "Subtask"}
    assert fields["parent"] == {"key": "WEB-3"}


@pytest.mark.parametrize(
    "option, message",
    [
        ({"issue_type": "Sub-task"}, "WEB has no issue type 'Sub-task'."),
        ({"priority": "Urgent"}, "WEB has no priority 'Urgent'."),
        ({"components": ["Parser"]}, "WEB has no component 'Parser'."),
        ({"fix_versions": ["2.0"]}, "WEB has no version '2.0'."),
        ({"affects_versions": ["1.0"]}, "WEB has no version '1.0'."),
        ({"parent": "WEB-404"}, "No issue WEB-404."),
        ({"reporter": "Bob"}, "No one in Jira matches 'Bob'."),
        ({"links": [("depends on", "WEB-3")]}, "Jira has no relation 'depends on'."),
        ({"links": [("blocks", "WEB-3"), ("blocks", "WEB-404")]}, "No issue WEB-404."),
    ],
)
def test_anything_jira_lacks_files_nothing(filing, option, message):
    with pytest.raises(Precondition) as raised:
        file(**option)
    assert raised.value.message == message
    assert filing.writes == []


@pytest.mark.parametrize("option", ["assign", "reporter"])
def test_a_person_is_needed_for_assign_and_reporter(filing, option):
    with pytest.raises(Precondition) as raised:
        file(**{option: "None"})
    assert raised.value.message == f"--{option} needs someone: me, or a name or email."
    assert filing.tokens_read == 0


def test_a_due_date_that_is_not_a_date_is_refused_before_the_token_is_read(filing):
    with pytest.raises(Precondition) as raised:
        file(due="next week")
    assert raised.value.message == (
        "--due takes a date as YYYY-MM-DD, such as 2026-10-31, not 'next week'."
    )
    assert filing.tokens_read == 0


def test_links_the_new_issue_to_others_once_it_is_filed(filing, capsys):
    result = file(links=[("is blocked by", "WEB-3"), ("Relates To", "5")])
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Filed WEB-1, linked to WEB-3 and WEB-5.",
        f"{SITE}/browse/WEB-1",
    )
    assert filing.linked("WEB-1") == ["is blocked by WEB-3", "relates to WEB-5"]
    assert capsys.readouterr().out == (
        "Filed WEB-1.\nLinked: WEB-1 is blocked by WEB-3.\nLinked: WEB-1 relates to WEB-5.\n"
    )


def test_an_issue_already_filed_gets_the_links_it_lacks(filing):
    filing.add("WEB-2", labels=["deferred"])
    filing.link("Blocks", "WEB-3", "WEB-2")
    result = file(links=[("is blocked by", "WEB-3"), ("relates to", "WEB-5")])
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Already filed as WEB-2; linked it to WEB-5.",
        f"{SITE}/browse/WEB-2",
    )
    assert filing.linked("WEB-2") == ["is blocked by WEB-3", "relates to WEB-5"]
    assert changes(filing) == ["issueLink"]


def test_an_issue_already_filed_with_every_link_given_is_left_alone(filing):
    filing.add("WEB-2", labels=["deferred"])
    filing.link("Relates", "WEB-5", "WEB-2")
    result = file(links=[("relates to", "WEB-5")])
    assert isinstance(result, NothingToDo)
    assert result.summary == "Already filed as WEB-2."
    assert changes(filing) == []


def test_a_dry_run_shows_the_fields_and_links_as_given_and_reads_no_token(filing, capsys):
    file(
        issue_type="subtask",
        priority="high",
        parent="3",
        assign="me",
        reporter="alice",
        due="2026-10-31",
        components=["api"],
        fix_versions=["1.2"],
        affects_versions=["1.1"],
        links=[("blocks", "5")],
        dry_run=True,
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["fields"] == {
        "project": {"key": "WEB"},
        "issuetype": {"name": "subtask"},
        "summary": "Scan skips symlinks",
        "labels": [],
        "description": None,
        "priority": {"name": "high"},
        "parent": {"key": "WEB-3"},
        "assignee": "me",
        "reporter": "alice",
        "duedate": "2026-10-31",
        "components": [{"name": "api"}],
        "fixVersions": [{"name": "1.2"}],
        "versions": [{"name": "1.1"}],
    }
    assert shown["links"] == [{"relation": "blocks", "other": "WEB-5"}]
    assert filing.tokens_read == 0


def test_the_command_line_takes_the_fields_and_links(filing, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    argv = ["create", "Scan skips symlinks", "--priority", "Low", "--parent", "WEB-3"]
    argv += ["--assign", "me", "--reporter", "alice", "--due", "2026-10-31"]
    argv += ["--component", "API", "--component", "Scanner", "--fix-version", "1.2"]
    argv += ["--affects-version", "1.1", "--link", "is blocked by", "WEB-3"]
    argv += ["--link", "relates to", "WEB-5"]
    assert main(argv) == 0
    issue = filing.issues["WEB-1"]
    assert issue["priority"] == {"name": "Low"}
    assert issue["parent"] == {"key": "WEB-3"}
    assert issue["assignee"] == {"accountId": "me-1"}
    assert issue["reporter"] == {"accountId": "a-1"}
    assert issue["duedate"] == "2026-10-31"
    assert issue["components"] == [{"name": "API"}, {"name": "Scanner"}]
    assert issue["fixVersions"] == [{"name": "1.2"}]
    assert issue["versions"] == [{"name": "1.1"}]
    assert filing.linked("WEB-1") == ["is blocked by WEB-3", "relates to WEB-5"]


def test_a_link_that_fails_once_filed_stops_it_saying_what_was_done(filing, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    linking = filing.link

    def link(link_type: str, inward: str, outward: str) -> None:
        if "WEB-5" in (inward, outward):
            raise Failure("Jira answered 500.")
        linking(link_type, inward, outward)

    monkeypatch.setattr(filing, "link", link)
    argv = ["create", "Scan skips symlinks", "--link", "blocks", "WEB-3", "--link", "blocks", "5"]
    assert main(argv) == 1
    assert capsys.readouterr().err.startswith(
        "🛑 Stopped.\nDone before it stopped:\n  Filed WEB-1.\n  Linked: WEB-1 blocks WEB-3.\n"
    )


PRIORITY = {"name": "Priority", "schema": {"type": "priority", "system": "priority"}}


def test_fields_set_by_their_own_options_and_by_name_are_filed_together(filing):
    filing.fields = {**FIELDS, "priority": PRIORITY}
    file(priority="high", field_values=["Story points=3"])
    fields = filed(filing)
    assert fields["priority"] == {"name": "High"}
    assert fields["customfield_10016"] == 3


def test_a_field_set_by_its_own_option_and_by_name_files_nothing(filing):
    filing.fields = {"priority": PRIORITY}
    with pytest.raises(Precondition) as raised:
        file(priority="High", field_values=["priority=Low"])
    assert [raised.value.message, *raised.value.details] == [
        "--priority and --field both set Priority.",
        "Give it once.",
    ]
    assert changes(filing) == []


def test_a_dry_run_shows_fields_set_by_name_beside_those_set_by_their_own_options(filing, capsys):
    file(priority="high", field_values=["Story points=3"], estimate="2d", dry_run=True)
    shown = json.loads(capsys.readouterr().out)
    assert shown["fields"]["priority"] == {"name": "high"}
    assert shown["set_by_name"] == ["Story points=3", "timetracking=2d"]
    assert filing.tokens_read == 0


def test_a_field_with_its_own_option_given_by_name_files_nothing(filing):
    filing.fields = {"labels": {"name": "Labels", "schema": {"type": "array", "items": "string"}}}
    with pytest.raises(Precondition) as raised:
        file(field_values=["Labels=other"])
    assert raised.value.message == "Labels can't be set with --field."
    assert changes(filing) == []


def test_a_parent_or_linked_issue_named_by_its_number_is_in_the_space_filed_in(filing, capsys):
    file(space="OPS", parent="3", links=[("blocks", "5")], dry_run=True)
    shown = json.loads(capsys.readouterr().out)
    assert shown["fields"]["parent"] == {"key": "OPS-3"}
    assert shown["links"] == [{"relation": "blocks", "other": "OPS-5"}]


def test_a_stage_kept_as_a_label_is_filed_with_its_label(filing):
    result = file(stage="needs-developer")
    assert isinstance(result, Done)
    assert result.summary == "Filed WEB-1 at needs-developer."
    assert filed(filing)["labels"] == ["stage-needs-developer"]


def test_a_stage_kept_in_a_status_moves_the_issue_there_once_filed(filing):
    filing.settings = Config("me.atlassian.net", "WEB", stages={"ready-for-agent": "Ready"})
    result = file(stage="ready-for-agent")
    assert result.summary == "Filed WEB-1 at ready-for-agent."
    assert filing.issues["WEB-1"]["status"]["name"] == "Ready"
    assert filed(filing)["labels"] == []


def test_an_open_issue_with_the_same_summary_is_already_filed_whatever_its_stage(filing):
    filing.add("WEB-2", labels=["stage-needs-codebase"])
    result = file(stage="needs-developer")
    assert isinstance(result, NothingToDo)
    assert result.summary == "Already filed as WEB-2."
    assert filing.issues["WEB-2"]["labels"] == ["stage-needs-codebase"]


@pytest.mark.parametrize(
    "stage, description, problem",
    [
        ("triage", "", "No stage triage."),
        ("ready-for-agent", "## Open questions\n\n- Which?", "The issue has open questions."),
    ],
)
def test_a_wrong_stage_is_refused_before_anything_is_filed(filing, stage, description, problem):
    with pytest.raises(Precondition) as raised:
        file(description=description, stage=stage)
    assert raised.value.message == problem
    assert changes(filing) == []


def test_a_dry_run_shows_the_stage(filing, capsys):
    file(stage="needs-codebase", dry_run=True)
    shown = json.loads(capsys.readouterr().out)
    assert shown["stage"] == "needs-codebase"
    assert shown["fields"]["labels"] == ["stage-needs-codebase"]
