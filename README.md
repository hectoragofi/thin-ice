# Thin Ice

A reinforcement learning environment for **planning several moves ahead against an opponent**: finding a move that works against every reply, by the agent's own reasoning, in a system it has never seen.

**Why this setting.** The game is invented, so nothing can be recalled from training data, and it is solved exhaustively, so every single move has an exact verdict. **What an agent learns here, in order** (the post-training curve below shows each step): the rules (legal moves 50% → 100% within the first 1,024 training examples), then immediate wins (win in 1: 0.02 → 1.00), then forced sequences (win in 2: 0.64, win in 3: 0.20), and, under the clock, when to stop thinking and commit.

**Every model has a planning horizon, the environment measures where it is, and you can move the horizon by adding depth.**

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

(A real position from a Gemini 4 Hydrogen run: the agent played c1-g5, which loses to a forced Red win in 2.)

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
| **No code, no look-ahead tool (this task)** | Planning has to happen in the model's own reasoning. This is where the Gemini 4 models fall through. |

So the environment measures one thing on purpose: **how far ahead a model can plan without a program doing the planning for it.** Writing a search is a solved skill; holding a 5-move forced line in your head, with every Red defence answered, is not. The organisers confirmed that removing code execution is a legitimate setting ("if code solves it then remove its ability to write code, just tools").

## The decisions that matter

Everything the agent needs is in front of it: the complete rules, a board view, unlimited practice with ground-truth feedback, notes, and a clock it can see. What it has to decide:

- **Which moves to consider.** In a deep puzzle only one move of ~20 keeps the win. The winning move is often quiet (no immediate threat), and the natural attacking move loses.
- **Which Red defences to answer.** A forced win means every Red reply is answered. The usual mistake is to check the reply you expect and miss the one that refutes you.
- **When a line is settled enough to play.** There is no undo, so playing on a hunch costs the puzzle; thinking past the clock costs it too.
- **How much to think, and in what steps.** A long analysis has to be spread over turns with notes; one reply that runs past the model's output limit ends the session.

## Results

Every model has a planning horizon, the environment measures where it is, and you can move the horizon by adding depth. The table measures the horizon on 12 puzzles from win in 1 to win in 6; the deep variant below adds win in 7 to 9.

Every row is a Harbor run on Modal (`-e modal`) at commit 24d6707, the same task for every model, reproducible with the command in the next section. Agents: stock OpenCode, 90 minutes per run. Gemini models ran in up to six sets of 3 (`jobs/final/clock-24d6707-<model>-x3`, `-x3b` ... `-x3f`); Claude models through the Anthropic API (`clock-24d6707-{opus55,fable52,haiku55,sonnet5}-*`); Nemotron through NVIDIA's OpenAI-compatible API (`nim-24d6707-nemotron3-ultra-*`). A run is left out only if it has no score sheet (3 Gemini runs whose sandbox was stopped when the local Harbor process was killed) or if an API error ended the session while a puzzle was still open (4 Argon runs, "Requests ending with a model turn are not supported"; and every Claude Sonnet 5.5 run, see below). No other run is left out.

| run | reward: mean (runs, range) |
|---|---|
| Reference: perfect play (moves from the solver) | **1.000** |
| Reference: rules-only search, 20 s per puzzle (80 lines of Python that know only the rules) | **0.917** |
| Claude Fable 5.2 | **0.750** (1 run) |
| Gemini 4 Carbon | **0.593** (17 runs, 0.417 - 0.667) |
| Gemini 4 Hydrogen | **0.537** (18 runs, 0.417 - 0.667) |
| Gemini 4 Argon | **0.536** (14 runs, 0.417 - 0.667) |
| Claude Opus 5.5 | **0.531** (8 runs, 0.417 - 0.833) |
| Claude Haiku 5.5 | **0.500** (3 runs, 0.500 - 0.500) |
| Gemini 3.8 Flash (older generation) | **0.441** (17 runs, 0.333 - 0.583) |
| Gemini 3.1 Pro (older generation) | **0.392** (17 runs, 0.333 - 0.583) |
| Claude Sonnet 5 | **0.389** (3 runs, 0.333 - 0.417) |
| Nemotron 3 Ultra | **0.194** (3 runs, 0.167 - 0.250) |
| Baseline: stop early (wins the 2 easiest, then quits) | 0.167 |
| Baseline: do nothing | 0.000 |

