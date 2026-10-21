"""Checks on an issue's summary and description before it's filed. Each returns what it found,
for the caller to refuse with, or None when there's nothing wrong."""

import re

MAX_SUMMARY = 80

FENCE = re.compile(r"^\s*`{3,}")

# Markdown that adf.from_markdown keeps as plain text, so Jira would show its symbols as written.
UNSHOWN = [
    ("a table", re.compile(r"^\s*\|.*\|\s*$")),
    ("a quote", re.compile(r"^\s*>")),
    ("an image", re.compile(r"!\[[^\]]*\]\([^)]*\)")),
    ("a nested list", re.compile(r"^\s{2,}(?:[-*+]|\d+[.)])\s")),
    ("a horizontal rule", re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")),
    ("HTML", re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?/?>")),
]

# Secrets by their shape, so their values are never filed where anyone with the issue can read
# them. An assignment counts only with a value that isn't a placeholder, such as <x> or $X.
SECRETS = [
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("an AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}|\bgithub_pat_\w{20,}")),
    ("a Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("an Atlassian API token", re.compile(r"\bATATT[A-Za-z0-9_=-]{20,}")),
    ("an API key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("a JSON web token", re.compile(r"\beyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}")),
    (
        "a password or token",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key)\b\s*[:=]\s*"
            r"""["']?(?![<$%{])[^\s"'<>]{6,}"""
        ),
    ),
]


def summary(text: str) -> str | None:
    """What's wrong with a summary, or None."""
    if len(text) > MAX_SUMMARY:
        return f"The summary is {len(text)} characters; it can have at most {MAX_SUMMARY}."
    return None


def markdown(text: str) -> str | None:
    """The first Markdown outside code that Jira would show as plain text, with its line, such
    as "a table, on line 3", or None."""
    for number, line in _outside_code(text):
        without_code = re.sub(r"`[^`]*`", "", line)
        for name, pattern in UNSHOWN:
            if pattern.search(without_code):
                return f"{name}, on line {number}"
    return None


def secret(text: str) -> str | None:
    """The first secret in text, by its kind and line but not its value, such as "a GitHub
    token, on line 2", or None."""
    for number, line in enumerate(text.splitlines(), 1):
        for name, pattern in SECRETS:
            if pattern.search(line):
                return f"{name}, on line {number}"
    return None


def _outside_code(text: str) -> list[tuple[int, str]]:
    """Each line of text outside fenced code blocks, with its number from 1."""
    lines = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            lines.append((number, line))
    return lines
