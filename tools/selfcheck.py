"""Plays the built task in-process with a set of baseline policies and prints their scores.

    python tools/selfcheck.py [seed ...]

No Docker and no model needed: this drives the same Run object the game server uses.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from thinice.board import key, mask_of, move_name, parse_sq  # noqa: E402
from thinice.search import find_win  # noqa: E402
from thinice.session import Run, load_pack, pick, sign, verify  # noqa: E402

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


def tools_only(seed) -> float:
    """The tools-only player, through the same tool functions the server answers with."""
    sys.path.insert(0, str(ROOT / "tools"))
    from size_task import LocalTools, toolplay

    run = new_run(seed)
    tools = LocalTools(run)
    for pid in run.attempts:
        toolplay.play_puzzle(tools, pid, 400, 120)
    return run.scorecard()["score"]


def main() -> None:
    seeds = sys.argv[1:] or ["1", "2", "3"]
    rows = [
        ("do nothing", lambda s: play(new_run(s), lambda a: None)),
        ("stop early (first 4 puzzles, perfect)", lambda s: play(new_run(s), book, limit=4)),
        ("always first legal move", lambda s: play(new_run(s), first_legal)),
        ("random legal moves", lambda s: play(new_run(s), rng_policy(s))),
        ("win-in-1 if seen, else random", lambda s: play(new_run(s), mate_in_one_else_random(s))),
        ("rules-only search, 2s per move", lambda s: play(new_run(s), searcher(2.0))),
        ("tools-only reference (agent's tools only)", tools_only),
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
    explore_checks(run)


def explore_checks(run: Run) -> None:
    """The look-ahead tools answer from the rules alone and never touch a puzzle."""
    from thinice.explore import walk, lines

    for att in run.attempts.values():
        if att.status != "open":
            continue
        before = (att.blue, att.red, att.used, att.status, list(att.history))
        root = walk(att.blue, att.red, "")
        assert root["moves"] == att.legal(), f"{att.pid}: rules and pack disagree on legal moves"
        firsts = lines(att.blue, att.red, root["moves"][:40])
        # Same answers with the solver's data removed: nothing comes from the pack.
        saved, att.puzzle.nodes = att.puzzle.nodes, {}
        try:
            assert walk(att.blue, att.red, "") == root
            assert lines(att.blue, att.red, root["moves"][:40]) == firsts
        finally:
            att.puzzle.nodes = saved
        # The winning first move and the losing ones answer in exactly the same shape.
        assert len({tuple(sorted(r)) for r in firsts}) == 1
        assert (att.blue, att.red, att.used, att.status, list(att.history)) == before
    print("explore checks passed: rules-only, pack-independent, no state change")


if __name__ == "__main__":
    main()
