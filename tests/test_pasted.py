"""The images pasted into a Claude Code session, read from its transcript."""

import base64
import json
from pathlib import Path

import pytest
from cli_kit.outcome import Precondition

from jira_tools import pasted

SESSION = "1d7994f2-5552-4b0c-910c-56025078d493"


def image(data: bytes, media_type: str = "image/png") -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(data).decode(),
        },
    }


@pytest.fixture
def transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Writes the session's transcript, one entry per line, where Claude Code keeps it."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))

    def write(*entries: dict) -> Path:
        path = tmp_path / "claude" / "projects" / "-Users-me-app" / f"{SESSION}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(e) + "\n" for e in entries) + "not json\n")
        return path

    return write


def user(*content: dict, ids: list[int] | None = None, **more) -> dict:
    entry = {"type": "user", "message": {"role": "user", "content": list(content)}, **more}
    if ids is not None:
        entry["imagePasteIds"] = ids
    return entry


def test_each_pasted_image_is_numbered_in_the_order_it_was_pasted_with_its_type(transcript):
    # Claude Code's own paste numbers needn't start at 1; Claude can only count.
    transcript(
        user(image(b"one"), {"type": "text", "text": "See [Image #2]"}, ids=[2]),
        user({"type": "text", "text": "and"}),
        user(image(b"two", "image/jpeg"), image(b"three"), ids=[5, 6]),
    )
    images = pasted.images(SESSION)
    assert [(i.number, i.name, i.content) for i in images] == [
        (1, "pasted-image-1.png", b"one"),
        (2, "pasted-image-2.jpg", b"two"),
        (3, "pasted-image-3.png", b"three"),
    ]


def test_images_read_from_files_or_seen_by_subagents_are_not_pasted_ones(transcript):
    tool_result = {"type": "tool_result", "tool_use_id": "t", "content": [image(b"read")]}
    transcript(
        user(tool_result),
        user(image(b"side"), ids=[1], isSidechain=True),
        {"type": "assistant", "message": {"role": "assistant", "content": [image(b"x")]}},
    )
    assert pasted.images(SESSION) == []


def test_a_session_with_no_transcript_is_named(transcript):
    with pytest.raises(Precondition) as raised:
        pasted.images("0d7994f2-5552-4b0c-910c-56025078d493")
    assert raised.value.message == "No Claude Code session 0d7994f2-5552-4b0c-910c-56025078d493."


@pytest.mark.parametrize("session", ["../x", "a/b", "", "*"])
def test_a_session_id_that_is_not_one_is_refused(transcript, session):
    with pytest.raises(Precondition) as raised:
        pasted.images(session)
    assert raised.value.message == f"{session!r} isn't a session id."
