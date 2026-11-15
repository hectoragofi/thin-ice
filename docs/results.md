# Results in full

Every table behind the summary in the [README](../README.md): scores per model, how each model lost, wins by depth, the deeper puzzle set, the effort runs and the one-move probe. Paths are relative to the repository root.

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

## Where the agents go wrong

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

**Where the horizon sits.** The Gemini 4 family plans about three moves ahead: it wins nearly every win in 1 and 2, three quarters of win in 3, under half of win in 4, and almost nothing deeper. Claude Opus 5.5 reaches further (8 of 32 puzzles at win in 5 and 6, against 14 of 196 for Gemini 4) but is erratic: in 5 of 8 runs it lost P01, a win in 1, by moving a stone that let Red win at once, and it scored 0.833 in one run and 0.417 - 0.583 in the other seven. Claude Fable 5.2 won every puzzle up to win in 4 in its one run. Older and smaller models stop earlier: Gemini 3.8 Flash, 3.1 Pro and Claude Sonnet 5 win almost nothing past win in 3, and Nemotron 3 Ultra almost nothing past win in 1. Every puzzle was reached in every kept run except the one Sonnet 5 run above, and no agent called anything but the game's tools. Of the 261 puzzles Gemini 4 lost, 256 were lost by a move the solver proves wrong, 2 by moves that kept the win but too slowly to finish within the allowed moves, and 3 by the puzzle clock. Over all 101 kept runs of every model, 579 of the 616 lost puzzles were lost by a solver-proven wrong move; the rest were 7 too slow, 10 clock, 13 given up and 7 never reached (one Sonnet 5 run). The losses are planning errors, not harness errors.

**Moving the horizon: the deep variant.** `experiments/deep/` (build and commands in [`experiments/README.md`](../experiments/README.md)) builds the same task with 6 puzzles at win in 7, 8 and 9, drawn from the deeper tiers of the same scored pool, with a 102-minute run; everything else is byte-identical. Perfect play scores 1.000 and doing nothing 0.000 on Modal (`deep-24d6707-reference`, `deep-24d6707-do-nothing`); locally, rules-only search at 2 s per move scores 0.000 and stopping after 2 puzzles 0.333. Claude Opus 5.5 scored 0.000 in 2 runs and Gemini 4 Carbon 0.000 in 3 runs: 0 of 30 puzzles, every loss a solver-wrong move, no clock loss, sessions ended on their own. Two of the strongest models in the main table are past their horizon here, and the reference is not.

**More thinking moves the middle, not the edge.** Harbor's `--effort` option (passed to OpenCode as `--variant`), same task otherwise, 3 runs each (`jobs/final/effort-24d6707-*`). Gemini 4 Carbon: low 0.500, default 0.593, high 0.639. Claude Opus 5.5: default 0.531, high 0.639. At high effort both win 11 of 12 puzzles at win in 3 and 4 (default: Carbon 48 of 68, Opus 16 of 32), but at win in 5 and 6 they win 0 and 1 of 12 (default: 5 of 68 and 8 of 32). Low effort costs Carbon at win in 3 and 4 (6 of 12) and adds 2 puzzles lost to the clock. With 3 runs per setting these are indications, but two families show the same shape: extra reasoning fills in the depths a model can nearly reach and does not extend its horizon.

**Older models.** Both older Gemini models score below all three Gemini 4 models (0.441 and 0.392 against 0.536 to 0.593), win almost nothing beyond win in 3, and lose differently: they missed Red's immediate win 43 and 42 times in 17 runs each, against 20 times in all 49 Gemini 4 runs. 3.1 Pro also gave up 12 puzzles. In the one-move probe below the order is less clean (3.1 Pro scores 0.417, level with Argon's 0.400), so we read this as the older models trailing in the full task, not as a strict ranking.

**What 12 puzzles can and cannot say.** One puzzle is worth 0.083, and one model's runs span 0.417 to 0.833, so a few runs cannot rank models. With 14 to 18 runs each, Carbon is ahead of Argon and Hydrogen by about 0.06, about two standard errors (the one-move probe also puts Carbon first), while Argon and Hydrogen cannot be told apart. Opus 5.5 (8 runs) cannot be separated from Argon or Hydrogen on its mean, though its depth profile differs, and Fable 5.2's single 0.750 is a data point, not a rank. All runs play the same 12 puzzles, so this is a ranking on this draw; the one-move probe draws 60 different puzzles per model and gives the independent comparison.

**Replays.** `demo/replays.html` (live at https://hectoragofi.github.io/thin-ice-replays/) replays every kept run move by move, with the solver's verdict on each Blue move, and lets you play the 12 puzzles yourself. It is one file that opens from disk; regenerate it with `python tools/replay_site.py`.

`python tools/mistakes.py <job folders>` builds this table; `python tools/analyze.py <job folder>` writes, for every lost puzzle, the position, the move played, the solver's verdict on it and the move that would have kept the win.

## The horizon, measured a second way

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
