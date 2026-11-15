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

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from analyze import diagnose  # noqa: E402
from mistakes import ending  # noqa: E402
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
    ("fable52", "Claude Fable 5.2", "Fable 5.2", "Claude", "model", "The AI", ["clock-24d6707-fable52-x*"]),
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


# ---------------------------------------------------------------- rules demo for the game screen
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
                         ("reward", "results/curve-rl-qwen3-0.6b-7x6.json", "moves_played"),
                         ("imitation4b", "results/curve-qwen3-4b-7x6.json", "examples_seen")):
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
            pt = {"x": h.get(xk) or 0, "y": round(y, 4), "tiers": tiers, "legal": round(h.get("legal_rate") or 0, 4)}
            if h.get("policy_hit_rate") is not None:  # reward-only rounds: rewarded share of the model's own and of random moves
                pt["hit"], pt["rand"] = round(h["policy_hit_rate"], 4), round(h.get("random_hit_rate") or 0, 4)
            pts.append(pt)
        if len(pts) >= 2:
            out[key] = {"source": rel, "model": d.get("model"), "points": pts}
    # the like-for-like frontier number: the same one-move-per-call probe (results/probe/)
    probe, older = [], []
    for slug, label, name, into in (("argon", "Gemini 4 Argon", "gemini-4-argon", probe), ("carbon", "Gemini 4 Carbon", "gemini-4-carbon", probe),
                                    ("hydrogen", "Gemini 4 Hydrogen", "gemini-4-hydrogen", probe),
                                    ("pro31", "Gemini 3.1 Pro", "gemini-3.1-pro-preview", older), ("flash38", "Gemini 3.8 Flash", "gemini-3.8-flash", older)):
        f = ROOT / "results" / "probe" / f"{name}.summary.json"
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            by = s.get("puzzles_solved_by_win_in") or {}
            into.append({"label": label, "score": s["score_these_tiers"], "per_tier": s.get("per_tier"), "tiers": [by.get(str(t)) for t in range(1, 7)]})
        except (OSError, ValueError, KeyError):
            print(f"learning: {f.relative_to(ROOT)} missing, left out")
    # other models probed later (in progress while this was written): shown only once all six tiers are in, at the Gemini sample size
    other = []
    for f in sorted([*(ROOT / "results" / "probe").glob("claude-*.summary.json"), *(ROOT / "results" / "probe").glob("nemotron*.summary.json")]):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            by = s.get("puzzles_solved_by_win_in") or {}
            if any(str(t) not in by for t in range(1, 7)) or (probe and s.get("per_tier") != probe[0]["per_tier"]):
                print(f"learning: {f.relative_to(ROOT)} incomplete (tiers {sorted(by)}, {s.get('per_tier')} per tier), left out")
                continue
            first = s.get("parse") == "first" or s.get("tag") == "parse-first"
            other.append({"label": s.get("model") or f.stem, "score": s["score_these_tiers"], "per_tier": s.get("per_tier"), "tiers": [by[str(t)] for t in range(1, 7)], "_first": first, "_f": f.name})
        except (OSError, ValueError, KeyError):
            print(f"learning: {f.relative_to(ROOT)} unreadable, left out")
    # one series per model: a summary parsed by the first move in the answer ("parse": "first") replaces the untagged one,
    # which read the last move in the model's explanation and is kept in the repo only as a record
    one = {}
    for q in other:
        k = q["label"]
        if k not in one or (q["_first"] and not one[k]["_first"]):
            if k in one:
                print(f"learning: probe {one[k]['_f']} replaced by {q['_f']}")
            one[k] = q
        else:
            print(f"learning: probe {q['_f']} left out, {one[k]['_f']} kept")
    other = [{k: v for k, v in q.items() if not k.startswith("_")} for q in sorted(one.values(), key=lambda q: q["label"])]
    # probes that never finished (a .partial.json only): named in the text, never drawn
    done = {q["label"] for q in other}
    partial = sorted({f.name.split(".")[0] for f in (ROOT / "results" / "probe").glob("*.partial.json")} - done)
    out["probe"], out["probe_older"], out["probe_other"], out["probe_partial"] = probe, older, other, partial
    return out


