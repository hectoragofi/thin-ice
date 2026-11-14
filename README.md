# Thin Ice

A reinforcement learning environment that measures how many moves ahead an agent can plan in a system it has never seen.

Thin Ice is a small board game we invented for this challenge and then **solved completely**: all 151,420,500 positions, by exhaustive retrograde analysis. Because the game is solved, every move an agent makes is provably right or wrong. There is no judge model, no heuristic and no partial-credit guesswork anywhere in the reward.

Built for AfterQuery's "Break the Agent" challenge at Junction 2026. It is a standard [Harbor](https://github.com/laude-institute/harbor) task.

```
5 . . . B .        Blue to move and win in 3.
4 R . . R .
3 . . . R .        16 legal moves.
2 . B . . .         1 keeps the win.
1 B . R B .        15 lose the game.
  a b c d e
```

## The game

- 5x5 board. Blue has 4 stones, Red has 4. Players alternate, one stone per turn.
- A stone slides in one of 8 directions and cannot stop early: it stops on the last empty cell before the edge or before another stone.
- First to get 3 of their stones in a row wins. A player who cannot move loses.

That is the whole rulebook. It fits in a paragraph, and yet forced wins run up to 41 plies deep, almost no position is a draw (0.2%), and in a typical puzzle exactly one move wins while every other move loses outright. One slip and you fall through, hence the name.

## What the agent has to do

24 puzzles. In each, Blue (the agent) is to move and has a forced win; Red is played by a perfect opponent that always chooses the longest defence. The puzzles come in 12 tiers, two per tier: a win in 1 move, in 2, ... up to a win in 12 moves (23 plies).

The agent talks to the game over MCP (`list_puzzles`, `show_puzzle`, `play_move`, `new_practice_puzzle`, `rules`), or through the `ice` command or plain HTTP if it prefers to script. A puzzle ends the moment the agent plays a move that no longer wins. No undo, no retry. Thirty minutes in total.

It also gets an unlimited-feedback **practice mode**: fresh puzzles that never count and that answer a wrong move with the move that would have won. Everything needed to get better is on the table: the full rules, Python, and a way to test your own understanding against ground truth.

**Score = puzzles won / 24.** One number between 0 and 1, written to `/logs/verifier/reward.txt`.

## Why it is hard

The score spans three different abilities, and the tiers separate them cleanly.

| tiers (win in N moves) | what it takes | who gets there |
|---|---|---|
| 1 - 2 | read the rules, simulate a slide, see one reply ahead | careful reasoning in context |
| 3 - 7 | look ahead 5 to 13 plies without a single slip | only with a tool: a look-ahead search the agent writes itself |
| 8 - 12 | 15 to 23 plies | beyond a quick search (cost grows about 20x per extra move); needs a much better search, or real skill at the game |

We ship that tool as a second reference, so the claim is checkable: `task/solution/thinice/search.py` is 60 lines of plain Python that knows only the rules. It solves every puzzle up to a win in 7 and none beyond, in 20 seconds per puzzle.

So the decisions that matter are real ones: whether to play by feel or build a tool; whether to check that tool against practice mode before trusting it with a one-shot puzzle; how to spend 30 minutes across 24 puzzles of rising difficulty.

## Results

Every row below is a real Harbor run and is reproduced by the one command in the next section.

| run | reward |
|---|---|
| Reference: perfect play (moves from the solver) | **1.000** |
| Reference: rules-only search, 20 s per puzzle | 0.583 |
| Baseline: stop early (wins the 4 easiest, then quits) | 0.167 |
| Baseline: do nothing | 0.000 |
| Frontier agent (OpenCode), 3 runs | see `results/` |

Scripted policies, 3 seeds each (`python tools/selfcheck.py`): random legal moves 0.00 - 0.04; always the first legal move 0.00 - 0.04; "take a win in 1 if you see it, otherwise random" 0.08 - 0.13.

## Run it

Needs Docker and Harbor (`uv tool install harbor`).

