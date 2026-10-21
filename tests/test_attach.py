"""jira attach: files uploaded to an issue, each once, against a fake Jira site."""

import os
from pathlib import Path

import pytest
from cli_kit.outcome import Done, Failure, NothingToDo, Precondition

from jira_tools import api
from jira_tools.__main__ import main
from jira_tools.commands.attach import attach

SITE = "https://me.atlassian.net"


@pytest.fixture
def files(tmp_path: Path):
    def write(name: str, content: bytes = b"trace") -> str:
        path = tmp_path / name
        path.write_bytes(content)
        return str(path)

    return write


def test_uploads_each_file_and_gives_the_issues_url(site, files, capsys):
    site.add("WEB-12")
    result = attach("WEB-12", [files("trace.txt", b"trace"), files("shot.png", b"\x89PNG")])
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Attached 2 files to WEB-12.",
        f"{SITE}/browse/WEB-12",
    )
    assert capsys.readouterr().out == "Attached trace.txt.\nAttached shot.png.\n"
    attached = site.issues["WEB-12"]["attachment"]
    assert [(a["filename"], a["size"]) for a in attached] == [("trace.txt", 5), ("shot.png", 4)]


def test_a_file_the_issue_has_by_name_and_size_is_not_uploaded_again(site, files):
    site.add("WEB-12")
    site.attach("WEB-12", "trace.txt", b"trace")
    site.writes.clear()
    result = attach("WEB-12", [files("trace.txt", b"trace"), files("shot.png")])
    assert isinstance(result, Done)
    assert (result.summary, *result.details) == (
        "Attached 1 file to WEB-12.",
        "Already there: trace.txt.",
        f"{SITE}/browse/WEB-12",
    )
    assert [body["file"][0] for _, _, body in site.writes] == ["shot.png"]


def test_a_file_whose_size_differs_is_uploaded_beside_the_one_with_its_name(site, files):
    site.add("WEB-12")
    site.attach("WEB-12", "trace.txt", b"old")
    assert isinstance(attach("WEB-12", [files("trace.txt", b"newer")]), Done)
    assert len(site.issues["WEB-12"]["attachment"]) == 2


def test_when_the_issue_has_every_file_there_is_nothing_to_do(site, files):
    site.add("WEB-12")
    site.attach("WEB-12", "trace.txt", b"trace")
    site.writes.clear()
    result = attach("WEB-12", [files("trace.txt", b"trace")])
    assert isinstance(result, NothingToDo)
    assert result.summary == "WEB-12 already has trace.txt."
    assert site.writes == []


def test_the_same_file_named_twice_is_uploaded_once(site, files):
    site.add("WEB-12")
    path = files("trace.txt")
    assert isinstance(attach("WEB-12", [path, path]), Done)
    assert len(site.issues["WEB-12"]["attachment"]) == 1


def test_a_missing_file_is_refused_before_anything_is_uploaded(site, files, tmp_path):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        attach("WEB-12", [files("trace.txt"), str(tmp_path / "gone.txt")])
    assert raised.value.message == f"No file {tmp_path / 'gone.txt'}."
    assert site.writes == []
    assert site.tokens_read == 0


def test_a_folder_is_refused_before_anything_is_uploaded(site, files, tmp_path):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        attach("WEB-12", [files("trace.txt"), str(tmp_path)])
    assert raised.value.message == f"{tmp_path} is a folder, not a file."
    assert site.writes == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_an_unreadable_file_is_refused_before_anything_is_uploaded(site, files):
    site.add("WEB-12")
    path = files("secret.txt")
    os.chmod(path, 0)
    with pytest.raises(Precondition) as raised:
        attach("WEB-12", [path])
    assert raised.value.message == f"Can't read {path}."
    assert site.writes == []


def test_an_issue_that_is_not_there_is_named(site, files):
    with pytest.raises(Precondition) as raised:
        attach("WEB-12", [files("trace.txt")])
    assert raised.value.message == "No issue WEB-12."


