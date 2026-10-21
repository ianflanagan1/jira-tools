"""jira move: an issue moved to a status by its workflow, filling in the fields its move asks
for, against a fake Jira site."""

import io

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf
from jira_tools.__main__ import main
from jira_tools.commands.move import move

SITE = "https://me.atlassian.net"

ROOT_CAUSE = {
    "required": True,
    "schema": {"type": "option", "custom": "select", "customId": 10050},
    "name": "Root cause",
    "hasDefaultValue": False,
    "allowedValues": [{"id": "1", "value": "Config"}, {"id": "2", "value": "Code"}],
}


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def no_stdin(monkeypatch):
    """stdin is a terminal, as when nothing is piped in."""
    monkeypatch.setattr("sys.stdin", Terminal())


def moved(key: str, status: str, comment: str, **options):
    return move(key, status, stdin=io.StringIO(comment), **options)


@pytest.fixture
def to_done(site):
    """An issue in progress, whose move to Done asks for a resolution."""
    site.add("WEB-12", status="In Progress")
    site.screens["Done"] = {"resolution": site.resolution}
    return site


def test_moves_the_issue_to_the_status_and_gives_its_url(site):
    site.add("WEB-12", status="In Progress")
    result = move("WEB-12", "In Review")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Moved WEB-12 to In Review.",
        f"{SITE}/browse/WEB-12",
    )
    assert site.issues["WEB-12"]["status"]["name"] == "In Review"


def test_the_status_is_matched_ignoring_case_and_named_as_the_workflow_names_it(site):
    site.add("WEB-12")
    assert move("WEB-12", " in progress ").summary == "Moved WEB-12 to In Progress."


def test_an_issue_already_in_the_status_is_left_alone(site):
    site.add("WEB-12", status="In Review")
    result = move("WEB-12", "in review")
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 is already In Review."
    assert site.writes == []


def test_a_status_the_workflow_cannot_reach_from_here_names_those_it_can(site):
    site.add("WEB-12")
    site.moves = {"To Do": ["In Progress", "Done"]}
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "In Review")
    assert [raised.value.message, *raised.value.details] == [
        "WEB-12 can't move from To Do to In Review.",
        "From To Do it can move to: In Progress, Done.",
    ]
    assert site.writes == []


def test_a_status_with_no_moves_says_so(site):
    site.add("WEB-12", status="Done")
    site.moves = {}
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "To Do")
    assert raised.value.details == ("Its workflow has no moves from Done.",)


def test_a_move_to_the_status_it_is_in_is_not_offered(site):
    # A workflow that lets every status move to every other, as a team-managed space's does by
    # default, offers each status a move to itself too.
    site.add("WEB-12")
    site.moves = {"To Do": ["To Do", "In Progress"]}
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "Done")
    assert raised.value.details == ("From To Do it can move to: In Progress.",)


def test_a_status_whose_only_move_is_to_itself_has_no_moves(site):
    site.add("WEB-12")
    site.moves = {"To Do": ["To Do"]}
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "Done")
    assert raised.value.details == ("Its workflow has no moves from To Do.",)


def test_an_issue_that_is_not_there_is_named(site):
    with pytest.raises(Precondition) as raised:
        move("WEB-404", "Done")
    assert raised.value.message == "No issue WEB-404."


def test_a_number_alone_is_an_issue_in_the_set_space(site):
    site.add("WEB-12")
    assert move("12", "Done").summary == "Moved WEB-12 to Done."


def test_the_command_line_takes_the_key_and_status(site, capsys):
    site.add("WEB-12", status="In Progress")
    assert main(["move", "WEB-12", "In Review"]) == 0
    assert capsys.readouterr().out == f"✅ Moved WEB-12 to In Review.\n{SITE}/browse/WEB-12\n"


def test_a_move_whose_screen_needs_a_field_names_it_with_its_allowed_values(to_done):
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "Done")
    assert [raised.value.message, *raised.value.details] == [
        "Moving WEB-12 to Done needs: Resolution (Done, Won't Do, Duplicate).",
        "Give the resolution with --resolution <name>.",
    ]
    assert to_done.writes == []


