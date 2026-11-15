# Training a small model on Thin Ice

The post-training experiments: practice inside a session, imitation of the solver, and learning from the reward alone. Summary in the [README](../README.md).

Yes, from nothing to a bit below the Gemini 4 models. This is not the 12-puzzle Harbor score above: the small models are scored with the one-move-per-call rollout of the probe, on a held-out pool, and compared with the Gemini probe numbers.

**The agents do not use the feedback they are given; a small model trained on it does.** Practice puzzles with ground-truth feedback were available in every run. In the 83 Gemini runs kept above, 45 never practised (mean 0.504), 30 practised 1 to 3 puzzles (0.506) and 8 practised 4 to 9 (0.448). Argon never practised; Carbon opened 1 or 2 practice puzzles in every run. Practice did not raise scores, though model and practice are mixed here, so this is a description, not a controlled test. The controlled version (`experiments/practice/`, the same task with one added instruction to play 12 or 30 practice puzzles first) points the same way: Claude Haiku 5.5 scored 0.500 in 3 runs without practice, 0.583 in 5 runs told to practise 12 (it played 6 to 12) and 0.483 in 5 runs told to practise 30 (it played 11 to 35); Gemini 4 Argon told to practise 12 scored 0.611 in 3 runs (0.536 without) and Carbon 0.583 in 3 runs (0.593 without). Every difference is within one puzzle on 3 to 5 runs, so in-context practice gives no reliable gain. The 0.6B model below, trained on the same feedback, goes from 0.003 to 0.32.

 `training/` fine-tunes Qwen3 (LoRA, on Modal) on the feedback the environment's practice mode gives: a position and the move that wins it, generated at scale by the solver. This is imitation of the solver's winning moves, the same information practice mode returns after a wrong move; it is not trial-and-error on the reward. It is evaluated with the same rollout as the probe above, on a held-out pool removed from the training data together with all its rotations and reflections, with the same prompt before and after.

| model | before | after 600k examples | legal moves | after, by tier (win in 1 / 2 / 3 / 4 / 5 / 6) |
|---|---|---|---|---|
| Qwen3-0.6B | 0.003 | **0.320** | 50% → 100% | 1.00 / 0.64 / 0.20 / 0.06 / 0.00 / 0.02 |
| Qwen3-1.7B | 0.003 | **0.317** | 93% → 100% | 0.98 / 0.58 / 0.28 / 0.06 / 0.00 / 0.00 |
| Qwen3-4B (200k examples only) | 0.020 | **0.280** at 200k | 91% → 100% | 0.96 / 0.50 / 0.18 / 0.04 / 0.00 / 0.00 |

Scores are the mean over win in 1 to 6, the task's scale. The 0.6B curve is still rising at the end (0.293 at 400k examples). A 0.6B model trained on the environment's own feedback reaches 0.32 against the Gemini 4 models' 0.40 - 0.52 in the same one-move-per-call setting. Qwen was scored on 50 puzzles per tier, the Gemini probes on 10 per tier from the same pool. Curves: `results/curve-qwen3-*-7x6.json`; probes: `results/probe/`.

**Does a bigger model learn more from the same feedback?** Barely. At equal examples the three sizes score: at 100k, 0.193 (0.6B), 0.220 (1.7B), 0.230 (4B); at 200k, 0.223, 0.260, 0.280. The 4B run used the same prompt, held-out pool, batch, learning rate and LoRA settings as the 1.7B run, but stopped at 200k examples for time (about 94 minutes on one H100). Two caveats both favour the 4B: its 200k training positions were drawn from a larger labels file (3.0M positions against 0.6M; same held-out exclusion, each position seen once), and its learning-rate schedule had fully decayed at 200k while the others were mid-schedule. So seven times the parameters buys at most a few hundredths at equal examples, and win in 4 and deeper stays near zero for every size.

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