Standard error of the mean is 0.016 - 0.023 for the Gemini models (14 to 18 runs) and 0.047 for Opus (8 runs); models with 1 or 3 runs are indicative only (Fable 5.2 has one run, about $12.60 of API cost per run). Not measured: **Claude Sonnet 5.5** refused the unchanged instruction on its first call in all 4 sessions (provider refusal, category `reasoning_extraction`), so it has no score; **Mistral Large 4** through NVIDIA's API ran at about 9 tokens per second (14 turns in 85 minutes, one call over 10 minutes), too slow for the 2-minute move clock to be a fair run, so its 0.167 is not in the table. One Sonnet 5 run ended when a single reply hit the output limit (63,998 reasoning tokens) with 7 puzzles never reached; no API error, so it stays in.

Scripted policies, 3 seeds each, in-process (`python tools/selfcheck.py`, no Docker): random legal moves 0.00 - 0.08; always the first legal move 0.00; win in 1 if seen, otherwise random 0.17; rules-only search at 2 s per move 0.67 - 0.83.

### Where the agents go wrong

| model | runs | lost puzzles, by solver verdict (all runs) | how sessions ended |
|---|---|---|---|
| Claude Fable 5.2 | 1 | walked into a forced loss 2, overlooked Red's immediate win 1 | agent stopped by itself 1 |
| Gemini 4 Carbon | 17 | walked into a forced loss 80, puzzle clock ran out 2, overlooked Red's immediate win 1 | agent stopped by itself 17 |
| Gemini 4 Hydrogen | 18 | walked into a forced loss 84, overlooked Red's immediate win 16 | agent stopped by itself 18 |
| Gemini 4 Argon | 14 | walked into a forced loss 72, overlooked Red's immediate win 3, too slow 2, puzzle clock ran out 1 | agent stopped by itself 14 |
| Claude Opus 5.5 | 8 | walked into a forced loss 36, overlooked Red's immediate win 9 | agent stopped by itself 8 |
| Claude Haiku 5.5 | 3 | walked into a forced loss 16, overlooked Red's immediate win 1, given up 1 | agent stopped by itself 3 |
| Gemini 3.8 Flash | 17 | walked into a forced loss 67, overlooked Red's immediate win 43, too slow 4 | agent stopped by itself 7, 90-minute limit reached 6, API quota error after the last puzzle was decided 4 |
| Gemini 3.1 Pro | 17 | walked into a forced loss 70, overlooked Red's immediate win 42, given up 12 | agent stopped by itself 17 |
| Claude Sonnet 5 | 3 | never reached 7, overlooked Red's immediate win 5, walked into a forced loss 5, puzzle clock ran out 4, too slow 1 | agent stopped by itself 2, output limit hit mid-turn 1 |
| Nemotron 3 Ultra | 3 | walked into a forced loss 17, overlooked Red's immediate win 9, puzzle clock ran out 3 | agent stopped by itself 3 |

Wins by depth (puzzles solved / puzzles played; 2 puzzles per tier per run):

| win in | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Claude Fable 5.2, 1 run | 2/2 | 2/2 | 2/2 | 2/2 | 0/2 | 1/2 |
| Gemini 4, all 49 runs | 97/98 | 97/98 | 76/98 | 43/98 | 7/98 | 7/98 |
| Claude Opus 5.5, 8 runs | 11/16 | 16/16 | 7/16 | 9/16 | 2/16 | 6/16 |
| Claude Haiku 5.5, 3 runs | 6/6 | 6/6 | 3/6 | 3/6 | 0/6 | 0/6 |
| Gemini 3.8 Flash, 17 runs | 34/34 | 34/34 | 14/34 | 8/34 | 0/34 | 0/34 |
| Gemini 3.1 Pro, 17 runs | 34/34 | 34/34 | 11/34 | 1/34 | 0/34 | 0/34 |
| Claude Sonnet 5, 3 runs | 6/6 | 6/6 | 1/6 | 1/6 | 0/6 | 0/6 |
| Nemotron 3 Ultra, 3 runs | 6/6 | 1/6 | 0/6 | 0/6 | 0/6 | 0/6 |