def test_any_other_field_it_needs_is_named_with_how_to_give_it(to_done):
    to_done.screens["Done"]["customfield_10050"] = ROOT_CAUSE
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "Done")
    assert [raised.value.message, *raised.value.details] == [
        "Moving WEB-12 to Done needs: Resolution (Done, Won't Do, Duplicate); Root cause (Config,"
        " Code).",
        "Give the resolution with --resolution <name>.",
        "Give Root cause with --field 'Root cause=<value>'.",
    ]


def test_a_required_field_with_a_default_or_that_the_issue_already_has_is_not_asked_for(to_done):
    to_done.screens["Done"]["customfield_10050"] = ROOT_CAUSE
    to_done.screens["Done"]["resolution"] = to_done.resolution | {"hasDefaultValue": True}
    to_done.issues["WEB-12"]["customfield_10050"] = {"value": "Code"}
    assert isinstance(move("WEB-12", "Done"), Done)
    assert to_done.issues["WEB-12"]["status"]["name"] == "Done"


def test_a_field_the_move_asks_for_is_given_by_name_and_sent_with_the_move(to_done):
    to_done.screens["Done"]["customfield_10050"] = ROOT_CAUSE
    move("WEB-12", "Done", resolution="done", fields=["root cause=code"])
    assert to_done.issues["WEB-12"]["customfield_10050"] == {"id": "2"}
    assert to_done.issues["WEB-12"]["status"]["name"] == "Done"


def test_a_field_given_that_the_move_cannot_set_is_refused_before_moving(to_done):
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "Done", resolution="done", fields=["Root cause=Code"])
    assert raised.value.message == "'Root cause' can't be set on the move to Done."
    assert to_done.writes == []


def test_a_field_given_a_value_it_cannot_take_is_refused_before_moving(to_done):
    to_done.screens["Done"]["customfield_10050"] = ROOT_CAUSE
    with pytest.raises(Precondition):
        move("WEB-12", "Done", resolution="done", fields=["Root cause=Typo"])
    assert to_done.writes == []


def test_a_field_can_be_given_from_a_file(to_done, tmp_path):
    to_done.screens["Done"]["customfield_10050"] = ROOT_CAUSE
    (tmp_path / "cause.txt").write_text("Config\n")
    move("WEB-12", "Done", resolution="done", files=[f"Root cause={tmp_path / 'cause.txt'}"])
    assert to_done.issues["WEB-12"]["customfield_10050"] == {"id": "1"}


def test_the_command_line_takes_fields(to_done, tmp_path):
    to_done.screens["Done"]["customfield_10050"] = ROOT_CAUSE
    (tmp_path / "cause.txt").write_text("Config")
    argv = ["move", "WEB-12", "Done", "--resolution", "Done", "--field", "Root cause=Code"]
    assert main(argv) == 0
    assert to_done.issues["WEB-12"]["customfield_10050"] == {"id": "2"}


def test_a_field_on_the_screen_that_is_not_required_is_not_asked_for(to_done):
    to_done.screens["Done"]["resolution"] = to_done.resolution | {"required": False}
    assert isinstance(move("WEB-12", "Done"), Done)


def test_the_resolution_is_matched_ignoring_case_and_sent_with_the_move(to_done):
    result = move("WEB-12", "Done", resolution="won't do")
    assert result.summary == "Moved WEB-12 to Done."
    assert to_done.writes == [
        (
            "POST",
            "issue/WEB-12/transitions",
            {"transition": {"id": "3"}, "fields": {"resolution": {"name": "Won't Do"}}},
        )
    ]
    assert to_done.issues["WEB-12"]["resolution"] == {"name": "Won't Do"}


def test_the_resolution_can_be_given_by_name_as_a_field(to_done):
    move("WEB-12", "Done", fields=["Resolution=won't do"])
    assert to_done.writes[-1][2]["fields"] == {"resolution": {"id": "10001"}}
    assert to_done.issues["WEB-12"]["status"]["name"] == "Done"


