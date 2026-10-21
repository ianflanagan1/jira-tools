"""Setting any field by name: Name=value given on the command line turned into Jira's JSON for
the field, by the field's metadata, against a fake Jira site for people and sprints."""

from datetime import datetime

import pytest
from cli_kit.credentials import Credential
from cli_kit.outcome import Precondition

from jira_tools import adf, api, fields
from jira_tools.fields import Changes

SITE = "https://me.atlassian.net"
CUSTOM = "com.atlassian.jira.plugin.system.customfieldtypes:"


def field(name: str, kind: str, custom: str | None = None, **more) -> dict:
    schema = {"type": kind, **({"custom": CUSTOM + custom} if custom else {})}
    if "items" in more:
        schema["items"] = more.pop("items")
    return {"name": name, "required": False, "schema": schema, **more}


def options(*values: str) -> list[dict]:
    return [{"id": str(100 + n), "value": value} for n, value in enumerate(values)]


def named(*names: str) -> list[dict]:
    return [{"id": str(200 + n), "name": name} for n, name in enumerate(names)]


META = {
    "customfield_10010": field("Team name", "string", "textfield"),
    "customfield_10011": field("Acceptance criteria", "string", "textarea"),
    "environment": {"name": "Environment", "schema": {"type": "string", "system": "environment"}},
    "customfield_10016": field("Story points", "number", "float"),
    "customfield_10012": field("Start date", "date", "datepicker"),
    "customfield_10013": field("Deployed at", "datetime", "datetime"),
    "customfield_10014": field(
        "Severity", "option", "select", allowedValues=options("Low", "High")
    ),
    "customfield_10015": field(
        "Browsers",
        "array",
        "multicheckboxes",
        items="option",
        allowedValues=options("Chrome", "Edge"),
    ),
    "customfield_10017": field("Reviewer", "user", "userpicker"),
    "customfield_10018": field("Approvers", "array", "multiuserpicker", items="user"),
    "customfield_10019": field("Tags", "array", "labels", items="string"),
    "fixVersions": field(
        "Fix versions", "array", items="version", allowedValues=named("1.2", "2.0")
    ),
    "components": field("Components", "array", items="component", allowedValues=named("API")),
    "priority": field("Priority", "priority", allowedValues=named("High", "Low")),
    "customfield_10020": {
        "name": "Sprint",
        "schema": {
            "type": "array",
            "items": "json",
            "custom": "com.pyxis.greenhopper.jira:gh-sprint",
        },
    },
    "timetracking": {"name": "Time tracking", "schema": {"type": "timetracking"}},
    "customfield_10021": field("Region", "option-with-child", "cascadingselect"),
}


@pytest.fixture
def jira(site) -> api.Jira:
    return api.Jira(SITE, Credential("me@example.com", "the-token"))


def convert(jira: api.Jira, *given: str, meta: dict = META) -> Changes:
    return fields.convert(meta, list(given), jira, space="WEB", screen="WEB-12's edit screen")


def refused(jira: api.Jira, *given: str, meta: dict = META) -> Precondition:
    with pytest.raises(Precondition) as raised:
        convert(jira, *given, meta=meta)
    return raised.value


def test_a_text_field_is_set_by_its_name_ignoring_case(jira):
    assert convert(jira, "team NAME= Scanner ") == Changes({"customfield_10010": "Scanner"}, ())


def test_a_field_is_named_by_its_id(jira):
    assert convert(jira, "customfield_10010=Scanner").fields == {"customfield_10010": "Scanner"}


def test_a_name_that_more_than_one_field_has_is_refused_with_their_ids(jira):
    meta = {"customfield_1": field("Team", "string"), "customfield_2": field("team", "string")}
    problem = refused(jira, "Team=Scanner", meta=meta)
    assert problem.message == "More than one field is named 'Team': customfield_1, customfield_2."
    assert problem.details == ("Name it by its id instead.",)


def test_a_field_the_screen_does_not_have_is_refused_with_the_close_names(jira):
    problem = refused(jira, "Story point=3")
    assert problem.message == "'Story point' can't be set on WEB-12's edit screen."
    assert problem.details == ("Did you mean Story points?",)


def test_a_field_with_no_close_name_is_refused_without_a_guess(jira):
    assert refused(jira, "Colour=red").details == ()


