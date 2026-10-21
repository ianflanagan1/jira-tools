"""Where an issue was raised: the sentence added to its description, read from the git
repository it was filed in."""

import subprocess
from pathlib import Path

import pytest

from jira_tools.context import where


def git(directory: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository called shop on branch main, with one commit."""
    path = tmp_path / "shop"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    who = ["-c", "user.name=t", "-c", "user.email=t@t"]
    git(path, *who, "commit", "-q", "--allow-empty", "-m", "x")
    return path


def test_outside_a_repository_there_is_nothing_to_say(tmp_path):
    assert where(tmp_path) is None


def test_a_repository_without_commits_has_nothing_to_say(tmp_path):
    git(tmp_path, "init", "-q")
    assert where(tmp_path) is None


@pytest.mark.parametrize(
    "origin",
    ["git@github.com:me/shop.git", "https://github.com/me/shop.git", "https://github.com/me/shop"],
)
def test_a_github_repository_links_the_commit_and_the_repository(repo, origin):
    git(repo, "remote", "add", "origin", origin)
    commit = git(repo, "rev-parse", "HEAD")
    assert where(repo) == (
        f"Raised on branch `main` at [{commit[:7]}](https://github.com/me/shop/commit/{commit})"
        " in [me/shop](https://github.com/me/shop)."
    )


def test_another_host_names_the_origin_url(repo):
    git(repo, "remote", "add", "origin", "git@gitlab.com:me/shop.git")
    commit = git(repo, "rev-parse", "--short=7", "HEAD")
    assert where(repo) == f"Raised on branch `main` at `{commit}` in `git@gitlab.com:me/shop.git`."


def test_without_an_origin_it_names_the_folder(repo):
    commit = git(repo, "rev-parse", "--short=7", "HEAD")
    assert where(repo) == f"Raised on branch `main` at `{commit}` in `shop`."


def test_a_detached_head_names_no_branch(repo):
    git(repo, "checkout", "-q", "--detach")
    commit = git(repo, "rev-parse", "--short=7", "HEAD")
    assert where(repo) == f"Raised at `{commit}` in `shop`."


def test_it_works_from_a_folder_inside_the_repository(repo):
    (repo / "src").mkdir()
    assert where(repo / "src").endswith("in `shop`.")