def test_a_resolution_given_both_by_its_option_and_as_a_field_moves_nothing(to_done):
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "Done", resolution="Done", fields=["Resolution=Won't Do"])
    assert [raised.value.message, *raised.value.details] == [
        "--resolution and --field both set Resolution.",
        "Give it once.",
    ]
    assert to_done.writes == []


def test_a_resolution_the_move_does_not_allow_names_those_it_does(to_done):
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "Done", resolution="Fixed")
    assert [raised.value.message, *raised.value.details] == [
        "Moving WEB-12 to Done can't resolve it as Fixed.",
        "It can be resolved as: Done, Won't Do, Duplicate.",
    ]
    assert to_done.writes == []


def test_a_resolution_cannot_be_given_to_a_move_whose_screen_has_none(site):
    site.add("WEB-12", status="In Progress")
    with pytest.raises(Precondition) as raised:
        move("WEB-12", "In Review", resolution="Done")
    assert [raised.value.message, *raised.value.details] == [
        "Moving WEB-12 to In Review can't set a resolution.",
        "Its workflow doesn't ask for one on that move.",
    ]
    assert site.writes == []


def test_an_issue_already_in_the_status_is_left_alone_whatever_it_is_given(to_done):
    to_done.issues["WEB-12"]["status"] = to_done.status("Done")
    result = moved("WEB-12", "Done", "Shipped.", resolution="Fixed")
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 is already Done."
    assert to_done.writes == []


def test_markdown_on_stdin_is_a_comment_sent_with_a_move_whose_screen_takes_one(to_done):
    to_done.screens["Done"]["comment"] = to_done.comment_field
    result = moved("WEB-12", "Done", "Shipped in **1.2**.", resolution="Done")
    assert result.summary == "Moved WEB-12 to Done, with the comment."
    body = adf.from_markdown("Shipped in **1.2**.")
    [(method, path, sent)] = to_done.writes
    assert sent["update"] == {"comment": [{"add": {"body": body}}]}
    assert [c["body"] for c in to_done.comments["WEB-12"]] == [body]


def test_a_comment_on_a_move_without_a_screen_is_added_after_moving(site, capsys):
    site.add("WEB-12", status="In Progress")
    result = moved("WEB-12", "In Review", "Ready for review.")
    assert (result.summary, *result.details) == (
        "Commented on WEB-12.",
        f"{SITE}/browse/WEB-12?focusedCommentId=10000",
    )
    assert capsys.readouterr().out == "Moved WEB-12 to In Review.\n"
    assert [(method, path) for method, path, _ in site.writes] == [
        ("POST", "issue/WEB-12/transitions"),
        ("POST", "issue/WEB-12/comment"),
    ]
    assert site.issues["WEB-12"]["status"]["name"] == "In Review"
    assert [c["body"] for c in site.comments["WEB-12"]] == [adf.from_markdown("Ready for review.")]


def test_a_required_comment_is_asked_for_on_stdin(to_done):
    to_done.screens["Done"]["comment"] = to_done.comment_field | {"required": True}
    with pytest.raises(Precondition) as raised:
        moved("WEB-12", "Done", "  ", resolution="Done")
    assert [raised.value.message, *raised.value.details] == [
        "Moving WEB-12 to Done needs: Comment.",
        "Give the comment as Markdown on stdin.",
    ]


def test_the_command_line_takes_the_resolution_and_a_comment_on_stdin(to_done, monkeypatch, capsys):
    to_done.screens["Done"]["comment"] = to_done.comment_field
    monkeypatch.setattr("sys.stdin", io.StringIO("Shipped."))
    assert main(["move", "12", "done", "--resolution", "duplicate"]) == 0
    assert capsys.readouterr().out.startswith("✅ Moved WEB-12 to Done, with the comment.\n")
    assert to_done.issues["WEB-12"]["resolution"] == {"name": "Duplicate"}
    assert len(to_done.comments["WEB-12"]) == 1
