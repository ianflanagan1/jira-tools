An agent may work only on an issue a person has approved, so an issue goes to the `ready-for-agent` stage only when the user has read it as it will be written and said so, and it has no Open questions.

Show the user each issue as it will be written: its summary and its description. Then ask, one question for each issue, at most four in a round, with these answers:

- **Ready for an agent:** write it at `ready-for-agent`.
- **Not ready yet:** write it at `needs-developer`, to refine later with `/jira-refine`.
- **Change something:** they say what; change it, show it again and ask again.

An issue with Open questions can't be ready: offer only the last two.

When no one is there to answer, write it at `needs-developer`.

Set an issue's stage only with `jira create --stage <stage>` or `jira stage <key> <stage>`, which keep it in the status the repository's `.config/ianf-tracker.toml` maps it to, or as a `stage-` label. Never add a `stage-` label, or move an issue's status, any other way.
