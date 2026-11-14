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

12 puzzles, two per tier: a win in 1 move, in 2, ... up to a win in 6 moves (11 plies). Blue (the agent) is to move and has a forced win; Red is a perfect defender that always picks the longest defence. A puzzle ends the moment the agent plays a move that no longer wins. No undo, no retry. 150 minutes.

The agent **cannot run code**. With a shell it simply writes a search program and scores 1.000, which measures nothing. So the shell, file writing, subagents, web and skills are all denied (`task/environment/opencode-managed.json`). What it gets instead is the game's MCP server:

| tool | what it does |
|---|---|
| `rules`, `list_puzzles`, `show_puzzle` | the rules, the score sheet, a puzzle's board and legal moves |
| `play_move` | one real Blue move; Red replies at once |
| `new_practice_puzzle` | unscored puzzles that answer a wrong move with the winning one |
| `explore_position` | rules only: the board after any move sequence (both colours), whose turn it is, the legal moves, and each colour's moves that would make three in a row |
| `explore_lines` | the same for up to 40 sequences in one call, one row each |

The look-ahead tools apply the rules and nothing else. They never say whether a position is winning, what Red would reply or which move to play, and they never change a puzzle. So the agent has everything it needs to check a plan before committing to it, and the decisions that matter are its own: which candidate moves to examine, whether it really checked every Red defence before playing, when to stop exploring and commit.

**Score = puzzles won / 12.** One number between 0 and 1, written to `/logs/verifier/reward.txt`.

## Every puzzle is reachable with the agent's tools

`task/solution/toolplay.py` is a second reference that plays through **only the agent's interface**: the puzzle view, the look-ahead tool and `play_move`. It imports no game code, knows no rules of its own and reads no solver data; every legal move and every three in a row it uses comes back from a tool call. Its method is one a model can follow turn by turn:

1. If one of my moves makes three in a row, play it.
2. Otherwise look, in one `explore_lines` call, at the position after each of my moves: drop the moves after which Red can make three in a row, and rank the rest by how many three-in-a-row moves I then threaten.
3. For the best candidate, look at every Red reply in one call. Replies after which I make three in a row at once are no defence. Each real defence must again be beaten, with one move fewer (back to 1).
4. Moves that threaten nothing are tried only when two Blue moves are left.

The scored pool contains only puzzles this player wins within 50 tool calls (`python tools/size_task.py 6 50 --write`, deterministic). Per tier, over the whole pool:

| win in | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| puzzles in the scored pool | 30 | 30 | 30 | 19 | 13 | 3 |
| tool calls, median | 4 | 7 | 12 | 21 | 33 | 47 |
| tool calls, most | 4 | 11 | 45 | 51 | 57 | 48 |

A full run of 12 puzzles takes it 224 to 291 tool calls (8 seeds). The 150-minute limit allows 31 seconds per call at the worst of those, about twice the pace (14 to 17 s per call) of frontier agents measured on the no-code version of this task. Deeper tiers are left out because this player cannot reach them within that budget: from a win in 4 on, the solutions increasingly need quiet moves, where every Red reply is a real defence and the tree a tool-only player has to walk grows by about 25 per move.

## Results

| run | reward |
|---|---|
| Reference: perfect play (moves from the solver) | 1.000 |
| Reference: tools only (agent's own tools, no code, no solver data) | 1.000 |
| Baseline: stop early (wins the 4 easiest, then quits) | 0.333 |
| Baseline: do nothing | 0.000 |
| Frontier agents (OpenCode), 3 runs | see `results/` |

Scripted policies, 3 seeds each (`python tools/selfcheck.py`): random legal moves 0.00 - 0.08; always the first legal move 0.00; "take a win in 1 if you see it, otherwise random" 0.17.

A run that ends early (the agent stops, its turn hits the model's output limit, or the clock runs out) is scored like any other: puzzles won so far count, unfinished ones do not.

## Run it

Needs Harbor (`uv tool install harbor`) and Docker or Modal.

```bash
harbor run -p task -a oracle                              # perfect play, 1.000
harbor run -p task -a oracle --ae SOLUTION=tools          # tools-only reference, 1.000
harbor run -p task -a nop                                 # do nothing, 0.000
harbor run -p task -a oracle --ae STOP_AFTER=4            # stop early, 0.333
harbor run -p task -a opencode -m <provider>/<model>      # an agent
THINICE_SEED=7 harbor run -p task -a oracle               # another draw of 12 puzzles from the pool
```

Add `-e modal` to run on Modal instead of local Docker. `python scripts/evaluate.py [--env modal] [--model <provider>/<model>]` runs the references, baselines and optionally 3 agent runs in one go.

## Why the reward cannot be gamed

The reward is the number of puzzles won against a perfect opponent, so the only way to raise it is to play winning moves.

| attack | what stops it |
|---|---|
| Do nothing, or stop early | 0 for nothing; 1/12 per puzzle actually won |
| Guess | A puzzle dies on the first non-winning move. Random play scores 0.00 - 0.08 |
| Retry, undo, reset | Not in the API. State lives in the game server and only moves forward |
| Ask the look-ahead tools for the answer | They are a pure function of position and moves, computed from the rules alone; the selfcheck gives the same answers with the solver data deleted. The winning move and the losing ones answer in the same shape |
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
