"""Settings from the repository's .config/ianf-tracker.toml, as it is in the worktree you're in, so
a branch can change them: the Jira site and space issues go to, the type and labels they're filed
with, and the status each stage of our process is kept in. The file is committed with the
repository, since where a repository's issues go is the team's to decide, not each person's;
ianf-tracker.example.toml shows it, and schema/ has its schema for each version.

The settings can also come from a product map's front matter, as its [tracker] table, which
product-map copies from the app's file, so an issue about an app can be filed from outside its
repository. site and space have no default; a setting with one that's left out is named on
stderr.
"""

import sys
import tomllib
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import assert_never

import repo_settings
from cli_kit.outcome import Precondition
from repo_settings import Invalid, Missing, Settings, Source, Unlocatable

from jira_tools.stages import STAGES

PURPOSE = "tracker"
FILE = repo_settings.location(PURPOSE)
EXAMPLE = "See ianf-tracker.example.toml in jira-tools."
REBUILD = "A product map copies its app's tracker settings: build and publish it again."
SETTINGS = ("kind", "site", "space", "issue_type", "labels", "stages")
WITH_DEFAULTS = ("kind", "issue_type", "labels", "stages")


class Version(IntEnum):
    """The versions of the file's format jira-tools reads."""

    V1 = 1


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
    """The settings in path: a .config/ianf-tracker.toml, or a Markdown file with them in the
    [tracker] table of its TOML front matter, such as a product map. Without path, those in the
    repository cwd, by default the current folder, is in. Raises Precondition when there's no
    such file, or its settings are missing or wrong."""
    return located(path, cwd or Path.cwd())[0]


def located(path: Path | None, cwd: Path) -> tuple[Config, str]:
    """The settings load reads, and the file they came from."""
    if path is None:
        read = _in_repository(cwd)
    elif path.suffix == ".md":
        read = repo_settings.parse(_front_matter_table(path), f"[tracker] in {path}", Version)
        if isinstance(read, Invalid):
            raise Precondition(read.message, REBUILD)
    else:
        read = repo_settings.read_file(path, Version)
        if isinstance(read, Missing):
            raise Precondition(f"No {read.where}.")
        if isinstance(read, Invalid):
            raise Precondition(read.message, *read.details)
    match read.version:
        case Version.V1:
            return _settings(read.table, read.where), str(path or read.where)
        case _:
            assert_never(read.version)


def _in_repository(folder: Path) -> Settings[Version]:
    """The settings in the worktree folder is in, as it is on disk. Raises Precondition outside
    a repository, or when it has none."""
    read = repo_settings.read(Source.LOCAL_THIS_WORKTREE, folder, PURPOSE, Version)
    match read:
        case Settings():
            return read
        case Unlocatable():
            raise Precondition(
                read.message,
                f"Run it in the repository the issue is about: its {FILE} says where its"
                " issues go.",
            )
        case Missing():
            raise Precondition(
                f"No {read.where}.",
                "Add one: copy ianf-tracker.example.toml from jira-tools there and edit it.",
            )
        case Invalid():
            raise Precondition(read.message, *read.details)
        case _:
            assert_never(read)


def _front_matter_table(path: Path) -> dict:
    """The [tracker] table of a Markdown file's front matter."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        raise Precondition(f"No {path}.") from None
    try:
        tracker = tomllib.loads(front_matter(text, path)).get("tracker")
    except tomllib.TOMLDecodeError as error:
        raise Precondition(f"{path} isn't valid TOML.", str(error)) from None
    if not isinstance(tracker, dict):
        raise Precondition(f"No [tracker] table in {path}.", EXAMPLE)
    return tracker


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


def _settings(tracker: dict, where: str) -> Config:
    if unknown := tracker.keys() - set(SETTINGS):
        raise Precondition(f"Unknown setting {', '.join(sorted(unknown))} in {where}.", EXAMPLE)
    for name in ("site", "space"):
        if name not in tracker:
            raise Precondition(f"No {name} set in {where}.", EXAMPLE)
    for name in ("kind", "site", "space", "issue_type"):
        if not isinstance(tracker.get(name, ""), str):
            raise Precondition(f"{name} must be a string in {where}.")
    if (kind := tracker.get("kind", "jira")) != "jira":
        raise Precondition(f"jira-tools files only in Jira, and {where} names {kind}.")
    labels = tracker.get("labels", list(Config.labels))
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise Precondition(f"labels must be a list of strings in {where}.")
    if defaulted := [name for name in WITH_DEFAULTS if name not in tracker]:
        names = " and ".join(", ".join(defaulted).rsplit(", ", 1))
        print(f"Using the defaults for {names}: {where} doesn't set them.", file=sys.stderr)
    return Config(
        tracker["site"],
        tracker["space"],
        tracker.get("issue_type", Config.issue_type),
        tuple(labels),
        _stages(tracker.get("stages"), where),
    )


def _stages(table: object, where: str) -> dict[str, str]:
    """The [stages] table: each stage named is kept in its status. Without the table, only
    being-worked-on is, in In Progress."""
    if table is None:
        return dict(Config("", "").stages)
    if not isinstance(table, dict):
        raise Precondition(f"stages must be a table in {where}.", EXAMPLE)
    if unknown := sorted(set(table) - set(STAGES)):
        raise Precondition(
            f"No stage {', '.join(unknown)} in {where}.", f"The stages are: {', '.join(STAGES)}."
        )
    stages: dict[str, str] = {}
    for stage in (name for name in STAGES if name in table):
        status = table[stage]
        if not isinstance(status, str) or not status.strip():
            raise Precondition(f"The status for {stage} must be a name in {where}.")
        status = status.strip()
        taken = (other for other, name in stages.items() if name.casefold() == status.casefold())
        if other := next(taken, None):
            raise Precondition(f"{other} and {stage} are both kept in {status} in {where}.")
        stages[stage] = status
    return stages
