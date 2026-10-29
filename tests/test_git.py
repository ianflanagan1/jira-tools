"""The git repository `jira start` works in: whether there is one, its branch, and the branch
for an issue, here or on origin."""

import subprocess
from pathlib import Path

import pytest
from cli_kit.outcome import Failure

from jira_tools import git


def run(directory: Path, *args: str) -> str:
    who = ["-c", "user.name=t", "-c", "user.email=t@t"]
    return subprocess.run(
        ["git", "-C", str(directory), *who, *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository on branch main, with one commit, cloned from origin."""
    origin = tmp_path / "origin"
    origin.mkdir()
    run(origin, "init", "--quiet", "--initial-branch", "main")
    run(origin, "commit", "--quiet", "--allow-empty", "--message", "x")
    run(origin, "branch", "WEB-7-on-origin")
    run(tmp_path, "clone", "--quiet", str(origin), "shop")
    return tmp_path / "shop"


def test_a_folder_in_a_repository_is_one(repo):
    (repo / "src").mkdir()
    assert git.is_repository(repo / "src")


def test_a_folder_outside_one_is_not(tmp_path):
    assert not git.is_repository(tmp_path)


def test_names_the_current_branch(repo):
    assert git.current_branch(repo) == "main"


def test_a_detached_head_is_on_no_branch(repo):
    run(repo, "switch", "--quiet", "--detach")
    assert git.current_branch(repo) is None


@pytest.mark.parametrize("name", ["WEB-12", "WEB-12-scan-skips-symlinks"])
def test_the_local_branch_for_an_issue_is_named_by_its_key(repo, name):
    run(repo, "branch", name)
    assert git.local_branch_for(repo, "WEB-12") == name


def test_a_branch_for_another_issue_whose_key_begins_the_same_is_not_it(repo):
    run(repo, "branch", "WEB-123-other")
    assert git.local_branch_for(repo, "WEB-12") is None


def test_finds_the_branch_for_an_issue_on_origin(repo):
    assert git.local_branch_for(repo, "WEB-7") is None
    assert git.remote_branch_for(repo, "WEB-7") == "WEB-7-on-origin"
    assert git.remote_branch_for(repo, "WEB-8") is None


def test_creates_a_branch_from_the_current_commit_and_switches_to_it(repo):
    git.create(repo, "WEB-12-x")
    assert git.current_branch(repo) == "WEB-12-x"
    assert run(repo, "rev-parse", "WEB-12-x") == run(repo, "rev-parse", "main")


def test_creates_a_branch_tracking_one_on_origin(repo):
    git.create(repo, "WEB-7-on-origin", tracking="origin/WEB-7-on-origin")
    assert run(repo, "rev-parse", "--abbrev-ref", "@{upstream}") == "origin/WEB-7-on-origin"


def test_switches_to_an_existing_branch(repo):
    run(repo, "branch", "WEB-12-x")
    git.switch(repo, "WEB-12-x")
    assert git.current_branch(repo) == "WEB-12-x"


def test_a_switch_git_refuses_is_a_failure(repo):
    with pytest.raises(Failure):
        git.switch(repo, "no-such-branch")