**Where the horizon sits.** The Gemini 4 family plans about three moves ahead: it wins nearly every win in 1 and 2, three quarters of win in 3, under half of win in 4, and almost nothing deeper. Claude Opus 5.5 reaches further (8 of 32 puzzles at win in 5 and 6, against 14 of 196 for Gemini 4) but is erratic: in 5 of 8 runs it lost P01, a win in 1, by moving a stone that let Red win at once, and it scored 0.833 in one run and 0.417 - 0.583 in the other seven. Claude Fable 5.2 won every puzzle up to win in 4 in its one run. Older and smaller models stop earlier: Gemini 3.8 Flash, 3.1 Pro and Claude Sonnet 5 win almost nothing past win in 3, and Nemotron 3 Ultra almost nothing past win in 1. Every puzzle was reached in every kept run except the one Sonnet 5 run above, and no agent called anything but the game's tools. Of the 261 puzzles Gemini 4 lost, 258 were lost by a move the solver proves wrong (the other 3 ran out their puzzle clock). The losses are planning errors, not harness errors.

**Moving the horizon: the deep variant.** `experiments/deep/` (build and commands in [`experiments/README.md`](experiments/README.md)) builds the same task with 6 puzzles at win in 7, 8 and 9, drawn from the deeper tiers of the same scored pool, with a 102-minute run; everything else is byte-identical. Perfect play scores 1.000 and doing nothing 0.000 on Modal (`deep-24d6707-reference`, `deep-24d6707-do-nothing`); locally, rules-only search at 2 s per move scores 0.000 and stopping after 2 puzzles 0.333. Claude Opus 5.5 scored 0.000 in 2 runs and Gemini 4 Carbon 0.000 in 3 runs: 0 of 30 puzzles, every loss a solver-wrong move, no clock loss, sessions ended on their own. Two of the strongest models in the main table are past their horizon here, and the reference is not.

**More thinking moves the middle, not the edge.** Harbor's `--effort` option (passed to OpenCode as `--variant`), same task otherwise, 3 runs each (`jobs/final/effort-24d6707-*`). Gemini 4 Carbon: low 0.500, default 0.593, high 0.639. Claude Opus 5.5: default 0.531, high 0.639. At high effort both win 11 of 12 puzzles at win in 3 and 4 (default: Carbon 48 of 68, Opus 16 of 32), but at win in 5 and 6 they win 0 and 1 of 12 (default: 5 of 68 and 8 of 32). Low effort costs Carbon at win in 3 and 4 (6 of 12) and adds 2 puzzles lost to the clock. With 3 runs per setting these are indications, but two families show the same shape: extra reasoning fills in the depths a model can nearly reach and does not extend its horizon.

**Older models.** Both older Gemini models score below all three Gemini 4 models (0.441 and 0.392 against 0.536 to 0.593), win almost nothing beyond win in 3, and lose differently: they missed Red's immediate win 43 and 42 times in 17 runs each, against 20 times in all 49 Gemini 4 runs. 3.1 Pro also gave up 12 puzzles. In the one-move probe below the order is less clean (3.1 Pro scores 0.417, level with Argon's 0.400), so we read this as the older models trailing in the full task, not as a strict ranking.

**What 12 puzzles can and cannot say.** One puzzle is worth 0.083, and one model's runs span 0.417 to 0.833, so a few runs cannot rank models. With 14 to 18 runs each, Carbon is ahead of Argon and Hydrogen by about 0.06, about two standard errors (the one-move probe also puts Carbon first), while Argon and Hydrogen cannot be told apart. Opus 5.5 (8 runs) cannot be separated from Argon or Hydrogen on its mean, though its depth profile differs, and Fable 5.2's single 0.750 is a data point, not a rank. All runs play the same 12 puzzles, so this is a ranking on this draw; the one-move probe draws 60 different puzzles per model and gives the independent comparison.

**Replays.** `demo/replays.html` replays every final run move by move, with the solver's verdict on each Blue move. It covers every batch of each model (`-x3`, `-x3b`, ...), so its run counts and means can be ahead of the table above. Press T for a short tour of moments picked from the data. It is one file that opens from disk (fonts load from Google Fonts when online); regenerate it with `python tools/replay_site.py`.

`python tools/mistakes.py <job folders>` builds this table; `python tools/analyze.py <job folder>` writes, for every lost puzzle, the position, the move played, the solver's verdict on it and the move that would have kept the win.

