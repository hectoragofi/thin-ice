# Thin Ice

A reinforcement learning environment that measures how many moves ahead an agent can plan, by its own reasoning, in a system it has never seen.

Thin Ice is a small board game we invented for this challenge and then **solved completely**: all 16.5 billion positions of the 7x6 board, by exhaustive retrograde analysis. Because the game is solved, every move an agent makes is provably right or wrong. There is no judge model, no heuristic and no partial credit anywhere in the reward.

Built for AfterQuery's "Break the Agent" challenge at Junction 2026. It is a standard [Harbor](https://github.com/laude-institute/harbor) task, run with the stock OpenCode agent.

```
6 . . . . . . .
5 . . B . B . .        Blue to move and win in 4.
4 . . . . R . .        25 legal moves.
3 . . R R . . .         1 keeps the win (c1-a1).
2 B . . . . . .        24 lose the game.
1 . . B . . . R
  a b c d e f g
```

(A real position from a frontier run: the agent played c1-g5, which loses to a forced Red win in 2.)

## The game

- 7 columns by 6 rows. Blue has 4 stones, Red has 4. Players alternate, one stone per turn.
- A stone slides in one of 8 directions and cannot stop early: it stops on the last empty cell before the edge or before another stone.
- First to get 3 of their stones in a row wins. A player who cannot move loses.

That is the whole rulebook. It fits in a paragraph, yet forced wins run up to 63 moves deep, and in a typical puzzle exactly one move keeps the win while every other move loses. One slip and you fall through, hence the name.

## What the agent has to do

32 puzzles in 16 tiers, two per tier: a win in 1 move, in 2, ... up to a win in 16. In each, Blue (the agent) is to move and has a forced win; Red is played by a perfect opponent that always picks the longest defence. The agent may use N+1 moves on a win in N. A puzzle is lost the moment the agent plays a move after which the win is no longer forced. There is no undo and no retry. Thirty minutes in total.

The agent talks to the game over MCP: `rules`, `list_puzzles`, `show_puzzle`, `play_move`, `new_practice_puzzle`, and `save_note` for keeping its own analysis between turns. **It has no shell, no file writing and no way to run code**: it has to find each move by thinking it through. Practice mode is unlimited and never counts: it serves fresh puzzles and answers a wrong move with the move that would have won.

**Score = puzzles won / 32.** One number between 0 and 1, written to `/logs/verifier/reward.txt`.

## Why no code

We built this environment three times, and the first two taught us what it should measure.

| version | what happened |
|---|---|
| 5x5 board, agent has a shell | Gemini 4 Carbon writes its own look-ahead search and scores **1.000**. |
| 7x6 board, agent has a shell | Same: it writes a search, **1.000**. The board size does not matter to a program. |
| Rules-only look-ahead offered as a tool, no shell | Every model scores about **1.0**: it checks every branch with the tool until it is certain. |
| Same tool with a look-ahead budget | Gemini 4 Argon wins all 10 puzzles using ~1,100 explored positions, fewer than our own selective reference needs (3,096). No budget leaves a gap above the strongest model. |
| **No code, no look-ahead tool (this task)** | Planning has to happen in the model's own reasoning. This is where frontier models fall through. |

So the environment measures one thing on purpose: **how far ahead a model can plan without a program doing the planning for it.** Writing a search is a solved skill; holding a 5-move forced line in your head, with every Red defence answered, is not. The organisers confirmed that removing code execution is a legitimate setting ("if code solves it then remove its ability to write code, just tools").

## The decisions that matter

Everything the agent needs is in front of it: the complete rules, a board view, unlimited practice with ground-truth feedback, and 30 minutes. What it has to decide:

- **Which moves to consider.** In a deep puzzle only one move of ~25 keeps the win. The winning move is often quiet (no immediate threat), and the natural attacking move loses.
- **Which Red defences to answer.** A forced win means every Red reply is answered. The usual mistake is to check the reply you expect and miss the one that refutes you.
- **When a line is settled enough to play.** There is no undo, so playing on a hunch costs the whole puzzle.
- **How to use practice.** Practice tells you the right move when you are wrong; it is the agent's only source of feedback on its own reading.
- **How to spend 30 minutes over 32 puzzles** of rising difficulty, and how long to think before acting (see the next section).

## Results

Every row is a Harbor run on Modal (`-e modal`) at the commit in the job name, reproducible with the command in the next section. Frontier agents: OpenCode with Gemini 4, 3 runs each.

| run | reward |
|---|---|
| Reference: perfect play (moves from the solver) | **1.000** |
| Reference: rules-only search, 20 s per puzzle (wins every win in 1 to 5, never loses one, leaves deeper ones open) | 0.344 |
| Gemini 4 Argon, 3 runs | RESULT_ARGON |
| Gemini 4 Carbon, 3 runs | RESULT_CARBON |
| Gemini 4 Hydrogen, 3 runs | RESULT_HYDROGEN |
| Baseline: stop early (wins the 4 easiest, then quits) | 0.125 |
| Baseline: do nothing | 0.000 |

### Where the agents go wrong

MISTAKE_TABLE

Scripted policies, 3 seeds each, in-process (`python tools/selfcheck.py`, no Docker): random legal moves 0.00 - 0.03; always the first legal move 0.00; win in 1 if seen, otherwise random 0.06; rules-only search at 2 s per move 0.25 - 0.31.

