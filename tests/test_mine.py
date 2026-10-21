"""jira mine: the open issues assigned to you, against a fake Jira site."""

from cli_kit.outcome import NothingToDo

from jira_tools.__main__ import main
from jira_tools.commands.mine import mine


def test_lists_your_open_issues_in_progress_first_then_to_do_each_in_the_order_jira_gives(
    site, capsys
):
    site.add("WEB-3", "Third", status="To Do", assignee=site.me)
    site.add("WEB-12", "Twelfth", status="In Review", issuetype={"name": "Bug"}, assignee=site.me)
    site.add("WEB-7", "Seventh", status="In Progress", assignee=site.me)
    site.add("WEB-104", "Hundred and fourth", status="In Progress", assignee=site.me)
    result = mine()
    assert isinstance(result, NothingToDo)
    assert result.summary == "4 open issues assigned to you in WEB."
    assert capsys.readouterr().out == (
        "In Review\n"
        "  WEB-12   Bug   Twelfth\n"
        "In Progress\n"
        "  WEB-7    Task  Seventh\n"
        "  WEB-104  Task  Hundred and fourth\n"
        "To Do\n"
        "  WEB-3    Task  Third\n"
    )


def test_searches_the_set_space_unless_another_is_given(site):
    mine()
    mine(space="OPS")
    assert [s.split(" AND ")[0] for s in site.searches] == ['project = "WEB"', 'project = "OPS"']


def test_with_none_it_says_so(site, capsys):
    result = mine()
    assert result.summary == "No open issues assigned to you in WEB."
    assert capsys.readouterr().out == ""


def test_issues_of_others_done_or_in_another_space_are_left_out(site, capsys):
    site.add("WEB-3", "Mine", assignee=site.me)
    site.add("WEB-4", "Someone else's", assignee=site.person("a-1", "Alice"))
    site.add("WEB-5", "Unassigned")
    site.add("WEB-6", "Done", status="Done", assignee=site.me)
    site.add("OPS-7", "Elsewhere", assignee=site.me)
    mine()
    assert capsys.readouterr().out == "To Do\n  WEB-3  Task  Mine\n"


def test_one_issue_is_one_issue(site):
    site.add("WEB-3", assignee=site.me)
    assert mine().summary == "1 open issue assigned to you in WEB."


def test_the_command_line_takes_the_space(site, capsys):
    assert main(["mine", "--space", "OPS"]) == 0
    assert capsys.readouterr().out == "➖ No open issues assigned to you in OPS.\n"
