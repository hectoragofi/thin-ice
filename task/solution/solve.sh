#!/bin/bash
# Reference run.
#   SOLUTION=book   (default) perfect play: every move comes from the exhaustive solver.
#   SOLUTION=search rules-only look-ahead program, no precomputed answers.
#   SOLUTION=tools  tools-only player: only the agent's own tools (puzzle view, explore, move),
#                   no game code and no solver data; searches selectively inside the budget.
#   SOLUTION=exhaustive  the same player proving every Red branch first (the costly habit).
set -u
cd "$(dirname "$0")"
if [ "${SOLUTION:-book}" = "tools" ]; then
    python3 toolplay.py
elif [ "${SOLUTION:-book}" = "exhaustive" ]; then
    # the same tools-only player, but proving every branch before each first move
    HORIZON=99 PUZZLE_CAP= python3 toolplay.py
else
    python3 solve.py
fi
