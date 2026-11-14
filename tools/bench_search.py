"""Checks the Python rules against the solver's output and times the rules-only search per depth.

usage: python tools/bench_search.py data/puz_strict.jsonl [per_depth] [time_limit_seconds]
"""
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from thinice.board import mask_of, moves  # noqa: E402
from thinice.search import find_win  # noqa: E402

path = sys.argv[1]
per = int(sys.argv[2]) if len(sys.argv) > 2 else 5
limit = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0

by_depth = defaultdict(list)
for line in open(path):
    p = json.loads(line)
    by_depth[p["depth"]].append(p)

print(f"{'depth':>5} {'moves':>5} {'solved':>7} {'median s':>9} {'max s':>8} {'median nodes':>13}")
for depth in sorted(by_depth):
    times, nodes, solved = [], [], 0
    for p in by_depth[depth][:per]:
        blue, red = mask_of(p["blue"]), mask_of(p["red"])
        assert len(moves(blue, blue | red)) == p["legal"], "move generator disagrees with the solver"
        need = (depth + 1) // 2
        t0 = time.perf_counter()
        mv, n, nn = find_win(blue, red, need, limit)
        times.append(time.perf_counter() - t0)
        nodes.append(nn)
        if mv is not None:
            assert n == need, f"search found a win in {n}, tablebase says {need}"
            assert list(mv) == p["pv"][0], "search and tablebase disagree on a unique winning move"
            solved += 1
    print(f"{depth:>5} {(depth + 1) // 2:>5} {solved:>3}/{len(times):<3} {statistics.median(times):>9.2f} {max(times):>8.2f} {int(statistics.median(nodes)):>13}")
