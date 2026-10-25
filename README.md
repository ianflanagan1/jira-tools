# jira-tools

Jira issues from the command line: filing them, reading them, setting their fields, linking them, logging time on them, and moving them along the board as you work on them; and two Claude Code skills: one files an issue for something raised in a conversation that won't be fixed now, such as a code-review finding, and one refines an issue someone filed without knowing the code, both written so an AI agent can do the work from the issue alone. Built on [cli-kit](../cli-kit).

```
$ jira create 'Scan skips repositories reached through a symlink' <<'EOF'
## Problem

`scan_folder()` in `src/scan.py:42` doesn't follow symlinks, so ...
EOF
✅ Filed WEB-9.
https://me.atlassian.net/browse/WEB-9
```

## `jira create <summary>`

Files an issue with that summary in the space, of the type and with the labels set in the repository's [`.config/ianf-tracker.toml`](#configianf-trackertoml). Its description is the Markdown on stdin, followed by where it was raised: the branch, commit and repository of the current folder, linked on GitHub.

Nothing is filed, with ⚠️ saying why, when the summary is over 80 characters, the description has Markdown Jira would show as plain text, such as a table, a quote or a nested list, or either has what looks like a secret, such as a token, a private key or `password = …`. It names the kind of secret and its line, never its value.

