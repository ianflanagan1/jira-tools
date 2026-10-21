"""Settings from the [tracker] table of the repository's .workspace.toml, or of a product map's
front matter: which site and space issues go to, the type and labels they're filed with, and the
status each stage is kept in."""

import subprocess
from pathlib import Path

import pytest
from cli_kit.outcome import Precondition

from jira_tools import config
from jira_tools.config import Config

ROOT = Path(__file__).parent.parent
TRACKER = '[tracker]\nkind = "jira"\nsite = "me.atlassian.net"\nspace = "WEB"\n'


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "deep").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def write(folder: Path, content: str, name: str = ".workspace.toml") -> Path:
    path = folder / name
    path.write_text(content)
    return path


def problem(path: Path | None = None, cwd: Path | None = None) -> list[str]:
    with pytest.raises(Precondition) as raised:
        config.load(path, cwd=cwd)
    return [raised.value.message, *raised.value.details]


def test_reads_every_setting(tmp_path):
    path = write(
        tmp_path,
        TRACKER + 'issue_type = "Bug"\nlabels = ["later", "x"]\n'
        '[tracker.stages]\nbeing-worked-on = "Doing"\nready-for-agent = "Ready"\n',
    )
    assert config.load(path) == Config(
        "me.atlassian.net",
        "WEB",
        "Bug",
        ("later", "x"),
        {"being-worked-on": "Doing", "ready-for-agent": "Ready"},
    )


def test_without_a_file_it_reads_the_workspace_file_at_the_root_of_the_current_repository(repo):
    write(repo, TRACKER)
    assert config.load(cwd=repo / "src" / "deep").space == "WEB"


def test_outside_a_repository_it_files_nothing(tmp_path):
    assert problem(cwd=tmp_path) == [
        "Not in a git repository.",
        "Run it in the repository the issue is about: its .workspace.toml says where its "
        "issues go.",
    ]


def test_a_repository_without_a_workspace_file_is_named(repo):
    assert problem(cwd=repo) == [
        f"No .workspace.toml in {repo}.",
        "Add one with a [tracker] table: see workspace.example.toml in jira-tools.",
    ]


def test_a_workspace_file_without_a_tracker_table_is_named(tmp_path):
    path = write(tmp_path, '[product-map]\nname = "Shop"\n')
    assert problem(path) == [
        f"No [tracker] table in {path}.",
        "See workspace.example.toml in jira-tools.",
    ]


def test_the_other_tables_of_the_workspace_file_are_ignored(tmp_path):
    path = write(tmp_path, '[product-map]\nname = "Shop"\n\n' + TRACKER)
    assert config.load(path).site == "me.atlassian.net"


def test_a_product_map_s_toml_front_matter_is_read(tmp_path):
    path = write(tmp_path, f'+++\napp = "Shop"\n\n{TRACKER}+++\n\n# Shop\n', "shop.md")
    assert config.load(path) == Config("me.atlassian.net", "WEB")


def test_a_markdown_file_without_front_matter_is_named(tmp_path):
    path = write(tmp_path, "# Shop\n", "shop.md")
    assert problem(path) == [
        f"No front matter in {path}.",
        "A product map starts with its settings between +++ lines; build it again.",
    ]


def test_a_missing_file_is_named(tmp_path):
    path = tmp_path / "nothing.toml"
    assert problem(path) == [f"No {path}."]


def test_settings_left_out_take_their_defaults_and_say_so(tmp_path, capsys):
    path = write(tmp_path, '[tracker]\nsite = "me.atlassian.net"\nspace = "WEB"\n')
    assert config.load(path) == Config(
        "me.atlassian.net", "WEB", "Task", (), {"being-worked-on": "In Progress"}
    )
    assert capsys.readouterr().err == (
        f"Using the defaults for kind, issue_type, labels and stages: {path} doesn't set them.\n"
    )


def test_with_every_setting_it_says_nothing_of_defaults(tmp_path, capsys):
    path = write(tmp_path, TRACKER + 'issue_type = "Task"\nlabels = []\n[tracker.stages]\n')
    config.load(path)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "site", ["me.atlassian.net", "https://me.atlassian.net", "https://me.atlassian.net/"]
)
def test_the_site_can_be_given_with_or_without_its_scheme(site):
    assert Config(site, "WEB").base_url == "https://me.atlassian.net"


@pytest.mark.parametrize("missing", ["site", "space"])
def test_site_and_space_are_needed(tmp_path, missing):
    lines = [line for line in TRACKER.splitlines() if not line.startswith(missing)]
    path = write(tmp_path, "\n".join(lines) + "\n")
    assert problem(path) == [
        f"No {missing} set in [tracker] in {path}.",
        "See workspace.example.toml in jira-tools.",
    ]


def test_a_tracker_other_than_jira_is_refused(tmp_path):
    path = write(tmp_path, TRACKER.replace('"jira"', '"linear"'))
    assert problem(path) == [f"jira-tools files only in Jira, and {path} names linear."]


def test_an_unknown_setting_is_named(tmp_path):
    path = write(tmp_path, TRACKER + 'label = "x"\n')
    assert problem(path) == [
        f"Unknown setting label in [tracker] in {path}.",
        "See workspace.example.toml in jira-tools.",
    ]


def test_a_setting_of_the_wrong_type_is_named(tmp_path):
    path = write(tmp_path, TRACKER + 'labels = "x"\n')
    assert problem(path) == [f"labels must be a list of strings in {path}."]


def test_stages_left_out_of_the_stages_table_are_kept_as_labels(tmp_path):
    path = write(tmp_path, TRACKER + '[tracker.stages]\nready-for-agent = "Ready"\n')
    assert config.load(path).stages == {"ready-for-agent": "Ready"}


@pytest.mark.parametrize(
    "table, message",
    [
        ('triage = "New"', "No stage triage in {path}."),
        ("needs-developer = 1", "The status for needs-developer must be a name in {path}."),
        ('needs-developer = " "', "The status for needs-developer must be a name in {path}."),
        (
            'needs-developer = "To Do"\nneeds-codebase = "to do"',
            "needs-codebase and needs-developer are both kept in To Do in {path}.",
        ),
    ],
)
def test_a_wrong_stage_or_status_is_named(tmp_path, table, message):
    path = write(tmp_path, f"{TRACKER}[tracker.stages]\n{table}\n")
    assert problem(path)[0] == message.format(path=path)


def test_a_file_that_is_not_toml_is_named(tmp_path):
    path = write(tmp_path, "[tracker]\nsite = \n")
    assert problem(path)[0] == f"{path} isn't valid TOML."


def test_the_example_workspace_file_is_valid_and_uses_placeholders():
    assert config.load(ROOT / "workspace.example.toml") == Config(
        "your-site.atlassian.net", "PROJ", "Task", (), {"being-worked-on": "In Progress"}
    )
