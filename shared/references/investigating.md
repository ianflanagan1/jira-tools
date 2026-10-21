Fill in what each issue needs from the code. Read files with the Read tool, and search them with the Grep and Glob tools, or where you don't have those, with `grep` and `ls` commands; nothing else that runs in a shell. Find:

- Where the behaviour comes from: the files, functions, screens, routes or handlers involved.
- The conditions that change it, such as roles, plans, feature flags and settings.
- The tests covering it, and the command that runs them, in the repository's README, CLAUDE.md, devbox.json, package.json or the like.

A likely cause the code doesn't show for certain is a guess: say so. Don't change any file or run the tests.
