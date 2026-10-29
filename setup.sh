#!/bin/sh
# Links jira-tools's commands onto your PATH. Run with `devbox run setup`, which first runs
# `uv sync` to build .venv.

set -o errexit -o nounset

here=$(cd "$(dirname "$0")" && pwd -P)
"$here/.venv/bin/python" -m cli_kit.link "$here"
