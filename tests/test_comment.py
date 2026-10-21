"""jira comment: the Markdown on stdin added to an issue as a comment from you, or replacing one of
yours, and deleting yours, against a fake Jira site."""

import io
import json

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf
from jira_tools.__main__ import main
from jira_tools.commands.comment import comment, delete, edit

SITE = "https://me.atlassian.net"


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class Unread(io.StringIO):
    def read(self, *args) -> str:
        raise AssertionError("stdin was read")


def add(markdown: str, key: str = "WEB-12", **options):
    return comment(key, stdin=io.StringIO(markdown), **options)


def test_adds_the_markdown_as_a_comment_and_gives_its_url(site):
    site.add("WEB-12")
    result = add("PR: **ready**.\n")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Commented on WEB-12.",
        f"{SITE}/browse/WEB-12?focusedCommentId=10000",
    )
    [posted] = site.comments["WEB-12"]
    assert posted["body"] == adf.from_markdown("PR: **ready**.")


def test_a_comment_from_you_that_reads_the_same_is_not_added_again(site):
    site.add("WEB-12")
    site.comment("WEB-12", adf.from_markdown("PR: **ready**."))
    result = add("PR: **ready**.\n")
    assert isinstance(result, NothingToDo)
    assert result.summary == "Already commented on WEB-12."
    assert site.writes == []


def test_the_same_comment_from_someone_else_does_not_stop_yours(site):
    other = site.person("a-1", "Alice")
    site.add("WEB-12")
    site.comment("WEB-12", adf.from_markdown("+1"), author=other)
    assert isinstance(add("+1"), Done)


@pytest.mark.parametrize("stdin", [io.StringIO("  \n"), Terminal("ignored")])
def test_an_empty_comment_is_refused_before_the_token_is_read(site, stdin):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        comment("WEB-12", stdin=stdin)
    assert raised.value.message == "The comment is empty."
    assert site.tokens_read == 0


def test_an_issue_that_is_not_there_is_named(site):
    with pytest.raises(Precondition) as raised:
        add("Hi")
    assert raised.value.message == "No issue WEB-12."


def test_a_dry_run_shows_the_comment_and_reads_no_token_and_sends_nothing(site, capsys):
    result = add("Hi", dry_run=True)
    assert isinstance(result, NothingToDo)
    assert result.summary == "Dry run: nothing commented."
    shown = json.loads(capsys.readouterr().out)
    assert shown == {"issue": "WEB-12", "body": adf.from_markdown("Hi")}
    assert site.tokens_read == 0


def test_the_command_line_takes_the_key_and_reads_stdin(site, monkeypatch, capsys):
    site.add("WEB-12")
    monkeypatch.setattr("sys.stdin", io.StringIO("Hi"))
    assert main(["comment", "12"]) == 0
    assert capsys.readouterr().out.startswith("✅ Commented on WEB-12.\n")


def replace(markdown: str, comment_id: str = "10000", key: str = "WEB-12", **options):
    return edit(key, comment_id, stdin=io.StringIO(markdown), **options)


def test_edit_replaces_your_comment_with_the_markdown_and_gives_its_url(site):
    site.add("WEB-12")
    site.comment("WEB-12", adf.from_markdown("PR: draft."))
    result = replace("PR: **ready**.\n")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Edited comment 10000 on WEB-12.",
        f"{SITE}/browse/WEB-12?focusedCommentId=10000",
    )
    [edited] = site.comments["WEB-12"]
    assert edited["body"] == adf.from_markdown("PR: **ready**.")


def test_a_comment_that_already_reads_so_is_not_edited(site):
    site.add("WEB-12")
    site.comment("WEB-12", adf.from_markdown("PR: **ready**."))
    result = replace("PR: **ready**.\n")
    assert isinstance(result, NothingToDo)
    assert result.summary == "Comment 10000 on WEB-12 already reads so."
    assert site.writes == []