def test_a_value_without_a_name_is_refused(jira):
    for given in ("Story points", "=3"):
        problem = refused(jira, given)
        assert problem.message == f"{given!r} isn't a field and its value."
        assert problem.details == ("Give it as <name>=<value>, such as 'Story points=3'.",)


@pytest.mark.parametrize("name", ["Acceptance criteria", "Environment"])
def test_a_rich_text_field_takes_markdown(jira, name):
    changes = convert(jira, f"{name}=- follows links\n- no loops")
    [value] = changes.fields.values()
    assert value == adf.from_markdown("- follows links\n- no loops")


def test_a_number_field_takes_a_whole_or_decimal_number(jira):
    assert convert(jira, "Story points=3").fields == {"customfield_10016": 3}
    assert convert(jira, "Story points=0.5").fields == {"customfield_10016": 0.5}


def test_a_number_field_refuses_anything_else(jira):
    assert (
        refused(jira, "Story points=three").message == "Story points takes a number, not 'three'."
    )


def test_a_date_field_takes_a_date_as_yyyy_mm_dd(jira):
    assert convert(jira, "Start date=2026-10-20").fields == {"customfield_10012": "2026-10-20"}


@pytest.mark.parametrize("value", ["20/10/2026", "2026-02-30", "2026-10-20T10:00"])
def test_a_date_field_refuses_anything_else(jira, value):
    problem = refused(jira, f"Start date={value}")
    assert problem.message == (
        f"Start date takes a date as YYYY-MM-DD, such as 2026-10-31, not {value!r}."
    )


def test_a_datetime_field_takes_a_time_with_its_offset_or_in_local_time(jira):
    given = convert(jira, "Deployed at=2026-10-20T14:30+01:00").fields
    assert given == {"customfield_10013": "2026-10-20T14:30:00.000+0100"}
    local = convert(jira, "Deployed at=2026-10-20 14:30").fields["customfield_10013"]
    offset = datetime(2026, 10, 20, 14, 30).astimezone().strftime("%z")
    assert local == f"2026-10-20T14:30:00.000{offset}"


def test_a_datetime_field_refuses_anything_else(jira):
    problem = refused(jira, "Deployed at=tomorrow")
    assert problem.message == (
        "Deployed at takes a date and time, such as 2026-10-20T14:30, not 'tomorrow'."
    )


def test_an_option_is_chosen_from_the_allowed_values_ignoring_case(jira):
    assert convert(jira, "Severity=high").fields == {"customfield_10014": {"id": "101"}}


def test_an_option_that_is_not_allowed_is_refused_with_those_that_are(jira):
    problem = refused(jira, "Severity=Urgent")
    assert problem.message == "Severity can't be 'Urgent'."
    assert problem.details == ("It can be: Low, High.",)


def test_an_option_without_allowed_values_is_sent_by_its_value(jira):
    meta = {"customfield_1": field("Severity", "option", "radiobuttons")}
    assert convert(jira, "Severity=High", meta=meta).fields == {"customfield_1": {"value": "High"}}


def test_a_field_of_several_options_takes_one_for_each_time_it_is_given(jira):
    changes = convert(jira, "Browsers=chrome", "Browsers=Edge")
    assert changes.fields == {"customfield_10015": [{"id": "100"}, {"id": "101"}]}


def test_a_field_of_one_value_given_twice_is_refused(jira):
    problem = refused(jira, "Story points=3", "story points=5")
    assert problem.message == "Story points takes one value, and was given 2."


def test_a_user_is_named_as_assign_names_them(jira, site):
    site.person("a-1", "Alice Smith", "alice@example.com")
    assert convert(jira, "Reviewer=alice").fields == {"customfield_10017": {"accountId": "a-1"}}
    assert convert(jira, "Reviewer=me").fields == {"customfield_10017": {"accountId": "me-1"}}


def test_a_user_field_set_to_none_is_cleared(jira):
    assert convert(jira, "Reviewer=none") == Changes({}, ("customfield_10017",))


def test_a_field_of_several_users_takes_one_for_each_time_it_is_given(jira, site):
    site.person("a-1", "Alice Smith")
    changes = convert(jira, "Approvers=Alice", "Approvers=me")
    assert changes.fields == {"customfield_10018": [{"accountId": "a-1"}, {"accountId": "me-1"}]}


