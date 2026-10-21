#!/bin/sh
# Prints the shared reference named by each argument, from shared/references/<name>.md, for the
# skills to load. The skills load them with this rather than cat: Claude Code blocks a load-time
# cat of a file outside the session's working directories, which a plugin's files always are in
# real use, but runs a script its allowed-tools allow wherever it is.
#
# Usage: reference.sh <name>...
# Exit status: 0, or 1 when a reference doesn't exist.

references=$(cd "$(dirname "$0")/../references" && pwd -P)
status=0
for name; do
    case $name in
        */* | .*) echo "No reference $name." >&2; status=1; continue ;;
    esac
    if [ -f "$references/$name.md" ]; then
        cat "$references/$name.md"
    else
        echo "No reference $name." >&2
        status=1
    fi
done
exit "$status"