@pytest.mark.parametrize("act", [lambda: replace("Mine now"), lambda: delete("WEB-12", "10000")])
def test_someone_elses_comment_is_neither_edited_nor_deleted(site, act):
    alice = site.person("a-1", "Alice Smith")
    site.add("WEB-12")
    site.comment("WEB-12", adf.from_markdown("+1"), author=alice)
    with pytest.raises(Precondition) as raised:
        act()
    assert raised.value.message == "Comment 10000 on WEB-12 is Alice Smith's, not yours."
    assert site.writes == []


def test_editing_a_comment_the_issue_does_not_have_is_refused(site):
    site.add("WEB-12")
    site.add("WEB-13")
    site.comment("WEB-13", adf.from_markdown("Elsewhere."))
    with pytest.raises(Precondition) as raised:
        replace("Hi", "10000")
    assert raised.value.message == "WEB-12 has no comment 10000."
    assert site.writes == []


def test_editing_with_an_empty_comment_is_refused_before_the_token_is_read(site):
    with pytest.raises(Precondition) as raised:
        replace("  \n")
    assert raised.value.message == "The comment is empty."
    assert site.tokens_read == 0


def test_a_dry_run_edit_shows_the_comment_and_reads_no_token_and_sends_nothing(site, capsys):
    result = replace("Hi", dry_run=True)
    assert isinstance(result, NothingToDo)
    assert result.summary == "Dry run: nothing edited."
    shown = json.loads(capsys.readouterr().out)
    assert shown == {"issue": "WEB-12", "comment": "10000", "body": adf.from_markdown("Hi")}
    assert site.tokens_read == 0


def test_delete_deletes_your_comment_without_reading_stdin(site, monkeypatch):
    monkeypatch.setattr("sys.stdin", Unread())
    site.add("WEB-12")
    site.comment("WEB-12", adf.from_markdown("Wrong issue."))
    site.comment("WEB-12", adf.from_markdown("Kept."))
    result = delete("WEB-12", "10000")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Deleted comment 10000 from WEB-12.",
        f"{SITE}/browse/WEB-12",
    )
    assert [c["id"] for c in site.comments["WEB-12"]] == ["10001"]


def test_a_comment_the_issue_does_not_have_is_already_deleted(site):
    site.add("WEB-12")
    result = delete("WEB-12", "10000")
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 has no comment 10000 to delete."
    assert site.writes == []


@pytest.mark.parametrize("act", [lambda: replace("Hi"), lambda: delete("WEB-12", "10000")])
def test_editing_or_deleting_on_an_issue_that_is_not_there_is_refused(site, act):
    with pytest.raises(Precondition) as raised:
        act()
    assert raised.value.message == "No issue WEB-12."


def test_the_command_line_edits_a_comment_with_stdin(site, monkeypatch, capsys):
    site.add("WEB-12")
    site.comment("WEB-12", adf.from_markdown("Draft."))
    monkeypatch.setattr("sys.stdin", io.StringIO("Final."))
    assert main(["comment", "12", "--edit", "10000"]) == 0
    assert capsys.readouterr().out.startswith("✅ Edited comment 10000 on WEB-12.\n")


def test_the_command_line_deletes_a_comment(site, monkeypatch, capsys):
    site.add("WEB-12")
    site.comment("WEB-12", adf.from_markdown("Oops."))
    monkeypatch.setattr("sys.stdin", Unread())
    assert main(["comment", "12", "--delete", "10000"]) == 0
    assert capsys.readouterr().out.startswith("✅ Deleted comment 10000 from WEB-12.\n")


@pytest.mark.parametrize(
    "options", [["--edit", "10000", "--delete", "10000"], ["--delete", "10000", "--dry-run"]]
)
def test_the_command_line_refuses_options_that_do_not_go_together(site, options):
    with pytest.raises(SystemExit) as raised:
        main(["comment", "12", *options])
    assert raised.value.code == 2
    assert site.writes == []
