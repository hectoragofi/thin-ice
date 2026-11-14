#!/bin/bash
# Reference run.
#   SOLUTION=book   (default) perfect play: every move comes from the exhaustive solver.
#   SOLUTION=search rules-only look-ahead, no precomputed answers; solves what it can in time.
set -u
cd "$(dirname "$0")"
python3 solve.py