# ---------------------------------------------------------------- collect every attempt
def cost_of(t: Path):
    try:
        c = (json.loads((t / "result.json").read_text(encoding="utf-8")).get("agent_result") or {}).get("cost_usd")
        return float(c) if c else None
    except (OSError, ValueError, TypeError):
        return None


def sheet(t: Path):
    """(details, None) for a counted attempt, or (None, reason) for one that is left out."""
    try:
        det = json.loads((t / "verifier" / "details.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        det = None
    if not det or not isinstance(det.get("puzzles"), list) or "solved" not in det or "total" not in det:
        return None, ("no score sheet yet (still running or not started)" if not (t / "result.json").exists() and not (t / "exception.txt").exists()
                      else "no usable score sheet (verifier/details.json)")
    n_open = sum(1 for r in det["puzzles"] if r["status"] == "open")
    if (t / "exception.txt").exists() and n_open:
        return None, f"an API error ended the session with {plural(n_open, 'puzzle')} still open"
    return det, None


# Side experiment: the same task with one added instruction line telling the agent to play N practice puzzles first
# (experiments/practice/build_practice.py). Kept apart from every other number on the page.
PRACTICE_ARMS = [("p12", "Told to practise 12", 12), ("p30", "Told to practise 30", 30)]


def practice_experiment(groups: list) -> tuple:
    out, notes = [], []
    for g in groups:
        if g["kind"] != "model":
            continue
        arms = []
        for key, label, told in PRACTICE_ARMS:
            dirs = sorted(d for d in JOBS.glob(f"practice-24d6707-{g['slug']}-{key}-x*") if d.is_dir())
            runs, left = [], []
            for d in dirs:
                for t in sorted(d.glob("task__*"), key=lambda p: p.name.lower()):
                    det, why = sheet(t)
                    if why:
                        left.append(f"{d.name}/{t.name}: {why}")
                    else:
                        runs.append({"reward": det["reward"], "solved": det["solved"], "total": det["total"], "played": det.get("practice_started") or 0})
            if dirs and not runs and not left:
                left.append(f"{', '.join(d.name for d in dirs)}: no attempts yet (still running)")
            notes += [f"{g['label']} {label.lower()}: {x}" for x in left]
            if runs:
                arms.append({"key": key, "label": label, "told": told, "runs": runs})
        if not arms or not g["runs"]:
            continue
        base = [{"reward": r["reward"], "solved": r["solved"], "total": r["total"], "played": r["practice"] or 0} for r in g["runs"]]
        arms.insert(0, {"key": "base", "label": "No practice instruction", "told": 0, "runs": base})
        for a in arms:
            s, n = sum(r["solved"] for r in a["runs"]), sum(r["total"] for r in a["runs"])
            a["mean"] = round(s / n, 4)
        out.append({"slug": g["slug"], "label": g["label"], "jobs": g["jobs"], "arms": arms})
    return out, notes


# Side experiment "deep set": same rules, tools and verifier, 6 puzzles with a forced win in 7, 8 and 9 moves
# (experiments/deep/build_deep.py). Its puzzles come from the same scored pack, so frames() grades them as is.
# The extra field names the main-test group each row is shown next to; none of this enters any main-test number.
DEEP_MODELS = [
    ("deep-opus55", "Claude Opus 5.5", "Opus 5.5", "Deep set", "deep", "The AI", ["deep-24d6707-opus55-x*"], "opus55"),
    ("deep-carbon", "Gemini 4 Carbon", "Carbon", "Deep set", "deep", "The AI", ["deep-24d6707-carbon-x*"], "carbon"),
    ("deep-reference", "Perfect play (solver)", "Perfect play", "Deep set", "deep", "The solver", ["deep-24d6707-reference"], "reference"),
    ("deep-do-nothing", "Baseline: do nothing", "Do nothing", "Deep set", "deep", "The baseline", ["deep-24d6707-do-nothing"], "do-nothing"),
]

# Side experiment "effort": the main task with the model's reasoning effort set high (or low). Shown only as a
# by-depth comparison against the same model's normal runs; none of it enters any main-test number.
EFFORT_MODELS = [
    ("effort-opus55-high", "Claude Opus 5.5, high effort", "Opus 5.5 high", "Effort", "effort", "The AI", ["effort-24d6707-opus55-high-x*"], "opus55"),
    ("effort-carbon-high", "Gemini 4 Carbon, high effort", "Carbon high", "Effort", "effort", "The AI", ["effort-24d6707-carbon-high-x*"], "carbon"),
    ("effort-carbon-low", "Gemini 4 Carbon, low effort", "Carbon low", "Effort", "effort", "The AI", ["effort-24d6707-carbon-low-x*"], "carbon"),
]


def collect(models=None):
    groups, excluded_all, puzzles = [], [], None
    for slug, label, short, maker, kind, actor, patterns, *of in (models or MODELS):
        dirs = sorted({d for pat in patterns for d in JOBS.glob(pat) if d.is_dir()}, key=lambda d: d.name.lower())
        runs, excluded = [], []
        for d in dirs:
            for t in sorted(d.glob("task__*"), key=lambda p: p.name.lower()):
                det, why = sheet(t)
                if why:
                    excluded.append({"job": d.name, "trial": t.name, "reason": why})
                    continue
                rows = sorted(det["puzzles"], key=lambda r: r["id"])
                ids = [(r["id"], r["win_in"]) for r in rows]
                if puzzles is None:
                    puzzles = ids
                assert ids == puzzles, f"{t}: different puzzle set"
                runs.append({"n": len(runs) + 1, "job": d.name, "trial": t.name, "reward": det["reward"], "solved": det["solved"], "practice": det.get("practice_started"),
                             "total": det["total"], "cost": cost_of(t), "ended": ending(t), "cells": [cell(r) for r in rows]})
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
        if of:
            groups[-1]["of"] = of[0]
    pz = [{"id": i, "num": int(i[1:]), "win_in": w} for i, w in (puzzles or [])]
    if models is not None:
        for g in groups:
            g["puzzles"] = pz
    return groups, excluded_all, pz


PAGE = (Path(__file__).resolve().parent / "replay_site.html").read_text(encoding="utf-8")


# ------------------------------------------------------------------ Play: the 12 scored puzzles of the default run
PACKS = ROOT / "task" / "environment" / "game-server" / "packs"
PLAY_SEED = "1"  # the game server's default THINICE_SEED: the same P01..P12 every model played


def probe_system() -> str:
    """The exact system text of the one-move probe (tools/probe.py), read from its source without importing it."""
    import ast
    from thinice.board import RULES
    tree = ast.parse((ROOT / "tools" / "probe.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "SYSTEM" for t in n.targets))
    return eval(compile(ast.Expression(node.value), "probe.py", "eval"), {"RULES": RULES})  # noqa: S307 - the repo's own constant


def play_data() -> dict:
    from thinice.session import LOSS0, Attempt, load_pack, pick
    manifest = json.loads((PACKS / "manifest.json").read_text(encoding="utf-8"))
    chosen = pick(load_pack(PACKS / "scored.jsonl"), PLAY_SEED, manifest["tiers"], manifest["per_tier"])
    system = probe_system()
    puzzles, checked, missing = [], 0, 0
    for i, p in enumerate(chosen):
        for k, ents in p.nodes.items():
            b, r = (mask_of(json.loads(x)) for x in k.split("|"))
            assert sorted(moves(b, b | r)) == sorted((e[0], e[1]) for e in ents), f"{k}: table moves differ from the rules"
            checked += 1
        # every position a player can reach with moves left (any winning move, slow ones too, then Red's reply) is in the table
        todo, seen = [(p.blue, p.red, 0)], set()
        while todo:
            b, r, used = todo.pop()
            k = f"[{','.join(map(str, squares(b)))}]|[{','.join(map(str, squares(r)))}]"
            if (k, used) in seen:
                continue
            seen.add((k, used))
            if k not in p.nodes:
                missing += 1
                continue
            todo += [(b ^ (1 << e[0]) ^ (1 << e[1]), r ^ (1 << e[3]) ^ (1 << e[4]), used + 1) for e in p.nodes[k] if e[2] > LOSS0 and used + 1 < p.cap]
        pid = f"P{i + 1:02d}"
        puzzles.append({"id": pid, "index": p.index, "need": p.need, "cap": p.cap, "blue": squares(p.blue), "red": squares(p.red),
                        "nodes": p.nodes, "prompt": system + "\n\n" + Attempt(pid, p).text()})
    # the reference run (perfect play) of the same seed: its moves, replayed in the browser logic, must solve all 12
    ref = None
    for t in sorted((JOBS / "clock-24d6707-reference").glob("task__*")):
        f = t / "verifier" / "details.json"
        if f.exists():
            ref = json.loads(f.read_text(encoding="utf-8"))
            break
    assert ref and str(ref.get("seed")) == PLAY_SEED, "no reference run of the default seed"
    rows = sorted(ref["puzzles"], key=lambda r: r["id"])
    assert [r["index"] for r in rows] == [q["index"] for q in puzzles], "reference run played other puzzles"
    assert not missing, f"{missing} reachable positions are missing from the table"
    print(f"play: {len(puzzles)} puzzles, {checked} positions, rules match the table in all, every reachable position covered")
    return {"seed": PLAY_SEED, "system": system, "puzzles": puzzles, "ref": [r["history"] for r in rows]}


def check_play_in_node(play: dict) -> None:
    """Runs the page's own play logic under node: legal moves equal the table, the reference moves solve all 12,
    a losing first move is graded lost, typed notation parses, and the prompt equals the probe's text."""
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node")
    if not node:
        raise SystemExit("node not found: the play logic cannot be checked, so the page is not written")
    block = PAGE[PAGE.index("/*PLAY-LOGIC*/"):PAGE.index("/*END-PLAY-LOGIC*/")]
    harness = block + r"""
const D = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const PL = playLogic(D.w, D.h, D.files), fail = m => { console.error('FAIL ' + m); process.exit(1); };
let pos = 0;
D.play.puzzles.forEach((pz, i) => {
  Object.entries(pz.nodes).forEach(([k, ents]) => {
    const [b, r] = k.split('|').map(x => JSON.parse(x));
    const js = PL.legal(b, r).map(m => m.join(',')).join(' '), tb = ents.map(e => e[0] + ',' + e[1]).sort((p, q) => { const [a1, a2] = p.split(',').map(Number), [b1, b2] = q.split(',').map(Number); return a1 - b1 || a2 - b2; }).join(' ');
    if (js !== tb) fail(pz.id + ' ' + k + ': js ' + js + ' table ' + tb);
    pos++;
  });
  const st = PL.start(pz);
  if (PL.prompt(st, D.play.system) !== pz.prompt) fail(pz.id + ': prompt differs from the probe text');
  D.play.ref[i].forEach(([b, r]) => { const m = PL.parse(b); const o = m && PL.move(st, m[0], m[1]); if (!o) fail(pz.id + ' ' + b + ' not playable'); if ((o.reply || null) !== (r || null)) fail(pz.id + ' reply ' + o.reply + ' vs ' + r); });
  if (st.status !== 'solved') fail(pz.id + ': reference moves do not solve it (' + st.status + ')');
  const s2 = PL.start(pz), bad = PL.entries(s2).find(e => e[2] < PL.LOSS0);
  if (bad) { const o = PL.move(s2, bad[0], bad[1]); if (s2.status !== 'failed' || !['draw', 'loss'].includes(o.kind)) fail(pz.id + ': a losing first move was not graded lost'); }
});
const p = PL.parse(' C1 - a1 '); if (!p || p[0] !== 2 || p[1] !== 0) fail('typed notation');
if (PL.parse('z9-a1') || PL.parse('c1a1')) fail('bad notation accepted');
console.log('node play check: ' + pos + ' positions, ' + D.play.puzzles.length + ' puzzles solved by the reference moves, prompts equal, notation ok');
"""
    with tempfile.TemporaryDirectory() as td:
        js, data = Path(td) / "check.js", Path(td) / "data.json"
        js.write_text(harness, encoding="utf-8")
        data.write_text(json.dumps({"w": W, "h": H, "files": FILES, "play": play}), encoding="utf-8")
        res = subprocess.run([node, str(js), str(data)], capture_output=True, text=True, timeout=300)
    print(res.stdout.strip() or res.stderr.strip())
    if res.returncode:
        raise SystemExit("play logic check failed, page not written: " + res.stderr.strip())


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo" / "replays.html"
    groups, excluded, puzzles = collect()
    practice, practice_notes = practice_experiment(groups)
    deep, deep_excluded, _ = collect(DEEP_MODELS)
    deep_shown = [g for g in deep if g["runs"]]
    effort, effort_excluded, _ = collect(EFFORT_MODELS)
    effort = [{k: g[k] for k in ("slug", "label", "of", "jobs", "solved", "total", "mean", "cost", "cost_n")}
              | {"runs": [{"reward": r["reward"], "won": [c["state"] == "solved" for c in r["cells"]]} for r in g["runs"]]}
              for g in effort if g["runs"]]
    play = play_data()
    check_play_in_node(play)
    play_page = {"seed": play["seed"], "system": play["system"], "puzzles": [{k: v for k, v in q.items() if k != "prompt"} for q in play["puzzles"]]}
    data = {"w": W, "h": H, "files": FILES, "puzzles": puzzles, "groups": groups + deep_shown, "demo": demo(), "learn": learning(), "practice": practice, "effort": effort, "play": play_page,
            "source": "jobs/final (job names clock-24d6707-* and nim-24d6707-*)"}
    js = json.dumps(data, separators=(",", ":"), sort_keys=True).replace("</", "<\\/")
    out.parent.mkdir(parents=True, exist_ok=True)
    art = {f.stem: "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode() for f in sorted((ROOT / "demo" / "art").glob("*.webp")) if f'data-img="{f.stem}"' in PAGE}
    out.write_text(PAGE.replace("__DATA__", js).replace("__ART__", json.dumps(art)), encoding="utf-8", newline="\n")
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
    print("practice experiment (side experiment, not in any other number):")
    for p in practice:
        for a in p["arms"]:
            print(f"  {p['label']} / {a['label']}: {plural(len(a['runs']), 'run')}, mean {a['mean']:.3f}; played "
                  + ", ".join(str(r["played"]) for r in a["runs"]) + "; rewards " + ", ".join(f"{r['reward']:.3f}" for r in a["runs"]))
    for x in practice_notes:
        print(f"  not shown: {x}")
    print("deep set (side experiment, not in any other number):")
    for g in deep_shown:
        print(f"  {g['label']}: {plural(len(g['runs']), 'run')}, {g['solved']}/{g['total']}; rewards " + ", ".join(f"{r['reward']:.3f}" for r in g["runs"])
              + "; by puzzle " + " ".join(c["state"] for r in g["runs"] for c in r["cells"]))
    for e in deep_excluded:
        print(f"  not shown: {e['model']}: {e['job']}/{e['trial']}: {e['reason']}")
    print("effort (side experiment, not in any other number):")
    for g in effort:
        print(f"  {g['label']}: {plural(len(g['runs']), 'run')}, {g['solved']}/{g['total']}; rewards " + ", ".join(f"{r['reward']:.3f}" for r in g["runs"]))
    for e in effort_excluded:
        print(f"  not shown: {e['model']}: {e['job']}/{e['trial']}: {e['reason']}")


if __name__ == "__main__":
    main()
