Write each issue for its usual reader: an AI agent given only `jira view <key>` and the repository, weeks from now, that can't ask anyone. A person picking it up needs the same. Everything the agent couldn't work out from the code goes in the issue; everything it could, it needn't, though pointing to where to look saves it the search.

## What each kind needs

Before writing, check the issue has what its kind needs. An item the conversation, the code or the user can't supply is a gap: ask about it, or list it under Open questions.

- **Bug:** where it happens; steps to reproduce, or the input that triggers it; what happens and what should; how often, and what it affects.
- **Feature or change:** who it's for and what they're trying to do; how it should behave, including edge cases; what's out of scope.
- **Follow-up** (a review finding, tech debt, something put off): where it is; what's wrong with it and what that causes; why it was put off.

Every issue also needs a way to check it's done: the behaviour a test could state, and the command that runs the tests. And any constraints the fix must keep to: an API that can't change, a dependency that can't be added, behaviour others rely on.

## Summary

One line, of 80 characters at most, stating the problem as behaviour, not the fix, and specific enough to find again: `Scan skips repositories reached through a symlink`, not `Fix scan` or `Finding 3`.

## Description

Markdown, in these sections, each a few lines at most. Leave out a section with nothing to say, except Problem and Done when.

```markdown
## Problem

What's wrong and what it causes, and where. For a bug: the steps or input, what happens, and what should.

## Context

Why it matters, who it affects, and, for one put off, why not now: outside this branch's scope, needs a decision, part of a larger change.

## Where to start

The files, functions and tests involved: `src/scan.py:42`, `scan_folder()`, `tests/test_scan.py`.

## Suggested approach

The fix that was discussed, saying whether it was tried. Alternatives ruled out, and why.

## Constraints

What the fix must keep to, and what's out of scope.

## Done when

- What will be true once it's fixed, each as a behaviour a test could state.
- The command that runs the tests: `devbox run test`.

## Open questions

- Each gap left: what's unknown and, where known, who could answer it. Leave the section out when there are none.
```

- Leave out "as discussed", "finding 3", "the reviewer" and anything else that only makes sense inside this conversation.
- State only what the conversation, the code or the user's answers show. Mark a guess as a guess, and don't invent figures, causes or answers: a gap belongs under Open questions, not filled in.
- An image attached to the issue, such as a pasted screenshot, is named by its file name, `pasted-image-1.png`, where it shows something the text describes.
- A short snippet in a fenced block is fine; don't paste whole functions or diffs. Never include secrets, tokens or personal data.
- `jira` converts paragraphs, `##` headings, `-` and `1.` lists, fenced code, `` `code` ``, `**bold**` and `[links](url)`. Use nothing else: no tables, nested lists or italics.
