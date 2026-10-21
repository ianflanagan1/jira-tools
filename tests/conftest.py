"""A fake Jira site for the commands' tests. It stands in for api._send and api._upload, keeping
issues, their comments, attachments, worklogs, watchers and statuses, and people, and the
settings and the credential store are replaced too."""

import json
import re
import urllib.parse

import pytest
from cli_kit import credentials
from cli_kit.outcome import Failure

from jira_tools import api, config
from jira_tools.config import Config

SITE = "https://me.atlassian.net"

# Each status, in workflow order, and its category.
STATUSES = {"To Do": "new", "In Progress": "indeterminate", "In Review": "indeterminate"}
STATUSES |= {"Done": "done", "Ready": "new"}

# Jira's default link types.
LINK_TYPES = [
    {"id": "1", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
    {"id": "2", "name": "Cloners", "inward": "is cloned by", "outward": "clones"},
    {"id": "3", "name": "Duplicate", "inward": "is duplicated by", "outward": "duplicates"},
    {"id": "4", "name": "Relates", "inward": "relates to", "outward": "relates to"},
]

# The space's issue types, and what else its issues can have.
ISSUE_TYPES = [
    {"id": "10001", "name": "Task", "subtask": False},
    {"id": "10002", "name": "Bug", "subtask": False},
    {"id": "10003", "name": "Subtask", "subtask": True},
]
PRIORITIES = ["Highest", "High", "Medium", "Low", "Lowest"]
COMPONENTS = ["Scanner", "API"]
VERSIONS = [
    {"name": "1.0", "archived": True},
    {"name": "1.1", "archived": False},
    {"name": "1.2", "archived": False},
]
# Fields whose changes Jira takes as a list of {"add": {"name": ...}} or {"remove": ...}.
NAMED_LISTS = ("components", "fixVersions", "versions")

# The Resolution field on a move's screen, as Jira gives it with the move.
RESOLUTION = {
    "required": True,
    "schema": {"type": "resolution", "system": "resolution"},
    "name": "Resolution",
    "key": "resolution",
    "hasDefaultValue": False,
    "operations": ["set"],
    "allowedValues": [
        {"id": "10000", "name": "Done"},
        {"id": "10001", "name": "Won't Do"},
        {"id": "10002", "name": "Duplicate"},
    ],
}

# The Comment field on a move's screen.
COMMENT = {
    "required": False,
    "schema": {"type": "comments-page", "system": "comment"},
    "name": "Comment",
    "key": "comment",
    "hasDefaultValue": False,
    "operations": ["add"],
}


class FakeSite:
    def __init__(self) -> None:
        self.settings = Config("me.atlassian.net", "WEB")
        self.people: list[dict] = []
        self.me = self.person("me-1", "Ian Flanagan", "me@example.com")
        self.issues: dict[str, dict] = {}
        self.names: dict[str, str] = {}
        self.schemas: dict[str, dict] = {}
        """Each field's schema, as an issue read with expand=schema has it."""
        self.fields: dict[str, dict] = {}
        """The fields every issue's edit screen, and every type's create screen, can set: each
        field's metadata by its id."""
        self.boards: list[dict] = []
        self.sprints: dict[int, list[dict]] = {}
        """Each board's active and future sprints, by the board's id."""
        self.comments: dict[str, list[dict]] = {}
        self.web_links: dict[str, list[dict]] = {}
        """Each issue's web links, as Jira's remote link endpoints show them."""
        self.web_link_ids = 0
        self.comment_ids = 10000
        self.attachment_ids = 10000
        self.worklogs: dict[str, list[dict]] = {}
        self.watchers: dict[str, list[str]] = {}
        """Each issue's watchers' account ids."""
        self.watchers_hidden = False
        """Whether Jira withholds the list of an issue's watchers, as from someone without
        permission to see them."""
        self.web_links_refused = False
        """Whether Jira refuses to show web links, as on a site with issue linking turned off."""
        self.time_tracking = {"workingHoursPerDay": 8.0, "workingDaysPerWeek": 5.0}
        self.moves: dict[str, list[str]] | None = None
        """The statuses each status can move to; None for any other."""
        self.screens: dict[str, dict[str, dict]] = {}
        """The fields on the screen of the move to each status, by field id; a move to any other
        status has no screen."""
        self.resolution = RESOLUTION
        self.comment_field = COMMENT
        self.tokens_read = 0
        self.writes: list[tuple[str, str, dict | str | None]] = []
        """Each request that changes something: its method, its path after /rest/api/3/, and
        its body."""
        self.searches: list[str] = []
        self.link_types = LINK_TYPES
        self.links = 0
        self.issue_types = ISSUE_TYPES
        self.priorities = PRIORITIES
        self.components = COMPONENTS
        self.versions = VERSIONS
        self.filed = 0
        """The number of the last issue filed; the next is the next one not taken."""

    def person(self, account_id: str, name: str, email: str | None = None, **more) -> dict:
        person = {"accountId": account_id, "displayName": name, "accountType": "atlassian"}
        person |= {"active": True, **({"emailAddress": email} if email else {}), **more}
        self.people.append(person)
        return person

    def add(
        self, key: str, summary: str = "Scan skips symlinks", status: str = "To Do", **fields
    ) -> dict:
        self.issues[key] = {
            "summary": summary,
            "status": self.status(status),
            "issuetype": {"name": "Task"},
            "assignee": None,
            **fields,
        }
        self.comments[key] = []
        self.web_links[key] = []
        self.worklogs[key] = []
        self.watchers[key] = []
        return self.issues[key]

    def link(self, link_type: str, inward: str, outward: str) -> None:
        """Links the issues so that inward <link type's outward phrase> outward, as Jira does:
        each issue lists the link with the other one."""
        self.links += 1
        kind = next(t for t in self.link_types if t["name"] == link_type)
        link = {"id": str(20000 + self.links), "type": kind}
        self.issues[inward].setdefault("issuelinks", []).append(
            link | {"outwardIssue": {"key": outward}}
        )
        self.issues[outward].setdefault("issuelinks", []).append(
            link | {"inwardIssue": {"key": inward}}
        )

    def linked(self, key: str) -> list[str]:
        """The issue's links, as Jira shows them on it."""
        return [
            f"{link['type']['outward']} {link['outwardIssue']['key']}"
            if "outwardIssue" in link
            else f"{link['type']['inward']} {link['inwardIssue']['key']}"
            for link in self.issues[key].get("issuelinks", [])
        ]

    def web_link(self, key: str, url: str, title: str, global_id: str | None = None) -> dict:
        """Links the issue to url, as Jira's remote link endpoint does: a link with global_id
        updated, replacing all of it, or else a new one."""
        link = {"object": {"url": url, "title": title}}
        if global_id is not None:
            link["globalId"] = global_id
        links = self.web_links[key]
        same = [
            i for i, found in enumerate(links) if global_id and found.get("globalId") == global_id
        ]
        if same:
            links[same[0]] = {"id": links[same[0]]["id"], **link}
            return links[same[0]]
        self.web_link_ids += 1
        links.append({"id": 10000 + self.web_link_ids, **link})
        return links[-1]

    def comment(self, key: str, body: dict, author: dict | None = None, created: str = "") -> None:
        self.comment_ids += 1
        self.comments[key].append(
            {
                "id": str(self.comment_ids - 1),
                "author": author or self.me,
                "body": body,
                "created": created or "2026-10-13T09:00:00.000+0100",
            }
        )

    def issue_type(self, named: dict) -> dict:
        """The issue type named by its name or id, as Jira shows it on an issue."""
        return next(t for t in self.issue_types if named.items() <= t.items())

    def attach(self, key: str, name: str, content: bytes) -> dict:
        self.attachment_ids += 1
        attachment = {
            "id": str(self.attachment_ids),
            "filename": name,
            "size": len(content),
            "mimeType": "application/octet-stream",
            "content": f"{SITE}/rest/api/3/attachment/content/{self.attachment_ids}",
        }
        self.issues[key].setdefault("attachment", []).append(attachment)
        return attachment

    def upload(self, url: str, auth: str, name: str, content: bytes) -> list[dict]:
        assert url.endswith("/attachments")
        return self.send("POST", url, auth, {"file": (name, content)})

    @staticmethod
    def check_screen(screen: dict[str, dict], body: dict, issue: dict) -> None:
        """Refuses a move as Jira does: one that sets a field not on its screen, or leaves out a
        required one without a default that the issue has no value for."""
        given = {**body.get("fields", {}), **body.get("update", {})}
        for field in given:
            if field not in screen:
                raise Failure(
                    "Jira answered 400.",
                    f"{field}: Field '{field}' cannot be set. It is not on the appropriate"
                    " screen, or unknown.",
                )
        for field, meta in screen.items():
            if meta["required"] and not meta["hasDefaultValue"] and field not in given:
                if field == "comment" or not issue.get(field):
                    raise Failure("Jira answered 400.", f"{field}: {meta['name']} is required.")

    def worklog(
        self,
        key: str,
        time_spent: str,
        started: str,
        comment: dict | None = None,
        author: dict | None = None,
    ) -> None:
        """Logs time on the issue as Jira keeps it: the time spent also in seconds, by the site's
        working day and week."""
        day = self.time_tracking["workingHoursPerDay"] * 3600
        units = {"w": self.time_tracking["workingDaysPerWeek"] * day, "d": day, "h": 3600, "m": 60}
        spent = sum(int(n) * units[u] for n, u in re.findall(r"(\d+)([wdhm])", time_spent))
        worklog = {
            "id": str(10000 + len(self.worklogs[key])),
            "author": author or self.me,
            "started": started,
            "timeSpent": time_spent,
            "timeSpentSeconds": int(spent),
        }
        self.worklogs[key].append(worklog | ({"comment": comment} if comment else {}))

    def estimate(self, duration: str) -> dict:
        """An original estimate as Jira keeps it: in seconds, and written in the largest units of
        the site's working day and week, so that 8h is 1d."""
        day = int(self.time_tracking["workingHoursPerDay"] * 3600)
        units = {"w": int(self.time_tracking["workingDaysPerWeek"] * day), "d": day, "h": 3600}
        units["m"] = 60
        seconds = sum(int(n) * units[u] for n, u in re.findall(r"(\d+)([wdhm])", duration))
        written, rest = [], seconds
        for unit, size in units.items():
            count, rest = divmod(rest, size)
            if count:
                written.append(f"{count}{unit}")
        return {"originalEstimate": " ".join(written) or "0m", "originalEstimateSeconds": seconds}

    def finds(self, jql: str, key: str, fields: dict) -> bool:
        """Whether jql finds the issue with key and fields: jql being clauses joined by AND, of
        those jira searches by, then any ORDER BY, which is ignored."""
        for clause in jql.split(" ORDER BY ")[0].split(" AND "):
            name, operator, value = clause.split(" ", 2)
            if value.startswith('"'):
                value = json.loads(value)
            match name, operator:
                case "project", "=":
                    found = key.split("-")[0] == value
                case "statusCategory", "!=":
                    assert value == "Done"
                    found = fields["status"]["statusCategory"]["key"] != "done"
                case "labels", "=":
                    found = value in (fields.get("labels") or [])
                case "assignee", "=":
                    assert value == "currentUser()"
                    found = (fields.get("assignee") or {}).get("accountId") == self.me["accountId"]
                case _:
                    raise AssertionError(f"Unexpected JQL clause: {clause}")
            if not found:
                return False
        return True

    @staticmethod
    def status(name: str) -> dict:
        return {"name": name, "statusCategory": {"key": STATUSES[name]}}

    def send(self, method: str, url: str, auth: str, body: dict | str | None):
        parts = urllib.parse.urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}" == SITE
        # The Agile API's paths are under agile/, the platform API's under nothing.
        relative = parts.path.removeprefix("/rest/api/3/").replace("/rest/agile/1.0/", "agile/")
        path = [urllib.parse.unquote(p) for p in relative.split("/")]
        query = {name: values[0] for name, values in urllib.parse.parse_qs(parts.query).items()}
        if method != "GET":
            self.writes.append((method, "/".join(path), body))
        match method, path:
            case "GET", ["myself"]:
                return self.me
            case "POST", ["search", "jql"]:
                self.searches.append(body["jql"])
                found = [(k, f) for k, f in self.issues.items() if self.finds(body["jql"], k, f)]
                return {"issues": [{"key": k, "fields": f} for k, f in found]}
            case "GET", ["user", "search"]:
                wanted = query["query"].casefold()
                return [
                    p
                    for p in self.people
                    if wanted in p["displayName"].casefold()
                    or wanted in p.get("emailAddress", "").casefold()
                ]
            case "GET", ["project", space]:
                return {"id": "10000", "key": space}
            case "GET", ["priority", "search"]:
                assert query["projectId"] == "10000"
                start, size = int(query["startAt"]), int(query["maxResults"])
                values = [{"id": str(n), "name": name} for n, name in enumerate(self.priorities)]
                page = values[start : start + size]
                return {"values": page, "isLast": start + size >= len(values)}
            case "GET", ["project", space, "components"]:
                return [{"id": str(n), "name": name} for n, name in enumerate(self.components)]
            case "GET", ["project", space, "versions"]:
                return [{"id": str(n), **version} for n, version in enumerate(self.versions)]
            case "POST", ["issue"]:
                space = body["fields"]["project"]["key"]
                self.filed += 1
                while f"{space}-{self.filed}" in self.issues:
                    self.filed += 1
                key = f"{space}-{self.filed}"
                fields = {k: v for k, v in body["fields"].items() if k != "project"}
                self.add(key, **fields)
                self.issues[key]["issuetype"] = self.issue_type(fields["issuetype"])
                if "timetracking" in fields:
                    estimate = fields["timetracking"]["originalEstimate"]
                    self.issues[key]["timetracking"] = self.estimate(estimate)
                return {"id": str(self.filed), "key": key}
            case "GET", ["configuration"]:
                return {
                    "timeTrackingEnabled": True,
                    "timeTrackingConfiguration": self.time_tracking,
                }
            case "GET", ["issue", "createmeta", _, "issuetypes"]:
                return {"issueTypes": self.issue_types, "total": len(self.issue_types)}
            case "GET", ["issue", "createmeta", _, "issuetypes", _]:
                fields = [{"fieldId": field, **meta} for field, meta in self.fields.items()]
                return {"fields": fields, "total": len(fields)}
            case "GET", ["agile", "board"]:
                return {"values": self.boards, "isLast": True}
            case "GET", ["agile", "board", board, "sprint"]:
                assert query["state"] == "active,future"
                return {"values": self.sprints.get(int(board), []), "isLast": True}
            case "GET", ["issueLinkType"]:
                return {"issueLinkTypes": self.link_types}
            case "POST", ["issueLink"]:
                for side in ("inwardIssue", "outwardIssue"):
                    if body[side]["key"] not in self.issues:
                        raise api.NotFound("Jira answered 404.", "Issue does not exist.")
                self.link(
                    body["type"]["name"], body["inwardIssue"]["key"], body["outwardIssue"]["key"]
                )
                return {}
            case "DELETE", ["issueLink", link_id]:
                for fields in self.issues.values():
                    fields["issuelinks"] = [
                        link for link in fields.get("issuelinks", []) if link["id"] != link_id
                    ]
                return {}
            case _, ["issue", key, *_] if key not in self.issues:
                raise api.NotFound("Jira answered 404.", "Issue does not exist.")
            case "GET", ["issue", key]:
                return {
                    "key": key,
                    "fields": self.issues[key],
                    "names": self.names,
                    "schema": self.schemas,
                }
            case "GET", ["issue", key, "editmeta"]:
                return {"fields": self.fields}
            case "GET", ["issue", key, "remotelink"]:
                if self.web_links_refused:
                    raise api.Forbidden("Jira answered 403.", "Issue linking is disabled.")
                return self.web_links[key]
            case "POST", ["issue", key, "remotelink"]:
                link = self.web_link(key, **body["object"], global_id=body.get("globalId"))
                return {"id": link["id"], "self": url}
            case "PUT", ["issue", key, "remotelink", link_id]:
                links = self.web_links[key]
                found = next(i for i, link in enumerate(links) if str(link["id"]) == link_id)
                links[found] = {"id": links[found]["id"], **body}
                return {}
            case "DELETE", ["issue", key, "remotelink", link_id]:
                self.web_links[key] = [
                    link for link in self.web_links[key] if str(link["id"]) != link_id
                ]
                return {}
            case "GET", ["issue", key, "comment"]:
                start, size = int(query["startAt"]), int(query["maxResults"])
                comments = self.comments[key]
                return {"comments": comments[start : start + size], "total": len(comments)}
            case "POST", ["issue", key, "comment"]:
                self.comment(key, body["body"])
                return self.comments[key][-1]
            case "PUT" | "DELETE", ["issue", key, "comment", comment_id]:
                found = [c for c in self.comments[key] if c["id"] == comment_id]
                if not found:
                    raise api.NotFound("Jira answered 404.", "Comment does not exist.")
                if method == "DELETE":
                    self.comments[key].remove(found[0])
                    return {}
                found[0]["body"] = body["body"]
                return found[0]
            case "POST", ["issue", key, "attachments"]:
                return [self.attach(key, *body["file"])]
            case "GET", ["issue", key, "worklog"]:
                start, size = int(query["startAt"]), int(query["maxResults"])
                worklogs = self.worklogs[key]
                return {"worklogs": worklogs[start : start + size], "total": len(worklogs)}
            case "POST", ["issue", key, "worklog"]:
                self.worklog(key, body["timeSpent"], body["started"], body.get("comment"))
                if query.get("adjustEstimate") == "new":
                    tracking = self.issues[key].setdefault("timetracking", {})
                    tracking["remainingEstimate"] = query["newEstimate"]
                return self.worklogs[key][-1]
            case "GET", ["issue", key, "watchers"]:
                watchers = [p for p in self.people if p["accountId"] in self.watchers[key]]
                answer = {"isWatching": self.me["accountId"] in self.watchers[key]}
                answer["watchCount"] = len(watchers)
                return answer | ({} if self.watchers_hidden else {"watchers": watchers})
            case "POST", ["issue", key, "watchers"]:
                self.watchers[key].append(body)
                return {}
            case "DELETE", ["issue", key, "watchers"]:
                self.watchers[key].remove(query["accountId"])
                return {}
            case "GET", ["issue", key, "transitions"]:
                current = self.issues[key]["status"]["name"]
                targets = (
                    [s for s in STATUSES if s != current]
                    if self.moves is None
                    else self.moves.get(current, [])
                )
                assert query.get("expand") == "transitions.fields"
                return {
                    "transitions": [
                        {
                            "id": str(list(STATUSES).index(t)),
                            "name": f"Go {t}",
                            "to": {"name": t, "statusCategory": {"key": STATUSES[t]}},
                            "hasScreen": t in self.screens,
                            "fields": self.screens.get(t, {}),
                        }
                        for t in targets
                    ]
                }
            case "POST", ["issue", key, "transitions"]:
                target = list(STATUSES)[int(body["transition"]["id"])]
                self.check_screen(self.screens.get(target, {}), body, self.issues[key])
                self.issues[key]["status"] = self.status(target)
                self.issues[key].update(body.get("fields", {}))
                for change in body.get("update", {}).get("comment", []):
                    self.comment(key, change["add"]["body"])
                return {}
            case "PUT", ["issue", key]:
                fields = self.issues[key]
                fields.update(body.get("fields", {}))
                if "issuetype" in body.get("fields", {}):
                    fields["issuetype"] = self.issue_type(body["fields"]["issuetype"])
                if body.get("fields", {}).get("timetracking"):
                    # Set as a field, time tracking is replaced whole.
                    estimate = body["fields"]["timetracking"]["originalEstimate"]
                    fields["timetracking"] = self.estimate(estimate)
                update = body.get("update", {})
                labels = fields.setdefault("labels", [])
                for change in update.get("labels", []):
                    if "add" in change and change["add"] not in labels:
                        labels.append(change["add"])
                    if "remove" in change and change["remove"] in labels:
                        labels.remove(change["remove"])
                for name in NAMED_LISTS:
                    values = fields.setdefault(name, [])
                    for change in update.get(name, []):
                        if "add" in change and change["add"] not in values:
                            values.append(change["add"])
                        if "remove" in change:
                            values.remove(change["remove"])
                for change in update.get("timetracking", []):
                    estimate = change["edit"]["originalEstimate"]
                    fields.setdefault("timetracking", {}).update(self.estimate(estimate))
                return {}
            case "PUT", ["issue", key, "assignee"]:
                account = body["accountId"]
                self.issues[key]["assignee"] = next(
                    (p for p in self.people if p["accountId"] == account), None
                )
                return {}
        raise AssertionError(f"Unexpected request: {method} {url}")


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeSite:
    site = FakeSite()

    def read(token: credentials.Token) -> credentials.Credential:
        site.tokens_read += 1
        return credentials.Credential("me@example.com", "the-token")

    monkeypatch.setattr(config, "load", lambda *args, **kwargs: site.settings)
    monkeypatch.setattr(credentials.Token, "read", read)
    monkeypatch.setattr(api, "_send", site.send)
    monkeypatch.setattr(api, "_upload", site.upload)
    return site
