# Thin Ice

A reinforcement learning environment that measures how well an agent can plan by reasoning, with tools but without code, in a system it has never seen.

Thin Ice is a small board game we invented for this challenge and then **solved completely** by exhaustive retrograde analysis. Because the game is solved, every move an agent makes is provably right or wrong. There is no judge model, no heuristic and no partial-credit guesswork anywhere in the reward.

Built for AfterQuery's "Break the Agent" challenge at Junction 2026. It is a standard [Harbor](https://github.com/laude-institute/harbor) task.

```
6 . . . . . B .        Blue to move and win in 3.
5 . . R . . R B
4 . . . . . . .        16 legal moves.
3 . . . . . B .        One keeps the win.
2 R . . . . . .
1 B . . R . . .
  a b c d e f g
```

## The game

- 7x6 board. Blue has 4 stones, Red has 4. Players alternate, one stone per turn.
- A stone slides in one of 8 directions and cannot stop early: it stops on the last empty cell before the edge or before another stone.
- First to get 3 of their stones in a row wins. A player who cannot move loses.

## What the agent has to do

10 puzzles: one win in 2, one in 3, then two each of a win in 4, 5, 6 and 7 moves (up to 13 plies). Blue (the agent) is to move and has a forced win; Red is a perfect defender that always picks the longest defence. A puzzle ends the moment the agent plays a move that no longer wins. No undo, no retry. 150 minutes.

The agent **cannot run code**. With a shell it simply writes a search program and scores 1.000, which measures nothing. So the shell, file writing, subagents, web and skills are all denied (`task/environment/opencode-managed.json`). What it gets instead is the game's MCP server:

| tool | what it does |
|---|---|
| `rules`, `list_puzzles`, `show_puzzle` | the rules, the score sheet and remaining budget, a puzzle's board and legal moves |
| `play_move` | one real Blue move; Red replies at once |
| `new_practice_puzzle` | unscored puzzles that answer a wrong move with the winning one |
| `explore_position` | rules only: the board after any move sequence (both colours), whose turn it is, the legal moves, and each colour's moves that would make three in a row. Costs 1 |
| `explore_lines` | the same for up to 40 sequences in one call, one row each. Costs 1 per line |

The look-ahead tools apply the rules and nothing else. They never say whether a position is winning, what Red would reply or which move to play, and they never change a puzzle.

**Looking ahead costs.** The run has a budget of 4000 explored positions, shared by every puzzle (practice too), stated in the instruction and shown in every answer. With free look-ahead, a frontier model simply checks every branch until it is certain and wins everything (Gemini 4 Hydrogen: 12/12 on the unbudgeted version). With a budget, the decisions that matter are the agent's own: which candidate moves are worth a look, which Red defences really need answering, when a line is settled enough to play, and how much budget each puzzle deserves. Exploring everything still wins the early puzzles; it runs dry before the deep ones.

**Score = puzzles won / 10.** One number between 0 and 1, written to `/logs/verifier/reward.txt`.

## The budget is enough for a selective player

`task/solution/toolplay.py` is a second reference that plays through **only the agent's interface**: the puzzle view, the look-ahead tool and `play_move`, paying for every explored position from the same budget. It imports no game code, knows no rules of its own and reads no solver data; every legal move and every three in a row it uses comes back from a tool call. Its method is one a model can follow turn by turn:

1. If one of my moves makes three in a row, play it.
2. Otherwise look, in one `explore_lines` call, at the position after each of my moves: drop the moves after which Red can make three in a row, and keep the ones that threaten three in a row (quiet moves only when two moves are left).
3. Check every candidate one move deep: look at every Red reply in one call; a reply after which I make three in a row at once is no defence; the rest are real defences, and each needs a threatening answer.
4. Check only the survivors one move deeper. As soon as one candidate is left, play it, see Red's actual reply, and start again from there. Nothing explored is paid for twice.
5. Easiest puzzles first, with an allowance per depth; a puzzle that would cost more is left open rather than lost.

The scored pool holds only puzzles this player wins within its allowance (`python tools/size_task.py write ...`, deterministic; the command is recorded in the manifest). For comparison, the **exhaustive** player is the same code proving every Red branch before each first move (`SOLUTION=exhaustive`), which is what a model does when look-ahead is free. 10 seeds each, in-process (`tools/selfcheck.py` drives the same functions as the server):

| budget | selective: score | selective: positions used (mean / max) | exhaustive: score (mean, min-max) |
|---|---|---|---|
| 1500 | 0.63 | 1495 / 1500 | 0.53 (0.3-0.6) |
| 2000 | 0.76 | 1995 / 2000 | 0.59 (0.5-0.7) |
| 2500 | 0.84 | 2491 / 2500 | 0.65 (0.6-0.7) |
| 3000 | 0.92 | 2974 / 3000 | 0.68 (0.6-0.8) |
| 3500 | 1.00 | 3096 / 3263 | 0.74 (0.6-0.9) |
| **4000 (default)** | **1.00** | **3096 / 3263** | **0.76 (0.7-0.9)** |
| 4500 | 1.00 | 3096 / 3263 | 0.82 (0.7-1.0) |
| unlimited | 1.00 | 3096 / 3263 | 0.94 (uses 5422 / 6672) |

At the default the exhaustive player wins every win in 2 to 5, 14 of 20 wins in 6 and 2 of 20 wins in 7. A model that explores exhaustively but never misplays should land near 0.76; wrong moves at depth 5 and beyond (seen in every frontier run so far) push it lower.

