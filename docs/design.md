# Design notes

How the task ended up the way it is: the versions that did not work, what the agent has to decide, and the harness problems we hit on the way. Summary in the [README](../README.md).

## Why no code

We built this environment several times, and each version taught us what it should measure.

| version | what happened |
|---|---|
| 5x5 board, agent has a shell | Gemini 4 Carbon writes its own look-ahead search and scores **1.000**. |
| 7x6 board, agent has a shell | Same: it writes a search, **1.000**. The board size does not matter to a program. |
| Rules-only look-ahead offered as a tool, no shell | Every model scores about **1.0**: it checks every branch with the tool until it is certain. |
| Same tool with a look-ahead budget | Gemini 4 Argon wins all 10 puzzles using ~1,100 explored positions, fewer than our own selective reference needs (3,096). No budget leaves a gap above the strongest model. |
| **No code, no look-ahead tool (this task)** | Planning has to happen in the model's own reasoning. This is where the Gemini 4 models fall through. |

So the environment measures one thing on purpose: **how far ahead a model can plan without a program doing the planning for it.** Writing a search is a solved skill; holding a 5-move forced line in your head, with every Red defence answered, is not. The organisers confirmed that removing code execution is a legitimate setting ("if code solves it then remove its ability to write code, just tools").

## The decisions that matter

Everything the agent needs is in front of it: the complete rules, a board view, unlimited practice with ground-truth feedback, notes, and a clock it can see. What it has to decide:

- **Which moves to consider.** In a deep puzzle only one move of ~20 keeps the win. The winning move is often quiet (no immediate threat), and the natural attacking move loses.
- **Which Red defences to answer.** A forced win means every Red reply is answered. The usual mistake is to check the reply you expect and miss the one that refutes you.
- **When a line is settled enough to play.** There is no undo, so playing on a hunch costs the puzzle; thinking past the clock costs it too.
- **How much to think, and in what steps.** A long analysis has to be spread over turns with notes; one reply that runs past the model's output limit ends the session.

## Does the reward encourage the behaviour we intended?

Not at first, and the logs showed it. The first no-code version let a model think until its session died, and let it open six puzzles and try to solve them in one reply. Neither was intended. The fixes below changed the environment, not the model; the shortcuts were checked too:

| shortcut | score |
|---|---|
| Do nothing | 0.000 |
| Random legal moves | 0.007 (probe pool), 0.00 - 0.08 (task) |
| Stop early after the 2 easiest | 0.167 |
| Notes as a side channel, peeking ahead, beating the clock | refused, see the attack table; every note we read is real elimination analysis |

The same question came up for training on the reward. We trained a small model on the reward bit alone, with two definitions of "good move" (details under Post-training). "The move keeps the forced win" pays 17.7% of random moves; the model learned to play safe moves that never get closer to winning, and its score stalled at 0.033. "The move brings the forced win one move closer" pays 7% of random moves, and the score climbed to 0.207. That second definition matches what the task scores, a win against a perfect defender.

## Harness limits we found and removed

Our first no-code runs ended after 5 to 15 minutes with most puzzles never reached, and the cause was not the game. `opencode run` ends a session as soon as a reply carries no tool call, and a model that reasons through a long line in one reply hits its output limit (32,768 tokens for Argon and Carbon, a hard API limit) and is cut off mid-thought: 6 of 9 sessions ended this way. Models also opened several puzzles and tried to solve them all in one reply. Three changes, none of which touches the model's own settings:

1. **`save_note`** gives the agent a game action that keeps a half-finished analysis, so a long line can span many turns.
2. **One puzzle at a time** stops a reply from holding several puzzles' analysis.
3. **A per-puzzle clock** stops one puzzle from eating the run, so every puzzle is reached.

With notes, cut-off sessions fell from 6 of 9 to 1 of 7 (Hydrogen, once, on a win in 5 after 20 minutes of paced play). Agents use notes as intended: worked lines and refutation lists, e.g. *"1.c1-a1 stops 1...c3-c2# AND threatens 2.c5-a3#"* (correct: it is the only winning move). We also raised OpenCode's own output cap to 64,000 in the task image, which only matters for Hydrogen. The task ships its own OpenCode config (shell, file writing and web access denied; output cap raised to 64,000 tokens); the organisers confirmed on 15 Nov that changing the OpenCode config is allowed.
