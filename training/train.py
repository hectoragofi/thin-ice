"""Post-training experiment: fine-tune a small model on Thin Ice and measure it in the environment.

    python training/train.py --model Qwen/Qwen3-0.6B --labels data/labels.jsonl --out data/runs/qwen3-0.6b

Training data is what the environment's practice mode hands out (a position and the move that
wins it), generated at scale by the solver. Evaluation plays the scored puzzle pool, which is
removed from the training data together with all its mirror images and rotations. The model
is evaluated before any training and again at each checkpoint, with the same prompt.
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

from common import chat, eval_pool, held_out_positions, load_labels, rollout


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Qwen/Qwen3-0.6B")
    p.add_argument("--labels", default="data/labels.jsonl")
    p.add_argument("--out", default="data/runs/qwen3-0.6b")
    p.add_argument("--examples", type=int, default=200_000, help="training examples to see in total")
    p.add_argument("--eval-at", default="0,1000,3000,10000,30000,100000,200000")
    p.add_argument("--bs", type=int, default=8, help="examples per forward pass")
    p.add_argument("--accum", type=int, default=4, help="forward passes per optimizer step")
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--rank", type=int, default=64)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--eval-only", action="store_true")
    p.add_argument("--adapter", default=None, help="LoRA adapter to load before evaluating or training")
    return p.parse_args()


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
    model = model.to(device)
    if args.adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, args.adapter, is_trainable=not args.eval_only)
    elif not args.eval_only:
        cfg = LoraConfig(
            r=args.rank,
            lora_alpha=2 * args.rank,
            lora_dropout=0.0,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, cfg)
    pool = eval_pool()

    @torch.no_grad()
    def choose_batch(group) -> list:
        prompts = [chat(tok, a.blue, a.red, a.legal()) for a in group]
        enc = tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(device)
        with torch.autocast(device, dtype=dtype, enabled=device == "cuda"):
            gen = model.generate(**enc, max_new_tokens=8, do_sample=False, pad_token_id=tok.pad_token_id)
        texts = tok.batch_decode(gen[:, enc["input_ids"].shape[1] :], skip_special_tokens=True)
        return [t.strip().split()[0] if t.strip() else "" for t in texts]

    history = []

    def evaluate(seen: int) -> None:
        model.eval()
        t0 = time.time()
        res = rollout(pool, choose_batch)
        res.update(examples_seen=seen, eval_seconds=round(time.time() - t0, 1))
        history.append(res)
        (out / "curve.json").write_text(json.dumps({"model": args.model, "history": history}, indent=2))
        tiers = " ".join(f"{n}:{r:.2f}" for n, r in res["by_win_in"].items())
        print(f"[eval] seen={seen:>7} score={res['score']:.3f} legal={res['legal_rate']:.2f} | {tiers}", flush=True)
        model.train()

    eval_at = sorted(int(x) for x in args.eval_at.split(",") if x)
    if args.eval_only:
        evaluate(0)
        return

    data = load_labels(args.labels, held_out_positions())
    print(f"{len(data)} training positions, {sum(p.numel() for p in model.parameters() if p.requires_grad) / 1e6:.1f}M trainable parameters", flush=True)
    print(f"prompt length: {len(tok(chat(tok, *data[0][:3]), add_special_tokens=False)['input_ids'])} tokens", flush=True)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.0)
    steps = math.ceil(args.examples / (args.bs * args.accum))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps, pct_start=0.03, anneal_strategy="cos")
    tok.padding_side = "right"

    def batch_tensors(items):
        ids, labels = [], []
        for blue, red, legal, best, _ in items:
            p = tok(chat(tok, blue, red, legal), add_special_tokens=False)["input_ids"]
            a = tok(random.choice(best) + tok.eos_token, add_special_tokens=False)["input_ids"]
            ids.append(p + a)
            labels.append([-100] * len(p) + a)
        width = max(map(len, ids))
        pad = tok.pad_token_id
        x = torch.tensor([i + [pad] * (width - len(i)) for i in ids], device=device)
        y = torch.tensor([l + [-100] * (width - len(l)) for l in labels], device=device)
        return x, (x != pad) | (y != -100), y

    core = model.get_base_model() if hasattr(model, "get_base_model") else model

    def answer_loss(x, mask, y):
        # Only the answer tokens carry a loss, so the vocabulary projection runs on those few
        # positions instead of on the whole prompt (which would not fit in 8 GB).
        hidden = core.model(input_ids=x, attention_mask=mask).last_hidden_state[:, :-1]
        target = y[:, 1:]
        keep = target != -100
        return torch.nn.functional.cross_entropy(core.lm_head(hidden[keep]).float(), target[keep])

    seen, step, t0, running = 0, 0, time.time(), 0.0
    model.train()
    order = list(range(len(data)))
    random.shuffle(order)
    cursor = 0
    while eval_at and eval_at[0] <= 0:
        eval_at.pop(0)
        tok.padding_side = "left"
        evaluate(0)
        tok.padding_side = "right"
    while seen < args.examples:
        total = 0.0
        for _ in range(args.accum):
            if cursor + args.bs > len(order):
                random.shuffle(order)
                cursor = 0
            items = [data[i] for i in order[cursor : cursor + args.bs]]
            cursor += args.bs
            x, mask, y = batch_tensors(items)
            with torch.autocast(device, dtype=dtype, enabled=device == "cuda"):
                loss = answer_loss(x, mask, y) / args.accum
            loss.backward()
            total += loss.item()
            seen += args.bs
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step()
        sched.step()
        opt.zero_grad(set_to_none=True)
        step += 1
        running = total if step == 1 else 0.98 * running + 0.02 * total
        if step % 25 == 0:
            print(f"step {step:>6} seen {seen:>7} loss {running:.4f} {seen / (time.time() - t0):.0f} ex/s", flush=True)
        while eval_at and seen >= eval_at[0]:
            eval_at.pop(0)
            tok.padding_side = "left"
            evaluate(seen)
            tok.padding_side = "right"
            model.save_pretrained(out / "adapter")
    tok.padding_side = "left"
    if not history or history[-1]["examples_seen"] != seen:
        evaluate(seen)
    model.save_pretrained(out / "adapter")
    print("done", flush=True)


if __name__ == "__main__":
    main()
