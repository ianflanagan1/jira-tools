"""Jira Cloud's REST API (v3): finding, reading, creating, editing, commenting on, attaching
files to, moving, assigning, linking and watching issues, linking them to web pages, logging time
on them, and reading which fields they can be given and a space's issue types, priorities,
components and versions; and its Agile API (1.0), for a space's sprints.

It signs in with your Atlassian email and an API token, by basic auth. Jira's API still calls a
space a project: this module says space, and project only where Jira's JSON and JQL need it.
"""

import base64
import json
import mimetypes
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from cli_kit.credentials import Credential
from cli_kit.outcome import Failure, Precondition


@dataclass(frozen=True)
class Issue:
    key: str
    url: str


@dataclass(frozen=True)
class Transition:
    """A move an issue's workflow allows it from its status, to status. fields are the fields on
    its screen, as Jira gives them: by field id, each with its name, whether it's required and
    has a default value, its schema and any allowed values. A move without a screen has none."""

    id: str
    status: str
    fields: dict[str, dict] = field(default_factory=dict, compare=False)
    category: str = field(default="", compare=False)
    """The status's category: new, indeterminate or done."""


@dataclass(frozen=True)
class IssueType:
    """A type a space files issues as. A subtask type files an issue under a parent issue."""

    id: str
    name: str
    subtask: bool


@dataclass(frozen=True)
class LinkType:
    """A kind of link between two issues, such as Blocks, and how it reads from each: from the
    issue that blocks, outward, "blocks"; from the other, inward, "is blocked by". A link type such
    as Relates reads the same both ways."""

    id: str
    name: str
    inward: str
    outward: str


@dataclass(frozen=True)
class User:
    account_id: str
    name: str
    email: str | None = None


class NotFound(Failure):
    """Jira answered 404: there's no such issue, or the token can't see it."""


class Forbidden(Failure):
    """Jira answered 403: the token's user isn't allowed to do it, or the site has it turned off,
    such as issue linking or attachments."""


@dataclass(frozen=True)
class Watchers:
    """An issue's watchers' account ids, or None when Jira withholds them from the token's user;
    and whether that user watches it, which Jira always says."""

    ids: tuple[str, ...] | None
    you: bool


