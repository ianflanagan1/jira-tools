"""Settings from the [tracker] table of the repository's .workspace.toml: the Jira site and space
issues go to, the type and labels they're filed with, and the status each stage of our process is
kept in. The file is committed with the repository, since where a repository's issues go is the
team's to decide, not each person's; workspace.example.toml shows the table.

The table can also come from a product map's front matter, which product-map copies from the
app's .workspace.toml, so an issue about an app can be filed from outside its repository. site
and space have no default; a setting with one that's left out is named on stderr.
"""

import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from cli_kit.outcome import Precondition

from jira_tools.stages import STAGES

FILE = ".workspace.toml"
EXAMPLE = "See workspace.example.toml in jira-tools."
SETTINGS = ("kind", "site", "space", "issue_type", "labels", "stages")
WITH_DEFAULTS = ("kind", "issue_type", "labels", "stages")


@dataclass(frozen=True)
class Config:
    site: str
    """The Jira Cloud site, such as "me.atlassian.net"."""
    space: str
    """The key of the space issues are filed in, such as "WEB". Jira's API calls a space a
    project."""
    issue_type: str = "Task"
    labels: tuple[str, ...] = ()
    """Every issue filed gets these labels."""
    stages: dict[str, str] = field(default_factory=lambda: {"being-worked-on": "In Progress"})
    """The status each stage is kept in, by stage; a stage left out is kept as a label."""

    @property
    def base_url(self) -> str:
        site = self.site.removeprefix("https://").removeprefix("http://").rstrip("/")
        return f"https://{site}"


def load(path: Path | None = None, *, cwd: Path | None = None) -> Config:
    """The [tracker] settings in path: a .workspace.toml, or a Markdown file with them in its
    TOML front matter, such as a product map. Without path, those in the .workspace.toml at the
    root of the repository cwd, by default the current folder, is in. Raises Precondition when
    there's no such file, or its settings are missing or wrong."""
    path = path or find(cwd or Path.cwd())
    try:
        text = path.read_text()
    except FileNotFoundError:
        raise Precondition(f"No {path}.") from None
    if path.suffix == ".md":
        text = front_matter(text, path)
    try:
        tracker = tomllib.loads(text).get("tracker")
    except tomllib.TOMLDecodeError as error:
        raise Precondition(f"{path} isn't valid TOML.", str(error)) from None
    if not isinstance(tracker, dict):
        raise Precondition(f"No [tracker] table in {path}.", EXAMPLE)
    return _settings(tracker, path)


def find(folder: Path) -> Path:
    """The .workspace.toml at the root of the repository folder is in. Raises Precondition
    outside a repository, or when it has none."""
    result = subprocess.run(
        ["git", "-C", str(folder), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise Precondition(
            "Not in a git repository.",
            f"Run it in the repository the issue is about: its {FILE} says where its issues go.",
        )
    root = Path(result.stdout.strip())
    if not (root / FILE).is_file():
        raise Precondition(
            f"No {FILE} in {root}.",
            "Add one with a [tracker] table: see workspace.example.toml in jira-tools.",
        )
    return root / FILE


def front_matter(text: str, path: Path) -> str:
    """The TOML between the +++ lines that open a Markdown file."""
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines[1:], 1) if line == "+++"), None)
    if not lines or lines[0] != "+++" or end is None:
        raise Precondition(
            f"No front matter in {path}.",
            "A product map starts with its settings between +++ lines; build it again.",
        )
    return "\n".join(lines[1:end])


def _settings(tracker: dict, path: Path) -> Config:
    where = f"[tracker] in {path}"
    if unknown := tracker.keys() - set(SETTINGS):
        raise Precondition(f"Unknown setting {', '.join(sorted(unknown))} in {where}.", EXAMPLE)
    for name in ("site", "space"):
        if name not in tracker:
            raise Precondition(f"No {name} set in {where}.", EXAMPLE)
    for name in ("kind", "site", "space", "issue_type"):
        if not isinstance(tracker.get(name, ""), str):
            raise Precondition(f"{name} must be a string in {path}.")
    if (kind := tracker.get("kind", "jira")) != "jira":
        raise Precondition(f"jira-tools files only in Jira, and {path} names {kind}.")
    labels = tracker.get("labels", list(Config.labels))
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise Precondition(f"labels must be a list of strings in {path}.")
    if defaulted := [name for name in WITH_DEFAULTS if name not in tracker]:
        names = " and ".join(", ".join(defaulted).rsplit(", ", 1))
        print(f"Using the defaults for {names}: {path} doesn't set them.", file=sys.stderr)
    return Config(
        tracker["site"],
        tracker["space"],
        tracker.get("issue_type", Config.issue_type),
        tuple(labels),
        _stages(tracker.get("stages"), path),
    )


def _stages(table: object, path: Path) -> dict[str, str]:
    """The [tracker.stages] table: each stage named is kept in its status. Without the table,
    only being-worked-on is, in In Progress."""
    if table is None:
        return dict(Config("", "").stages)
    if not isinstance(table, dict):
        raise Precondition(f"stages must be a table in {path}.", EXAMPLE)
    if unknown := sorted(set(table) - set(STAGES)):
        raise Precondition(
            f"No stage {', '.join(unknown)} in {path}.", f"The stages are: {', '.join(STAGES)}."
        )
    stages: dict[str, str] = {}
    for stage in (name for name in STAGES if name in table):
        status = table[stage]
        if not isinstance(status, str) or not status.strip():
            raise Precondition(f"The status for {stage} must be a name in {path}.")
        status = status.strip()
        taken = (other for other, name in stages.items() if name.casefold() == status.casefold())
        if other := next(taken, None):
            raise Precondition(f"{other} and {stage} are both kept in {status} in {path}.")
        stages[stage] = status
    return stages
