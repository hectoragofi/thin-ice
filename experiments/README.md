# Side experiments

Two variants of the task, built from `task/` by script so they can be rerun. They are not part of the
one-command evaluation and their results are reported separately from the main table.

Built folders (`experiments/*/task`, `experiments/practice/p*/task`) are generated and git-ignored.

## Deep: win in 7, 8 and 9

    python experiments/deep/build_deep.py     # writes experiments/deep/task
    python experiments/deep/check_deep.py     # self-check and overlap checks, no Docker

Six puzzles, two each with a win in 7, 8 and 9 moves, taken from the deeper tiers of the pool the main
build already solved and never serves. Same rules as the main task: N+1 moves, 2 minutes per move of the
forced win, same tools, permissions and verifier. Clocks add up to 96 minutes, the run is 102. Score is
puzzles won out of 6. These puzzles have no Lean proofs.

    harbor run -p experiments/deep/task -e modal -a oracle -k 1 -n 1 -y     # 1.000
    harbor run -p experiments/deep/task -e modal -a nop -k 1 -n 1 -y        # 0.000
    harbor run -p experiments/deep/task -e modal -a opencode -m <model> -k 1 -n 1 -y --ae <KEY>=$<KEY>

## Forced practice

    python experiments/practice/build_practice.py   # writes experiments/practice/p12/task and p30/task

The main task with one added paragraph in the instruction: play 12 (or 30) practice puzzles, 2 (or 5)
per depth, before the scored ones. Everything else is copied unchanged. Compare with the same model's
runs on the unchanged task.

    harbor run -p experiments/practice/p12/task -e modal -a opencode -m <model> -k 3 -n 3 -y --ae <KEY>=$<KEY>