class Jira:
    def __init__(self, base_url: str, credential: Credential) -> None:
        self.base_url = base_url
        pair = f"{credential.username}:{credential.token}".encode()
        self._auth = f"Basic {base64.b64encode(pair).decode()}"

    def find_open(self, space: str, labels: tuple[str, ...], summary: str) -> Issue | None:
        """The open issue in space with every one of labels whose summary is summary,
        ignoring case and surrounding space, or None."""
        clauses = [f"project = {_quote(space)}", "statusCategory != Done"]
        clauses += [f"labels = {_quote(label)}" for label in labels]
        wanted = _comparable(summary)
        for issue in self._search(" AND ".join(clauses), ["summary"]):
            if _comparable(issue["fields"]["summary"]) == wanted:
                return self.issue_link(issue["key"])
        return None

    def open_assigned_to_me(self, space: str) -> list[dict]:
        """The open issues in space assigned to the token's user, most recently updated first,
        with their summary, status and type."""
        jql = (
            f"project = {_quote(space)} AND assignee = currentUser() AND statusCategory != Done"
            " ORDER BY updated DESC"
        )
        return self._search(jql, ["summary", "status", "issuetype"])

    def create(
        self,
        space: str,
        issue_type: str,
        labels: tuple[str, ...],
        summary: str,
        description: dict | None,
        more: dict | None = None,
    ) -> Issue:
        """Creates the issue. description is an ADF document, or None for none; more is any
        other fields, as Jira's JSON names them."""
        fields: dict = {
            "project": {"key": space},
            "issuetype": {"name": issue_type},
            "summary": summary,
            "labels": list(labels),
            **(more or {}),
        }
        if description is not None:
            fields["description"] = description
        created = _send("POST", self._api("issue"), self._auth, {"fields": fields})
        return self.issue_link(created["key"])

    def edit(
        self,
        key: str,
        summary: str | None,
        description: dict | None,
        add: tuple[str, ...],
        remove: tuple[str, ...],
        more: dict | None = None,
        update: dict | None = None,
    ) -> None:
        """Replaces the issue's summary and its description, an ADF document, each unless None,
        and adds and removes labels. more is any other fields to set, and update any other
        fields' changes, as Jira's JSON names them."""
        body: dict = {"fields": {**(more or {})}, "update": {**(update or {})}}
        if summary is not None:
            body["fields"]["summary"] = summary
        if description is not None:
            body["fields"]["description"] = description
        changes = [{"add": label} for label in add] + [{"remove": label} for label in remove]
        if changes:
            body["update"]["labels"] = changes
        _send("PUT", self._api("issue", key), self._auth, body)

    def edit_meta(self, key: str) -> dict:
        """The fields the issue's edit screen can set, by id, each with its name, its schema
        and any values it allows."""
        return _send("GET", self._api("issue", key, "editmeta"), self._auth, None).get("fields", {})

    def issue_types(self, space: str) -> list[IssueType]:
        """The types an issue can be created as in space."""
        url = self._api("issue", "createmeta", space, "issuetypes")
        return [
            IssueType(t["id"], t["name"], bool(t.get("subtask")))
            for t in self._pages(url, "issueTypes")
        ]

    def create_meta(self, space: str, type_id: str) -> dict:
        """The fields the create screen for the type with type_id in space can set, by id, as
        edit_meta gives them."""
        url = self._api("issue", "createmeta", space, "issuetypes", type_id)
        return {field["fieldId"]: field for field in self._pages(url, "fields")}

    def sprints(self, space: str) -> list[dict]:
        """The active and future sprints of the space's scrum boards, each with its id, name and
        state. A sprint on more than one board is there once for each."""
        boards = self._pages(self._agile("board") + "?projectKeyOrId=" + _query(space), "values")
        sprints: list[dict] = []
        for board in boards:
            if board.get("type") == "scrum":
                url = self._agile("board", str(board["id"]), "sprint") + "?state=active%2Cfuture"
                sprints += self._pages(url, "values")
        return sprints

    def myself(self) -> User:
        """The token's user."""
        return _user(_send("GET", self._api("myself"), self._auth, None))

    def issue(self, key: str) -> dict | None:
        """The issue with every field, under "names" each field's name and under "schema" its
        type, or None when there's no such issue the token can see."""
        url = self._api("issue", key) + "?fields=*all&expand=names,schema"
        try:
            return _send("GET", url, self._auth, None)
        except NotFound:
            return None

    def comments(self, key: str) -> list[dict] | None:
        """The issue's comments, oldest first, or None when there's no such issue the token can
        see."""
        comments: list[dict] = []
        while True:
            query = f"?orderBy=created&maxResults=100&startAt={len(comments)}"
            try:
                page = _send("GET", self._api("issue", key, "comment") + query, self._auth, None)
            except NotFound:
                return None
            comments += page.get("comments", [])
            if not page.get("comments") or len(comments) >= page.get("total", 0):
                return comments

    def add_comment(self, key: str, body: dict) -> str:
        """Adds the ADF document body to the issue as a comment. Returns the comment's URL."""
        added = _send("POST", self._api("issue", key, "comment"), self._auth, {"body": body})
        return f"{self.issue_link(key).url}?focusedCommentId={added['id']}"

    def edit_comment(self, key: str, comment_id: str, body: dict) -> str:
        """Replaces the body of the issue's comment with comment_id with the ADF document body.
        Returns the comment's URL."""
        path = self._api("issue", key, "comment", comment_id)
        _send("PUT", path, self._auth, {"body": body})
        return f"{self.issue_link(key).url}?focusedCommentId={comment_id}"

    def worklogs(self, key: str) -> list[dict] | None:
        """The time logged on the issue, oldest first, or None when there's no such issue the
        token can see."""
        worklogs: list[dict] = []
        while True:
            query = f"?maxResults=1000&startAt={len(worklogs)}"
            try:
                page = _send("GET", self._api("issue", key, "worklog") + query, self._auth, None)
            except NotFound:
                return None
            worklogs += page.get("worklogs", [])
            if not page.get("worklogs") or len(worklogs) >= page.get("total", 0):
                return worklogs

    def add_worklog(self, key: str, worklog: dict, remaining: str | None) -> str:
        """Logs worklog on the issue, and sets its remaining estimate to remaining, a duration
        such as 2d 4h, or for None, leaves Jira to reduce it by the time spent. Returns the
        worklog's URL."""
        url = self._api("issue", key, "worklog")
        if remaining is not None:
            url += "?" + urllib.parse.urlencode({"adjustEstimate": "new", "newEstimate": remaining})
        added = _send("POST", url, self._auth, worklog)
        return f"{self.issue_link(key).url}?focusedWorklogId={added['id']}"

    def time_units(self) -> dict[str, int]:
        """The seconds in each unit of a duration, w, d, h and m, by the site's working day and
        week: 8 hours and 5 days unless it sets others."""
        answer = _send("GET", self._api("configuration"), self._auth, None)
        tracking = answer.get("timeTrackingConfiguration") or {}
        day = int(tracking.get("workingHoursPerDay", 8) * 3600)
        return {"w": int(tracking.get("workingDaysPerWeek", 5) * day), "d": day, "h": 3600, "m": 60}

    def delete_comment(self, key: str, comment_id: str) -> None:
        _send("DELETE", self._api("issue", key, "comment", comment_id), self._auth, None)

    def attach(self, key: str, name: str, content: bytes) -> dict:
        """Attaches content to the issue as a file named name. Returns the attachment, with its
        filename and size."""
        [attachment] = _upload(self._api("issue", key, "attachments"), self._auth, name, content)
        return attachment

    def transitions(self, key: str) -> list[Transition]:
        """The moves the issue's workflow allows it from its status, with their screens' fields."""
        url = self._api("issue", key, "transitions") + "?expand=transitions.fields"
        answer = _send("GET", url, self._auth, None)
        return [
            Transition(
                t["id"],
                t["to"]["name"],
                t.get("fields") or {},
                t["to"].get("statusCategory", {}).get("key", ""),
            )
            for t in answer.get("transitions", [])
        ]

    def transition(
        self,
        key: str,
        transition: Transition,
        fields: dict | None = None,
        update: dict | None = None,
    ) -> None:
        """Moves the issue by transition, setting fields and making update's changes as it moves,
        as Jira's JSON names them. Jira takes only the fields on the transition's screen."""
        body: dict = {"transition": {"id": transition.id}}
        if fields:
            body["fields"] = fields
        if update:
            body["update"] = update
        _send("POST", self._api("issue", key, "transitions"), self._auth, body)

    def assign(self, key: str, account_id: str | None) -> None:
        """Assigns the issue to the user with account_id, or unassigns it for None."""
        _send("PUT", self._api("issue", key, "assignee"), self._auth, {"accountId": account_id})

    def watchers(self, key: str) -> Watchers | None:
        """The issue's watchers, or None when there's no such issue the token can see."""
        try:
            answer = _send("GET", self._api("issue", key, "watchers"), self._auth, None)
        except NotFound:
            return None
        listed = answer.get("watchers")
        ids = None if listed is None else tuple(watcher["accountId"] for watcher in listed)
        return Watchers(ids, bool(answer.get("isWatching")))

    def watch(self, key: str, account_id: str) -> None:
        """Adds the user with account_id to the issue's watchers. Jira takes the id alone, as a
        JSON string."""
        _send("POST", self._api("issue", key, "watchers"), self._auth, account_id)

    def unwatch(self, key: str, account_id: str) -> None:
        query = "?" + urllib.parse.urlencode({"accountId": account_id})
        _send("DELETE", self._api("issue", key, "watchers") + query, self._auth, None)

    def with_label(self, space: str, label: str) -> list[dict]:
        """Every issue in space with label, newest first, with its summary, type, status,
        creation time and links to other issues."""
        jql = f"project = {_quote(space)} AND labels = {_quote(label)} ORDER BY created DESC"
        return self._search(jql, ["summary", "issuetype", "status", "created", "issuelinks"])

    def space_name(self, space: str) -> str | None:
        """The name of the space with key space, or None when the token can't see one."""
        try:
            return _send("GET", self._api("project", space), self._auth, None)["name"]
        except NotFound:
            return None

    def field_names(self) -> list[str]:
        """The names of every field the site has, its own and custom ones."""
        return [field["name"] for field in _send("GET", self._api("field"), self._auth, None)]

    def link_types(self) -> list[LinkType]:
        """The kinds of link the site has."""
        answer = _send("GET", self._api("issueLinkType"), self._auth, None)
        return [
            LinkType(t["id"], t["name"], t["inward"], t["outward"])
            for t in answer.get("issueLinkTypes", [])
        ]

    def link(self, link_type: str, inward: str, outward: str) -> None:
        """Links the issue with key inward to the one with key outward, so that inward reads
        <link_type's outward> outward: for Blocks, inward blocks outward. Jira names the two the
        other way round from how they read, and this keeps its names."""
        body = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward},
            "outwardIssue": {"key": outward},
        }
        _send("POST", self._api("issueLink"), self._auth, body)

    def unlink(self, link_id: str) -> None:
        """Removes the link with link_id, from both its issues."""
        _send("DELETE", self._api("issueLink", link_id), self._auth, None)

    def priorities(self, space: str) -> list[str]:
        """The names of the priorities space's issues can have, highest first. Jira finds them
        by the space's numeric id, not its key."""
        space_id = _send("GET", self._api("project", space), self._auth, None)["id"]
        url = self._api("priority", "search") + "?projectId=" + _query(space_id)
        return [priority["name"] for priority in self._pages(url, "values")]

    def components(self, space: str) -> list[str]:
        """The names of space's components."""
        answer = _send("GET", self._api("project", space, "components"), self._auth, None)
        return [component["name"] for component in answer]

    def versions(self, space: str) -> list[str]:
        """The names of space's versions, but not those archived, which issues can't be given."""
        answer = _send("GET", self._api("project", space, "versions"), self._auth, None)
        return [version["name"] for version in answer if not version.get("archived")]

    def web_links(self, key: str) -> list[dict] | None:
        """The issue's web links, which Jira calls remote links: each with its id, and under
        "object" the url and title it links to. None when Jira won't show them, as on a site with
        issue linking turned off, or for an issue the token can't see."""
        try:
            return _send("GET", self._api("issue", key, "remotelink"), self._auth, None)
        except (Forbidden, NotFound):
            return None

    def add_web_link(self, key: str, url: str, title: str) -> None:
        """Links the issue to url, titled title. The link's global id is its URL, so Jira updates
        a link to it with that id instead of adding another; one too long for an id, over 255
        characters, has none."""
        body: dict = {"object": {"url": url, "title": title}}
        if len(url) <= 255:
            body = {"globalId": url, **body}
        _send("POST", self._api("issue", key, "remotelink"), self._auth, body)

    def retitle_web_link(self, key: str, link: dict, title: str) -> None:
        """Gives link, one of the issue's web links, title. Jira clears whatever a change leaves
        out, so this sends the rest of the link as it was."""
        body = {name: value for name, value in link.items() if name not in ("id", "self")}
        body["object"] = {**link["object"], "title": title}
        url = self._api("issue", key, "remotelink", str(link["id"]))
        _send("PUT", url, self._auth, body)

    def remove_web_link(self, key: str, link_id: int) -> None:
        _send("DELETE", self._api("issue", key, "remotelink", str(link_id)), self._auth, None)

    def find_users(self, query: str) -> list[User]:
        """The active people, not apps, whose name or email matches query."""
        search = urllib.parse.urlencode({"query": query, "maxResults": 50})
        users = _send("GET", self._api("user", "search") + "?" + search, self._auth, None)
        return [
            _user(user)
            for user in users
            if user.get("accountType") == "atlassian" and user.get("active")
        ]

    def issue_link(self, key: str) -> Issue:
        return Issue(key, f"{self.base_url}/browse/{key}")

    def _search(self, jql: str, fields: list[str]) -> list[dict]:
        """Every issue jql finds, with fields."""
        query: dict = {"jql": jql, "fields": fields, "maxResults": 100}
        issues: list[dict] = []
        while True:
            page = _send("POST", self._api("search", "jql"), self._auth, query)
            issues += page.get("issues", [])
            if not page.get("nextPageToken"):
                return issues
            query = {**query, "nextPageToken": page["nextPageToken"]}

    def _pages(self, url: str, key: str) -> list[dict]:
        """Every item under key in each page of the answer to url, read by startAt until a page
        is the last, by isLast or total, or empty."""
        items: list[dict] = []
        separator = "&" if "?" in url else "?"
        while True:
            query = f"{separator}startAt={len(items)}&maxResults=50"
            page = _send("GET", url + query, self._auth, None)
            items += page.get(key, [])
            last = page.get("isLast") or len(items) >= page.get("total", len(items) + 1)
            if last or not page.get(key):
                return items

    def _api(self, *path: str) -> str:
        quoted = (urllib.parse.quote(part, safe="") for part in path)
        return f"{self.base_url}/rest/api/3/" + "/".join(quoted)

    def _agile(self, *path: str) -> str:
        quoted = (urllib.parse.quote(part, safe="") for part in path)
        return f"{self.base_url}/rest/agile/1.0/" + "/".join(quoted)


