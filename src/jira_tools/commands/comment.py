"""jira comment <key> [--edit <id> | --delete <id>] [--dry-run]

Adds the Markdown on stdin to the issue as a comment from you. It isn't added again while the
issue has a comment from you that reads the same, so running it again after a failure is safe.
--dry-run shows what would be sent, without the API token or Jira.

--edit <id> replaces your comment with that id with the Markdown on stdin instead, and
--delete <id> deletes it, reading nothing. Each touches only your own comments. A comment the
issue doesn't have is already deleted, so --delete leaves it at that. `jira view` shows each
comment's id.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

import json
import sys
from typing import TextIO

from cli_kit import cli
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import adf, api, config, keys, session


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "comment",
        help="comment on an issue with the Markdown on stdin, or edit or delete your comment",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--edit", metavar="<id>", help="replace your comment with this id")
    which.add_argument("--delete", metavar="<id>", help="delete your comment with this id")
    parser.add_argument("--dry-run", action="store_true", help="show what would be sent")

    def run(args) -> Done | NothingToDo:
        if args.delete is not None:
            if args.dry_run:
                parser.error("argument --dry-run: not allowed with argument --delete")
            return delete(args.key, args.delete)
        if args.edit is not None:
            return edit(args.key, args.edit, dry_run=args.dry_run)
        return comment(args.key, dry_run=args.dry_run)

    parser.set_defaults(run=run)


def comment(key: str, *, dry_run: bool = False, stdin: TextIO | None = None) -> Done | NothingToDo:
    body = _read(stdin)
    settings = config.load()
    key = keys.issue_key(key, settings.space)

    if dry_run:
        print(json.dumps({"issue": key, "body": body}, indent=2))
        return NothingToDo("Dry run: nothing commented.")

    jira = session.connect(settings)
    comments = _comments(jira, key)
    me = jira.myself().account_id
    reads = adf.to_markdown(body)
    if any(_author(c) == me and adf.to_markdown(c.get("body", {})) == reads for c in comments):
        return NothingToDo(f"Already commented on {key}.")
    return Done(f"Commented on {key}.", jira.add_comment(key, body))


def edit(
    key: str, comment_id: str, *, dry_run: bool = False, stdin: TextIO | None = None
) -> Done | NothingToDo:
    """Replaces your comment with comment_id with the Markdown on stdin."""
    body = _read(stdin)
    settings = config.load()
    key = keys.issue_key(key, settings.space)

    if dry_run:
        print(json.dumps({"issue": key, "comment": comment_id, "body": body}, indent=2))
        return NothingToDo("Dry run: nothing edited.")

    jira = session.connect(settings)
    found = _yours(jira, key, comment_id)
    if found is None:
        raise Precondition(f"{key} has no comment {comment_id}.", f"See its ids: jira view {key}")
    if adf.to_markdown(found.get("body", {})) == adf.to_markdown(body):
        return NothingToDo(f"Comment {comment_id} on {key} already reads so.")
    return Done(f"Edited comment {comment_id} on {key}.", jira.edit_comment(key, comment_id, body))


def delete(key: str, comment_id: str) -> Done | NothingToDo:
    """Deletes your comment with comment_id. One the issue doesn't have is taken as already
    deleted, so running it again is safe."""
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    jira = session.connect(settings)
    if _yours(jira, key, comment_id) is None:
        return NothingToDo(f"{key} has no comment {comment_id} to delete.")
    jira.delete_comment(key, comment_id)
    return Done(f"Deleted comment {comment_id} from {key}.", jira.issue_link(key).url)


def _read(stdin: TextIO | None) -> dict:
    """The Markdown on stdin, as an ADF document. Raises Precondition when there's none."""
    stdin = stdin or sys.stdin
    markdown = "" if stdin.isatty() else stdin.read().strip()
    if not markdown:
        raise Precondition("The comment is empty.", "Give it as Markdown on stdin.")
    return adf.from_markdown(markdown)


def _comments(jira: api.Jira, key: str) -> list[dict]:
    comments = jira.comments(key)
    if comments is None:
        raise session.missing(key)
    return comments


def _yours(jira: api.Jira, key: str, comment_id: str) -> dict | None:
    """The issue's comment with comment_id, or None when it has none. Raises Precondition when
    it's someone else's."""
    found = next((c for c in _comments(jira, key) if c.get("id") == comment_id), None)
    if found is not None and _author(found) != jira.myself().account_id:
        author = found.get("author", {}).get("displayName", "someone else")
        raise Precondition(
            f"Comment {comment_id} on {key} is {author}'s, not yours.",
            "jira edits and deletes only your own comments.",
        )
    return found


def _author(comment: dict) -> str | None:
    return comment.get("author", {}).get("accountId")
