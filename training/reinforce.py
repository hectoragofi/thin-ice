"""Reward-only training: a small model learns Thin Ice from the environment's win/lose signal alone.

    python training/reinforce.py --model Qwen/Qwen3-0.6B --labels data/7x6/labels.jsonl --out data/runs/rl-qwen3-0.6b

Each round the model is shown positions and plays one move in each. The environment answers
with one bit for that move (an illegal or unreadable answer is always 0). Two rewards:

  --reward progress   (default) 1 if the move brings Blue's forced win one move closer, i.e. the
                      move is one of the fastest winning moves in the position; else 0.
  --reward keeps-win  1 if Blue still has a forced win after the move (at any distance); else 0.
                      This is the first run's reward; about 18% of random legal moves earn it.

The model is never shown the solver's move or which move would have been rewarded. It then takes
gradient steps that raise the probability of its own rewarded moves (policy gradient with a
0/1 reward, plus replay of earlier rewarded moves), and is evaluated by playing the held-out
puzzle pool with the same prompt and the same rollout as training/train.py.

Exploration: the first round, and a shrinking share of every later round (--explore), draws
the move uniformly from the legal moves printed in the position instead of from the model.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import canon, chat, eval_pool, held_out_positions, rollout
from thinice.board import mask_of, move_name  # noqa: E402  (common puts the repo root on sys.path)

WIN = 128  # solver value of a move after which Blue still has its forced win


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Qwen/Qwen3-0.6B")
    p.add_argument("--labels", default="data/7x6/labels.jsonl", help="positions with the solver's verdict on every move; only used to compute the reward")
    p.add_argument("--out", default="data/runs/rl-qwen3-0.6b")
    p.add_argument("--reward", choices=["progress", "keeps-win"], default="progress", help="progress: fastest winning move; keeps-win: any move that keeps the forced win")
    p.add_argument("--rounds", type=int, default=8)
    p.add_argument("--random-first", type=int, default=400_000, help="moves played in round 0, all drawn at random from the legal moves")
    p.add_argument("--per-round", type=int, default=100_000, help="moves played in every later round")
    p.add_argument("--explore", default="0.6,0.4,0.3,0.2,0.2,0.1,0.1", help="share of random legal moves in rounds 1, 2, ...; the last value repeats")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--replay", type=float, default=0.5, help="earlier rewarded moves replayed per new one")
    p.add_argument("--act-bs", type=int, default=384, help="positions per generation batch")
    p.add_argument("--bs", type=int, default=32, help="examples per forward pass")
    p.add_argument("--accum", type=int, default=2, help="forward passes per optimizer step")
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--rank", type=int, default=64)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--minutes", type=float, default=0, help="stop starting new rounds after this long; 0 means no limit")
    p.add_argument("--eval-per-tier", type=int, default=0, help="evaluate on this many held-out puzzles per tier; 0 means all")
    p.add_argument("--keep-held-out", action="store_true", help="smoke tests only: do not remove the evaluation positions from training")
    return p.parse_args()


def load_positions(path, exclude: set, reward: str) -> list:
    """(blue, red, legal move names, names of the moves the environment rewards, depth).

    The rewarded set is used only by env_reward; the learner never sees it."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if canon(rec["blue"], rec["red"]) in exclude:
                continue
            legal = [move_name(m) for m in rec["moves"]]
            wins = [m for m in rec["moves"] if m[2] >= WIN]
            if reward == "progress":  # the smallest winning value is the fastest win
                fastest = min(m[2] for m in wins)
                good = frozenset(move_name(m) for m in wins if m[2] == fastest)
            else:
                good = frozenset(move_name(m) for m in wins)
            out.append((mask_of(rec["blue"]), mask_of(rec["red"]), legal, good, rec["depth"]))
    return out


