---
name: jira-ticket
description: File a Jira issue for something raised in this conversation that won't be fixed now, such as a code-review finding, linked to the branch and commit it was raised on. Refines it with you as it files, while you still have it in mind - reads the code, asks what it can't find out, and once you approve it, files it ready for an AI agent. Say "quick" to just file it and refine it later. Prints each issue's key and URL.
disable-model-invocation: true
model: inherit
allowed-tools: Bash(jira tracker:*), Bash(echo "exit $?"), Bash(sh *shared/scripts/reference.sh*), Bash(jira create:*), Bash(jira attach:*), Bash(grep *), Bash(ls *), Read, Grep, Glob
---

# Jira ticket

File what the user names as Jira issues, with the `jira` command from jira-tools, and unless they want it quick, refine each with them as you go, so it can be ready for an agent as soon as it's filed.

If a `reference.sh` command below still shows instead of a reference, read that reference, `shared/references/<name>.md` at the plugin's root, two folders above this one, before going on.

## Check

Where this repository's issues go, from `jira tracker`, captured when this skill loaded:

```
!`jira tracker 2>&1; echo "exit $?"`
```

If the block above still shows the command rather than its output, run `jira tracker` yourself.

- `exit 0`: go on. A line saying defaults were used is a note, not a problem.
- `exit 127`, or `jira` not found: reply `⚠️ jira isn't installed.`, then that it's set up as jira-tools' README describes, and stop.
- A `⚠️` line: reply with it and the lines after it, as they are, and stop. An issue is filed only from the repository it's about, whose `.config/ianf-tracker.toml` says where its issues go.

## Asking

!`sh "${CLAUDE_PLUGIN_ROOT}/shared/scripts/reference.sh" asking`

## What to file

Any text after the skill's name says what to file: a finding's number, a few words naming something discussed, or the problem itself. With no text, file the issue raised most recently in this conversation that the user chose not to fix now. If the text could mean more than one thing, or nothing in the conversation fits, ask which; don't guess. When no one is there to answer, reply `⚠️ Not sure what to file.`, then the readings you see, and stop. File one issue for each thing named.

The text may also say how to file it: "as a bug" is `--type Bug`, "label perf" is `--label perf`, "in OPS" is `--space OPS`. Otherwise leave these out, so the settings in the repository's `.config/ianf-tracker.toml` apply. It may also answer some of what the issue needs, such as when it's done.

## Quick or refined

- **Refined**, unless the user says otherwise: gather, ask, show it for approval, and file it at `ready-for-agent` once approved.
- **Quick**, when the text says so, such as "quick" or "just file it", or the user chooses it while you ask: gather, then file it at `needs-developer` without asking anything more or showing it first. Anything missing goes under Open questions, for `/jira-refine` later.
- **When no one is there to answer:** as quick.

## What a ticket needs

!`sh "${CLAUDE_PLUGIN_ROOT}/shared/scripts/reference.sh" writing-a-ticket`

## Gather

For each issue, fill in what it needs from the conversation first, then from the code.

!`sh "${CLAUDE_PLUGIN_ROOT}/shared/scripts/reference.sh" investigating`

## Ask

Refined only. Ask as Asking above says. Give the first question one more answer, `File it now, refine later`, which makes every issue quick.

## Approve

Refined only.

!`sh "${CLAUDE_PLUGIN_ROOT}/shared/scripts/reference.sh" approving`

## File it

Run one command for each issue, from the repository it was raised in, since `jira` adds that repository's branch and commit to the description:

```sh
jira create '<summary>' --stage <stage> <options> <<'EOF'
<description>
EOF
```

- The stage: `ready-for-agent` for an issue the user approved as ready for an agent; otherwise `needs-developer`.
- Quote the summary in single quotes, writing a `'` in it as `'\''`.
- Never put a line that is only `EOF` in the description.
- Don't add the branch or commit yourself.

An issue `jira create` says was already filed keeps its stage: say so, rather than changing it.

Then, when images were pasted in this conversation, attach them to each issue filed, or already filed. They're numbered in the order they were pasted, from 1, whatever the prompt called them:

```sh
jira attach <key> --session ${CLAUDE_SESSION_ID} --image <n>
```

With one issue, attach every image, leaving out `--image`. With several, give each issue the images that show it, an `--image` for each, and every image to each issue when you can't tell. In the description, refer to an image that shows something by the name it's attached as, `pasted-image-<n>.png`: write that before filing, since you know the numbers.

Never read, store or ask for the API token, and never edit `.config/ianf-tracker.toml`: when `jira` stops with ⚠️ about either, pass its message on and stop.

## Output

For one issue, reply with `jira create`'s output as it is: `✅ Filed WEB-9 at ready-for-agent.` and the issue's URL, `➖ Already filed as WEB-2.`, or its ⚠️ line and what it says to do. After ✅ at `needs-developer`, one line: `Refine it with /jira-refine WEB-9.`, adding the number of Open questions when it has some. Then `jira attach`'s first line, such as `✅ Attached 2 files to WEB-9.`, when images were attached; after ⚠️ or ❌ from it, its lines, then that the issue was filed without them. After `❌ Create failed.`, put the error in a fenced `text` block, then one short line on the cause and the fix you propose. When it wasn't filed for lack of a Problem or Done when, reply `⚠️ Not enough to file.`, then what's missing.

For several:

- `✅ Filed.` when at least one was filed and the rest were already open. Then one line for each: its key, summary and URL, adding its stage, `(already filed)` where it was, `(N open questions)` where it has some, and `(not filed: <what's missing>)` for any left unfiled.
- `➖ Already filed.` when every one was already open, and nothing after it.
- `⚠️ Not enough to file.` when none could be filed for lack of a Problem or Done when. Then what each is missing.
- `🛑 Stopped.` when one failed after others were filed. Then the ones filed, the error, and what's left. Running the skill again for the same issues resumes: `jira` skips those already open.
