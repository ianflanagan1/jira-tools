"""The jira-ticket skill: only the user starts it, and it may run what it needs without asking,
also headless, where no one is there to approve a command."""

import re
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SKILL = ROOT / "skills" / "jira-ticket" / "SKILL.md"


def frontmatter() -> dict[str, str]:
    block = SKILL.read_text().split("---\n")[1]
    return dict(line.split(": ", 1) for line in block.splitlines())


def rules() -> list[str]:
    return re.findall(r"Bash\(([^)]*)\)", frontmatter()["allowed-tools"])


def allowed(command: str) -> bool:
    """Whether a Bash rule matches command, as Claude Code matches it: "*" matches anything,
    and a legacy "prefix:*" matches the prefix alone or followed by a space."""
    for rule in rules():
        globs = [rule[:-2], rule[:-2] + " *"] if rule.endswith(":*") else [rule]
        if any(fnmatchcase(command, glob) for glob in globs):
            return True
    return False


def loading_commands() -> list[str]:
    """What the skill runs as it loads, other than cat, which needs no rule, split at "; "."""
    lines = re.findall(r"^!`(.*)`$", SKILL.read_text(), re.MULTILINE)
    commands = [part for line in lines for part in line.replace(" 2>&1", "").split("; ")]
    return [c for c in commands if not c.startswith("cat ")]


def loaded_files() -> list[Path]:
    """The shared references the skill loads."""
    pattern = r'^!`sh "\$\{CLAUDE_PLUGIN_ROOT\}/shared/scripts/reference\.sh" ([\w-]+)`$'
    names = re.findall(pattern, SKILL.read_text(), re.M)
    return [ROOT / "shared" / "references" / f"{name}.md" for name in names]


def test_only_the_user_starts_it():
    assert frontmatter()["disable-model-invocation"] == "true"


def test_it_checks_where_issues_go_as_it_loads():
    assert "jira workspace" in loading_commands()


@pytest.mark.parametrize("command", loading_commands())
def test_every_command_it_runs_as_it_loads_is_allowed(command):
    assert allowed(command)


@pytest.mark.parametrize(
    "command",
    [
        "jira create 'Scan skips symlinks' <<'EOF'\nIt skips them.\nEOF",
        "jira create 'Scan skips symlinks' --label review <<'EOF'\nIt skips them.\nEOF",
        "jira create 'Scan skips' --stage needs-developer --type Bug <<'EOF'\nIt.\nEOF",
        "jira attach WEB-9 --session 1d7994f2-5552-4b0c-910c-56025078d493 --image 2",
    ],
)
def test_filing_an_issue_is_allowed(command):
    assert allowed(command)


def test_it_reads_no_file_with_cat_as_it_loads():
    """Claude Code blocks a load-time cat outside the session's working directories, where a
    plugin's files are whenever the skill is used in another repository, and the skill then
    doesn't load at all."""
    assert not re.findall(r"^!`cat ", SKILL.read_text(), re.M)


def test_every_file_it_loads_is_there_and_reached_without_dot_dot():
    assert loaded_files()
    assert all(path.is_file() for path in loaded_files())
    assert not [line for line in re.findall(r"^!`(.*)`$", SKILL.read_text(), re.M) if ".." in line]


def test_it_may_read_the_code_it_files_about():
    tools = [tool.strip() for tool in frontmatter()["allowed-tools"].split(",")]
    assert {"Read", "Grep", "Glob"} <= set(tools)


def test_nothing_else_is_allowed():
    assert not allowed("jira delete WEB-1")
    assert not allowed("security find-generic-password -s jira-api-token -w")
