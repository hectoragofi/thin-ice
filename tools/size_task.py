"""Runs the tools-only reference player (task/solution/toolplay.py) on every puzzle of the
scored pool, in-process, and reports per depth how often it wins and how many tool calls it
needs. The in-process transport answers each call with the same functions the game server
uses (thinice.explore for look-ahead, thinice.session for play), so call counts are the
ones a run against the real server produces.

    python tools/size_task.py [max_win] [call_budget]           # report only
    python tools/size_task.py 6 50 --write                      # keep only what it wins

With --write, the scored pool is cut to the puzzles of win in 1..max_win that this player wins
within call_budget tool calls, and the manifest, the oracle's book and the vendored copies are
rewritten to match. Every scored puzzle is then provably winnable with the agent's own tools.
Running it again on the cut pool keeps the same puzzles (the player is deterministic).
"""
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "task" / "solution"))  # toolplay.py (it imports no game code)
sys.path.insert(0, str(ROOT))
from thinice.explore import lines as explore_lines  # noqa: E402
from thinice.board import move_name  # noqa: E402
from thinice.session import Run, load_pack  # noqa: E402
import toolplay  # noqa: E402

PACKS = ROOT / "task" / "environment" / "game-server" / "packs"


class LocalTools(toolplay.Tools):
    def __init__(self, run: Run):
        super().__init__("in-process")
        self.run = run

    def _call(self, method, path, body=None):
        self.calls += 1
        if path == "/api/puzzles":
            return self.run.scorecard()
        if path.startswith("/api/puzzle/"):
            return {"ok": True, **self.run.get(path.rsplit("/", 1)[1]).view()}
        if path == "/api/move":
            att = self.run.get(body["id"])
            out = att.move(body["move"])
            return {"ok": True, **out, "puzzle": att.view()}
        if path == "/api/explore":
            att = self.run.get(body["id"])
            assert att.status == "open"
            return {"ok": True, "results": explore_lines(att.blue, att.red, body["lines"])}
        raise KeyError(path)


def main() -> None:
    max_win = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    budget = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    pool = [p for p in load_pack(PACKS / "scored.jsonl") if p.need <= max_win]
    rows = []
    for p in pool:
        run = Run([p], [])
        tools = LocalTools(run)
        t0 = time.monotonic()
        r = toolplay.play_puzzle(tools, "P01", budget, 600)
        r.update(win_in=p.need, index=p.index, wall=round(time.monotonic() - t0, 2))
        rows.append(r)
        print(json.dumps(r), flush=True)
    print("\nwin_in  won/total  calls (won: median, max)  lines (won: median, max)")
    for n in sorted({r["win_in"] for r in rows}):
        rs = [r for r in rows if r["win_in"] == n]
        ok = [r for r in rs if r["status"] == "solved"]
        c = [r["calls"] for r in ok] or [0]
        ln = [r["lines"] for r in ok] or [0]
        print(f"{n:>6}  {len(ok):>3}/{len(rs):<5}  {statistics.median(c):>6} {max(c):>6}  {statistics.median(ln):>8} {max(ln):>6}")
    if "--write" in sys.argv:
        write(rows, max_win, budget)


def write(rows: list, max_win: int, budget: int) -> None:
    keep = {r["index"] for r in rows if r["status"] == "solved"}
    lines = [ln for ln in (PACKS / "scored.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    kept = [ln for ln in lines if json.loads(ln)["index"] in keep]
    manifest = json.loads((PACKS / "manifest.json").read_text())
    tiers = [2 * n - 1 for n in range(1, max_win + 1)]
    sizes = {}
    for n in range(1, max_win + 1):
        won = [r for r in rows if r["win_in"] == n and r["status"] == "solved"]
        if len(won) < manifest["per_tier"]:
            raise SystemExit(f"win in {n}: only {len(won)} puzzles within {budget} calls; need {manifest['per_tier']}")
        sizes[str(n)] = {
            "scored": len(won),
            "practice": manifest["pool"][str(n)]["practice"],
            "tools_reference_calls_max": max(r["calls"] for r in won),
            "tools_reference_calls_median": statistics.median(r["calls"] for r in won),
        }
    manifest.update(tiers=tiers, win_in=list(range(1, max_win + 1)), pool=sizes, tools_reference={"call_budget": budget, "max_win": max_win})
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
    print(f"kept {len(kept)} of {len(lines)} scored puzzles; tiers win in 1..{max_win}; book {len(book)} positions")


if __name__ == "__main__":
    main()
