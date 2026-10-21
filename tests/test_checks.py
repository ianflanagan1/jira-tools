"""What an issue's summary and description are checked for before anything is filed: a summary
short enough to read in a list, Markdown that Jira shows as written, and no secrets."""

import pytest

from jira_tools import checks


def test_a_summary_of_up_to_80_characters_is_fine():
    assert checks.summary("x" * 80) is None


def test_a_longer_summary_is_named_with_its_length():
    assert checks.summary("x" * 81) == "The summary is 81 characters; it can have at most 80."


def test_the_markdown_the_description_may_use_is_fine():
    markdown = (
        "## What happened\n\nIt **skips** them: see [the log](https://x.test) and `scan`.\n\n"
        "1. Run it.\n2. Look.\n\n- One\n  continued\n- Two\n\n```sh\n| not | a table |\n> nor"
        " a quote\n```\n"
    )
    assert checks.markdown(markdown) is None


@pytest.mark.parametrize(
    "markdown, found",
    [
        ("Intro.\n\n| a | b |\n|---|---|\n", "a table, on line 3"),
        ("> quoted\n", "a quote, on line 1"),
        ("See ![shot](a.png).\n", "an image, on line 1"),
        ("Line<br>break\n", "HTML, on line 1"),
        ("<details>\nx\n</details>\n", "HTML, on line 1"),
        ("- One\n  - Nested\n", "a nested list, on line 2"),
        ("Above\n\n---\n\nBelow\n", "a horizontal rule, on line 3"),
    ],
)
def test_markdown_jira_would_show_as_plain_text_is_named_with_its_line(markdown, found):
    assert checks.markdown(markdown) == found


def test_angle_brackets_that_are_not_html_are_fine():
    assert checks.markdown("Run `jira view <key>` when a < b and b > a.\n") is None


@pytest.mark.parametrize(
    "text, found",
    [
        ("-----BEGIN RSA PRIVATE KEY-----\nabc\n", "a private key, on line 1"),
        ("key AKIAIOSFODNN7EXAMPLE here\n", "an AWS access key, on line 1"),
        ("x\nghp_" + "a" * 36 + "\n", "a GitHub token, on line 2"),
        ("github_pat_" + "a" * 30 + "\n", "a GitHub token, on line 1"),
        ("xoxb-1234567890-abcdefghij\n", "a Slack token, on line 1"),
        ("ATATT3xFfGF0" + "a" * 20 + "\n", "an Atlassian API token, on line 1"),
        ("sk-ant-api03-" + "a" * 30 + "\n", "an API key, on line 1"),
        ("eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4\n", "a JSON web token, on line 1"),
        ("password = hunter2hunter\n", "a password or token, on line 1"),
        ("API_KEY: 'abcdef123456'\n", "a password or token, on line 1"),
    ],
)
def test_a_secret_is_named_with_its_line_but_not_its_value(text, found):
    assert checks.secret(text) == found


@pytest.mark.parametrize(
    "text",
    [
        "Set password = <the password> in config.\n",
        "token = $JIRA_TOKEN\n",
        "api_key: ${API_KEY}\n",
        "The token was rejected.\n",
        "Never put a password in a ticket.\n",
    ],
)
def test_naming_a_secret_without_its_value_is_fine(text):
    assert checks.secret(text) is None