Selective cost per puzzle, over the scored pool: win in 2: median 46 positions (max 143); 3: 84 (273); 4: 230 (416); 5: 273 (501); 6: 377 (543); 7: 548 (622).

**Deeper tiers.** Win in 8 is available as a dial: `THINICE_TOP_DEPTH=8` adds one win-in-8 puzzle (11 in total; the pool has only one such puzzle the selective player wins, so every seed gets the same one). With top depth 8 the selective player still scores 1.000 at a budget of 4000 (mean 3638, max 3805 used) and the exhaustive one 0.69; a budget of 4600 gives more slack (exhaustive 0.75). Win in 9 and 10 stay out: their solutions are mostly quiet moves, where every Red reply is a real defence, and no tools-only method we tried wins them within any reasonable budget.

## Results

| run | reward |
|---|---|
| Reference: perfect play (moves from the solver) | 1.000 |
| Reference: tools only, selective, inside the budget | 1.000 |
| Tools only, exhaustive habit, inside the budget | 0.76 (in-process, 10 seeds) |
| Baseline: stop early (wins the 4 easiest, then quits) | 0.400 |
| Baseline: do nothing | 0.000 |
| Frontier agents (OpenCode), 3 runs | see `results/` |

Scripted policies, 3 seeds each (`python tools/selfcheck.py`): random legal moves and always the first legal move 0.00.

A run that ends early (the agent stops, its turn hits the model's output limit, or the clock runs out) is scored like any other: puzzles won so far count, unfinished ones do not. Running out of look-ahead budget ends nothing: the agent can still play.

## Run it

Needs Harbor (`uv tool install harbor`) and Docker or Modal.

```bash
harbor run -p task -a oracle                              # perfect play, 1.000
harbor run -p task -a oracle --ae SOLUTION=tools          # selective tools-only reference, 1.000
harbor run -p task -a oracle --ae SOLUTION=exhaustive     # exhaustive habit inside the budget
harbor run -p task -a nop                                 # do nothing, 0.000
harbor run -p task -a oracle --ae STOP_AFTER=4            # stop early, 0.400
harbor run -p task -a opencode -m <provider>/<model>      # an agent
THINICE_SEED=7 harbor run -p task -a oracle               # another draw of puzzles from the pool
THINICE_EXPLORE_BUDGET=3000 harbor run ...                # dial: look-ahead budget (empty = 4000, "unlimited" = off)
THINICE_TOP_DEPTH=8 harbor run ...                        # dial: deepest tier (empty = 7)
```

The dials are read by the game server, written on the signed score sheet and copied to the verifier's `details.json` (`settings`, `explore_budget`, `explore_used`). Add `-e modal` to run on Modal instead of local Docker. `python scripts/evaluate.py [--env modal] [--model <provider>/<model>]` runs the references, baselines and optionally 3 agent runs in one go.

## Why the reward cannot be gamed

The reward is the number of puzzles won against a perfect opponent, so the only way to raise it is to play winning moves.

| attack | what stops it |
|---|---|
| Do nothing, or stop early | 0 for nothing; 1/10 per puzzle actually won |
| Guess | A puzzle dies on the first non-winning move. Random play scores 0.00 - 0.08 |
| Retry, undo, reset | Not in the API. State lives in the game server and only moves forward |
| Ask the look-ahead tools for the answer | They are a pure function of position and moves, computed from the rules alone; the selfcheck gives the same answers with the solver data deleted. The winning move and the losing ones answer in the same shape |
| Get more look-ahead budget | One counter for the whole run, charged under the game's lock before any answer is computed; practice puzzles pay too; no endpoint resets it; oversized or racing requests are refused whole. The red-team suite tries all of this |
| Use the look-ahead tools to change a puzzle | They read a snapshot and write nothing; the red-team suite explores thousands of lines and checks every puzzle and the score are unchanged. Finished puzzles cannot be explored |
| Write a program anyway | No shell, no file writing, no subagents (which would inherit the same denials anyway), no web. Root-owned managed config the agent user cannot change |
| Read the answers | Puzzles, opponent and solutions live in a separate container. The agent's container holds none of the game's code or data |
| Learn the scored puzzles in practice | All published puzzles, scored and practice, are mutually disjoint: no position reachable in one occurs in any other, up to rotation and reflection |
| Edit the score | The verifier reads one file: a score sheet written and HMAC-signed by the game server, mounted read-only. The key never exists in the agent's sandbox |
| Tamper with the grader | Verification runs in a separate container that the agent never touches. The agent itself is not root |

`python tools/redteam.py <server url>` runs the attack suite against a live game server.

## Post-training: does a small model get better?

See `training/` and `results/`. A small open model (Qwen3-0.6B, LoRA) is trained on what practice mode hands out, a position and the move that wins it, generated at scale by the solver, and evaluated on a separate pool that is removed from the training data together with all its rotations and reflections.

## How it was built

```
solver/     Rust. Solves the game, extracts sharp puzzles, and packs every position Blue can
            reach in each one with the verdict on every move and Red's reply.
thinice/    Python game core: rules, puzzle sessions, the rules-only look-ahead tools.
task/       The Harbor task: instruction, game server (MCP + HTTP), verifier, references.
tools/      build_task.py regenerates task/ from the solver; size_task.py cuts the scored pool
            to what the tools-only reference wins; selfcheck.py and redteam.py check it.
training/   The post-training experiment.
scripts/    evaluate.py, the one-command reproduction.
```

The game server needs no tablebase at run time. Play walks the packs the solver wrote, so the server cannot disagree with the solver; look-ahead uses the rules module and never touches the packs.
