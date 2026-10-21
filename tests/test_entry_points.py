"""The jira command that uv installs into .venv/bin."""

import os
import subprocess
import sys
from pathlib import Path

BIN = Path(sys.prefix) / "bin"


def launch(command: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([command, *args], capture_output=True, text=True, cwd=cwd)


def test_the_command_runs_from_any_directory(tmp_path: Path):
    result = launch(BIN / "jira", "--help", cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.startswith("usage: jira")


def test_the_command_works_through_a_symlink(tmp_path: Path):
    os.symlink(BIN / "jira", tmp_path / "jira")
    assert launch(tmp_path / "jira", "--help", cwd=tmp_path).returncode == 0


def test_a_problem_prints_only_its_status_line(tmp_path: Path):
    result = launch(BIN / "jira", "create", " ", cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == "⚠️ The summary is empty.\n"