def env_reward(position, move: str) -> int:
    """All the learner is told about a move: one bit. With --reward progress, 1 if the move is a
    fastest winning move (Blue's forced win is one move closer); with --reward keeps-win, 1 if
    Blue still has a forced win after it. Illegal or unreadable moves are never in the set: 0."""
    return int(move in position[3])


def main() -> None:
    args = parse()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32

    tok = AutoTokenizer.from_pretrained(args.model)
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    try:
        model = AutoModelForCausalLM.from_pretrained(args.model, dtype=dtype)
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=dtype)
    model = get_peft_model(
        model.to(device),
        LoraConfig(
            r=args.rank,
            lora_alpha=2 * args.rank,
            lora_dropout=0.0,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            task_type="CAUSAL_LM",
        ),
    )
    core = model.get_base_model()
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)

    pool = eval_pool()
    if args.eval_per_tier:
        taken: dict = {}
        kept = []
        for puzzle in pool:
            taken[puzzle.need] = taken.get(puzzle.need, 0) + 1
            if taken[puzzle.need] <= args.eval_per_tier:
                kept.append(puzzle)
        pool = kept
    positions = load_positions(args.labels, set() if args.keep_held_out else held_out_positions(), args.reward)
    random.shuffle(positions)
    print(f"{len(positions)} training positions, {len(pool)} held-out puzzles, {sum(p.numel() for p in params) / 1e6:.1f}M trainable parameters", flush=True)

    def generate(prompts: list, sample: bool) -> list:
        enc = tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(device)
        kwargs = {"do_sample": True, "temperature": args.temperature, "top_k": 0, "top_p": 1.0} if sample else {"do_sample": False}
        with torch.autocast(device, dtype=dtype, enabled=device == "cuda"):
            gen = model.generate(**enc, max_new_tokens=8, pad_token_id=tok.pad_token_id, **kwargs)
        texts = tok.batch_decode(gen[:, enc["input_ids"].shape[1] :], skip_special_tokens=True)
        return [t.strip().split()[0] if t.strip() else "" for t in texts]

    @torch.no_grad()
    def choose_batch(group) -> list:  # greedy, for evaluation: identical to training/train.py
        return generate([chat(tok, a.blue, a.red, a.legal()) for a in group], sample=False)

    @torch.no_grad()
    def act(batch: list) -> list:  # the model's own moves, sampled
        moves = []
        for i in range(0, len(batch), args.act_bs):
            moves += generate([chat(tok, b, r, legal) for b, r, legal, _, _ in batch[i : i + args.act_bs]], sample=True)
        return moves

    def answer_loss(items: list) -> torch.Tensor:
        """Cross-entropy on the move tokens only, for (blue, red, legal, move) items."""
        ids, labels = [], []
        for blue, red, legal, move in items:
            p = tok(chat(tok, blue, red, legal), add_special_tokens=False)["input_ids"]
            a = tok(move + tok.eos_token, add_special_tokens=False)["input_ids"]
            ids.append(p + a)
            labels.append([-100] * len(p) + a)
        width = max(map(len, ids))
        pad = tok.pad_token_id
        x = torch.tensor([i + [pad] * (width - len(i)) for i in ids], device=device)
        y = torch.tensor([l + [-100] * (width - len(l)) for l in labels], device=device)
        hidden = core.model(input_ids=x, attention_mask=(x != pad) | (y != -100)).last_hidden_state[:, :-1]
        target = y[:, 1:]
        keep = target != -100
        return torch.nn.functional.cross_entropy(core.lm_head(hidden[keep]).float(), target[keep])

    history: list = []
    started = time.time()
    totals = {"moves": 0, "rewarded": 0, "trained": 0, "steps": 0}

    def evaluate(tag: dict) -> None:
        model.eval()
        t0 = time.time()
        res = rollout(pool, choose_batch)
        rates = {int(k): v for k, v in res["by_win_in"].items()}
        res.update(
            six_tier=round(sum(rates.get(n, 0.0) for n in range(1, 7)) / 6, 4),
            moves_played=totals["moves"],
            moves_rewarded=totals["rewarded"],
            examples_trained=totals["trained"],
            minutes=round((time.time() - started) / 60, 1),
            eval_seconds=round(time.time() - t0, 1),
            **tag,
        )
        history.append(res)
        (out / "curve.json").write_text(json.dumps({"model": args.model, "method": "reward-only", "reward": args.reward, "history": history}, indent=2))
        tiers = " ".join(f"{n}:{r:.2f}" for n, r in sorted(rates.items())[:6])
        print(f"[eval] round={tag['round']:>2} moves={totals['moves']:>8} rewarded={totals['rewarded']:>7} six-tier={res['six_tier']:.3f} score={res['score']:.3f} legal={res['legal_rate']:.2f} | {tiers}", flush=True)

    def learn(items: list, lr: float) -> None:
        model.train()
        random.shuffle(items)
        per_step = args.bs * args.accum
        t0, running = time.time(), 0.0
        for start in range(0, len(items) - per_step + 1, per_step):
            warm = min(1.0, (totals["steps"] + 1) / 50)
            for group in opt.param_groups:
                group["lr"] = lr * warm
            total = 0.0
            for k in range(args.accum):
                with torch.autocast(device, dtype=dtype, enabled=device == "cuda"):
                    loss = answer_loss(items[start + k * args.bs : start + (k + 1) * args.bs]) / args.accum
                loss.backward()
                total += loss.item()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)
            totals["steps"] += 1
            totals["trained"] += per_step
            running = total if running == 0.0 else 0.98 * running + 0.02 * total
            if totals["steps"] % 100 == 0:
                print(f"  step {totals['steps']:>6} loss {running:.4f} {(start + per_step) / (time.time() - t0):.0f} ex/s", flush=True)

    explore = [float(x) for x in args.explore.split(",") if x]
    buffer: list = []  # every rewarded (blue, red, legal, move) so far
    cursor = 0
    evaluate({"round": -1, "explore": None, "policy_hit_rate": None, "random_hit_rate": None})
    for rnd in range(args.rounds):
        if args.minutes and (time.time() - started) / 60 > args.minutes:
            print(f"time budget of {args.minutes} min reached, stopping before round {rnd}", flush=True)
            break
        n = args.random_first if rnd == 0 else args.per_round
        eps = 1.0 if rnd == 0 else explore[min(rnd - 1, len(explore) - 1)]
        if cursor + n > len(positions):
            random.shuffle(positions)
            cursor = 0
        batch = positions[cursor : cursor + n]
        cursor += n
        n_random = round(eps * len(batch))
        t0 = time.time()
        model.eval()
        moves = [random.choice(p[2]) for p in batch[:n_random]] + act(batch[n_random:])
        rewards = [env_reward(p, m) for p, m in zip(batch, moves)]
        new = [(p[0], p[1], p[2], m) for p, m, r in zip(batch, moves, rewards) if r]
        hit_random = sum(rewards[:n_random]) / n_random if n_random else None
        hit_policy = sum(rewards[n_random:]) / (len(batch) - n_random) if len(batch) > n_random else None
        totals["moves"] += len(batch)
        totals["rewarded"] += len(new)
        shown = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
        print(f"[act] round={rnd} moves={len(batch)} explore={eps:.2f} rewarded={len(new)} hit rate: own moves {shown(hit_policy)}, random moves {shown(hit_random)} ({time.time() - t0:.0f}s)", flush=True)
        replay = random.sample(buffer, min(len(buffer), int(args.replay * len(new))))
        buffer += new
        learn(new + replay, args.lr * (1 - 0.7 * rnd / max(1, args.rounds - 1)))
        evaluate({"round": rnd, "explore": eps, "policy_hit_rate": hit_policy, "random_hit_rate": hit_random})
        model.save_pretrained(out / "adapter")
    print("done", flush=True)


if __name__ == "__main__":
    main()