### The horizon, measured a second way

`tools/probe.py` (the idea: separate "find the next move" from "manage a whole session") asks a model for **one move per fresh API call**: the rules and one position, no tools, no history, no clock. Puzzles from a held-out pool are played to the end against the perfect defender and every move is graded by the solver. 10 puzzles per tier.

| win in | 1 | 2 | 3 | 4 | 5 | 6 | mean (= task scale) |
|---|---|---|---|---|---|---|---|
| Gemini 4 Argon | 1.00 | 0.80 | 0.40 | 0.10 | 0.10 | 0.00 | **0.400** |
| Gemini 4 Hydrogen | 1.00 | 1.00 | 0.60 | 0.30 | 0.00 | 0.00 | **0.483** |
| Gemini 4 Carbon | 1.00 | 1.00 | 0.90 | 0.10 | 0.10 | 0.00 | **0.517** |
| Gemini 3.1 Pro (older generation) | 1.00 | 0.90 | 0.50 | 0.10 | 0.00 | 0.00 | **0.417** |
| Gemini 3.8 Flash (older generation)* | 1.00 | 0.80 | 0.30 | 0.00 | 0.00 | 0.00 | **0.350** |
| Claude Haiku 5.5** | 1.00 | 0.70 | 0.30 | 0.10 | 0.10 | 0.00 | **0.367** |
| Random legal moves | | | | | | | 0.007 |

\* Two 3.8 Flash runs overlapped by accident and shared one cache; the other scored 0.367 (one more win in 5). Either way it sits below every Gemini 4 model.

\*\* Graded on the first move in the reply (`--parse first`): Haiku states its move and then explains, naming later Blue and Red moves, so the default rule (the last move in the reply) picked the wrong one. All 554 cached Gemini replies were re-graded under the first-move rule with no change, so the rows are comparable. File: `results/probe/claude-haiku-5-5-parse-first.summary.json`; the earlier `claude-haiku-5-5.summary.json` is the mis-parsed run, kept as the record. Other Claude models and Nemotron were not probed.

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

The same question came up for training on the reward. We trained a small model on the reward bit alone, with two definitions of "good move" (details under Post-training). "The move keeps the forced win" pays 17.7% of random moves; the model learned to play safe moves that never get closer to winning, and its score stalled at 0.033. "The move brings the forced win one move closer" pays 7% of random moves, and the score climbed to 0.207. That second definition matches what the task scores, a win against a perfect defender.

### Harness limits we found and removed

Our first no-code runs ended after 5 to 15 minutes with most puzzles never reached, and the cause was not the game. `opencode run` ends a session as soon as a reply carries no tool call, and a model that reasons through a long line in one reply hits its output limit (32,768 tokens for Argon and Carbon, a hard API limit) and is cut off mid-thought: 6 of 9 sessions ended this way. Models also opened several puzzles and tried to solve them all in one reply. Three changes, none of which touches the model's own settings:

1. **`save_note`** gives the agent a game action that keeps a half-finished analysis, so a long line can span many turns.
2. **One puzzle at a time** stops a reply from holding several puzzles' analysis.
3. **A per-puzzle clock** stops one puzzle from eating the run, so every puzzle is reached.

With notes, cut-off sessions fell from 6 of 9 to 1 of 7 (Hydrogen, once, on a win in 5 after 20 minutes of paced play). Agents use notes as intended: worked lines and refutation lists, e.g. *"1.c1-a1 stops 1...c3-c2# AND threatens 2.c5-a3#"* (correct: it is the only winning move). We also raised OpenCode's own output cap to 64,000 in the task image, which only matters for Hydrogen. The task ships its own OpenCode config (shell, file writing and web access denied; output cap raised to 64,000 tokens); the organisers confirmed on 15 Nov that changing the OpenCode config is allowed.

## Run it

Needs Harbor (`uv tool install harbor`, or `uv tool install "harbor[modal]"` for Modal) and Docker, or Modal with `-e modal`. Verified both ways: on plain local Docker (Harbor 0.26.0, Docker 28.4.0) perfect play scores 1.000, do nothing 0.000, stop early 0.167, rules-only search 0.917 and a Claude Haiku 5.5 run 0.500, the same as on Modal; the first run on a clean machine takes 1 to 3 minutes including image builds.

