"""Plays the built task in-process with a set of baseline policies and prints their scores.

    python tools/selfcheck.py [seed ...]

No Docker and no model needed: this drives the same Run object the game server uses.
"""
import json
import random
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from thinice.board import key, mask_of, move_name, parse_sq  # noqa: E402
from thinice.search import find_win  # noqa: E402
from thinice.session import GameError, Run, load_pack, pick, sign, verify  # noqa: E402

PACKS = ROOT / "task" / "environment" / "game-server" / "packs"
MANIFEST = json.loads((PACKS / "manifest.json").read_text())
SCORED = load_pack(PACKS / "scored.jsonl")
PRACTICE = load_pack(PACKS / "practice.jsonl")
BOOK = json.loads((ROOT / "task" / "solution" / "book.json").read_text())


def new_run(seed) -> Run:
    return Run(pick(SCORED, seed, MANIFEST["tiers"], MANIFEST["per_tier"]), PRACTICE, seed=seed)


def play(run: Run, choose, limit=None) -> float:
    """Plays every puzzle with `choose(attempt) -> move text or None`; stops after `limit` puzzles."""
    for i, att in enumerate(run.attempts.values()):
        if limit is not None and i >= limit:
            break
        while att.status == "open":
            mv = choose(att)
            if mv is None:
                break
            att.move(mv)
    return run.scorecard()["score"]


def book(att):
    return BOOK[key(att.blue, att.red)]


def rng_policy(seed):
    rng = random.Random(seed)
    return lambda att: rng.choice(att.legal())


def first_legal(att):
    return att.legal()[0]


def mate_in_one_else_random(seed):
    """Takes an immediate three-in-a-row if there is one, otherwise moves at random."""
    rng = random.Random(seed)

    def choose(att):
        mv, _, _ = find_win(att.blue, att.red, 1)
        return move_name(mv) if mv else rng.choice(att.legal())

    return choose


def searcher(seconds):
    def choose(att):
        mv, _, _ = find_win(att.blue, att.red, att.puzzle.cap - att.used, seconds)
        return move_name(mv) if mv else None

    return choose


def clock_checks() -> None:
    """The per-puzzle clock, driven by a fake time source."""
    t = [0.0]
    run = Run(pick(SCORED, "1", MANIFEST["tiers"], MANIFEST["per_tier"]), PRACTICE, seed="1", clock=lambda n: 60 * n, now=lambda: t[0])
    p1, p2, p3 = list(run.attempts.values())[:3]
    t[0] = 500
    assert p1.started is None and not run.tick() and p1.time_left() == 60, "the clock ran before the first look"
    run.get("P01")
    assert p1.started == 500
    t[0] = 559
    run.get(" p01 ").move(book(p1))
    assert p1.status == "solved", "a move inside the clock was not accepted"
    run.get("P02")
    t[0] += 61
    try:
        run.get("P02").move(book(p2))
        raise SystemExit("a move after the clock ran out was played")
    except GameError:
        pass
    assert (p2.status, p2.reason, p2.used) == ("failed", "out of time", 0)
    assert run.current() is p3 and p3.started is None, "the next puzzle must unlock with its clock not started"
    practice = run.practice_new(1)
    assert practice.clock is None and practice.time_left() is None, "practice puzzles have no clock"
    run.get("P03")
    t[0] += 10_000
    card = run.scorecard()
    assert card["puzzles"][2]["reason"] == "out of time" and card["solved"] == 1, "a clock nobody looks at again must still run out"
    assert all(a.clock is None for a in new_run("1").attempts.values()), "a run built without a clock must not be timed"

    clock = MANIFEST.get("clock")
    if clock:
        limit = tomllib.loads((ROOT / "task" / "task.toml").read_text())["agent"]["timeout_sec"]
        assert clock["run_sec"] == limit, f"manifest clock run_sec {clock['run_sec']} differs from task.toml agent timeout {limit}"
        total = MANIFEST["per_tier"] * sum(clock.get("base_sec", 0) + clock["per_move_sec"] * n for n in MANIFEST["win_in"])
        note = "every puzzle can be reached" if total <= limit else "longer than the run, so late puzzles can still go unreached"
        print(f"puzzle clocks add up to {total / 60:.0f} min, the run limit is {limit / 60:.0f} min: {note}")
    print("clock checks passed")


def main() -> None:
    seeds = sys.argv[1:] or ["1", "2", "3"]
    rows = [
        ("do nothing", lambda s: play(new_run(s), lambda a: None)),
        ("stop early (first 2 puzzles, perfect)", lambda s: play(new_run(s), book, limit=2)),
        ("always first legal move", lambda s: play(new_run(s), first_legal)),
        ("random legal moves", lambda s: play(new_run(s), rng_policy(s))),
        ("win-in-1 if seen, else random", lambda s: play(new_run(s), mate_in_one_else_random(s))),
        ("rules-only search, 2s per move", lambda s: play(new_run(s), searcher(2.0))),
        ("perfect play (solver's book)", lambda s: play(new_run(s), book)),
    ]
    print(f"{'policy':<40} " + " ".join(f"seed {s:>3}" for s in seeds))
    for name, fn in rows:
        print(f"{name:<40} " + " ".join(f"{fn(s):>8.3f}" for s in seeds))

    # Receipt signing: a valid receipt verifies, an edited one does not.
    run = new_run(seeds[0])
    receipt = sign(run.scorecard(), b"k")
    assert verify(receipt, b"k")["score"] == 0.0
    receipt["scorecard"]["solved"] = 24
    try:
        verify(receipt, b"k")
        raise SystemExit("tampered receipt was accepted")
    except ValueError:
        pass
    # Stone lists in a view parse back to the same position.
    att = next(iter(run.attempts.values()))
    v = att.view()
    assert mask_of(parse_sq(s) for s in v["blue"]) == att.blue and mask_of(parse_sq(s) for s in v["red"]) == att.red
    print("receipt and view checks passed")
    clock_checks()


if __name__ == "__main__":
    main()
