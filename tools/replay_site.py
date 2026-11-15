"""Builds one self-contained demo page for every final run: what the game is, what was tested, what happened,
and a replay of any attempt move by move with the solver's verdict.

    python tools/replay_site.py                  # writes demo/replays.html
    python tools/replay_site.py out.html         # or somewhere else

Models are a label plus job-name patterns under jobs/final (see MODELS). For every trial:
  verifier/details.json   the signed score sheet (no usable sheet: the attempt is excluded)
  exception.txt           an API error ended the session; with puzzles still open the attempt is excluded
  result.json             agent_result.cost_usd, the harness's cost estimate
Excluded attempts are left out of every mean, listed in the page and printed here.

Each move is graded by `frames` (tools/replay.py). After a losing move, Red's winning line is found with the
rules-only search in thinice/search.py (Red attacking, Blue choosing the longest resistance), under a fixed
node budget so the output is the same on every run. The data is baked into the page; the one external
resource is the Google Fonts stylesheet of the presentation deck (offline: Georgia, Arial, Courier New).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from analyze import diagnose  # noqa: E402
from replay import frames  # noqa: E402
from thinice.board import FILES, H, W, completes_line, mask_of, move_name, moves, parse_move, squares  # noqa: E402
from thinice.search import Searcher, Timeout  # noqa: E402

JOBS = ROOT / "jobs" / "final"
# slug, label, short, maker, kind, actor (who plays Blue, for sentences), job-name patterns
MODELS = [
    ("argon", "Gemini 4 Argon", "Argon", "Gemini", "model", "The AI", ["clock-24d6707-argon-x3*"]),
    ("carbon", "Gemini 4 Carbon", "Carbon", "Gemini", "model", "The AI", ["clock-24d6707-carbon-x3*"]),
    ("hydrogen", "Gemini 4 Hydrogen", "Hydrogen", "Gemini", "model", "The AI", ["clock-24d6707-hydrogen-x3*"]),
    ("flash38", "Gemini 3.8 Flash", "3.8 Flash", "Gemini", "model", "The AI", ["clock-24d6707-flash38-x3*"]),
    ("pro31", "Gemini 3.1 Pro", "3.1 Pro", "Gemini", "model", "The AI", ["clock-24d6707-pro31-x3*"]),
    ("haiku55", "Claude Haiku 5.5", "Haiku 5.5", "Claude", "model", "The AI", ["clock-24d6707-haiku55-x1", "clock-24d6707-haiku55-x2b"]),
    ("sonnet5", "Claude Sonnet 5", "Sonnet 5", "Claude", "model", "The AI", ["clock-24d6707-sonnet5-x1", "clock-24d6707-sonnet5-x2b"]),
    ("opus55", "Claude Opus 5.5", "Opus 5.5", "Claude", "model", "The AI", ["clock-24d6707-opus55-x*"]),
    ("nemotron3-ultra", "Nemotron 3 Ultra", "Nemotron 3 Ultra", "NVIDIA", "model", "The AI", ["nim-24d6707-nemotron3-ultra-x*"]),
    ("reference", "Perfect play (solver)", "Perfect play", "Reference", "ref", "The solver", ["clock-24d6707-reference"]),
    ("reference-search", "Rules-only search, 20 s per puzzle", "Rules-only search", "Reference", "ref", "The search", ["clock-24d6707-reference-search"]),
    ("stop-early", "Baseline: stop early (2 easiest)", "Stop early", "Reference", "base", "The baseline", ["clock-24d6707-stop-early"]),
    ("do-nothing", "Baseline: do nothing", "Do nothing", "Reference", "base", "The baseline", ["clock-24d6707-do-nothing"]),
]
NODE_BUDGET = 400_000  # per position searched for Red's winning line; fixed so the output is deterministic


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


# ---------------------------------------------------------------- Red's winning line after a losing move
class Budget(Searcher):
    def __init__(self, budget: int):
        super().__init__(None)
        self.budget = budget

    def _tick(self) -> None:
        self.nodes += 1
        if self.nodes > self.budget:
            raise Timeout


LINES: dict = {}
LINE_STATS = {"found": 0, "not found": 0}


def red_line(blue: int, red: int, k: int):
    """Red to move and the solver says Red wins in k. Returns Red's line [(side, from, to), ...] to three in a row,
    Blue answering with the reply that holds out longest, or None if the budgeted search cannot prove it."""
    key0 = (blue, red, k)
    if key0 in LINES:
        return LINES[key0]
    s, line, b, r, out = Budget(NODE_BUDGET), [], blue, red, None
    try:
        while True:
            mv = next((m for n in range(1, k + 1) for m in [s.attack(r, b, n)] if m), None)
            if mv is None:
                break
            f, t = mv
            r ^= (1 << f) | (1 << t)
            line.append(("Red", f, t))
            if completes_line(r, t):
                out = line
                break
            best = None
            replies = moves(b, b | r)
            if not replies:
                out = line  # Blue cannot move and loses
                break
            for bf, bt in replies:
                nb = b ^ (1 << bf) ^ (1 << bt)
                if completes_line(nb, bt):
                    best = None
                    break
                need = next((n for n in range(1, k + 1) if s.attack(r, nb, n)), None)
                if need is None:
                    best = None
                    break
                if best is None or need > best[0]:
                    best = (need, bf, bt)
            if best is None:
                break
            k, bf, bt = best
            b ^= (1 << bf) | (1 << bt)
            line.append(("Blue", bf, bt))
    except Timeout:
        out = None
    LINES[key0] = out
    return out


# ---------------------------------------------------------------- one puzzle of one attempt
def plain(fr: dict, win_in: int) -> str:
    """Verdict text in plain words, from the facts frames() put in its text."""
    k, t = fr["kind"], fr["text"]
    if k == "start":
        return f"Blue to move. Blue can force a win in {plural(win_in, 'move')}, whatever Red does."
    if k == "reply":
        return "Red's best defence: the reply that holds out longest."
    if k == "good":
        if "Solved" in t:
            return "Three in a row. Puzzle won."
        m = re.search(r"\((\d+) of (\d+) legal", t)
        return f"Still a guaranteed win. {m[1]} of {m[2]} possible moves kept it." if m else "Still a guaranteed win."
    if "move" not in fr:
        return "Blue was still winning, but too slowly: the allowed moves ran out."
    m = re.search(r"Winning: (.*?) \((\d+) of (\d+)\)", t)
    alt = ""
    if m:
        first = m[1].split()[0]
        alt = f" {first} would have won ({m[2]} of {m[3]} possible moves did)."
    if "draw" in t:
        return "With best play the game is now a draw." + alt
    r = re.search(r"Red wins in (\d+)", t)
    n = int(r[1]) if r else None
    return (f"Red can now force a win in {plural(n, 'move')}." if n else "The win is gone.") + alt


def state(row: dict) -> str:
    if row["status"] == "solved":
        return "solved"
    if row["status"] == "open":
        return "open"
    reason = row.get("reason") or ""
    if reason == "out of time":
        return "time"
    if reason == "skipped":
        return "skipped"
    if reason == "out of moves":
        return "slow"
    return "lost"


def cell(row: dict) -> dict:
    fs = frames(row)
    names = iter([m for pair in row["history"] for m in pair if m])
    for fr in fs:
        if "move" in fr:
            fr["name"] = next(names)
            fr["side"] = "Red" if fr["kind"] == "reply" else "Blue"
    st = state(row)
    for fr in fs:
        if fr["kind"] == "good":
            fr["verb"] = "wins" if "Solved" in fr["text"] else "keeps the win"
        elif fr["kind"] == "bad" and "move" in fr:
            fr["verb"] = "throws the win away"
        elif fr["kind"] == "bad":
            fr["title"] = "Out of moves"
        say = plain(fr, row["win_in"])
        if fr["kind"] == "bad" and "move" in fr:
            m = re.search(r"Winning: (\S+)", fr["text"])
            if m:
                fr["alt"] = list(parse_move(m[1]))
                fr["alt_name"] = m[1]
            r = re.search(r"Red wins in (\d+)", fr["text"])
            if r:
                fr["red_in"] = int(r[1])
        fr["text"] = say
    last = fs[-1]
    end = {"time": "The puzzle clock ran out before Blue finished. The puzzle counts as lost.",
           "skipped": "The AI gave up this puzzle. It counts as lost."}
    if st in end:
        fs.append({"blue": last["blue"], "red": last["red"], "kind": "bad", "title": "Ran out of time" if st == "time" else "Gave up", "text": end[st]})
    elif st == "open" and not row["history"]:
        fs[0]["text"] = "This attempt ended before reaching this puzzle."
        fs[0]["title"] = "Not reached"
    elif st == "open":
        fs.append({"blue": last["blue"], "red": last["red"], "kind": "bad", "title": "Not finished", "text": "The attempt ended before this puzzle was finished."})
    bad = next((i for i, fr in enumerate(fs) if fr["kind"] == "bad"), None)
    line_at = None
    if bad is not None and fs[bad].get("red_in"):
        b, r = mask_of(fs[bad]["blue"]), mask_of(fs[bad]["red"])
        line = red_line(b, r, fs[bad]["red_in"])
        LINE_STATS["found" if line else "not found"] += 1
        if line:
            line_at = len(fs)
            for i, (side, f, t) in enumerate(line):
                if side == "Red":
                    r ^= (1 << f) | (1 << t)
                else:
                    b ^= (1 << f) | (1 << t)
                done = i == len(line) - 1
                fs.append({"blue": squares(b), "red": squares(r), "kind": "line", "side": side, "move": [f, t], "name": move_name((f, t)),
                           "text": ("Red completes three in a row. " if done and side == "Red" else
                                    "Blue's longest resistance. " if side == "Blue" else "How Red now wins. ")
                           + "The solver's line, not played: the puzzle ended at Blue's losing move."})
    g = diagnose(row)
    return {"state": st, "bad": bad, "line": line_at, "moves_used": row["moves_used"], "moves_allowed": row["moves_allowed"],
            "diag": g["kind"] if g else None, "frames": fs}


# ---------------------------------------------------------------- rules demo for the opening and the tour
def demo() -> dict:
    from thinice.board import parse_sq
    blue = mask_of(parse_sq(s) for s in ("a4", "b1", "c1", "g1"))
    red = mask_of(parse_sq(s) for s in ("d4", "f6", "e3", "b6"))
    fs = [{"blue": squares(blue), "red": squares(red), "kind": "demo", "title": "Four stones each",
           "text": "Blue and Red each have 4 stones on a 7 by 6 board. They take turns, one stone per turn."}]
    titles = ["A stone slides until something stops it", "Red moves the same way", "Three in a row wins"]
    steps = [("Blue", "a4-c4", "A stone slides in a straight line, in any of 8 directions, and cannot stop early. Red's stone on d4 stops this one on c4."),
             ("Red", "b6-e6", "Red moves the same way. The stone on f6 stops it on e6."),
             ("Blue", "g1-d1", "Three in a row wins. The stone on c1 stops this slide on d1, and b1, c1, d1 are three in a row.")]
    for side, mv, text in steps:
        f, t = parse_move(mv)
        mine, other = (blue, red) if side == "Blue" else (red, blue)
        assert (f, t) in moves(mine, blue | red), mv
        if side == "Blue":
            blue ^= (1 << f) | (1 << t)
        else:
            red ^= (1 << f) | (1 << t)
        win = completes_line(blue if side == "Blue" else red, t)
        assert win == (mv == "g1-d1"), mv
        fs.append({"blue": squares(blue), "red": squares(red), "kind": "good" if win else "demo", "side": side, "move": [f, t], "name": mv, "text": text,
                   "title": titles[len(fs) - 1], "verb": "wins" if win else ""})
    return {"state": "solved", "bad": None, "line": None, "frames": fs}


# ---------------------------------------------------------------- small-model training curves (results/)
def learning() -> dict:
    out = {}
    for key, rel, xk in (("imitation", "results/curve-qwen3-0.6b-7x6.json", "examples_seen"),
                         ("reward", "results/curve-rl-qwen3-0.6b-7x6.json", "moves_played")):
        f = ROOT / rel
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"learning: {rel} missing or unreadable, left out")
            continue
        pts = []
        for h in d.get("history", []):
            bw = h.get("by_win_in") or {}
            tiers = [bw.get(str(t), 0.0) for t in range(1, 7)]
            y = h["six_tier"] if h.get("six_tier") is not None else sum(tiers) / 6
            pts.append({"x": h.get(xk) or 0, "y": round(y, 4), "tiers": tiers, "legal": round(h.get("legal_rate") or 0, 4)})
        if len(pts) >= 2:
            out[key] = {"source": rel, "model": d.get("model"), "points": pts}
    # the like-for-like frontier number: the same one-move-per-call probe (results/probe/)
    probe = []
    for slug, label in (("argon", "Gemini 4 Argon"), ("carbon", "Gemini 4 Carbon"), ("hydrogen", "Gemini 4 Hydrogen")):
        f = ROOT / "results" / "probe" / f"gemini-4-{slug}.summary.json"
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            probe.append({"label": label, "score": s["score_these_tiers"], "per_tier": s.get("per_tier")})
        except (OSError, ValueError, KeyError):
            print(f"learning: {f.relative_to(ROOT)} missing, left out")
    out["probe"] = probe
    return out


# ---------------------------------------------------------------- collect every attempt
def cost_of(t: Path):
    try:
        c = (json.loads((t / "result.json").read_text(encoding="utf-8")).get("agent_result") or {}).get("cost_usd")
        return float(c) if c else None
    except (OSError, ValueError, TypeError):
        return None


def collect():
    groups, excluded_all, puzzles = [], [], None
    for slug, label, short, maker, kind, actor, patterns in MODELS:
        dirs = sorted({d for pat in patterns for d in JOBS.glob(pat) if d.is_dir()}, key=lambda d: d.name.lower())
        runs, excluded = [], []
        for d in dirs:
            for t in sorted(d.glob("task__*"), key=lambda p: p.name.lower()):
                f = t / "verifier" / "details.json"
                try:
                    det = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    det = None
                if not det or not isinstance(det.get("puzzles"), list) or "solved" not in det or "total" not in det:
                    why = "no score sheet yet (still running or not started)" if not (t / "result.json").exists() and not (t / "exception.txt").exists() \
                        else "no usable score sheet (verifier/details.json)"
                    excluded.append({"job": d.name, "trial": t.name, "reason": why})
                    continue
                rows = sorted(det["puzzles"], key=lambda r: r["id"])
                n_open = sum(1 for r in rows if r["status"] == "open")
                if (t / "exception.txt").exists() and n_open:
                    excluded.append({"job": d.name, "trial": t.name, "reason": f"an API error ended the session with {plural(n_open, 'puzzle')} still open"})
                    continue
                ids = [(r["id"], r["win_in"]) for r in rows]
                if puzzles is None:
                    puzzles = ids
                assert ids == puzzles, f"{t}: different puzzle set"
                runs.append({"n": len(runs) + 1, "job": d.name, "trial": t.name, "reward": det["reward"], "solved": det["solved"], "practice": det.get("practice_started"),
                             "total": det["total"], "cost": cost_of(t), "cells": [cell(r) for r in rows]})
        excluded_all += [dict(e, model=label) for e in excluded]
        if not runs and not excluded:
            print(f"no jobs found for {label}, left out")
            continue
        solved, total = sum(r["solved"] for r in runs), sum(r["total"] for r in runs)
        costs = [r["cost"] for r in runs if r["cost"]]
        groups.append({"slug": slug, "label": label, "short": short, "maker": maker, "kind": kind, "actor": actor,
                       "jobs": [d.name for d in dirs], "solved": solved, "total": total,
                       "mean": round(solved / total, 4) if total else None, "runs": runs, "excluded": excluded,
                       "cost": round(sum(costs) / len(costs), 4) if costs else None, "cost_n": len(costs)})
    return groups, excluded_all, [{"id": i, "num": int(i[1:]), "win_in": w} for i, w in puzzles]


PAGE = (Path(__file__).resolve().parent / "replay_site.html").read_text(encoding="utf-8")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo" / "replays.html"
    groups, excluded, puzzles = collect()
    data = {"w": W, "h": H, "files": FILES, "puzzles": puzzles, "groups": groups, "demo": demo(), "learn": learning(),
            "source": "jobs/final (job names clock-24d6707-* and nim-24d6707-*)"}
    js = json.dumps(data, separators=(",", ":"), sort_keys=True).replace("</", "<\\/")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PAGE.replace("__DATA__", js), encoding="utf-8", newline="\n")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    for g in groups:
        mean = "no attempts" if g["mean"] is None else f"mean {g['mean']:.4f} ({g['solved']}/{g['total']})"
        cost = f", mean cost ${g['cost']:.2f} over {g['cost_n']}" if g["cost"] else ""
        print(f"  {g['label']}: {plural(len(g['runs']), 'attempt')}, {mean}{cost}; rewards "
              + ", ".join(f"{r['reward']:.3f}" for r in g["runs"]))
    print(f"Red's winning line after a losing move: found {LINE_STATS['found']}, not found within budget {LINE_STATS['not found']}")
    print("excluded attempts:" if excluded else "excluded attempts: none")
    for e in excluded:
        print(f"  {e['model']}: {e['job']}/{e['trial']}: {e['reason']}")


if __name__ == "__main__":
    main()
