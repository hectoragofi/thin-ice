"""Builds everything the Harbor task ships, from the exhaustive solver's output.

    python tools/build_task.py                 # the published puzzle pools
    python tools/build_task.py --seed 12345    # fresh pools (puzzles nobody has seen)
    python tools/build_task.py --labels 20000  # also export training labels (positions per depth)

Steps: solve the game if the table is missing -> extract candidate puzzles per depth -> pack
every position Blue can reach in each one -> choose pools that share no position at all ->
write the oracle's book, the manifest, the vendored game code and the receipt key.

"Share no position" is strict. Two puzzles conflict if any position reachable in one equals any
position reachable in the other, up to rotation and reflection of the board. All chosen puzzles
are mutually disjoint, scored and practice alike, so nothing learned in practice, and nothing
seen while playing one scored puzzle, gives away a move in another.

Sliding moves merge positions, so long forced wins run along a limited number of independent
lines. Deep tiers therefore have smaller pools (the manifest lists the sizes).

The board size comes from THINICE_W / THINICE_H. Solving the published 7x6 board needs about
17 GB of memory; tools/modal_build.py runs this script on a cloud machine.
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# The board size must be fixed before the rules module is imported: it is what we are building.
os.environ.setdefault("THINICE_W", "7")
os.environ.setdefault("THINICE_H", "6")
from thinice.board import H, W, canonical, move_name  # noqa: E402

DATA = Path(os.environ.get("THINICE_DATA", ROOT / "data" / f"{W}x{H}"))
TASK = ROOT / "task"
SERVER = TASK / "environment" / "game-server"
SOLVER = Path(os.environ.get("THINICE_SOLVER", ROOT / "solver" / "target" / "release" / ("thinice-solver.exe" if sys.platform == "win32" else "thinice-solver")))

GAME = {"w": W, "h": H, "sb": 4, "sr": 4, "k": 3, "dirs": 8, "slide": 1}
PER_TIER = 2  # scored puzzles per tier in one run
POOL = 30  # most scored puzzles per tier (the run seed picks PER_TIER of them)
PRACTICE = 20  # most practice puzzles per tier
EVAL = 50  # puzzles per tier in the separate pool used to evaluate trained models
SLACK = 1  # extra Blue moves allowed beyond the fastest win
DEEP = 13  # from this depth on, independent puzzles are scarce and need a wider search
SEED = 20261114


def solver(*args: str) -> None:
    cmd = [str(SOLVER), *args, *[f"{k}={v}" for k, v in GAME.items()]]
    print("+", " ".join(cmd[1:3]), "...", flush=True)
    done = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if done.returncode:
        raise SystemExit(f"solver failed ({done.returncode}):\n" + "\n".join(done.stderr.splitlines()[-8:]))


def forms(line: str) -> frozenset:
    """Every position reachable in a packed puzzle, in canonical form."""
    out = set()
    for pos in json.loads(line)["nodes"]:
        b, r = pos.split("|")
        out.add(canonical(json.loads(b), json.loads(r)))
    return frozenset(out)


def depth_of(line: str) -> int:
    return int(line.split('"depth":', 1)[1].split(",", 1)[0])


def order(line: str) -> str:
    index = line.split('"index":', 1)[1].split(",", 1)[0]
    return hashlib.sha256(f"{SEED}:{index}".encode()).hexdigest()


def candidates(tb: Path, name: str, seed: int, rootmax: int, pvmax: int, per: int, per_deep: int, tiers: list) -> dict:
    """Extracts and packs candidate puzzles; returns {depth: [(packed line, positions), ...]}."""
    raw, packed = DATA / f"{name}_raw.jsonl", DATA / f"{name}_packed.jsonl"
    parts = []
    for lo, hi, n in ((1, DEEP - 2, per), (DEEP, max(tiers), per_deep)):
        part = DATA / f"{name}_raw_{lo}.jsonl"
        solver("puzzles", f"tb={tb}", f"out={part}", f"per={n}", f"seed={seed}", f"rootmax={rootmax}", f"pvmax={pvmax}", f"dmin={lo}", f"dmax={hi}")
        parts.append(part.read_text())
    raw.write_text("".join(parts))
    solver("pack", f"tb={tb}", f"in={raw}", f"out={packed}", f"slack={SLACK}")
    by_depth: dict = {}
    with open(packed, encoding="utf-8") as fh:
        for line in sorted(fh.read().splitlines(), key=order):
            by_depth.setdefault(depth_of(line), []).append((line, forms(line)))
    return by_depth


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def vendor() -> None:
    """Copies the game code, the manifest and the receipt key to the places the task needs them.

    The agent's own container gets none of this.
    """
    for dest, modules in ((SERVER / "thinice", ("__init__", "board", "session", "explore")), (TASK / "solution" / "thinice", ("__init__", "board", "search"))):
        dest.mkdir(parents=True, exist_ok=True)
        for mod in modules:
            shutil.copyfile(ROOT / "thinice" / f"{mod}.py", dest / f"{mod}.py")
    manifest = SERVER / "packs" / "manifest.json"
    for dest in (TASK / "tests" / "manifest.json", TASK / "solution" / "manifest.json"):
        shutil.copyfile(manifest, dest)
    key_file = SERVER / "receipt.key"
    if not key_file.exists():
        write(key_file, secrets.token_hex(32) + "\n")
    shutil.copyfile(key_file, TASK / "tests" / "receipt.key")


def main() -> None:
    global SEED
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--max-win", type=int, default=16, help="deepest tier: a forced win in this many moves")
    ap.add_argument("--labels", type=int, default=0, help="also export this many training positions per depth")
    ap.add_argument("--vendor-only", action="store_true", help="only refresh the copies of code, manifest and key inside task/")
    args = ap.parse_args()
    if args.vendor_only:
        vendor()
        return
    SEED = args.seed
    tiers = [2 * n - 1 for n in range(1, args.max_win + 1)]  # plies to the fastest forced win

    DATA.mkdir(parents=True, exist_ok=True)
    tb = DATA / "tb.bin"
    if not tb.exists():
        solver("solve", f"out={tb}")

    # Scored and practice puzzles have exactly one winning first move.
    main_line = candidates(tb, "unique", SEED, rootmax=1, pvmax=6, per=300, per_deep=1500, tiers=tiers)

    # Round-robin, deepest tier first, so the scarce deep lines are shared out evenly.
    chosen = {d: [] for d in tiers}
    cursor = {d: 0 for d in tiers}
    taken: set = set()
    progress = True
    while progress:
        progress = False
        for depth in reversed(tiers):
            if len(chosen[depth]) >= POOL + PRACTICE:
                continue
            cands = main_line.get(depth, [])
            i = cursor[depth]
            while i < len(cands):
                line, pos = cands[i]
                i += 1
                if not (pos & taken):
                    chosen[depth].append(line)
                    taken |= pos
                    progress = True
                    break
            cursor[depth] = i

    scored, practice, sizes = [], [], {}
    for depth in tiers:
        n = len(chosen[depth])
        n_scored = min(POOL, max(PER_TIER, round(n * 0.75)))
        n_practice = min(PRACTICE, n - n_scored)
        if n < PER_TIER + 1:
            raise SystemExit(f"tier {(depth + 1) // 2}: only {n} independent puzzles, cannot fill a run; lower --max-win")
        scored += chosen[depth][:n_scored]
        practice += chosen[depth][n_scored : n_scored + n_practice]
        sizes[str((depth + 1) // 2)] = {"scored": n_scored, "practice": n_practice}

    all_forms = [forms(line) for line in scored + practice]
    assert sum(map(len, all_forms)) == len(set().union(*all_forms)), "two chosen puzzles share a position"

    packs = SERVER / "packs"
    write(packs / "scored.jsonl", "\n".join(scored) + "\n")
    write(packs / "practice.jsonl", "\n".join(practice) + "\n")

    # A larger pool of very sharp puzzles, used only to evaluate trained models (training/).
    strict = candidates(tb, "strict", SEED + 2, rootmax=1, pvmax=2, per=EVAL + 20, per_deep=EVAL + 20, tiers=tiers)
    evals = [line for depth in tiers for line, _ in strict.get(depth, [])[:EVAL]]
    write(ROOT / "training" / "eval_pool.jsonl", "\n".join(evals) + "\n")

    # The oracle's book: the fastest winning move in every position of the scored pool.
    book = {}
    for line in scored:
        for pos, entries in json.loads(line)["nodes"].items():
            wins = [e for e in entries if e[2] >= 128]
            if wins:
                book[pos] = move_name(min(wins, key=lambda e: (e[2], e[0], e[1])))
    write(TASK / "solution" / "book.json", json.dumps(book, separators=(",", ":")))

    manifest = {
        "game": GAME,
        "tiers": tiers,
        "win_in": [(d + 1) // 2 for d in tiers],
        "per_tier": PER_TIER,
        "slack": SLACK,
        "pool": sizes,
        "build_seed": SEED,
        "positions": int(tb.stat().st_size),
    }
    write(packs / "manifest.json", json.dumps(manifest, indent=2) + "\n")

    vendor()

    if args.labels:
        # Shallow positions get more examples: seeing a win in one or two is the base skill.
        outs = []
        for lo, hi, n in ((1, 3, args.labels * 6), (5, 7, args.labels * 3), (9, max(tiers), args.labels)):
            part = DATA / f"labels_{lo}.jsonl"
            solver("labels", f"tb={tb}", f"out={part}", f"per={n}", f"seed={SEED + 7}", f"dmin={lo}", f"dmax={hi}")
            outs.append(part.read_text())
        (DATA / "labels.jsonl").write_text("".join(outs))

    size = sum(f.stat().st_size for f in packs.iterdir()) / 1e6
    print(f"scored pool {len(scored)}, practice pool {len(practice)}, eval pool {len(evals)}, book {len(book)} positions, packs {size:.1f} MB")
    print("pool sizes by tier (win in N):", " ".join(f"{k}:{v['scored']}+{v['practice']}" for k, v in sizes.items()))


if __name__ == "__main__":
    main()
