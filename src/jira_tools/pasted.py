"""The images pasted into a Claude Code session, as files to upload.

Claude Code keeps a pasted image only in the session's transcript, as base64 in the user's
message, not as a file: <config>/projects/<project>/<session id>.jsonl, where <config> is
CLAUDE_CONFIG_DIR or ~/.claude. They're numbered in the order they were pasted, from 1, which
Claude can count as it reads the conversation; the prompt's own labels, [Image #2], needn't
match, since Claude Code doesn't always number from 1. Images Claude read from files, and those
in subagents' sidechains, aren't pasted ones.
"""

import base64
import binascii
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from cli_kit.outcome import Precondition

EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}


@dataclass(frozen=True)
class Image:
    number: int
    media_type: str
    content: bytes

    @property
    def name(self) -> str:
        return f"pasted-image-{self.number}.{EXTENSIONS.get(self.media_type, 'png')}"


def images(session: str) -> list[Image]:
    """The images pasted in session, in order. Raises Precondition when there's no such
    session."""
    found: list[Image] = []
    for line in transcript(session).read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "user" or entry.get("isSidechain"):
            continue
        content = (entry.get("message") or {}).get("content")
        blocks = [c for c in content if _pasted(c)] if isinstance(content, list) else []
        for block in blocks:
            source = block["source"]
            try:
                data = base64.b64decode(source["data"], validate=True)
            except (binascii.Error, ValueError):
                continue
            found.append(Image(len(found) + 1, source.get("media_type", "image/png"), data))
    return found


def transcript(session: str) -> Path:
    """The session's transcript. Raises Precondition when session isn't an id, or there's none."""
    if not re.fullmatch(r"[0-9A-Za-z-]+", session):
        raise Precondition(f"{session!r} isn't a session id.")
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    if found := sorted((config / "projects").glob(f"*/{session}.jsonl")):
        return found[0]
    raise Precondition(f"No Claude Code session {session}.")


def _pasted(block: object) -> bool:
    return (
        isinstance(block, dict)
        and block.get("type") == "image"
        and isinstance(block.get("source"), dict)
        and block["source"].get("type") == "base64"
        and isinstance(block["source"].get("data"), str)
    )
