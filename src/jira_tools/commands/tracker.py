"""jira tracker [--tracker <file>]

Shows where the current repository's issues go: the settings in its .config/ianf-tracker.toml,
or in the file --tracker names, with the defaults of any left out. Skills run it as they load,
so they stop before any work when nothing could be filed.

jira workspace and --workspace, its names before the settings moved to .config/, still run it,
with a warning, and are left out of the command list.
"""

import argparse
from pathlib import Path

from cli_kit import cli
from cli_kit.outcome import NothingToDo

from jira_tools import config
from jira_tools.stages import STAGES


def register(subparsers: cli.Subparsers) -> None:
    description = __doc__.split("\n\n", 1)[1]
    parser = subparsers.add_parser(
        "tracker", help="show where this repository's issues go", description=description
    )
    # Without help, the old name is left out of the command list.
    old = subparsers.add_parser("workspace", description=description, deprecated=True)
    for each in (parser, old):
        _add_option(each)
        each.set_defaults(run=lambda args: tracker(args.tracker))


def _add_option(parser: argparse.ArgumentParser) -> None:
    """--tracker, the file to read the settings from instead, and --workspace, its old name."""
    parser.add_argument(
        "--tracker",
        metavar="file",
        type=Path,
        help="the ianf-tracker.toml or product map to read instead",
    )
    parser.add_argument(
        "--workspace", dest="tracker", type=Path, help=argparse.SUPPRESS, deprecated=True
    )


def tracker(path: Path | None = None, *, cwd: Path | None = None) -> NothingToDo:
    settings, source = config.located(path, cwd or Path.cwd())
    kept = [f"{stage} in {status}" for stage, status in settings.stages.items()]
    labelled = [stage for stage in STAGES if stage not in settings.stages]
    if labelled:
        kept.append(f"{' and '.join(', '.join(labelled).rsplit(', ', 1))} as stage-<name> labels")
    print(f"Settings: {source}")
    print(f"Site: {settings.base_url}")
    print(f"Space: {settings.space}")
    print(f"Issue type: {settings.issue_type}")
    print(f"Labels: {', '.join(settings.labels) or 'none'}")
    print(f"Stages: {'; '.join(kept)}")
    return NothingToDo(f"Issues go to {settings.space} at {settings.base_url}.")
