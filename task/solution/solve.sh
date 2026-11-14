#!/bin/bash
# Reference run.
#   SOLUTION=book   (default) perfect play: every move comes from the exhaustive solver.
#   SOLUTION=search rules-only look-ahead program, no precomputed answers.
#   SOLUTION=tools  tools-only player: only the agent's own tools (puzzle view, explore, move),
#                   no game code and no solver data; proves every scored puzzle is reachable.
set -u
cd "$(dirname "$0")"
if [ "${SOLUTION:-book}" = "tools" ]; then
    python3 toolplay.py
else
    python3 solve.py
fi