def test_an_upload_that_fails_after_another_says_what_was_attached(
    site, files, monkeypatch, capsys
):
    site.add("WEB-12")
    uploads = []

    def upload(url: str, auth: str, name: str, content: bytes) -> list[dict]:
        if uploads:
            raise Failure("Jira answered 413.")
        uploads.append(name)
        return site.upload(url, auth, name, content)

    monkeypatch.setattr(api, "_upload", upload)
    first, second = files("trace.txt"), files("huge.bin")
    assert main(["attach", "WEB-12", first, second]) == 1
    assert (
        "🛑 Stopped.\nDone before it stopped:\n  Attached trace.txt.\n" in capsys.readouterr().err
    )
    assert [a["filename"] for a in site.issues["WEB-12"]["attachment"]] == ["trace.txt"]


def test_the_command_line_takes_the_key_and_the_files(site, files, capsys):
    site.add("WEB-12")
    assert main(["attach", "12", files("a.txt"), files("b.txt")]) == 0
    assert "✅ Attached 2 files to WEB-12.\n" in capsys.readouterr().out


def test_quotes_and_line_breaks_in_a_name_are_uploaded_as_underscores_and_found_so_again(
    site, files
):
    # A quote or line break in a file name can't go in the upload's header as it is, and Jira
    # doesn't decode the escapes a browser would use, so it would keep a name nothing matches.
    site.add("WEB-12")
    path = files('say "hi".txt')
    assert attach("WEB-12", [path]).summary == "Attached 1 file to WEB-12."
    assert [a["filename"] for a in site.issues["WEB-12"]["attachment"]] == ["say _hi_.txt"]
    assert isinstance(attach("WEB-12", [path]), NothingToDo)


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A session in which two images were pasted."""
    import base64
    import json

    session_id = "1d7994f2-5552-4b0c-910c-56025078d493"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    path = tmp_path / "claude" / "projects" / "-app" / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True)

    def image(data: bytes) -> dict:
        source = {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(data).decode(),
        }
        return {"type": "image", "source": source}

    entry = {
        "type": "user",
        "imagePasteIds": [1, 2],
        "message": {"content": [image(b"a"), image(b"bb")]},
    }
    path.write_text(json.dumps(entry) + "\n")
    return session_id


def test_the_images_pasted_into_a_session_are_uploaded(site, session):
    site.add("WEB-12")
    result = attach("WEB-12", [], session=session)
    assert isinstance(result, Done)
    assert result.summary == "Attached 2 files to WEB-12."
    assert [(a["filename"], a["size"]) for a in site.issues["WEB-12"]["attachment"]] == [
        ("pasted-image-1.png", 1),
        ("pasted-image-2.png", 2),
    ]


def test_only_the_images_named_are_uploaded_beside_any_files(site, session, files):
    site.add("WEB-12")
    attach("WEB-12", [files("trace.txt")], session=session, images=[2])
    names = [a["filename"] for a in site.issues["WEB-12"]["attachment"]]
    assert names == ["trace.txt", "pasted-image-2.png"]


def test_a_session_with_no_pasted_images_has_nothing_to_attach(site, session, tmp_path):
    site.add("WEB-12")
    path = next((tmp_path / "claude" / "projects").rglob("*.jsonl"))
    path.write_text("")
    result = attach("WEB-12", [], session=session)
    assert isinstance(result, NothingToDo)
    assert result.summary == "Nothing to attach: no images were pasted in the session."


@pytest.mark.parametrize(
    "options, problem",
    [
        ({"images": [3]}, "No image 3 was pasted in the session."),
        ({"session": None, "images": [1]}, "--image needs --session."),
        ({"session": None}, "Give files to attach, or --session."),
    ],
)
def test_wrong_images_are_refused_before_anything_is_uploaded(site, session, options, problem):
    site.add("WEB-12")
    with pytest.raises(Precondition) as raised:
        attach("WEB-12", [], **{"session": session, **options})
    assert raised.value.message == problem
    assert site.writes == []


def test_the_command_line_takes_the_session_and_images(site, session, capsys):
    site.add("WEB-12")
    assert main(["attach", "WEB-12", "--session", session, "--image", "1"]) == 0
    assert "✅ Attached 1 file to WEB-12.\n" in capsys.readouterr().out
    assert [a["filename"] for a in site.issues["WEB-12"]["attachment"]] == ["pasted-image-1.png"]
