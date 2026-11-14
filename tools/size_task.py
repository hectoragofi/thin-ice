"""Sizes the task with the tools-only reference player (task/solution/toolplay.py).

The player runs in-process, through the same functions the game server answers with
(thinice.explore for look-ahead, thinice.session for play and for the look-ahead budget), so
the explored-position counts are the ones a run against the real server produces.

    python tools/size_task.py measure --horizon 2 --max-win 10        # per-puzzle cost table
    python tools/size_task.py write --horizon 2 --max-win 10 --cap 3:200,... --per-tier 1:1,...

`write` keeps the puzzles of the full pool (tools/pool/scored_all.jsonl, the solver's original
pool) that the player wins within the per-depth cap, and rewrites the scored pack, the
manifest, the oracle's book and the vendored copies. Every scored puzzle is then won by a
player that uses only the agent's own tools within its share of the budget.
"""
import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "task" / "solution"))  # toolplay.py (it imports no game code)
sys.path.insert(0, str(ROOT))
from thinice.board import move_name  # noqa: E402
from thinice.explore import lines as explore_lines  # noqa: E402
from thinice.session import GameError, Run, load_pack  # noqa: E402
import toolplay  # noqa: E402

PACKS = ROOT / "task" / "environment" / "game-server" / "packs"
SOURCE = ROOT / "tools" / "pool" / "scored_all.jsonl"


class LocalTools(toolplay.Tools):
    """The agent's tools, answered in-process by the server's own functions."""

    def __init__(self, run: Run):
        super().__init__("in-process")
        self.run = run

    def _call(self, method, path, body=None):
        self.calls += 1
        if path == "/api/puzzles":
            card = self.run.scorecard()
            return {**card, "explore_left": self.run.explore_left()}
        if path.startswith("/api/puzzle/"):
            return {"ok": True, **self.run.get(path.rsplit("/", 1)[1]).view()}
        if path == "/api/move":
            att = self.run.get(body["id"])
            out = att.move(body["move"])
            return {"ok": True, **out, "puzzle": att.view()}
        if path == "/api/explore":
            att = self.run.get(body["id"])
            assert att.status == "open"
            try:
                self.run.charge(len(body["lines"]))
            except GameError as exc:
                raise toolplay.BudgetRefused(str(exc)) from None
            return {"ok": True, "budget_left": self.run.explore_left(), "results": explore_lines(att.blue, att.red, body["lines"])}
        raise KeyError(path)


def measure(pool: list, horizon: int, caps: dict) -> list:
    rows = []
    for p in pool:
        tools = LocalTools(Run([p], []))
        r = toolplay.play_puzzle(tools, "P01", 600.0, caps.get(p.need), horizon)
        r.update(win_in=p.need, index=p.index)
        rows.append(r)
    return rows


def table(rows: list) -> None:
    print("win_in  won/total  positions (won: median, p90, max)")
    for n in sorted({r["win_in"] for r in rows}):
        rs = [r for r in rows if r["win_in"] == n]
        ok = sorted(r["lines"] for r in rs if r["status"] == "solved") or [0]
        lost = sum(r["status"] == "failed" for r in rs)
        p90 = ok[min(len(ok) - 1, int(0.9 * len(ok)))]
        print(f"{n:>6}  {sum(r['status'] == 'solved' for r in rs):>3}/{len(rs):<4} {statistics.median(ok):>7} {p90:>6} {max(ok):>6}" + (f"   lost by a wrong move: {lost}" if lost else ""))


def write(rows: list, args, per_tier: dict, caps: dict) -> None:
    keep = {r["index"] for r in rows if r["status"] == "solved"}
    lines = [ln for ln in SOURCE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    kept = [ln for ln in lines if json.loads(ln)["index"] in keep and (json.loads(ln)["depth"] + 1) // 2 in per_tier]
    manifest = json.loads((PACKS / "manifest.json").read_text())
    full = json.loads(subprocess.run(["git", "show", "d9a11e9:task/environment/game-server/packs/manifest.json"], capture_output=True, text=True, cwd=ROOT).stdout)
    sizes = {}
    for n, want in sorted(per_tier.items()):
        won = [r for r in rows if r["win_in"] == n and r["status"] == "solved"]
        if len(won) < want:
            raise SystemExit(f"win in {n}: only {len(won)} puzzles won within the cap; need {want}")
        cost = sorted(r["lines"] for r in won)
        sizes[str(n)] = {
            "scored": len(won),
            "practice": full["pool"][str(n)]["practice"],
            "reference_positions_median": statistics.median(cost),
            "reference_positions_max": cost[-1],
        }
    manifest.update(
        tiers=[2 * n - 1 for n in sorted(per_tier)],
        win_in=sorted(per_tier),
        per_tier={str(n): c for n, c in sorted(per_tier.items())},
        pool=sizes,
        explore_budget=args.budget,
        top_depth=args.top or max(per_tier),
        tools_reference={"mode": toolplay.MODE, "horizon": args.horizon, "min_check": toolplay.MIN_CHECK, "quiet_depth": toolplay.QUIET_DEPTH, "cap": {str(k): v for k, v in caps.items()}},
    )
    nl = chr(10)
    (PACKS / "scored.jsonl").write_text(nl.join(kept) + nl, encoding="utf-8", newline=nl)
    (PACKS / "manifest.json").write_text(json.dumps(manifest, indent=2) + nl, encoding="utf-8", newline=nl)
    book = {}
    for ln in kept:
        for pos, entries in json.loads(ln)["nodes"].items():
            wins = [e for e in entries if e[2] >= 128]
            if wins:
                book[pos] = move_name(min(wins, key=lambda e: (e[2], e[0], e[1])))
    (ROOT / "task" / "solution" / "book.json").write_text(json.dumps(book, separators=(",", ":")), encoding="utf-8", newline=nl)
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_task.py"), "--vendor-only"], check=True)
    print(f"kept {len(kept)} of {len(lines)} puzzles; tiers {sorted(per_tier)}; book {len(book)} positions")


def parse_map(text: str) -> dict:
    return {int(a): int(b) for a, b in (p.split(":") for p in filter(None, text.split(",")))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["measure", "write"])
    ap.add_argument("--horizon", type=int, default=toolplay.HORIZON)
    ap.add_argument("--max-win", type=int, default=10)
    ap.add_argument("--min-win", type=int, default=1)
    ap.add_argument("--cap", default="", help="most explored positions per puzzle, by win-in, like 3:150,4:300")
    ap.add_argument("--per-tier", default="", help="scored puzzles per run, by win-in, like 1:1,4:2 (write)")
    ap.add_argument("--budget", type=int, default=0, help="default look-ahead budget (write)")
    ap.add_argument("--top", type=int, default=0, help="default top depth (write); deeper tiers only with THINICE_TOP_DEPTH")
    ap.add_argument("--json", default="", help="also save per-puzzle rows here")
    args = ap.parse_args()
    caps = parse_map(args.cap)
    pool = [p for p in load_pack(SOURCE) if args.min_win <= p.need <= args.max_win]
    rows = measure(pool, args.horizon, caps)
    if args.json:
        Path(args.json).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    table(rows)
    if args.mode == "write":
        write(rows, args, parse_map(args.per_tier), caps)


if __name__ == "__main__":
    main()