def _user(user: dict) -> User:
    return User(user["accountId"], user.get("displayName", ""), user.get("emailAddress"))


def _query(value: str) -> str:
    """value as a URL's query parameter."""
    return urllib.parse.quote(value, safe="")


def _quote(value: str) -> str:
    """value as a JQL string."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _comparable(summary: str) -> str:
    return summary.strip().casefold()


def _send(method: str, url: str, auth: str, body: dict | str | None) -> Any:
    """Sends body as JSON, a str as a JSON string, or nothing for None, and returns Jira's JSON
    answer: {} when it answers with nothing, as it does to a move or an assignment.

    Raises Precondition when Jira refuses the token, NotFound when it answers 404, and Failure,
    with Jira's messages, for any other error or when the site can't be reached. Jira often
    answers a request it couldn't sign in as an anonymous user instead of refusing it, saying so
    in X-Seraph-LoginReason: that's a refused token too, whatever the answer.
    """
    headers = {"Authorization": auth, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    data = None if body is None else json.dumps(body).encode()
    return _exchange(urllib.request.Request(url, data=data, headers=headers, method=method))


def _upload(url: str, auth: str, name: str, content: bytes) -> Any:
    """POSTs content as a file named name, in a multipart/form-data part named file, as Jira
    takes attachments, and returns Jira's JSON answer. Raises as _send does.

    Jira refuses an upload without X-Atlassian-Token: no-check, its guard against cross-site
    requests. The name goes in the part's header as a browser sends it: in UTF-8, with quotes
    and line breaks percent-encoded.
    """
    boundary = secrets.token_hex(16)
    quoted = name.replace('"', "%22").replace("\r", "%0D").replace("\n", "%0A")
    kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
    data = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{quoted}"\r\n'.encode(),
            f"Content-Type: {kind}\r\n\r\n".encode(),
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    headers = {
        "Authorization": auth,
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-Atlassian-Token": "no-check",
    }
    return _exchange(urllib.request.Request(url, data=data, headers=headers, method="POST"))


def _exchange(request: urllib.request.Request) -> Any:
    """Sends request and returns Jira's JSON answer, or {} for none, raising as _send says."""
    try:
        with urllib.request.urlopen(request) as response:
            if _sign_in_failed(response.headers):
                raise _refused()
            content = response.read()
            return json.loads(content) if content.strip() else {}
    except urllib.error.HTTPError as error:
        if error.code == 401 or _sign_in_failed(error.headers):
            raise _refused() from None
        messages = _messages(error.read().decode(errors="replace"))
        if error.code == 403:
            hint = "Your account isn't allowed to do this, or the site has it turned off."
            raise Forbidden("Jira answered 403.", *messages, hint) from None
        kind = NotFound if error.code == 404 else Failure
        raise kind(f"Jira answered {error.code}.", *messages) from None
    except urllib.error.URLError as error:
        raise Failure(f"Can't reach {request.host}.", str(error.reason)) from None


def _sign_in_failed(headers) -> bool:
    reason = headers.get("X-Seraph-LoginReason") or ""
    return "AUTHENTICATED_FAILED" in reason or "AUTHENTICATION_DENIED" in reason


def _refused() -> Precondition:
    return Precondition(
        "Jira refused the API token.",
        "It must be a token created without scopes, stored under the email you sign in to"
        " Atlassian with, and not expired. Delete it from the credential store and run again to"
        " see how to store a new one.",
    )


def _messages(body: str) -> list[str]:
    """The messages in a Jira error's body, or the body itself when it has none."""
    try:
        answer = json.loads(body)
    except json.JSONDecodeError:
        return [body.strip()] if body.strip() else []
    if not isinstance(answer, dict):
        return [body.strip()]
    errors = answer.get("errors") or {}
    return [*answer.get("errorMessages", []), *(f"{k}: {v}" for k, v in errors.items())]