```bash
git clone https://github.com/hectoragofi/thin-ice && cd thin-ice

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
| Write a program anyway | The agent has no tool that can write files or run code, so it cannot install a config or pick another agent, and Harbor always runs OpenCode's default build agent. A root-owned managed OpenCode config (`/etc/opencode/opencode.json`) denies shell, file editing, file writing, web fetch and web search, and subagents inherit the denials. Someone with a shell in the container could define a new OpenCode agent with those tools; the agent has no shell |
| Use `save_note` for something else | A note is the agent's own text, kept in the game server's memory for that run only and shown back by `show_puzzle`. The server never reads it, it is not on the score sheet, and it is capped (4,000 characters, 100 per puzzle, 2,000 in total). It only lets a long analysis span several turns |
| Peek at or play ahead on later puzzles | Locked until the current puzzle is won, lost or skipped; viewing or moving on a locked puzzle is refused, under any spelling of its id. A skip counts as lost and cannot be undone |
| Beat the clock | A move after the puzzle's clock is refused and the puzzle is lost. The clock is server time, starts at the first look and cannot be restarted by re-reading, practising, skipping or another spelling of the id |
| Read the answers | Puzzles, opponent and solutions live in a separate container. The agent's container holds none of the game's code or data |
| Learn the scored puzzles in practice | All published puzzles, scored and practice, are mutually disjoint: no position reachable in one occurs in any other, up to rotation and reflection. The build fails if two share a position |
| Edit the score | The verifier reads one file: a score sheet written and HMAC-signed by the game server, mounted read-only into the agent's container. The key never exists in the agent's sandbox. The key file is in this repo (`task/environment/game-server/receipt.key`, `task/tests/receipt.key`) because the game server and verifier need it; the agent has no web access, so it cannot read it during a run |
| Tamper with the grader | Verification runs in a separate container that the agent never touches. The agent itself is not root |
| Break the verifier's input | A missing, malformed or mis-signed score sheet scores 0 |

`python tools/redteam.py <server url>` runs the attack suite against a live game server: 96 checks, all passing, including the puzzle lock and `skip_puzzle`; `--clock` adds 13 attacks on the clock (also run from inside the agent's container on local Docker: 96 of 96, and 12 of 13 on the clock; the one miss was the check rounding 29.x seconds down, fixed in the check, not the server) (late winning moves under three id spellings, skip after expiry, re-looking, practice), all refused. The note tool was attacked through a real MCP client (locked puzzles, oversized notes, a fake score written into a note, the caps): the score and the signed receipt never change. In every agent run we read, notes contain only game analysis and no agent touched a non-game tool.

### The puzzles are proven, not just solved

Twelve scored puzzles also come with machine-checked proofs, in Lean 4 (`lean/`, build with `lake build`). Lean has its own copy of the rules. For each of the 12 puzzles the server serves with seed "1", it proves that Blue has a forced win within the stated number of moves. For puzzle P07, it proves that the mistake c1-g5 lets Red force a win within two moves, and that c3-e1 and d3-f1 are Red's only winning first moves. The winning strategies come from an untrusted search, but Lean re-checks every move and every Red reply itself. Eleven of the twelve are checked by Lean's kernel alone; the last (P12) also trusts the Lean compiler (`native_decide`). Not proven: that these wins are the fastest, that a move is the only one that holds (except the P07 line), anything about draws, or the solved game as a whole. That the Lean rules match `board.py` is checked against Python on these positions, not proven.

Building the proofs is optional and not part of the one-command evaluation; it needs elan and Lean 4.35.0 (pinned in `lean/lean-toolchain`). Writing them turned up one gap in the rules-only search reference: `thinice/search.py` does not count a win when Blue's last allowed move leaves Red with no legal move, which the rules score as a loss for Red. It changes no result on these 12 puzzles, and the task is frozen, so it is noted here rather than fixed.

## Post-training: does a small model get better?

Yes, from nothing to a bit below the Gemini 4 models. This is not the 12-puzzle Harbor score above: the small models are scored with the one-move-per-call rollout of the probe, on a held-out pool, and compared with the Gemini probe numbers.

**The agents do not use the feedback they are given; a small model trained on it does.** Practice puzzles with ground-truth feedback were available in every run. In the 83 Gemini runs kept above, 45 never practised (mean 0.504), 30 practised 1 to 3 puzzles (0.506) and 8 practised 4 to 9 (0.448). Argon never practised; Carbon opened 1 or 2 practice puzzles in every run. Practice did not raise scores, though model and practice are mixed here, so this is a description, not a controlled test. The controlled version (`experiments/practice/`, the same task with one added instruction to play 12 or 30 practice puzzles first) points the same way: Claude Haiku 5.5 scored 0.500 in 3 runs without practice, 0.583 in 5 runs told to practise 12 (it played 6 to 12) and 0.483 in 5 runs told to practise 30 (it played 11 to 35); Gemini 4 Argon told to practise 12 scored 0.611 in 3 runs (0.536 without) and Carbon 0.583 in 3 runs (0.593 without). Every difference is within one puzzle on 3 to 5 runs, so in-context practice gives no reliable gain. The 0.6B model below, trained on the same feedback, goes from 0.003 to 0.32.

 `training/` fine-tunes Qwen3 (LoRA, on Modal) on the feedback the environment's practice mode gives: a position and the move that wins it, generated at scale by the solver. This is imitation of the solver's winning moves, the same information practice mode returns after a wrong move; it is not trial-and-error on the reward. It is evaluated with the same rollout as the probe above, on a held-out pool removed from the training data together with all its rotations and reflections, with the same prompt before and after.

| model | before | after 600k examples | legal moves | after, by tier (win in 1 / 2 / 3 / 4 / 5 / 6) |
|---|---|---|---|---|
| Qwen3-0.6B | 0.003 | **0.320** | 50% → 100% | 1.00 / 0.64 / 0.20 / 0.06 / 0.00 / 0.02 |
| Qwen3-1.7B | 0.003 | **0.317** | 93% → 100% | 0.98 / 0.58 / 0.28 / 0.06 / 0.00 / 0.00 |

Scores are the mean over win in 1 to 6, the task's scale. The 0.6B curve is still rising at the end (0.293 at 400k examples). A 0.6B model trained on the environment's own feedback reaches 0.32 against the Gemini 4 models' 0.40 - 0.52 in the same one-move-per-call setting. Qwen was scored on 50 puzzles per tier, the Gemini probes on 10 per tier from the same pool. Curves: `results/curve-qwen3-*-7x6.json`; probes: `results/probe/`.

**From the reward alone.** `training/reinforce.py` trains Qwen3-0.6B (LoRA, same prompt, same held-out pool and rollout) without ever showing it the right move. The model plays one move per position and receives one bit: 1 if the move brings Blue's forced win one move closer (its value equals that of the fastest winning move), else 0; an illegal or unreadable answer gets 0. Round 0 is exploration only: 400,000 moves drawn at random from the legal moves printed in the position. Rounds 1 to 4 are 40,000 moves each, a shrinking share random (0.5, 0.4, 0.3, 0.2) and the rest sampled from the model. Each round trains on its rewarded moves plus replay.

| round | moves played | rewarded share of the model's own moves | of random moves | score | win in 1 | win in 2 |
|---|---|---|---|---|---|---|
| start | 0 | | | 0.003 | 0.02 | 0.00 |
| 0 | 400,000 | | 0.071 | 0.160 | 0.62 | 0.28 |
| 1 | 440,000 | 0.196 | 0.071 | 0.140 | 0.62 | 0.18 |
| 2 | 480,000 | 0.260 | 0.069 | 0.170 | 0.66 | 0.28 |
| 3 | 520,000 | 0.301 | 0.068 | 0.197 | 0.74 | 0.34 |
| 4 | 560,000 | 0.337 | 0.073 | 0.207 | 0.78 | 0.44 |

Legal moves rise from 50% to 100%. About three quarters of the gain (0.003 to 0.160) comes from round 0, which is random search filtered by the reward; the four rounds on the model's own moves add 0.047, with one dip in round 1. Win in 3 stays at noise level (0.02 - 0.10) and deeper tiers at 0. It ends below imitation (0.320 after 600k examples) and close to imitation at a similar amount of training (0.193 at 100k examples; this run trained on 78k). The first reward definition, "keeps the forced win", stalled at 0.033 after 3 rounds. Curves: `results/curve-rl-qwen3-0.6b-7x6.json`, `results/curve-rl-keepswin-qwen3-0.6b-7x6.json`. About 62 A100 minutes for all three runs.

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
