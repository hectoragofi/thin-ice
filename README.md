# Thin Ice

A reinforcement learning environment for **planning several moves ahead against an opponent**: finding a move that works against every reply, by the agent's own reasoning, in a system it has never seen.

**Why this setting.** The game is invented, so nothing can be recalled from training data, and it is solved exhaustively, so every single move has an exact verdict. **What an agent learns here, in order** (the post-training curve below shows each step): the rules (legal moves 50% → 100% within the first 1,024 training examples), then immediate wins (win in 1: 0.02 → 1.00), then forced sequences (win in 2: 0.64, win in 3: 0.20), and, under the clock, when to stop thinking and commit.

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

**12 puzzles in 6 tiers**, two per tier: a win in 1 move, in 2, ... up to a win in 6. In each, Blue (the agent) is to move and has a forced win; Red is played by a perfect opponent that always picks the longest defence. The agent may use N+1 moves on a win in N. A puzzle is lost the moment the agent plays a move after which the win is no longer forced. There is no undo and no retry.

- **One puzzle at a time, in order.** Only the current puzzle can be viewed or played; the next unlocks when it is won, lost or given up (`skip_puzzle`, counts as lost).
- **A clock per puzzle:** 2 minutes per move of its forced win (a win in 3 gets 6 minutes), from the first look at it. When it runs out the puzzle is lost and the next one unlocks. Every tool reply shows the time left. The clocks add up to 84 minutes and the run has 90, so every puzzle is reached.
- **No code.** The agent talks to the game over MCP (`rules`, `list_puzzles`, `show_puzzle`, `play_move`, `save_note`, `skip_puzzle`, `new_practice_puzzle`). It has no shell, no file writing and no way to run code: it has to find each move by thinking it through. `save_note` keeps its own half-finished analysis between turns.
- **Practice** is unlimited and never counts: fresh puzzles that answer a wrong move with the move that would have won.

**Score = puzzles won / 12.** One number between 0 and 1, written to `/logs/verifier/reward.txt`.

| | |
|---|---|
| **Actions** | 7 game tools: `play_move`, `show_puzzle`, `list_puzzles`, `save_note`, `skip_puzzle`, `new_practice_puzzle`, `rules` |
| **Observations** | the board, legal moves, the win depth, moves and time left on the puzzle and the run, Red's reply, the result; in practice, the move that would have won |
| **Reward** | puzzles won / 12, read only from the game server's HMAC-signed score sheet |

## Why no code

We built this environment several times, and each version taught us what it should measure.

| version | what happened |
|---|---|
| 5x5 board, agent has a shell | Gemini 4 Carbon writes its own look-ahead search and scores **1.000**. |
| 7x6 board, agent has a shell | Same: it writes a search, **1.000**. The board size does not matter to a program. |
| Rules-only look-ahead offered as a tool, no shell | Every model scores about **1.0**: it checks every branch with the tool until it is certain. |
| Same tool with a look-ahead budget | Gemini 4 Argon wins all 10 puzzles using ~1,100 explored positions, fewer than our own selective reference needs (3,096). No budget leaves a gap above the strongest model. |
| **No code, no look-ahead tool (this task)** | Planning has to happen in the model's own reasoning. This is where frontier models fall through. |

So the environment measures one thing on purpose: **how far ahead a model can plan without a program doing the planning for it.** Writing a search is a solved skill; holding a 5-move forced line in your head, with every Red defence answered, is not. The organisers confirmed that removing code execution is a legitimate setting ("if code solves it then remove its ability to write code, just tools").

## The decisions that matter

Everything the agent needs is in front of it: the complete rules, a board view, unlimited practice with ground-truth feedback, notes, and a clock it can see. What it has to decide:

- **Which moves to consider.** In a deep puzzle only one move of ~20 keeps the win. The winning move is often quiet (no immediate threat), and the natural attacking move loses.
- **Which Red defences to answer.** A forced win means every Red reply is answered. The usual mistake is to check the reply you expect and miss the one that refutes you.
- **When a line is settled enough to play.** There is no undo, so playing on a hunch costs the puzzle; thinking past the clock costs it too.
- **How much to think, and in what steps.** A long analysis has to be spread over turns with notes; one reply that runs past the model's output limit ends the session.

## Results

Every row is a Harbor run on Modal (`-e modal`) at commit 24d6707, reproducible with the command in the next section. Frontier agents: OpenCode with Gemini 4, 3 runs each, 90 minutes.

| run | reward |
|---|---|
| Reference: perfect play (moves from the solver) | **1.000** |
| Reference: rules-only search, 20 s per puzzle (60 lines of Python that know only the rules) | **0.917** |
| Gemini 4 Argon, 3 runs | RESULT_ARGON |
| Gemini 4 Carbon, 3 runs | RESULT_CARBON |
| Gemini 4 Hydrogen, 3 runs | RESULT_HYDROGEN |
| Baseline: stop early (wins the 2 easiest, then quits) | 0.167 |
| Baseline: do nothing | 0.000 |

