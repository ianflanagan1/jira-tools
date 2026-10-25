"""`jira <command> ...`."""

import sys

from cli_kit import cli

from jira_tools.commands import (
    assign,
    attach,
    comment,
    create,
    edit,
    link,
    log,
    mine,
    move,
    stage,
    start,
    tracker,
    unlink,
    unwatch,
    unweblink,
    view,
    watch,
    weblink,
)

COMMANDS = [
    create,
    view,
    mine,
    start,
    move,
    assign,
    comment,
    attach,
    log,
    watch,
    unwatch,
    edit,
    link,
    unlink,
    weblink,
    unweblink,
    stage,
    tracker,
]


def main(argv: list[str] | None = None) -> int:
    return cli.run(
        "jira",
        "File, read, edit, stage, start, move, assign, link, watch, attach to, log time on and"
        " comment on Jira issues.",
        COMMANDS,
        argv,
    )


if __name__ == "__main__":
    sys.exit(main())
