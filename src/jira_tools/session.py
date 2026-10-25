"""Signing in to the Jira site set in .config/ianf-tracker.toml, and reading the issue a command
names."""

from cli_kit.credentials import Token
from cli_kit.outcome import Precondition

from jira_tools import api
from jira_tools.config import Config

TOKEN = Token(
    service="jira-api-token",
    name="Jira API token",
    username="atlassian-email",
    create="Create an API token at https://id.atlassian.com/manage-profile/security/api-tokens.",
)


def connect(settings: Config) -> api.Jira:
    return api.Jira(settings.base_url, TOKEN.read())


def fetch(jira: api.Jira, key: str) -> dict:
    """The issue with key, with every field. Raises Precondition when there's none to see."""
    issue = jira.issue(key)
    if issue is None:
        raise missing(key)
    return issue


def missing(key: str) -> Precondition:
    return Precondition(f"No issue {key}.", "It doesn't exist, or your account can't see it.")
