"""jira workspace [--workspace <file>]

Shows where the current repository's issues go: the settings in the [tracker] table of its
.workspace.toml, or of the file --workspace names, with the defaults of any left out. Skills run
it as they load, so they stop before any work when nothing could be filed.
"""

from pathlib import Path

from cli_kit import cli
from cli_kit.outcome import NothingToDo

from jira_tools import config
from jira_tools.stages import STAGES


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "workspace",
        help="show where this repository's issues go",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument(
        "--workspace",
        metavar="file",
        type=Path,
        help="the .workspace.toml or product map to read instead",
    )
    parser.set_defaults(run=lambda args: workspace(args.workspace))


def workspace(path: Path | None = None, *, cwd: Path | None = None) -> NothingToDo:
    path = path or config.find(cwd or Path.cwd())
    settings = config.load(path)
    kept = [f"{stage} in {status}" for stage, status in settings.stages.items()]
    labelled = [stage for stage in STAGES if stage not in settings.stages]
    if labelled:
        kept.append(f"{' and '.join(', '.join(labelled).rsplit(', ', 1))} as stage-<name> labels")
    print(f"Settings: {path}")
    print(f"Site: {settings.base_url}")
    print(f"Space: {settings.space}")
    print(f"Issue type: {settings.issue_type}")
    print(f"Labels: {', '.join(settings.labels) or 'none'}")
    print(f"Stages: {'; '.join(kept)}")
    return NothingToDo(f"Issues go to {settings.space} at {settings.base_url}.")