`python tools/analyze.py <job folder>` writes this report for any run: for every lost puzzle the position, the move played, the solver's verdict on it, and the move that would have kept the win.

### A harness limit we found and removed

In our first no-code runs most sessions ended after 4 to 8 puzzles with 21 to 28 puzzles never attempted. The cause was not the game: OpenCode caps one model turn at 32,000 output tokens, and a model that reasons through a long line in a single turn is cut off (`step_finish reason=length`), which ends `opencode run`. We raised the cap to 64,000 in the task image (`OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX`, `task/environment/Dockerfile`), and the instruction now states the limit plainly and tells the agent to think one move at a time. The results above are with the fix.

## Run it

Needs Harbor (`uv tool install harbor`, or `uv tool install "harbor[modal]"` for Modal) and Docker, or Modal with `-e modal`.

```bash
# everything: references, baselines and 3 agent runs, one table at the end
export GEMINI_API_KEY=...            # or OPENAI_API_KEY / ANTHROPIC_API_KEY
python scripts/evaluate.py --model google/gemini-4-carbon [--env modal]

# references and baselines only, no API key needed
python scripts/evaluate.py [--env modal]
```

Or straight through Harbor:

```bash
harbor run -p task -a oracle                              # perfect play, 1.000
harbor run -p task -a oracle --ae SOLUTION=search         # rules-only search reference
harbor run -p task -a nop                                 # do nothing, 0.000
harbor run -p task -a oracle --ae STOP_AFTER=4            # stop early, 0.125
harbor run -p task -a opencode -m <provider>/<model>      # an agent
THINICE_SEED=7 harbor run -p task -a oracle               # another draw of 32 puzzles from the pool
```

## Why the reward cannot be gamed

The reward is the number of puzzles won against a perfect opponent, so the only way to raise it is to play winning moves.

| attack | what stops it |
|---|---|
| Do nothing, or stop early | 0 for nothing; 1/32 per puzzle actually won |
| Guess | A puzzle dies on the first non-winning move. Random play scores 0.00 - 0.03; "take a win in 1 if you see it, otherwise random" 0.06 |
| Retry, undo, reset | Not in the API. State lives in the game server and only moves forward |
| Write a program anyway | Shell, file editing, web fetch and web search are denied by a root-owned OpenCode config (`/etc/opencode/opencode.json`) the agent user cannot change; subagents inherit the same denials |
| Use `save_note` for something else | A note is the agent's own text, kept in the game server's memory for that run only and shown back by `show_puzzle`. The server never reads it, it is not on the score sheet, and it is capped (4,000 characters, 100 per puzzle, 2,000 in total). It gives the agent nothing it could not already write in its own reply; it only lets a long analysis span several turns |
| Read the answers | Puzzles, opponent and solutions live in a separate container. The agent's container holds none of the game's code or data |
| Learn the scored puzzles in practice | All published puzzles, scored and practice, are mutually disjoint: no position reachable in one occurs in any other, up to rotation and reflection. The build fails if two share a position |
| Edit the score | The verifier reads one file: a score sheet written and HMAC-signed by the game server, mounted read-only into the agent's container. The key never exists in the agent's sandbox |
| Tamper with the grader | Verification runs in a separate container that the agent never touches. The agent itself is not root |
| Break the verifier's input | A missing, malformed or mis-signed score sheet scores 0 |

`python tools/redteam.py <server url>` runs the attack suite against a live game server.

## Post-training: does a small model get better?

Yes, to the level of the frontier models. `training/` fine-tunes Qwen3 (LoRA, on Modal) on what practice mode hands out: a position and the move that wins it, generated at scale by the solver. It is evaluated by playing a separate puzzle pool, which is removed from the training data together with all its rotations and reflections, with the same prompt before and after.

| model | before | after | legal moves before → after | after, by tier (win in 1 / 2 / 3 / 4) |
|---|---|---|---|---|
| Qwen3-0.6B (600k examples) | 0.001 | **0.120** | 50% → 100% | 1.00 / 0.64 / 0.20 / 0.06 |
| Qwen3-1.7B (600k examples) | 0.001 | **0.119** | 93% → 100% | 0.98 / 0.58 / 0.28 / 0.06 |

A 0.6B model trained on the environment's own feedback reaches the score that frontier models reach by reasoning. Curves: `results/curve-qwen3-*-7x6.json`.

## How it was built

```
solver/     Rust. Solves the game, extracts sharp puzzles, and packs every position Blue
            can reach in each one with the verdict on every move and Red's reply.
thinice/    Python game core: rules, puzzle sessions, the rules-only search.
task/       The Harbor task: instruction, game server (MCP + HTTP), verifier, references.
tools/      build_task.py and modal_build.py regenerate task/ from the solver;
            analyze.py grades agent runs move by move; selfcheck.py scores scripted
            policies in-process; redteam.py attacks a live server.
training/   The post-training experiment.
scripts/    evaluate.py, the one-command reproduction.
```

The game server needs no rules engine and no tablebase at run time. It only walks the packs the solver wrote, so the server cannot disagree with the solver.

Earlier versions (5x5, and 7x6 with a shell) and their results are kept under `results/v1-5x5` and `results/v2-7x6`.
