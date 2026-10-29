"""jira start: an issue assigned to you, moved to in progress, and its branch checked out, against
a fake Jira site and a real git repository."""

import subprocess
from pathlib import Path

import pytest
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.start import branch_name, start

SITE = "https://me.atlassian.net"


def git(directory: Path, *args: str) -> str:
    who = ["-c", "user.name=t", "-c", "user.email=t@t"]
    return subprocess.run(
        ["git", "-C", str(directory), *who, *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The current folder: a repository on main with one commit, cloned from origin."""
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "--quiet", "--initial-branch", "main")
    git(origin, "commit", "--quiet", "--allow-empty", "--message", "x")
    git(tmp_path, "clone", "--quiet", str(origin), "shop")
    monkeypatch.chdir(tmp_path / "shop")
    return tmp_path / "shop"


def branch(repo: Path) -> str:
    return git(repo, "branch", "--show-current")


def test_assigns_it_to_you_moves_it_in_progress_and_creates_its_branch(site, repo, capsys):
    site.add("WEB-12", "Scan skips symlinks")
    result = start("WEB-12")
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == ("Started WEB-12.", f"{SITE}/browse/WEB-12")
    assert capsys.readouterr().out == (
        "Assigned WEB-12 to you.\n"
        "Moved WEB-12 to In Progress.\n"
        "Created branch WEB-12-scan-skips-symlinks.\n"
    )
    issue = site.issues["WEB-12"]
    assert issue["assignee"]["accountId"] == "me-1"
    assert issue["status"]["name"] == "In Progress"
    assert branch(repo) == "WEB-12-scan-skips-symlinks"


def test_moves_it_to_the_set_start_status(site, repo):
    site.settings = site.settings.__class__(
        "me.atlassian.net", "WEB", stages={"being-worked-on": "In Review"}
    )
    site.add("WEB-12")
    start("WEB-12")
    assert site.issues["WEB-12"]["status"]["name"] == "In Review"


def test_switches_to_the_issues_branch_when_it_has_one(site, repo):
    git(repo, "branch", "WEB-12-older-name")
    site.add("WEB-12", "A newer summary")
    start("WEB-12")
    assert branch(repo) == "WEB-12-older-name"


def test_takes_the_issues_branch_from_origin_following_it(site, repo, tmp_path):
    git(tmp_path / "origin", "branch", "WEB-12-pushed")
    git(repo, "fetch", "--quiet")
    site.add("WEB-12")
    start("WEB-12")
    assert branch(repo) == "WEB-12-pushed"
    assert git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") == "origin/WEB-12-pushed"


def test_an_issue_already_started_is_left_alone(site, repo):
    git(repo, "switch", "--quiet", "--create", "WEB-12-x")
    site.add("WEB-12", status="In Progress", assignee=site.me)
    result = start("WEB-12")
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 is already started, on branch WEB-12-x."
    assert site.writes == []


def test_an_issue_in_any_other_open_status_is_moved_to_the_start_status(site, repo):
    site.add("WEB-12", status="In Review", assignee=site.me)
    start("WEB-12")
    assert site.issues["WEB-12"]["status"]["name"] == "In Progress"


def test_an_issue_its_workflow_cannot_move_to_the_start_status_in_one_move_is_left_alone(
    site, repo
):
    site.add("WEB-12", status="In Review")
    site.moves = {"In Review": ["Done"]}
    with pytest.raises(Precondition) as raised:
        start("WEB-12")
    assert [raised.value.message, *raised.value.details] == [
        "WEB-12 can't move from In Review to In Progress.",
        "From In Review it can move to: Done.",
    ]
    assert site.writes == []
    assert branch(repo) == "main"


def test_a_move_to_the_start_status_that_needs_fields_stops_it_before_any_change(site, repo):
    site.add("WEB-12")
    sprint = {"required": True, "name": "Sprint", "hasDefaultValue": False}
    site.screens["In Progress"] = {"customfield_10020": sprint}
    with pytest.raises(Precondition) as raised:
        start("WEB-12")
    assert [raised.value.message, *raised.value.details] == [
        "Moving WEB-12 to In Progress needs: Sprint.",
        "Move it with jira move WEB-12 'In Progress' and its options, then run start again.",
        "Give Sprint with --field 'Sprint=<value>'.",
    ]
    assert site.writes == []
    assert branch(repo) == "main"


def test_a_move_that_needs_the_assignee_start_sets_is_made(site, repo):
    site.add("WEB-12")
    assignee = {"required": True, "name": "Assignee", "hasDefaultValue": False}
    site.screens["In Progress"] = {"assignee": assignee}
    start("WEB-12")
    assert site.issues["WEB-12"]["status"]["name"] == "In Progress"
    assert site.issues["WEB-12"]["assignee"] == site.me


def test_an_issue_assigned_to_someone_else_is_left_alone(site, repo):
    alice = site.person("a-1", "Alice Smith")
    site.add("WEB-12", assignee=alice)
    with pytest.raises(Precondition) as raised:
        start("WEB-12")
    assert [raised.value.message, *raised.value.details] == [
        "WEB-12 is assigned to Alice Smith.",
        "If you're taking it over, assign it to yourself first: jira assign WEB-12",
    ]
    assert site.writes == []
    assert branch(repo) == "main"


def test_a_done_issue_is_left_alone(site, repo):
    site.add("WEB-12", status="Done")
    with pytest.raises(Precondition) as raised:
        start("WEB-12")
    assert raised.value.message == "WEB-12 is Done."
    assert site.writes == []


def test_a_workflow_that_cannot_reach_the_start_status_stops_it_before_any_change(site, repo):
    site.add("WEB-12")
    site.moves = {"To Do": ["Done"]}
    with pytest.raises(Precondition) as raised:
        start("WEB-12")
    assert raised.value.message == "WEB-12 can't move from To Do to In Progress."
    assert site.writes == []
    assert branch(repo) == "main"


def test_outside_a_repository_it_tries_nothing(site, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        start("WEB-12")
    assert raised.value.message == "Not in a git repository."
    assert site.tokens_read == 0


def test_a_branch_git_cannot_switch_to_stops_it_saying_what_was_done(site, repo, capsys):
    git(repo, "switch", "--quiet", "--create", "WEB-12-x")
    (repo / "file").write_text("one")
    git(repo, "add", "file")
    git(repo, "commit", "--quiet", "--message", "file")
    git(repo, "switch", "--quiet", "main")
    (repo / "file").write_text("uncommitted")
    site.add("WEB-12")
    assert main(["start", "WEB-12"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("🛑 Stopped.\nDone before it stopped:\n  Assigned WEB-12 to you.\n")
    assert site.issues["WEB-12"]["status"]["name"] == "In Progress"


@pytest.mark.parametrize(
    ("summary", "name"),
    [
        ("Scan skips symlinks", "WEB-12-scan-skips-symlinks"),
        ("Fix `scan()`'s crash on Ünïcode paths!", "WEB-12-fix-scan-s-crash-on-n-code-paths"),
        (
            "A very long summary that goes on and on past the point of use",
            ("WEB-12-a-very-long-summary-that-goes-on-and-on"),
        ),
        ("???", "WEB-12"),
    ],
)
def test_a_new_branch_is_named_for_the_key_and_summary(summary, name):
    assert branch_name("WEB-12", summary) == name
