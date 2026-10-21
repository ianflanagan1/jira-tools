"""The git repository `jira start` works in: whether there is one, its branch, and the branch for
an issue, which is named by its key: WEB-12, or WEB-12 and a hyphen and more."""

import subprocess
from pathlib import Path

from cli_kit import proc


def is_repository(directory: Path) -> bool:
    return _git(directory, "rev-parse", "--git-dir") is not None


def current_branch(directory: Path) -> str | None:
    """The branch checked out, or None on a detached HEAD."""
    return _git(directory, "symbolic-ref", "--short", "-q", "HEAD")


def local_branch_for(directory: Path, key: str) -> str | None:
    """The local branch for the issue with key, or None. The first by name when there are
    several."""
    return _first_branch(directory, "refs/heads/", key)


def remote_branch_for(directory: Path, key: str) -> str | None:
    """The branch on origin for the issue with key, without origin/, or None."""
    return _first_branch(directory, "refs/remotes/origin/", key)


def create(directory: Path, branch: str, tracking: str | None = None) -> None:
    """Creates branch and switches to it: from tracking, such as origin/WEB-12, and following
    it, or from the current commit. Raises Failure when git refuses."""
    start = ["--track", tracking] if tracking else []
    proc.output("git", "-C", str(directory), "switch", "-q", "-c", branch, *start)


def switch(directory: Path, branch: str) -> None:
    """Switches to branch. Raises Failure when git refuses, such as when uncommitted changes
    would be overwritten."""
    proc.output("git", "-C", str(directory), "switch", "-q", branch)


def _first_branch(directory: Path, prefix: str, key: str) -> str | None:
    found = _git(
        directory,
        "for-each-ref",
        "--format=%(refname)",
        f"{prefix}{key}",
        f"{prefix}{key}-*",
    )
    names = sorted(ref.removeprefix(prefix) for ref in (found or "").splitlines())
    return names[0] if names else None


def _git(directory: Path, *args: str) -> str | None:
    """git's output in directory, or None when it fails or prints nothing."""
    result = subprocess.run(
        ["git", "-C", str(directory), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
