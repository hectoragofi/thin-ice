"""Builds the forced-practice variants of the task: the main task with one added instruction paragraph.

    python experiments/practice/build_practice.py        # writes experiments/practice/p12/task and p30/task

Nothing else changes: game server, puzzles, clocks, tools, permissions and verifier are copied as they
are from task/. The added paragraph tells the agent to play N practice puzzles per depth (win in 1 to 6)
before the scored puzzles: N = 2 gives 12 practice puzzles (p12), N = 5 gives 30 (p30).
"""
from __future__ import annotations

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "task"

for per_depth in (2, 5):
    dst = HERE / f"p{per_depth * 6}" / "task"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("__pycache__"))
    path = dst / "instruction.md"
    text = path.read_text(encoding="utf-8").rstrip()
    text += (
        f"\n\n**Practise first.** Before you look at `P01`, play {per_depth * 6} practice puzzles: {per_depth} each "
        "with a win in 1, 2, 3, 4, 5 and 6 moves, in that order. Play each one to its end and read what the reply "
        "says about any move you got wrong. Then start the scored puzzles.\n"
    )
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"built {dst}")
