"""jira tracker: where the current repository's issues go, from its .config/ianf-tracker.toml,
for a skill to read as it loads and stop before any work when nothing could be filed."""

import subprocess
from pathlib import Path

import pytest
from cli_kit.outcome import NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.tracker import tracker

TRACKER = (
    'version = 1\nkind = "jira"\nsite = "me.atlassian.net"\nspace = "WEB"\nissue_type = "Bug"\n'
    'labels = ["deferred"]\n[stages]\nbeing-worked-on = "Doing"\n'
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def settings(repo: Path) -> Path:
    path = repo / ".config" / "ianf-tracker.toml"
    path.parent.mkdir()
    path.write_text(TRACKER)
    return path


def test_shows_each_setting_and_where_it_came_from(repo, capsys):
    path = settings(repo)
    result = tracker(cwd=repo)
    assert isinstance(result, NothingToDo)
    assert result.summary == "Issues go to WEB at https://me.atlassian.net."
    assert capsys.readouterr().out == (
        f"Settings: {path}\n"
        "Site: https://me.atlassian.net\n"
        "Space: WEB\n"
        "Issue type: Bug\n"
        "Labels: deferred\n"
        "Stages: being-worked-on in Doing; needs-codebase, needs-developer, ready-for-agent and "
        "awaiting-review as stage-<name> labels\n"
    )


def test_reads_a_given_file_instead(tmp_path, capsys):
    path = tmp_path / "shop.md"
    table = "[tracker]\n" + TRACKER.replace("[stages]", "[tracker.stages]")
    path.write_text(f"+++\n{table}+++\n# Shop\n")
    assert tracker(path).summary == "Issues go to WEB at https://me.atlassian.net."
    assert capsys.readouterr().out.startswith(f"Settings: {path}\n")


def test_without_settings_it_says_why(repo):
    with pytest.raises(Precondition) as raised:
        tracker(cwd=repo)
    assert raised.value.message == f"No {repo.resolve()}/.config/ianf-tracker.toml."


def test_the_command_line_runs_it(repo, monkeypatch, capsys):
    settings(repo)
    monkeypatch.chdir(repo)
    assert main(["tracker"]) == 0
    assert capsys.readouterr().out.endswith("➖ Issues go to WEB at https://me.atlassian.net.\n")


def test_the_command_line_reads_a_given_file(tmp_path, capsys):
    path = tmp_path / "shop.md"
    path.write_text(f"+++\n[tracker]\n{TRACKER.replace('[stages]', '[tracker.stages]')}+++\n")
    assert main(["tracker", "--tracker", str(path)]) == 0
    assert capsys.readouterr().out.startswith(f"Settings: {path}\n")


def test_the_old_name_and_option_still_run_it_and_say_they_are_deprecated(tmp_path, capsys):
    path = tmp_path / "shop.md"
    path.write_text(f"+++\n[tracker]\n{TRACKER.replace('[stages]', '[tracker.stages]')}+++\n")
    assert main(["workspace", "--workspace", str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith(f"Settings: {path}\n")
    assert "command 'workspace' is deprecated" in captured.err
    assert "option '--workspace' is deprecated" in captured.err


def test_the_old_name_is_left_out_of_the_command_list(capsys):
    assert main(["help"]) == 0
    out = capsys.readouterr().out
    assert "  tracker" in out
    assert "workspace" not in out