def test_a_field_of_several_strings_takes_one_for_each_time_it_is_given(jira):
    changes = convert(jira, "Tags=scan", "Tags=symlinks")
    assert changes.fields == {"customfield_10019": ["scan", "symlinks"]}


def test_versions_components_and_priority_are_chosen_by_name(jira):
    changes = convert(jira, "Fix versions=2.0", "components=api", "Priority=low")
    assert changes.fields == {
        "fixVersions": [{"id": "201"}],
        "components": [{"id": "200"}],
        "priority": {"id": "201"},
    }


def test_a_version_that_is_not_allowed_is_refused_with_those_that_are(jira):
    problem = refused(jira, "Fix versions=3.0")
    assert problem.message == "Fix versions can't be '3.0'."
    assert problem.details == ("It can be: 1.2, 2.0.",)


def test_a_sprint_is_named_by_its_id(jira, site):
    assert convert(jira, "Sprint=37").fields == {"customfield_10020": 37}
    assert site.boards == []


def test_a_sprint_is_named_by_the_name_of_an_active_or_future_sprint_of_the_space(jira, site):
    site.boards = [{"id": 1, "type": "scrum"}, {"id": 2, "type": "scrum"}]
    sprint = {"id": 38, "name": "Sprint 5", "state": "future"}
    site.sprints = {1: [{"id": 37, "name": "Sprint 4", "state": "active"}, sprint], 2: [sprint]}
    assert convert(jira, "Sprint=sprint 5").fields == {"customfield_10020": 38}


def test_a_sprint_name_the_space_does_not_have_is_refused_with_those_it_does(jira, site):
    site.boards = [{"id": 1, "type": "scrum"}]
    site.sprints = {1: [{"id": 37, "name": "Sprint 4", "state": "active"}]}
    problem = refused(jira, "Sprint=Sprint 9")
    assert problem.message == "WEB has no active or future sprint named 'Sprint 9'."
    assert problem.details == ("It has: Sprint 4 (37).",)


def test_a_sprint_name_more_than_one_sprint_has_is_refused_with_their_ids(jira, site):
    site.boards = [{"id": 1, "type": "scrum"}]
    site.sprints = {1: [{"id": 37, "name": "Next"}, {"id": 40, "name": "next"}]}
    problem = refused(jira, "Sprint=Next")
    assert problem.message == "More than one sprint is named 'Next': 37, 40."
    assert problem.details == ("Name it by its id instead.",)


def test_time_tracking_takes_the_original_estimate(jira):
    changes = convert(jira, "timetracking=1H30m")
    assert changes.fields == {"timetracking": {"originalEstimate": "1h 30m"}}


@pytest.mark.parametrize(
    ("field_id", "name", "kind", "detail"),
    [
        ("summary", "Summary", "string", "Give it with --summary."),
        ("description", "Description", "string", "Give it as Markdown on stdin."),
        ("labels", "Labels", "array", "Give them with --label, and on jira edit --unlabel."),
        ("issuetype", "Issue Type", "issuetype", "Give it with --type."),
        ("project", "Project", "project", "Give it with --space."),
    ],
)
def test_a_field_with_its_own_option_is_refused_naming_the_option(
    jira, field_id, name, kind, detail
):
    meta = {field_id: {"name": name, "schema": {"type": kind, "system": field_id}}}
    for given in (f"{name}=x", f"{field_id}=x"):
        problem = refused(jira, given, meta=meta)
        assert [problem.message, *problem.details] == [f"{name} can't be set with --field.", detail]


def test_an_estimate_for_a_screen_without_time_tracking_is_refused_naming_the_option(jira):
    meta = {key: about for key, about in META.items() if key != "timetracking"}
    with pytest.raises(Precondition) as raised:
        fields.convert(meta, fields.given([], [], "1h"), jira, space="WEB", screen="the screen")
    assert [raised.value.message, *raised.value.details] == [
        "--estimate can't be set on the screen.",
        "It has no time tracking: that may be turned off, or not on the screen.",
    ]