Scripted policies, 3 seeds each, in-process (`python tools/selfcheck.py`, no Docker): random legal moves 0.00 - 0.08; always the first legal move 0.00; win in 1 if seen, otherwise random 0.17; rules-only search at 2 s per move 0.67 - 0.83.

### Where the agents go wrong

MISTAKE_TABLE

`python tools/mistakes.py <job folders>` builds this table; `python tools/analyze.py <job folder>` writes, for every lost puzzle, the position, the move played, the solver's verdict on it and the move that would have kept the win.

### The horizon, measured a second way

`tools/probe.py` (the idea: separate "find the next move" from "manage a whole session") asks a model for **one move per fresh API call**: the rules and one position, no tools, no history, no clock. Puzzles from a held-out pool are played to the end against the perfect defender and every move is graded by the solver. 10 puzzles per tier.

| win in | 1 | 2 | 3 | 4 | 5 | 6 | mean (= task scale) |
|---|---|---|---|---|---|---|---|
| Gemini 4 Argon | 1.00 | 0.80 | 0.40 | 0.10 | 0.10 | 0.00 | **0.400** |
| Gemini 4 Hydrogen | 1.00 | 1.00 | 0.60 | 0.30 | 0.00 | 0.00 | **0.483** |
| Gemini 4 Carbon | 1.00 | 1.00 | 0.90 | 0.10 | 0.10 | 0.00 | **0.517** |
| Random legal moves | | | | | | | 0.007 |

Puzzles solved per tier. Removing the session does not remove the difficulty: the first move of a win in N still needs the full N-deep look-ahead. Two opposite failures show up:

- **Argon answers fast and wrong.** Its median thinking is about 2,000 tokens at every depth from win in 3 on, and most of its first moves there are wrong (7 of 10 at win in 4, against about 5% chance).
- **Carbon and Hydrogen think until they run out.** From win in 4 on, most calls use the model's whole output limit (32,768 and 64,000 tokens) and end without a move.

Neither matches its effort to the position. All three have a horizon of about 3 moves.

### Does the reward encourage the behaviour we intended?

Not at first, and the logs showed it. The first no-code version let a model think until its session died, and let it open six puzzles and try to solve them in one reply. Neither was intended. The fixes below changed the environment, not the model; the shortcuts were checked too:

| shortcut | score |
|---|---|
| Do nothing | 0.000 |
| Random legal moves | 0.007 (probe pool), 0.00 - 0.08 (task) |
| Stop early after the 2 easiest | 0.167 |
| Notes as a side channel, peeking ahead, beating the clock | refused, see the attack table; every note we read is real elimination analysis |

### Harness limits we found and removed

Our first no-code runs ended after 5 to 15 minutes with most puzzles never reached, and the cause was not the game. `opencode run` ends a session as soon as a reply carries no tool call, and a model that reasons through a long line in one reply hits its output limit (32,768 tokens for Argon and Carbon, a hard API limit) and is cut off mid-thought: 6 of 9 sessions ended this way. Models also opened several puzzles and tried to solve them all in one reply. Three changes, none of which touches the model's own settings:

1. **`save_note`** gives the agent a game action that keeps a half-finished analysis, so a long line can span many turns.
2. **One puzzle at a time** stops a reply from holding several puzzles' analysis.
3. **A per-puzzle clock** stops one puzzle from eating the run, so every puzzle is reached.

