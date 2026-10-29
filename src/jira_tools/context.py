"""Where an issue was raised, read from the git repository it was filed in, as a sentence of
Markdown for its description."""

import re
import subprocess
from pathlib import Path

GITHUB = re.compile(r"^(?:git@github\.com:|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?/?$")


def where(directory: Path) -> str | None:
    """A sentence such as: Raised on branch `main` at <commit> in <repository>. The commit and
    repository are links on GitHub. None outside a repository or before its first commit."""
    commit = _git(directory, "rev-parse", "HEAD")
    if commit is None:
        return None
    branch = _git(directory, "symbolic-ref", "--short", "--quiet", "HEAD")
    origin = _git(directory, "remote", "get-url", "origin")
    top = _git(directory, "rev-parse", "--show-toplevel")

    on = f" on branch `{branch}`" if branch else ""
    if origin and (github := GITHUB.match(origin)):
        repository = f"https://github.com/{github[1]}"
        at = f"[{commit[:7]}]({repository}/commit/{commit})"
        within = f"[{github[1]}]({repository})"
    else:
        at = f"`{commit[:7]}`"
        within = f"`{origin or Path(top or directory).name}`"
    return f"Raised{on} at {at} in {within}."


def _git(directory: Path, *args: str) -> str | None:
    """git's output in directory, or None when it fails."""
    result = subprocess.run(
        ["git", "-C", str(directory), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
