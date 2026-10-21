"""jira attach <key> [<file>...] [--session <id> [--image <n>]...]

Uploads each file to the issue, and with --session, the images pasted into that Claude Code
session: all of them, or those --image names by their number, counting from 1 in the order they
were pasted. Claude Code keeps a pasted image only in the session's transcript, so this is how
one gets to an issue; each is uploaded as pasted-image-<n>.png.

A file the issue already has an attachment of, with its name and size, is left out, so running it
again after a failure is safe. Every file and image must be there and readable before any is
uploaded.

<key> is the issue's key, such as WEB-12, its number alone for one in the set space, or its URL.
"""

import re
from pathlib import Path

from cli_kit import cli, outcome
from cli_kit.outcome import Done, NothingToDo, Precondition

from jira_tools import config, keys, pasted
from jira_tools import session as connection


def register(subparsers: cli.Subparsers) -> None:
    parser = subparsers.add_parser(
        "attach",
        help="upload files to an issue",
        description=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("key", help="the issue's key, such as WEB-12")
    parser.add_argument("files", nargs="*", metavar="file", help="a file to attach")
    parser.add_argument("--session", metavar="id", help="a Claude Code session's id")
    parser.add_argument(
        "--image",
        type=int,
        action="append",
        default=[],
        dest="images",
        metavar="n",
        help="a pasted image's number; repeatable",
    )
    parser.set_defaults(
        run=lambda args: attach(args.key, args.files, session=args.session, images=args.images)
    )


def attach(
    key: str, files: list[str], *, session: str | None = None, images: list[int] | None = None
) -> Done | NothingToDo:
    if images and not session:
        raise Precondition("--image needs --session.")
    if not files and not session:
        raise Precondition("Give files to attach, or --session.")
    contents = [(upload_name(file), read(file)) for file in files]
    if session:
        contents += [(image.name, image.content) for image in _pasted(session, images or [])]
    if not contents:
        return NothingToDo("Nothing to attach: no images were pasted in the session.")
    settings = config.load()
    key = keys.issue_key(key, settings.space)
    jira = connection.connect(settings)
    issue = connection.fetch(jira, key)

    there = {(a["filename"], a["size"]) for a in issue["fields"].get("attachment") or []}
    attached: list[str] = []
    skipped: list[str] = []
    for name, content in contents:
        if (name, len(content)) in there:
            if name not in attached + skipped:
                skipped.append(name)
            continue
        jira.attach(key, name, content)
        there.add((name, len(content)))
        attached.append(name)
        outcome.changed(f"Attached {name}.")

    if not attached:
        return NothingToDo(f"{key} already has {', '.join(skipped)}.")
    count = f"{len(attached)} file" + ("s" if len(attached) > 1 else "")
    already = [f"Already there: {', '.join(skipped)}."] if skipped else []
    return Done(f"Attached {count} to {key}.", *already, jira.issue_link(key).url)


def _pasted(session: str, numbers: list[int]) -> list[pasted.Image]:
    """The images pasted in session, or of them, those numbered numbers. Raises Precondition
    when one of numbers wasn't pasted."""
    found = pasted.images(session)
    if not numbers:
        return found
    by_number = {image.number: image for image in found}
    if missing := [n for n in numbers if n not in by_number]:
        raise Precondition(f"No image {missing[0]} was pasted in the session.")
    return [by_number[n] for n in dict.fromkeys(numbers)]


def upload_name(file: str) -> str:
    """The name file is uploaded as: its own, with any quote or line break, which can't go in the
    upload as it is and which Jira would keep escaped, as an underscore."""
    return re.sub(r'["\r\n]', "_", Path(file).name)


def read(file: str) -> bytes:
    """The file's content. Raises Precondition when it isn't a file this can read."""
    path = Path(file)
    if path.is_dir():
        raise Precondition(f"{file} is a folder, not a file.", "Attach the files in it instead.")
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise Precondition(f"No file {file}.") from None
    except OSError as error:
        raise Precondition(f"Can't read {file}.", error.strerror or str(error)) from None