With notes, cut-off sessions fell from 6 of 9 to 1 of 7 (Hydrogen, once, on a win in 5 after 20 minutes of paced play). Agents use notes as intended: worked lines and refutation lists, e.g. *"1.c1-a1 stops 1...c3-c2# AND threatens 2.c5-a3#"* (correct: it is the only winning move). We also raised OpenCode's own output cap to 64,000 in the task image, which only matters for Hydrogen.

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
harbor run -p task -a oracle --ae STOP_AFTER=2            # stop early, 0.167
harbor run -p task -a opencode -m <provider>/<model>      # an agent
THINICE_SEED=7 harbor run -p task -a oracle               # another draw of 12 puzzles from the pool
```

`uvx --with modal python tools/live_modal.py --log 3` shows every running trial on Modal: score so far, puzzles, notes, longest thought and the model's latest reasoning.

## Why the reward cannot be gamed

The reward is the number of puzzles won against a perfect opponent, so the only way to raise it is to play winning moves.

| attack | what stops it |
|---|---|
| Do nothing, or stop early | 0 for nothing; 1/12 per puzzle actually won |
| Guess | A puzzle dies on the first non-winning move. Random play scores 0.00 - 0.08 |
| Retry, undo, reset | Not in the API. State lives in the game server and only moves forward |
| Write a program anyway | Shell, file editing, web fetch and web search are denied by a root-owned OpenCode config (`/etc/opencode/opencode.json`) the agent user cannot change; subagents inherit the same denials |
| Use `save_note` for something else | A note is the agent's own text, kept in the game server's memory for that run only and shown back by `show_puzzle`. The server never reads it, it is not on the score sheet, and it is capped (4,000 characters, 100 per puzzle, 2,000 in total). It only lets a long analysis span several turns |
| Peek at or play ahead on later puzzles | Locked until the current puzzle is won, lost or skipped; viewing or moving on a locked puzzle is refused, under any spelling of its id. A skip counts as lost and cannot be undone |
| Beat the clock | A move after the puzzle's clock is refused and the puzzle is lost. The clock is server time, starts at the first look and cannot be restarted by re-reading, practising, skipping or another spelling of the id |
| Read the answers | Puzzles, opponent and solutions live in a separate container. The agent's container holds none of the game's code or data |
| Learn the scored puzzles in practice | All published puzzles, scored and practice, are mutually disjoint: no position reachable in one occurs in any other, up to rotation and reflection. The build fails if two share a position |
| Edit the score | The verifier reads one file: a score sheet written and HMAC-signed by the game server, mounted read-only into the agent's container. The key never exists in the agent's sandbox. The key file is in this repo (`task/environment/game-server/receipt.key`, `task/tests/receipt.key`) because the game server and verifier need it; the agent has no web access, so it cannot read it during a run |
| Tamper with the grader | Verification runs in a separate container that the agent never touches. The agent itself is not root |
| Break the verifier's input | A missing, malformed or mis-signed score sheet scores 0 |

`python tools/redteam.py <server url>` runs the attack suite against a live game server: 96 checks, all passing, including the puzzle lock and `skip_puzzle`; `--clock` adds 13 attacks on the clock (late winning moves under three id spellings, skip after expiry, re-looking, practice), all refused. The note tool was attacked through a real MCP client (locked puzzles, oversized notes, a fake score written into a note, the caps): the score and the signed receipt never change. In every agent run we read, notes contain only game analysis and no agent touched a non-game tool.

## Post-training: does a small model get better?

Yes, from nothing to the frontier models' range. `training/` fine-tunes Qwen3 (LoRA, on Modal) on the feedback the environment's practice mode gives: a position and the move that wins it, generated at scale by the solver. This is imitation of the solver's winning moves, the same information practice mode returns after a wrong move; it is not trial-and-error on the reward. It is evaluated with the same rollout as the probe above, on a held-out pool removed from the training data together with all its rotations and reflections, with the same prompt before and after.

| model | before | after 600k examples | legal moves | after, by tier (win in 1 / 2 / 3 / 4 / 5 / 6) |
|---|---|---|---|---|
| Qwen3-0.6B | 0.003 | **0.320** | 50% → 100% | 1.00 / 0.64 / 0.20 / 0.06 / 0.00 / 0.02 |
| Qwen3-1.7B | 0.003 | **0.317** | 93% → 100% | 0.98 / 0.58 / 0.28 / 0.06 / 0.00 / 0.00 |

Scores are the mean over win in 1 to 6, the task's scale. The 0.6B curve is still rising at the end (0.293 at 400k examples). A 0.6B model trained on the environment's own feedback reaches 0.32 against the frontier models' 0.40 - 0.52 in the same one-move-per-call setting. Qwen was scored on 50 puzzles per tier, the Gemini probes on 10 per tier from the same pool. Curves: `results/curve-qwen3-*-7x6.json`; probes: `results/probe/`.

## How it was built

```
solver/     Rust. Solves the game, extracts sharp puzzles, and packs every position Blue
            can reach in each one with the verdict on every move and Red's reply.
thinice/    Python game core: rules, puzzle sessions and clocks, the rules-only search.
task/       The Harbor task: instruction, game server (MCP + HTTP), verifier, references.
tools/      build_task.py and modal_build.py regenerate task/ from the solver;
            analyze.py and mistakes.py grade agent runs move by move; probe.py is the
            one-move-per-call probe; selfcheck.py scores scripted policies in-process;
            redteam.py attacks a live server; live_modal.py watches running trials.
training/   The post-training experiment.
scripts/    evaluate.py, the one-command reproduction.
```

The game server needs no rules engine and no tablebase at run time. It only walks the packs the solver wrote, so the server cannot disagree with the solver.

Earlier versions (5x5, and 7x6 with a shell) and their results are kept under `results/v1-5x5` and `results/v2-7x6`.