def test_a_field_of_another_type_is_refused_naming_its_type(jira):
    problem = refused(jira, "Region=Europe")
    assert problem.message == "Region is a field of type option-with-child, which jira can't set."


def test_an_empty_value_clears_the_field(jira):
    assert convert(jira, "Story points=", "Browsers= ") == Changes(
        {}, ("customfield_10016", "customfield_10015")
    )


def test_changes_to_send_set_the_fields_and_clear_the_cleared_ones():
    changes = Changes({"customfield_1": 3}, ("customfield_2",))
    assert changes.json() == {"customfield_1": 3, "customfield_2": None}


@pytest.mark.parametrize(
    ("sent", "current"),
    [
        ("Scanner", "Scanner"),
        (3, 3.0),
        (adf.from_markdown("- a"), adf.from_markdown("- a")),
        ({"id": "101"}, {"id": "101", "value": "High", "self": "..."}),
        ([{"id": "100"}, {"id": "101"}], [{"id": "101", "value": "Edge"}, {"id": "100"}]),
        ({"accountId": "a-1"}, {"accountId": "a-1", "displayName": "Alice"}),
        ("2026-10-20T14:30:00.000+0100", "2026-10-20T13:30:00.000+0000"),
        (37, [{"id": 37, "name": "Sprint 4", "state": "active"}]),
        ({"originalEstimate": "3d"}, {"originalEstimate": "3d", "originalEstimateSeconds": 86400}),
    ],
)
def test_a_field_that_already_has_its_value_is_left_out(sent, current):
    changes = Changes({"customfield_1": sent}, ())
    assert changes.differing_from({"customfield_1": current}) == Changes({}, ())


@pytest.mark.parametrize(
    ("sent", "current"),
    [
        ("Scanner", "Scan"),
        (3, None),
        ({"id": "101"}, {"id": "100"}),
        ([{"id": "100"}], [{"id": "100"}, {"id": "101"}]),
        (37, [{"id": 36}]),
    ],
)
def test_a_field_with_another_value_is_kept(sent, current):
    changes = Changes({"customfield_1": sent}, ())
    assert changes.differing_from({"customfield_1": current}) == changes


def test_an_estimate_is_compared_in_seconds_by_the_sites_working_day_and_week():
    units = {"w": 5 * 8 * 3600, "d": 8 * 3600, "h": 3600, "m": 60}
    current = {"timetracking": {"originalEstimate": "1w", "originalEstimateSeconds": 144000}}
    same = Changes({"timetracking": {"originalEstimate": "5d"}}, ())
    other = Changes({"timetracking": {"originalEstimate": "4d"}}, ())
    assert same.differing_from(current, units) == Changes({}, ())
    assert other.differing_from(current, units) == other


def test_a_clear_of_a_field_with_no_value_is_left_out():
    changes = Changes({}, ("customfield_1", "customfield_2", "customfield_3"))
    current = {"customfield_1": None, "customfield_2": [], "customfield_3": 5}
    assert changes.differing_from(current) == Changes({}, ("customfield_3",))


def test_a_field_file_gives_the_field_the_files_contents(tmp_path):
    (tmp_path / "ac.md").write_text("- follows links\n- no loops\n")
    given = fields.from_files([f"Acceptance criteria={tmp_path / 'ac.md'}"])
    assert given == ["Acceptance criteria=- follows links\n- no loops\n"]


def test_a_field_file_that_cannot_be_read_is_refused(tmp_path):
    with pytest.raises(Precondition) as raised:
        fields.from_files([f"Acceptance criteria={tmp_path / 'missing.md'}"])
    assert raised.value.message == f"Can't read {tmp_path / 'missing.md'}."


def test_the_fields_given_are_the_values_then_the_files_then_the_estimate(tmp_path):
    (tmp_path / "ac.md").write_text("- follows links")
    files = [f"Acceptance criteria={tmp_path / 'ac.md'}"]
    assert fields.given(["Story points=3"], files, "1H") == [
        "Story points=3",
        "Acceptance criteria=- follows links",
        "timetracking=1h",
    ]


def test_a_field_given_without_its_value_is_refused_as_it_is_given(tmp_path):
    with pytest.raises(Precondition) as raised:
        fields.given(["Story points"], [], None)
    assert raised.value.message == "'Story points' isn't a field and its value."
