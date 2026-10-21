"""Naming an issue on the command line: by its key, such as WEB-12, in any case; by its number
alone, for one in the set space; or by its URL."""

import re

from cli_kit.outcome import Precondition

KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)-(\d+)$")


def issue_key(text: str, space: str) -> str:
    """The key of the issue text names, in capitals. Raises Precondition when it names none."""
    text = text.strip()
    named = text.split("/browse/", 1)[1].split("?", 1)[0] if "/browse/" in text else text
    if named.isdigit():
        return f"{space.upper()}-{int(named)}"
    if key := KEY.match(named):
        return f"{key[1].upper()}-{int(key[2])}"
    raise Precondition(
        f"{text!r} isn't an issue key.",
        "Name it by its key, such as WEB-12, or by its number alone for one in the set space.",
    )
