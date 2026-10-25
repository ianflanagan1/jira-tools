"""Settings from the repository's .config/ianf-tracker.toml, or from the [tracker] table of a
product map's front matter: which site and space issues go to, the type and labels they're filed
with, and the status each stage is kept in."""

import json
import subprocess
import tomllib
from pathlib import Path

import jsonschema
import pytest
from cli_kit.outcome import Precondition

from jira_tools import config
from jira_tools.config import Config
from jira_tools.stages import STAGES

ROOT = Path(__file__).parent.parent
SCHEMA = ROOT / "schema" / "ianf-tracker.v1.json"
TRACKER = 'version = 1\nkind = "jira"\nsite = "me.atlassian.net"\nspace = "WEB"\n'


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "deep").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def write(folder: Path, content: str, name: str = "ianf-tracker.toml") -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
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
        '[stages]\nbeing-worked-on = "Doing"\nready-for-agent = "Ready"\n',
    )
    assert config.load(path) == Config(
        "me.atlassian.net",
        "WEB",
        "Bug",
        ("later", "x"),
        {"being-worked-on": "Doing", "ready-for-agent": "Ready"},
    )


def test_without_a_file_it_reads_the_tracker_file_of_the_current_repository(repo):
    write(repo, TRACKER, ".config/ianf-tracker.toml")
    assert config.load(cwd=repo / "src" / "deep").space == "WEB"


def test_outside_a_repository_it_files_nothing(tmp_path):
    assert problem(cwd=tmp_path) == [
        f"{tmp_path} isn't in a worktree of a git repository.",
        "Run it in the repository the issue is about: its .config/ianf-tracker.toml says where "
        "its issues go.",
    ]


def test_a_repository_without_a_tracker_file_is_named(repo):
    assert problem(cwd=repo) == [
        f"No {repo.resolve()}/.config/ianf-tracker.toml.",
        "Add one: copy ianf-tracker.example.toml from jira-tools there and edit it.",
    ]


def test_a_file_without_a_version_says_to_add_one(tmp_path):
    path = write(tmp_path, TRACKER.replace("version = 1\n", ""))
    assert problem(path)[0] == f"No version in {path}."


def test_a_version_jira_tools_doesnt_read_is_named(tmp_path):
    path = write(tmp_path, TRACKER.replace("version = 1", "version = 9"))
    assert problem(path)[0] == f"{path} is version 9, which this tool doesn't read."


def test_a_product_map_s_toml_front_matter_is_read(tmp_path):
    table = "[tracker]\n" + TRACKER
    path = write(tmp_path, f'+++\napp = "Shop"\n\n{table}+++\n\n# Shop\n', "shop.md")
    assert config.load(path) == Config("me.atlassian.net", "WEB")


def test_a_product_map_without_a_tracker_table_is_named(tmp_path):
    path = write(tmp_path, '+++\napp = "Shop"\n+++\n# Shop\n', "shop.md")
    assert problem(path) == [
        f"No [tracker] table in {path}.",
        "See ianf-tracker.example.toml in jira-tools.",
    ]


def test_a_product_map_built_before_versions_says_to_build_it_again(tmp_path):
    table = "[tracker]\n" + TRACKER.replace("version = 1\n", "")
    path = write(tmp_path, f"+++\n{table}+++\n# Shop\n", "shop.md")
    assert problem(path) == [
        f"No version in [tracker] in {path}.",
        "A product map copies its app's tracker settings: build and publish it again.",
    ]


def test_a_product_map_s_tracker_table_names_where_it_is_wrong(tmp_path):
    table = "[tracker]\n" + TRACKER.replace('site = "me.atlassian.net"\n', "")
    path = write(tmp_path, f"+++\n{table}+++\n# Shop\n", "shop.md")
    assert problem(path)[0] == f"No site set in [tracker] in {path}."


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
    path = write(tmp_path, 'version = 1\nsite = "me.atlassian.net"\nspace = "WEB"\n')
    assert config.load(path) == Config(
        "me.atlassian.net", "WEB", "Task", (), {"being-worked-on": "In Progress"}
    )
    assert capsys.readouterr().err == (
        f"Using the defaults for kind, issue_type, labels and stages: {path} doesn't set them.\n"
    )


def test_with_every_setting_it_says_nothing_of_defaults(tmp_path, capsys):
    path = write(tmp_path, TRACKER + 'issue_type = "Task"\nlabels = []\n[stages]\n')
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
        f"No {missing} set in {path}.",
        "See ianf-tracker.example.toml in jira-tools.",
    ]


def test_a_tracker_other_than_jira_is_refused(tmp_path):
    path = write(tmp_path, TRACKER.replace('"jira"', '"linear"'))
    assert problem(path) == [f"jira-tools files only in Jira, and {path} names linear."]


def test_an_unknown_setting_is_named(tmp_path):
    path = write(tmp_path, TRACKER + 'label = "x"\n')
    assert problem(path) == [
        f"Unknown setting label in {path}.",
        "See ianf-tracker.example.toml in jira-tools.",
    ]


def test_a_setting_of_the_wrong_type_is_named(tmp_path):
    path = write(tmp_path, TRACKER + 'labels = "x"\n')
    assert problem(path) == [f"labels must be a list of strings in {path}."]


def test_stages_left_out_of_the_stages_table_are_kept_as_labels(tmp_path):
    path = write(tmp_path, TRACKER + '[stages]\nready-for-agent = "Ready"\n')
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
    path = write(tmp_path, f"{TRACKER}[stages]\n{table}\n")
    assert problem(path)[0] == message.format(path=path)


def test_a_file_that_is_not_toml_is_named(tmp_path):
    path = write(tmp_path, "version = 1\nsite = \n")
    assert problem(path)[0] == f"{path} isn't valid TOML."


def test_the_example_file_is_valid_and_uses_placeholders():
    assert config.load(ROOT / "ianf-tracker.example.toml") == Config(
        "your-site.atlassian.net", "PROJ", "Task", (), {"being-worked-on": "In Progress"}
    )


def test_the_schema_accepts_the_example_file():
    example = tomllib.loads((ROOT / "ianf-tracker.example.toml").read_text())
    jsonschema.validate(example, json.loads(SCHEMA.read_text()))


def test_the_schema_has_the_settings_and_stages_jira_tools_reads():
    schema = json.loads(SCHEMA.read_text())
    assert set(schema["properties"]) == {"version", *config.SETTINGS}
    assert tuple(schema["properties"]["stages"]["properties"]) == STAGES


def test_the_example_names_the_schema_of_its_version():
    first = (ROOT / "ianf-tracker.example.toml").read_text().splitlines()[0]
    assert first == f"#:schema {json.loads(SCHEMA.read_text())['$id']}"
