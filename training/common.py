"""Shared pieces of the post-training experiment: the prompt a model sees and the puzzle rollout."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from thinice.board import mask_of, move_name, moves, render, sq_name, squares  # noqa: E402
from thinice.session import GameError, Run, load_pack  # noqa: E402

PACKS = ROOT / "task" / "environment" / "game-server" / "packs"

SYSTEM = (
    "You are playing Blue in Thin Ice on a 5x5 board (columns a-e, rows 1-5, a1 bottom-left). "
    "On your turn you move one of your stones in one of 8 directions; it slides until the next cell "
    "is the edge of the board or another stone. You win when 3 of your stones are in a row "
    "(horizontal, vertical or diagonal). Blue has a forced win in this position. "
    "Reply with one move in from-to form, for example a1-a5, and nothing else."
)


def user_text(blue: int, red: int, legal: list) -> str:
    return (
        f"{render(blue, red)}\n"
        f"Blue: {' '.join(sq_name(s) for s in squares(blue))}\n"
        f"Red: {' '.join(sq_name(s) for s in squares(red))}\n"
        f"Legal moves: {' '.join(legal)}\n"
        "Blue to move."
    )


def chat(tokenizer, blue: int, red: int, legal: list) -> str:
    """The exact prompt string, identical for the untrained and the trained model."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_text(blue, red, legal)}]
    try:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def transforms() -> list:
    out = []
    for rot in range(4):
        for flip in (False, True):
            table = []
            for sq in range(25):
                x, y = sq % 5, sq // 5
                if flip:
                    x = 4 - x
                for _ in range(rot):
                    x, y = 4 - y, x
                table.append(y * 5 + x)
            out.append(table)
    return out


SYM = transforms()


def canon(blue_sqs, red_sqs) -> tuple:
    return min((tuple(sorted(t[s] for s in blue_sqs)), tuple(sorted(t[s] for s in red_sqs))) for t in SYM)


EVAL_POOL = ROOT / "training" / "eval_pool.jsonl"


def held_out_positions() -> set:
    """Every position (up to board symmetry) in the evaluation pool or in the task's own pools."""
    seen = set()
    for path in (EVAL_POOL, PACKS / "scored.jsonl", PACKS / "practice.jsonl"):
        for line in path.read_text().splitlines():
            for pos in json.loads(line)["nodes"]:
                b, r = pos.split("|")
                seen.add(canon(json.loads(b), json.loads(r)))
    return seen


def load_labels(path, exclude: set) -> list:
    """Training examples: (blue, red, legal move names, fastest winning move names, depth)."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if canon(rec["blue"], rec["red"]) in exclude:
                continue
            wins = [m for m in rec["moves"] if m[2] >= 128]
            fastest = min(m[2] for m in wins)
            out.append(
                (
                    mask_of(rec["blue"]),
                    mask_of(rec["red"]),
                    [move_name(m) for m in rec["moves"]],
                    [move_name(m) for m in wins if m[2] == fastest],
                    rec["depth"],
                )
            )
    return out


def eval_pool() -> list:
    """50 sharp puzzles for each of the 12 tiers, never used for training."""
    return load_pack(EVAL_POOL)


def rollout(pool: list, choose_batch, batch_size: int = 64) -> dict:
    """Plays every puzzle in `pool` to the end. choose_batch(list of Attempt) -> list of move texts.

    Returns the solve rate per tier (win in N moves), the mean over tiers (which is the expected
    score of the Harbor task, since the task draws the same number of puzzles from each tier)
    and how often the model's answer was a legal move.
    """
    run = Run(pool, [], seed="eval")
    live = list(run.attempts.values())
    asked = legal = 0
    while live:
        nxt = []
        for i in range(0, len(live), batch_size):
            group = live[i : i + batch_size]
            for att, text in zip(group, choose_batch(group)):
                asked += 1
                try:
                    att.move(text)
                    legal += 1
                except GameError:
                    att.status, att.reason = "failed", "illegal or unreadable move"
                if att.status == "open":
                    nxt.append(att)
        live = nxt
    tiers: dict = {}
    for att in run.attempts.values():
        t = tiers.setdefault(att.puzzle.need, [0, 0])
        t[0] += att.status == "solved"
        t[1] += 1
    rates = {n: s / c for n, (s, c) in sorted(tiers.items())}
    return {"by_win_in": rates, "score": sum(rates.values()) / len(rates), "legal_rate": legal / max(1, asked)}


__all__ = ["ROOT", "chat", "eval_pool", "held_out_positions", "load_labels", "moves", "rollout"]
