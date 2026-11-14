"""Builds everything the Harbor task ships, from the exhaustive solver's output.

    python tools/build_task.py

Steps: solve the game if data/tb.bin is missing -> extract sharp puzzles per depth -> drop
symmetric duplicates -> split into a scored pool and a practice pool -> pack every position
Blue can reach in each puzzle -> write the oracle's book, the manifest, the vendored game code
and the receipt key.
"""
import hashlib
import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TASK = ROOT / "task"
SERVER = TASK / "environment" / "game-server"
SOLVER = ROOT / "solver" / "target" / "release" / ("thinice-solver.exe" if sys.platform == "win32" else "thinice-solver")

GAME = {"w": 5, "h": 5, "sb": 4, "sr": 4, "k": 3, "dirs": 8, "slide": 1}
TIERS = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23]  # plies to the fastest forced win
PER_TIER = 2  # scored puzzles per tier in one run
POOL = 30  # scored puzzles per tier to choose from (the seed picks PER_TIER of them)
PRACTICE = 20  # practice puzzles per tier
SLACK = 1  # extra Blue moves allowed beyond the fastest win
SEED = 20261114


def solver(*args: str) -> None:
    cmd = [str(SOLVER), *args, *[f"{k}={v}" for k, v in GAME.items()]]
    print("+", " ".join(cmd[:6]), "...")
    subprocess.run(cmd, check=True)


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


def canon(p: dict) -> tuple:
    return min((tuple(sorted(t[s] for s in p["blue"])), tuple(sorted(t[s] for s in p["red"]))) for t in SYM)


def order(p: dict) -> str:
    return hashlib.sha256(f"{SEED}:{p['index']}".encode()).hexdigest()


def main() -> None:
    DATA.mkdir(exist_ok=True)
    tb = DATA / "tb.bin"
    if not tb.exists():
        solver("solve", f"out={tb}")

    raw = DATA / "puzzles.jsonl"
    solver("puzzles", f"tb={tb}", f"out={raw}", f"per={3 * (POOL + PRACTICE)}", f"seed={SEED}", "rootmax=1", "pvmax=2", f"dmax={max(TIERS)}")

    seen, by_depth = set(), {}
    for line in raw.read_text().splitlines():
        p = json.loads(line)
        c = canon(p)
        if c in seen:
            continue
        seen.add(c)
        by_depth.setdefault(p["depth"], []).append((p, line))

    scored, practice = [], []
    for depth in TIERS:
        items = sorted(by_depth.get(depth, []), key=lambda it: order(it[0]))
        if len(items) < POOL + PRACTICE:
            raise SystemExit(f"depth {depth}: only {len(items)} distinct sharp puzzles, need {POOL + PRACTICE}")
        scored += [line for _, line in items[:POOL]]
        practice += [line for _, line in items[POOL : POOL + PRACTICE]]

    packs = SERVER / "packs"
    packs.mkdir(parents=True, exist_ok=True)
    for name, lines in (("scored", scored), ("practice", practice)):
        sel = DATA / f"{name}_selected.jsonl"
        sel.write_text("\n".join(lines) + "\n", newline="\n")
        solver("pack", f"tb={tb}", f"in={sel}", f"out={packs / (name + '.jsonl')}", f"slack={SLACK}")

    # The oracle's book: the fastest winning move in every position of the scored pool.
    book = {}
    for line in (packs / "scored.jsonl").read_text().splitlines():
        for pos, entries in json.loads(line)["nodes"].items():
            wins = [e for e in entries if e[2] >= 128]
            if wins:
                f, t = min(wins, key=lambda e: (e[2], e[0], e[1]))[:2]
                book[pos] = "abcde"[f % 5] + str(f // 5 + 1) + "-" + "abcde"[t % 5] + str(t // 5 + 1)
    (TASK / "solution" / "book.json").write_text(json.dumps(book, separators=(",", ":")), newline="\n")

    manifest = {
        "game": GAME,
        "tiers": TIERS,
        "win_in": [(d + 1) // 2 for d in TIERS],
        "per_tier": PER_TIER,
        "slack": SLACK,
        "pool_per_tier": POOL,
        "practice_per_tier": PRACTICE,
        "build_seed": SEED,
        "tablebase_sha256": hashlib.sha256(tb.read_bytes()).hexdigest(),
    }
    for dest in (packs / "manifest.json", TASK / "tests" / "manifest.json"):
        dest.write_text(json.dumps(manifest, indent=2) + "\n", newline="\n")

    # Vendored game code. The agent's own container gets none of it.
    for dest, modules in ((SERVER / "thinice", ("__init__", "board", "session")), (TASK / "solution" / "thinice", ("__init__", "board", "search"))):
        dest.mkdir(parents=True, exist_ok=True)
        for mod in modules:
            shutil.copyfile(ROOT / "thinice" / f"{mod}.py", dest / f"{mod}.py")

    key_file = SERVER / "receipt.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32) + "\n", newline="\n")
    shutil.copyfile(key_file, TASK / "tests" / "receipt.key")

    size = sum(f.stat().st_size for f in packs.iterdir()) / 1e6
    print(f"scored pool {len(scored)}, practice pool {len(practice)}, book {len(book)} positions, packs {size:.1f} MB")


if __name__ == "__main__":
    main()