```bash
# references and baselines, no API key needed
python scripts/evaluate.py

# everything, including 3 agent runs
export OPENAI_API_KEY=...            # or GEMINI_API_KEY / ANTHROPIC_API_KEY
python scripts/evaluate.py --model <provider>/<model>
```

Or straight through Harbor:

```bash
harbor run -p task -a oracle                              # reference, 1.000
harbor run -p task -a oracle --ae SOLUTION=search         # rules-only reference
harbor run -p task -a nop                                 # do nothing, 0.000
harbor run -p task -a oracle --ae STOP_AFTER=4            # stop early
harbor run -p task -a opencode -m <provider>/<model>      # an agent
THINICE_SEED=7 harbor run -p task -a oracle               # another draw of 24 puzzles from the pool
```

## Why the reward cannot be gamed

The reward is the number of puzzles won against a perfect opponent, so the only way to raise it is to play winning moves. The rest is plumbing that keeps it that way.

| attack | what stops it |
|---|---|
| Do nothing, or stop early | 0 for nothing; 1/24 per puzzle actually won |
| Guess | A puzzle dies on the first non-winning move. Random play scores 0.00 - 0.04 |
| Retry, undo, reset | Not in the API. State lives in the game server and only moves forward |
| Read the answers | Puzzles, opponent and solutions live in a separate container. The agent's container holds none of the game's code or data |
| Learn the scored puzzles in practice, or copy one scored puzzle's line into another | All published puzzles, scored and practice, are mutually disjoint: no position reachable in one occurs in any other, up to rotation and reflection. The build fails if two share a position |
| Edit the score | The verifier reads one file: a score sheet written and HMAC-signed by the game server, mounted read-only into the agent's container. The key never exists in the agent's sandbox |
| Tamper with the grader | Verification runs in a separate container that the agent never touches. The agent itself is not root |
| Break the verifier's input | Missing, malformed or mis-signed score sheet scores 0 |

`harbor lint task --select ALL` passes with no findings.

## Post-training: does a small model get better?

Yes. See `training/` and `results/`. A small open model (Qwen3-0.6B, LoRA, one laptop GPU) is trained on what practice mode hands out, a position and the move that wins it, generated at scale by the solver. It is evaluated by playing the scored puzzle pool, which is removed from the training data together with all its rotations and reflections, with the same prompt before and after.

Untrained, it scores 0.008 and produces a legal move only half the time. The curve after training is in `results/`.

## How it was built

```
solver/     Rust. Solves the game (151M positions, under a minute on 16 threads), extracts
            sharp puzzles, and packs every position Blue can reach in each one with the
            verdict on every move and Red's reply.
thinice/    Python game core: rules, puzzle sessions, the rules-only search.
task/       The Harbor task: instruction, game server (MCP + HTTP), verifier, references.
tools/      build_task.py regenerates everything in task/ from the solver.
            selfcheck.py scores baseline policies in-process, no Docker needed.
training/   The post-training experiment.
scripts/    evaluate.py, the one-command reproduction.
```

The game server needs no rules engine and no tablebase at run time. It only walks the packs the solver wrote, so the server cannot disagree with the solver, and the whole task ships in 5 MB.

Fresh, never-published puzzles are one command away: `python tools/build_task.py <any number>` draws new pools from the 50 million won positions.

### A finding about the game itself

Making the puzzles disjoint turned up something we did not expect. Sliding moves merge positions (a stone that stops on c3 may have come from anywhere along the line), so long forced wins funnel into shared lines. The game has 10,884 positions that are a win in 12, yet they run along only a handful of independent lines. An early build let a practice puzzle and a scored puzzle share a position in 156 of 240 cases; the build now refuses to ship that.

The pools are therefore large where the game is wide and small where it is narrow. Scored + practice puzzles per tier:

| win in | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scored | 30 | 30 | 30 | 30 | 30 | 22 | 24 | 17 | 10 | 5 | 4 | 3 |
| practice | 20 | 20 | 20 | 20 | 19 | 7 | 8 | 6 | 3 | 2 | 1 | 1 |

A run draws 2 scored puzzles per tier; `THINICE_SEED` chooses which.
