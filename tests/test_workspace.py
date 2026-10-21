"""jira workspace: where the current repository's issues go, from its .workspace.toml, for a
skill to read as it loads and stop before any work when nothing could be filed."""

import subprocess
from pathlib import Path

import pytest
from cli_kit.outcome import NothingToDo, Precondition

from jira_tools.__main__ import main
from jira_tools.commands.workspace import workspace

TRACKER = (
    '[tracker]\nkind = "jira"\nsite = "me.atlassian.net"\nspace = "WEB"\nissue_type = "Bug"\n'
    'labels = ["deferred"]\n[tracker.stages]\nbeing-worked-on = "Doing"\n'
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def test_shows_each_setting_and_where_it_came_from(repo, capsys):
    (repo / ".workspace.toml").write_text(TRACKER)
    result = workspace(cwd=repo)
    assert isinstance(result, NothingToDo)
    assert result.summary == "Issues go to WEB at https://me.atlassian.net."
    assert capsys.readouterr().out == (
        f"Settings: {repo / '.workspace.toml'}\n"
        "Site: https://me.atlassian.net\n"
        "Space: WEB\n"
        "Issue type: Bug\n"
        "Labels: deferred\n"
        "Stages: being-worked-on in Doing; needs-codebase, needs-developer, ready-for-agent and "
        "awaiting-review as stage-<name> labels\n"
    )


def test_reads_a_given_file_instead(tmp_path, capsys):
    path = tmp_path / "shop.md"
    path.write_text(f"+++\n{TRACKER}+++\n# Shop\n")
    assert workspace(path).summary == "Issues go to WEB at https://me.atlassian.net."
    assert capsys.readouterr().out.startswith(f"Settings: {path}\n")


def test_without_settings_it_says_why(repo):
    with pytest.raises(Precondition) as raised:
        workspace(cwd=repo)
    assert raised.value.message == f"No .workspace.toml in {repo}."


def test_the_command_line_runs_it(repo, monkeypatch, capsys):
    (repo / ".workspace.toml").write_text(TRACKER)
    monkeypatch.chdir(repo)
    assert main(["workspace"]) == 0
    assert capsys.readouterr().out.endswith("➖ Issues go to WEB at https://me.atlassian.net.\n")