| Option | |
|---|---|
| `--type <type>` | file it as this type instead, such as `Bug` |
| `--label <label>` | add a label to the set ones; repeatable |
| `--stage <stage>` | file it at a [stage](#stages) of our process, as `jira stage` does; not at `ready-for-agent` with an Open questions section |
| `--space <key>` | file it in this space instead |
| `--tracker <file>` | take the settings from this file instead: another `ianf-tracker.toml`, or a product map, whose front matter has them. How report-problem files an issue about an app from outside its repository |
| `--priority <name>` | give it this priority, such as `High` |
| `--parent <key>` | file it under this issue: an epic, or for a subtask type, the issue it's part of |
| `--assign <who>` | assign it to `me`, or to someone by their name or email, as `jira assign` takes them |
| `--reporter <who>` | name this person its reporter instead of you, the same way |
| `--due <YYYY-MM-DD>` | give it this due date |
| `--component <name>` | give it this component; repeatable |
| `--fix-version <name>` | give it this version to be fixed in; repeatable |
| `--affects-version <name>` | give it this version it affects; repeatable |
| `--link <relation> <other>` | link it to the other issue once it's filed, as `jira link` does: `--link "is blocked by" WEB-9`; repeatable |
| `--field <name>=<value>` | set any field the type's create screen has, such as `"Story points=3"`; repeatable, as [Setting fields by name](#setting-fields-by-name) describes |
| `--field-file <name>=<path>` | set a field to what's in a file, such as acceptance criteria in Markdown; repeatable |
| `--estimate <duration>` | set the original estimate, such as `3d` or `1h 30m` |
| `--dry-run` | print what would be sent and stop, without the token or Jira |

Types, priorities, components and versions are matched ignoring case against those the space has, and named as Jira names them; archived versions aren't among them. Given one the space doesn't have, a relation the site doesn't have, or an issue or person that isn't there, `create` lists what there is, or names what's missing, and files nothing. `--dry-run` shows the options as given, unchecked, and people as you named them. `--parent` and `--link` name an issue as [other commands](#naming-an-issue) do, but a number alone is one in the space it's filed in.

A subtask is filed with its type and its parent: `jira create --type Subtask --parent WEB-12 'Add a test'`. What the subtask type is called depends on the site, `Subtask` or `Sub-task`; given the wrong one, `create` lists the space's types.

It isn't filed again while an open issue in the space has the same summary, ignoring case, and all of its labels: it ends `➖ Already filed as WEB-2.` That issue still gets any of the `--link`s it lacks, ending `✅ Already filed as WEB-2; linked it to WEB-9.` So running it again after a failure, even part-way through linking, finishes the job.

Jira Cloud takes descriptions in its own format, ADF, not Markdown. `jira` converts paragraphs, `##` headings, `-` and `1.` lists, fenced code, `` `code` ``, `**bold**` and `[links](url)`. Lists are flat, and anything else stays as text.

## Setting fields by name

`create` and `edit` set any field the issue's screen has, custom fields included, with `--field "<name>=<value>"`: `--field "Story points=3"`, `--field "Sprint=Sprint 4"`, `--field "Reviewer=me"`. The name is matched ignoring case; where two fields have it, `jira` lists their ids, and you name one by its id, such as `customfield_10016`. The value is read as the field takes it:

- text as it is, but a field of several lines, such as acceptance criteria or Environment, as Markdown, converted as a description is
- a number; a date as `2026-10-20`; a date and time as `2026-10-20T14:30`, in local time unless it gives its offset
- an option, version, component, priority or resolution by its name, ignoring case; given one the field doesn't have, it lists those it does
- a person as `assign` names them
- a sprint by its id, or by the name of an active or future sprint on one of the space's scrum boards
- a field of several values, such as checkboxes or a list of people, once for each: `--field Browsers=Chrome --field Browsers=Edge`

`--field-file "<name>=<path>"` reads the value from a file, for Markdown over several lines, and `--estimate` sets the original estimate, such as `3d` or `2w 1d 4h 30m`, in the time tracking field. A field with its own option, such as `--priority` or `--component`, is set by that or by `--field`, not both: given both, the command stops before anything is written. The summary, description, labels, type and space are set only by their own options and stdin; `--field` refuses them. On `edit`, an empty value, `--field "Story points="`, clears the field, and a field that already has the value is left as it is. A field the screen doesn't have, or of a kind not listed here, such as a cascading select, stops the command before anything is written. `--dry-run` shows the fields as given, under `set_by_name`, since reading them as their fields take them needs Jira.

## Naming an issue

Every command but `create` and `mine` takes the issue as `<key>`: its key, such as `WEB-12`, in any case; its number alone, `12`, for one in the set space; or its URL. A key is the space's key and the issue's number in that space. Jira also gives each issue an internal numeric id, but nothing here uses it.

## `jira view <key>`

Prints the issue as Markdown: its summary, type, status, resolution, priority, people, labels, components, versions and dates; the time estimated, spent and remaining, and how many watch it; its description and any other rich-text field, such as acceptance criteria, each under its own heading; any other custom field that's set, such as story points or the sprint, under Other fields; its parent, subtasks and linked issues, with their status; its web links; its attachments, linked; and every comment, oldest first, headed by its author, date and id, such as `### Ian Flanagan, 2026-10-13 (comment 10000)`, the id `jira comment --edit` and `--delete` take. It ends `➖ WEB-12 is In Progress.`

That's all someone needs to work on the issue, so it's also what to give Claude: `jira view WEB-12` in a session, or piped into a headless one. Jira's formatting is read back as Markdown, including tables, panels, task lists and mentions; an image in the description is named, `[attachment: shot.png]`, not shown.

## `jira mine [--space <key>]`

Lists the open issues assigned to you in the set space, or the one given, grouped by status: those in progress first, then those to do, the most recently updated first within each.

## `jira start <key>`

Starts work on the issue, from the repository you'll work on it in:

1. Assigns it to you.
2. Moves it to the `being-worked-on` [stage](#stages): the status `.config/ianf-tracker.toml` keeps it in, `In Progress` unless set, in one move: the same move you could make on the board. Jira allows only the moves the space's workflow has, so where it has none from the issue's status, such as a workflow that goes Backlog, Spec, Plan, In Progress, `start` stops and says which statuses it can move to. Move it on with `jira move` and run `start` again.
3. Switches to its branch: the one named by its key, `WEB-12` or `WEB-12-anything`, locally or on origin. When there's none, it creates one from the current commit, named for the key and summary: `WEB-12-scan-skips-symlinks`.

It stops, changing nothing, outside a repository, or when the issue is assigned to someone else (`jira assign` it to yourself first if you're taking it over), done, or can't move to `being-worked-on` from its status, or the move needs fields filled in: make that move with `jira move` and its options, and run `start` again. Each step is skipped when it's done, so after a failure you fix the cause and run it again.

The key in the branch name is what links a branch to its issue, for Jira's own GitHub and Bitbucket integrations as well as for `start`.

## `jira move <key> <status> [--resolution <name>] [--field <name>=<value>]...`

Moves the issue to a status, such as `"In Review"`, matched ignoring case. Jira moves an issue only by the transitions its workflow allows from its status, so when there's none to that status, it says which statuses it can move to. An issue already there ends `➖ WEB-12 is already In Review.`, whatever else it's given.

Some moves have a screen of fields to fill in, the commonest being the resolution on a move to Done. When one is required and not given, `move` stops before changing anything and names it, with the values it can take: `⚠️ Moving WEB-12 to Done needs: Resolution (Done, Won't Do, Duplicate).` A field the issue already has a value for, or one with a default, isn't asked for.

| Option | |
|---|---|
| `--resolution <name>` | resolve it as this, such as `"Won't Do"`, matched ignoring case; only on a move whose screen has a resolution |
| `--field <name>=<value>` | set any other field on the move's screen, as [Setting fields by name](#setting-fields-by-name) describes; repeatable. `--field Resolution=<name>` works too, but not with `--resolution` |
| `--field-file <name>=<path>` | the same, with the value read from a file; repeatable |

The Markdown on stdin, if any, is added as a comment, converted as `create` converts a description: with the move, where its screen takes a comment, or straight after it.

```
$ echo 'Released in 1.4.' | jira move WEB-12 done --resolution done
✅ Moved WEB-12 to Done, with the comment.
```

## `jira assign <key> [<who>]`

Assigns the issue to `me`, the default; to no one, with `none`; or to someone else, by their name or email. Someone else must match one person in Jira, or among several, one whose name or email is exactly what you gave.

## `jira comment <key> [--edit <id> | --delete <id>] [--dry-run]`

Adds the Markdown on stdin to the issue as a comment from you, converted as `create` converts a description. It isn't added again while the issue has a comment from you that reads the same, so running it again is safe.

| Option | |
|---|---|
| `--edit <id>` | replace your comment with that id with the Markdown on stdin instead |
| `--delete <id>` | delete your comment with that id, reading nothing from stdin |
| `--dry-run` | print what would be sent and stop, without the token or Jira; not with `--delete` |

`jira view` shows each comment's id. Both touch only your own comments: anyone else's stops it, changing nothing, as does editing a comment the issue doesn't have. A comment that already reads so ends `➖ Comment 10000 on WEB-12 already reads so.` A comment the issue doesn't have is taken as already deleted, since that's what running `--delete` again finds, and ends `➖ WEB-12 has no comment 10000 to delete.`; so check the id against `jira view` before you delete.

## `jira attach <key> <file>...`

Uploads each file to the issue, under its own name, with any quote or line break in it as `_`. A file the issue already has an attachment of, with the same name and size, isn't uploaded again, so running it again is safe: the issue's URL follows `✅ Attached 2 files to WEB-12.`, with any already there named, and an issue with them all ends `➖ WEB-12 already has trace.txt.` A file that's missing, can't be read, or is a folder stops it before anything is uploaded.

## `jira log <key> <duration> [--started <when>] [--remaining <duration>] [--dry-run]`

Logs time on the issue as you: the duration as Jira writes it, in weeks, days, hours and minutes, such as `1h 30m`, `2d` or `45m`, where Jira's day and week are the site's working day and week, by default 8 hours and 5 days. The Markdown on stdin, if any, is the worklog's comment, converted as `create` converts a description.

| Option | |
|---|---|
| `--started <when>` | when the work started, as `2026-10-14 09:00` or `2026-10-14T09:00`, in local time; now unless given |
| `--remaining <duration>` | set the issue's remaining estimate to this; without it, Jira takes the time spent off it |
| `--dry-run` | print what would be sent and stop, without the token or Jira |

Logged time adds up, so it isn't logged again while the issue has a worklog of yours with the same time, the same start to the minute, and the same comment: it ends `➖ Already logged 1h 30m on WEB-12 from 2026-10-14 09:00.` Without `--started`, the start is now, which moves on, so only a run again within the minute is caught. Pass `--started` when running it again must be safe, as a script or an agent logging time should.

## `jira watch <key> [<who>]`

Adds `me`, the default, or someone else, by their name or email, matched as `assign` matches them, to the issue's watchers, whom Jira tells of its changes. Someone already watching it ends `➖ You're already watching WEB-12.` Adding someone else takes the space's Manage watcher list permission, and watching or unwatching someone else takes permission to see who watches: without it, Jira tells you only whether you watch, and `watch` and `unwatch` stop.

## `jira unwatch <key> [<who>]`

Removes `me`, the default, or someone else from the issue's watchers. Someone not watching it ends `➖ You aren't watching WEB-12.`

## `jira edit <key> [<option>]...`

Replaces the issue's description with the Markdown on stdin, if any, converted as `create` converts it, and changes what the options give. Only what differs is sent: an issue that already reads so ends `➖ WEB-12 already reads so.`

| Option | |
|---|---|
| `--summary <summary>` | replace its summary |
| `--label <label>`, `--unlabel <label>` | add or remove a label; repeatable |
| `--priority <name>` | set its priority, such as `High` |
| `--parent <key>` | set its parent, such as its epic, or with `none` remove it |
| `--type <name>` | change its type, such as `Bug` |
| `--reporter <who>` | set its reporter: `me`, or someone's name or email, as `assign` takes them |
| `--due <YYYY-MM-DD>` | set its due date, or with `none` clear it |
| `--component <name>`, `--uncomponent <name>` | add or remove a component; repeatable |
| `--fix-version <name>`, `--unfix-version <name>` | add or remove a version it's fixed in; repeatable |
| `--affects-version <name>`, `--unaffects-version <name>` | add or remove a version it affects; repeatable |
| `--field <name>=<value>` | set any field its edit screen has, such as `"Story points=3"`, or with an empty value clear it; repeatable, as [Setting fields by name](#setting-fields-by-name) describes |
| `--field-file <name>=<path>` | set a field to what's in a file, such as acceptance criteria in Markdown; repeatable |
| `--estimate <duration>` | set the original estimate, such as `3d` or `1h 30m` |
| `--keep-original` | keep the description it replaces below the new one |
| `--dry-run` | print what would be sent and stop, without the token or Jira |

Priorities, types, components and versions are matched ignoring case against those the issue's space has; given one it doesn't have, `edit` lists those it does and changes nothing. Archived versions aren't among them. `--dry-run` shows them as given, unchecked, and people as you named them.

Jira changes an issue's type by an edit only where the two types share its workflow and fields; otherwise it refuses, and `edit` passes on what it says. A subtask becomes another type, or another type a subtask, only by Jira's Move, in its web app.

`--keep-original` keeps the replaced description under `## Original report`, in a code block: exactly as it read, and set apart so nothing in it, not even a line of backticks, reads as part of the new description. Edited again, the issue keeps that first original.

## `jira link <key> <relation> <other>`

Links the issue to the other one, as the relation reads from the issue: `jira link WEB-12 "is blocked by" WEB-9`, and WEB-9 then reads "blocks WEB-12". The relations are those of the site's link types, each read both ways, matched ignoring case: by default `blocks` and `is blocked by`, `clones` and `is cloned by`, `duplicates` and `is duplicated by`, and `relates to`. Given one the site doesn't have, it lists those it does. Issues already linked so end `➖ Already linked: WEB-12 is blocked by WEB-9.`

## `jira unlink <key> <relation> <other>`

Removes the link that reads so, from both issues; links between them of other kinds, or the other way round, are kept. Issues not linked so end `➖ Not linked: WEB-12 is blocked by WEB-9.`

## `jira weblink <key> <url> [<title>]`

Links the issue to a web page, such as a pull request or a document, titled `<title>`, or by its URL when there's none: `jira weblink WEB-12 https://github.com/me/web/pull/42 "Follow symlinks"`. Jira calls these remote links and shows them apart from linked issues; `jira view` lists them under Web links. The URL must start `http://` or `https://`. An issue that already links to the URL keeps that link: with the same title it ends `➖ WEB-12 already links to https://github.com/me/web/pull/42.`, and with another it's retitled.

## `jira unweblink <key> <url>`

Removes the issue's web links to the URL, every one there is. An issue without one ends `➖ WEB-12 has no link to https://github.com/me/web/pull/42.`

## Every command

Every command ends with one status line, ✅ ➖ ⚠️ ❌ or 🛑, as [cli-kit's README](../cli-kit/README.md#how-every-command-behaves) describes.

## Stages

Our skills take an issue through stages, each named for what has to happen next:

| Stage | Next | Set by |
|---|---|---|
| `needs-codebase` | a developer runs `/jira-refine`: no one has compared the report with the code yet | report-problem |
| `needs-developer` | a developer answers, decides or approves | `/jira-ticket` quick or not approved, `/jira-refine` not approved |
| `ready-for-agent` | an agent may work on it: a person approved it, with no open questions | `/jira-ticket` or `/jira-refine`, on approval only |
| `being-worked-on` | work has started | `jira start` |
| `awaiting-review` | the work is up for review | |
| done | nothing | any status in the workflow's done category |

`[stages]` in `.config/ianf-tracker.toml` maps a stage to the status your workflow has for it; a stage left out is kept as a `stage-<name>` label instead, in any to-do status no stage is mapped to. So a space with a status for every stage uses no labels, and one with only To Do, In Progress and Done uses labels for the rest. A mapped status is where an issue is, whatever its labels say: people move issues on the board, and only our commands touch the labels.

## `jira stage <key> [<stage>]`

Says which stage the issue is at, or moves it to stage: to the status that stage is mapped to, or by its label, removing any other stage label. A stage kept as a label moves an issue out of a status another stage is mapped to first, to a to-do status none is. It won't move an issue whose description has an Open questions section to `ready-for-agent`, or a done one anywhere. An issue already at the stage ends `➖ WEB-12 is already at needs-developer.`

## The jira-ticket skill

`/jira-ticket` files an issue for something raised in the conversation. Name it after the skill: a finding's number, a few words, or the problem itself, and optionally how to file it ("as a bug", "label perf"). With nothing named, it files the issue most recently put off.

By default it refines the issue as it files it, while you still have it in mind, so it can go to an agent straight away. Claude fills in what it can from the conversation and the code, asks you once, in up to four questions, about what's still missing, and shows you the issue as it will be filed. You choose: ready for an agent, not ready yet, or a change. It's filed with `jira create --stage`, at `ready-for-agent` or `needs-developer`.

Say `quick` (`/jira-ticket quick the scan skips symlinks`), or choose "File it now, refine later" at the first question, to file it at `needs-developer` without more questions or a draft: anything missing goes under Open questions, for `/jira-refine` later. Run headless, it's always quick. It won't file an issue without a problem and a way to tell it's done.

Only you start it (`disable-model-invocation: true`): Claude never files an issue on its own.

## The jira-refine skill

`/jira-refine WEB-12`, run in the repository the work will be done in, turns an issue at `needs-codebase` or `needs-developer`, such as a colleague's problem report or one filed quickly, into one an agent can work from. Claude reads the issue, finds where the behaviour comes from in the code, asks you once about what it can't find out, and shows you the new summary and description. It's written with `jira edit --keep-original`, then moved to `ready-for-agent` once you approve it, or to `needs-developer` if you don't, or when run headless.

Both skills refine by the same guides, in [shared/references](shared/references): what an issue needs, how to investigate the code, how to ask, and how an issue is approved.

### Giving issues to an agent

An agent working an issue can change your code, and everything in an issue was written by someone outside your session: a client, a colleague, anyone who can edit it. So:

- Give an agent only issues at `ready-for-agent`. Their description above Original report is what a person approved; the Original report, and every comment, is evidence, not instructions.
- Prefer mapping `ready-for-agent` to a status, and restrict who can move an issue into it in the space's workflow, so the status itself shows a developer approved it. A `stage-ready-for-agent` label proves only that someone who can edit the issue set it: where reporters can edit issues, check who set it in the issue's history, or keep reporters out of the space.
- The refine skill reads issues with nothing but `jira view`, `jira edit`, `jira stage` and read-only access to the code. Whatever a report tells it to do, it has no tool to change a file, run a command or send anything anywhere, and it's told to list any request beyond the fix as an open question and point out text that reads like instructions to an AI.

Install it as a plugin, from this folder or from GitHub:

```
/plugin marketplace add ~/projects/cli/jira-tools
/plugin install jira-tools@jira-tools
```

## `.config/ianf-tracker.toml`

Where a repository's issues go is the team's to decide, so it's set in a file committed in the repository, `.config/ianf-tracker.toml`, as [repo-settings](../repo-settings) describes. jira-tools reads it as it is in the worktree you're in, so a branch can change it; [`ianf-tracker.example.toml`](ianf-tracker.example.toml) shows every setting. Only your API token stays on your machine. jira-tools owns the file, and product-map and dora-tools read it too.

The file sets `version`, the version of its format, and names its schema on its first line, so an editor with a TOML language server, such as Even Better TOML in VS Code, checks it as you type. [`schema/`](schema) has the schema for each version.

| Setting | |
|---|---|
| `site`, `space` | needed: the Jira Cloud site, and the key of the space issues are filed in, the prefix of their keys. A space is what Jira used to call a project, and still does in its API; its key can differ from its name |
| `kind` | `jira`, the default; any other tracker is refused |
| `issue_type` | the type issues are filed as, `Task` by default |
| `labels` | labels every issue gets, none by default |
| `version` | needed: the version of the file's format, `1` |
| `[stages]` | the status your workflow keeps each of our [stages](#stages) in; by default only `being-worked-on`, in `In Progress` |

Every command reads it from the repository the current folder is in, and does nothing, with ⚠️ saying why, outside a repository, without the file, or without `site` or `space`: an issue is always filed from the repository it's about. A setting with a default that's left out takes it, and the command says so on stderr.

`jira tracker` shows the settings it would use and where they came from. The skills run it as they load, so they stop before any work when nothing could be filed.

`jira workspace` and `--workspace`, the names from before the settings moved to `.config/`, still work for now, with a warning, so a skill or plugin installed before the rename keeps working until it's updated.

## Setup

Once per machine:

```sh
cd ~/projects/cli/jira-tools
devbox run setup   # uv sync, building .venv
```

That also links `jira` into `~/.local/bin`, and says so if that folder isn't on your PATH. Where issues go is set in each repository, in its [`.config/ianf-tracker.toml`](#configianf-trackertoml), not on your machine.

`jira` signs in with your Atlassian email and an API token, kept in the macOS keychain or, on Linux, the Secret Service keyring. On Windows it doesn't yet read Windows Credential Manager, so it stops with ⚠️ saying credentials aren't supported; setup also uses devbox, which runs on Windows only inside WSL. The first time it needs the token it stops and prints the command that stores it on your system, under your email. Create the token at <https://id.atlassian.com/manage-profile/security/api-tokens>. It can do whatever your account can in Jira; `jira` reads, searches, creates, edits, comments on, attaches files to, assigns, moves, links and watches issues; links them to web pages and logs time on them; removes links and watchers; and edits and deletes your own comments, but never deletes issues, attachments or anyone else's comments.

For a Jira to try it on, Atlassian's Free plan gives you a site at `<name>.atlassian.net` for up to ten users.

## Development

```sh
devbox run test    # pytest
devbox run lint    # ruff check and format
```
