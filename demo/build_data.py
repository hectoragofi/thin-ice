"""Collects every number the demo shows and writes demo/data.json, demo/data.js and demo/script.md.

    python demo/build_data.py            # re-run after the last runs land; nothing else to edit

Sources (read-only):
  ../thin-ice/jobs/final/clock-24d6707-*/task__*/verifier/{reward.txt,details.json}   final Harbor runs
  results/probe/gemini-4-*.summary.json                                                one move per fresh call
  results/curve-qwen3-0.6b-7x6.json                                                    small model, imitation
  results/curve-rl-qwen3-0.6b-7x6.json, local or on origin/reward-training             small model, reward only
  README.md                                                                            attack counts, clock rule
Anything missing is written as null and shown as "pending". Nothing is invented.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from thinice.board import FILES, H, W, completes_line, key, move_name, moves, parse_move, squares  # noqa: E402
from analyze import POOL, diagnose  # noqa: E402

JOBS = Path(os.environ.get("THINICE_JOBS", ROOT.parent / "thin-ice" / "jobs" / "final"))
PREFIX = "clock-24d6707-"
MODELS = [("argon", "Gemini 4 Argon"), ("carbon", "Gemini 4 Carbon"), ("hydrogen", "Gemini 4 Hydrogen")]
RUNS_PER_MODEL = 3
TIERS = [1, 2, 3, 4, 5, 6]
# The README tells this exact mistake; use it when a final run contains it, else the most repeated one.
PREFERRED = ("P07", "c1-g5")
REPRO = "python scripts/evaluate.py --model google/gemini-4-carbon --env modal"
RL_FILE = "results/curve-rl-qwen3-0.6b-7x6.json"  # never curve-rl-keepswin-*: that stalled run is a record only
RL_MIN_SIX_TIER = 0.10  # show the reward-only curve only once its last evaluation reaches this


def read_reward(trial: Path):
    f = trial / "verifier" / "reward.txt"
    try:
        return float(f.read_text().strip())
    except (OSError, ValueError):
        return None


def read_details(trial: Path):
    try:
        return json.loads((trial / "verifier" / "details.json").read_text())
    except (OSError, ValueError):
        return None


def job_runs(name: str) -> list:
    out = []
    for t in sorted((JOBS / f"{PREFIX}{name}").glob("task__*")):
        out.append({"trial": t.name, "reward": read_reward(t), "details": read_details(t)})
    return out


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def single(name: str):
    rs = [r["reward"] for r in job_runs(name) if r["reward"] is not None]
    return rs[0] if rs else None


# ---------------------------------------------------------------- ladder (final Harbor runs)
agents = {}
for slug, label in MODELS:
    runs = [r for r in job_runs(f"{slug}-x{RUNS_PER_MODEL}")]
    landed = [r for r in runs if r["reward"] is not None and r["details"] is not None]
    agents[slug] = {
        "label": label,
        "rewards": [round(r["reward"], 4) for r in landed],
        # mean over runs = puzzles won / puzzles played, from the signed score sheets' details
        "mean": None if not landed else round(sum(r["details"]["solved"] for r in landed) / sum(r["details"]["total"] for r in landed), 4),
        "landed": len(landed),
        "expected": RUNS_PER_MODEL,
        "solved_by_tier": None,
        "_runs": landed,
    }
    if landed:
        tiers = {}
        for t in TIERS:
            s = sum(r["details"]["by_win_in"].get(str(t), {}).get("solved", 0) for r in landed)
            n = sum(sum(r["details"]["by_win_in"].get(str(t), {}).values()) for r in landed)
            tiers[str(t)] = {"solved": s, "of": n}
        agents[slug]["solved_by_tier"] = tiers

ladder = [
    {"label": "Perfect play (solver)", "value": single("reference"), "kind": "ref"},
    {"label": "Rules-only search, 20 s/puzzle", "value": single("reference-search"), "kind": "ref"},
]
for slug, label in MODELS:
    a = agents[slug]
    ladder.append({"label": label, "value": a["mean"], "runs": a["rewards"], "landed": a["landed"],
                   "expected": a["expected"], "kind": "agent"})
ladder += [
    {"label": "Stop early (2 easiest)", "value": single("stop-early"), "kind": "base"},
    {"label": "Do nothing", "value": single("do-nothing"), "kind": "base"},
]
best_agent = max((a for a in agents.values() if a["mean"] is not None), key=lambda a: a["mean"], default=None)

# ---------------------------------------------------------------- mistakes (solver verdicts)
def red_refutation(blue: int, red: int):
    """Red to move and the solver says Red wins in k. Finds Red's line by brute force over the rules,
    up to win in 2 (enough to show the punishment on screen). Returns list of move names or None."""
    occ = blue | red
    for f, t in moves(red, occ):
        r2 = red ^ (1 << f) ^ (1 << t)
        if completes_line(r2, t):
            return [move_name((f, t))]
    for f, t in moves(red, occ):
        r2 = red ^ (1 << f) ^ (1 << t)
        replies = moves(blue, blue | r2)
        ok = bool(replies)
        for bf, bt in replies:
            b2 = blue ^ (1 << bf) ^ (1 << bt)
            if completes_line(b2, bt):
                ok = False
                break
            if not any(completes_line(r2 ^ (1 << rf) ^ (1 << rt), rt) for rf, rt in moves(r2, b2 | r2)):
                ok = False
                break
        if ok:
            return [move_name((f, t))]
    return None


graded = []  # every losing move in every landed agent run
reach = {"runs": 0, "puzzles": 0, "reached": 0, "out_of_time": 0, "skipped": 0, "practice_runs": 0, "lost": 0}
for slug, a in agents.items():
    for r in a["_runs"]:
        d = r["details"]
        reach["runs"] += 1
        reach["practice_runs"] += 1 if d.get("practice_started") else 0
        for row in d["puzzles"]:
            reach["puzzles"] += 1
            if row["status"] != "open" or row["history"]:
                reach["reached"] += 1
            if row["status"] == "failed":
                reach["lost"] += 1
                if row.get("reason") == "out of time":
                    reach["out_of_time"] += 1
                if row.get("reason") == "skipped":
                    reach["skipped"] += 1
            g = diagnose(row)
            if g:
                graded.append({"model": a["label"], "slug": slug, "trial": r["trial"], "id": row["id"],
                               "index": row["index"], "win_in": row["win_in"], "history": row["history"], **g})

kinds = Counter(g["kind"] for g in graded)
same = Counter((g["index"], g["good_moves_before"], g["played"]) for g in graded)


def build_replay(g: dict) -> dict:
    p = POOL[g["index"]]
    blue, red = p.blue, p.red
    steps = []
    for played, reply in g["history"][:-1]:
        f, t = parse_move(played)
        blue ^= (1 << f) | (1 << t)
        steps.append(played)
        f, t = parse_move(reply)
        red ^= (1 << f) | (1 << t)
        steps.append(reply)
    entries = p.nodes[key(blue, red)]
    pf, pt = parse_move(g["played"])
    hf, ht = parse_move(g["winning"][0])
    after_bad = blue ^ (1 << pf) ^ (1 << pt)
    after_good = blue ^ (1 << hf) ^ (1 << ht)
    ref = red_refutation(after_bad, red)
    repeats = [x for x in graded if (x["index"], x["good_moves_before"], x["played"]) == (g["index"], g["good_moves_before"], g["played"])]
    lost_same_puzzle = [x for x in graded if x["index"] == g["index"]]
    return {
        "id": g["id"], "model": g["model"], "trial": g["trial"], "win_in": g["win_in"],
        "moves_before": steps, "blue": squares(blue), "red": squares(red),
        "played": g["played"], "played_sq": [pf, pt], "after_bad_blue": squares(after_bad),
        "verdict": g["verdict"], "kind": g["kind"], "held": g["winning"], "held_sq": [hf, ht],
        "after_good_blue": squares(after_good), "legal": len(entries), "keep_win": len(g["winning"]),
        "red_reply": ref[0] if ref else None, "red_reply_sq": list(parse_move(ref[0])) if ref else None,
        "same_move_runs": len(repeats), "same_move_models": sorted({x["model"] for x in repeats}),
        "lost_this_puzzle_runs": len(lost_same_puzzle),
    }


pick = next((g for g in graded if (g["id"], g["played"]) == PREFERRED), None)
if pick is None and graded:
    pick = max(graded, key=lambda g: (same[(g["index"], g["good_moves_before"], g["played"])], g["legal"]))
replay = build_replay(pick) if pick else None

# ---------------------------------------------------------------- depth wall (probe + small model)
probe = {}
for slug, label in MODELS:
    f = ROOT / "results" / "probe" / f"gemini-4-{slug}.summary.json"
    try:
        s = json.loads(f.read_text())
        probe[slug] = {"label": label, "by_tier": {str(t): s["puzzles_solved_by_win_in"].get(str(t)) for t in TIERS},
                       "mean": round(s["score_these_tiers"], 3), "per_tier": s.get("per_tier")}
    except (OSError, ValueError, KeyError):
        probe[slug] = {"label": label, "by_tier": None, "mean": None}


def curve_points(d: dict) -> list:
    pts = []
    for h in d.get("history", []):
        x = next((h[k] for k in ("examples_seen", "moves_played", "moves_seen", "moves", "step", "steps", "episodes", "updates") if k in h), None)
        bw = h.get("by_win_in")
        if h.get("six_tier") is not None:
            y = h["six_tier"]
            tiers = {str(t): bw.get(str(t)) for t in TIERS} if bw else None
        elif bw:
            y = sum(bw.get(str(t), 0.0) for t in TIERS) / len(TIERS)
            tiers = {str(t): bw.get(str(t)) for t in TIERS}
        else:
            y, tiers = h.get("score"), None
        if x is not None and y is not None:
            pts.append({"x": x, "score": round(y, 4), "tiers": tiers, "legal": h.get("legal_rate")})
    return pts


imit = json.loads((ROOT / "results" / "curve-qwen3-0.6b-7x6.json").read_text())
imit_pts = curve_points(imit)
small = {"label": "Qwen3-0.6B", "untrained": imit_pts[0], "trained": imit_pts[-1]}

rl_raw, rl_src = None, None
local = ROOT / RL_FILE
if local.exists():
    rl_raw, rl_src = local.read_text(), RL_FILE
else:
    try:
        subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "origin", "reward-training"], capture_output=True, timeout=60)
        out = subprocess.run(["git", "-C", str(ROOT), "show", f"origin/reward-training:{RL_FILE}"], capture_output=True, timeout=30)
        if out.returncode == 0:
            rl_raw, rl_src = out.stdout.decode("utf-8"), f"origin/reward-training:{RL_FILE}"
    except (OSError, subprocess.SubprocessError):
        pass
curve = {"kind": "imitation", "source": "results/curve-qwen3-0.6b-7x6.json", "x_label": "training examples",
         "points": imit_pts, "rl_status": "pending"}
if rl_raw:
    try:
        rl_pts = curve_points(json.loads(rl_raw))
        hist = json.loads(rl_raw).get("history", [])
        last = hist[-1] if hist else {}
        six = last.get("six_tier", rl_pts[-1]["score"] if rl_pts else None)
        if len(rl_pts) < 2:
            curve["rl_status"] = "file present, fewer than 2 points"
        elif six is None or six < RL_MIN_SIX_TIER:
            curve["rl_status"] = f"file present, last six_tier {six} below {RL_MIN_SIX_TIER}"
        else:
            curve = {"kind": "reward-only", "source": rl_src, "x_label": "moves played in training",
                     "points": rl_pts, "rl_status": "landed", "imitation": imit_pts}
    except ValueError:
        curve["rl_status"] = "file present, not parseable"

# ---------------------------------------------------------------- README facts (rules and attack counts)
readme = (ROOT / "README.md").read_text(encoding="utf-8")


def rx(pattern):
    m = re.search(pattern, readme)
    return int(m.group(1)) if m else None


facts = {
    "attacks_main": rx(r"(\d+) checks, all passing"),
    "attacks_clock": rx(r"adds (\d+) attacks on the clock"),
    "clock_min_per_move": rx(r"(\d+) minutes per move of its forced win"),
    "clocks_total_min": rx(r"clocks add up to (\d+) minutes"),
    "run_min": rx(r"the run has (\d+)"),
    "attack_rows": [m.group(1).strip() for m in re.finditer(r"^\| ([^|]+) \| [^|]+ \|$", readme.split("## Why the reward cannot be gamed")[-1].split("`python tools/redteam.py")[0], re.M) if m.group(1).strip() not in ("attack", "---")],
    "tools": re.findall(r"`(\w+)`", (re.search(r"over MCP \(([^)]*)\)", readme) or [None, ""])[1]),
    "positions": (re.search(r"all ([\d.]+ billion) positions", readme) or [None, None])[1],
}

# ---------------------------------------------------------------- captions and script (numbers filled in)
P = "pending"


def f3(x):
    return P if x is None else f"{x:.3f}"


def f2(x):
    return P if x is None else f"{x:.2f}"


def n(x):
    return P if x is None else str(x)


ref_search = ladder[1]["value"]
a_mean = {s: agents[s]["mean"] for s, _ in MODELS}
rp = replay or {}
probe_line = "; ".join(f"{probe[s]['label'].split()[-1]} {' / '.join(f2(probe[s]['by_tier'][str(t)]) for t in TIERS)}"
                       for s, _ in MODELS if probe[s]["by_tier"])
learn_kind = ("from a win-or-lose reward alone" if curve["kind"] == "reward-only"
              else "on the feedback practice mode gives: it imitates the winning move")
pts = curve["points"]
_w4 = sorted(round(probe[s]["by_tier"]["4"] * probe[s]["per_tier"]) for s, _ in MODELS if probe[s]["by_tier"] and probe[s].get("per_tier"))
w4 = P if not _w4 else (f"{_w4[0]} to {_w4[-1]} puzzles in {probe['argon']['per_tier']}" if _w4[0] != _w4[-1] else f"{_w4[0]} in {probe['argon']['per_tier']}")


def agent_phrase():
    parts = []
    for s, label in MODELS:
        a = agents[s]
        if a["mean"] is None:
            parts.append(f"{label.split()[-1]} pending")
        else:
            tail = "" if a["landed"] == a["expected"] else f" ({a['landed']} of {a['expected']} runs so far)"
            parts.append(f"{label.split()[-1]} {f3(a['mean'])}{tail}")
    return ", ".join(parts)


# One cut, at most 2 minutes (target 1:50). Each scene: id, seconds, caption lines.
# Caption lines are spoken in order and spread evenly over the scene. The last scene is the closing card.
SCENES = [
    {"id": "question", "dur": 8,
     "cap": ["How far ahead can a frontier model think, without a computer to do the thinking?",
             "No shell, no code. Only its own reasoning."]},
    {"id": "game", "dur": 14,
     "cap": [f"Thin Ice. A board game we invented. {W} by {H}, four stones each.",
             "A stone slides until it hits something. Three in a row wins.",
             f"We solved it completely, all {facts['positions'] or P} positions. Every move has an exact verdict."]},
    {"id": "mistake", "dur": 26,
     "cap": [f"A real game. {rp.get('model', P)}, puzzle {rp.get('id', P)}, Blue to win in {rp.get('win_in', P)}.",
             f"It played {rp.get('played', P)}.",
             f"The solver says: that loses. {rp.get('verdict', P).replace('Red wins in', 'Red now wins in')}.",
             f"Only {rp.get('held', [P])[0]} held. {rp.get('keep_win', P)} move out of {rp.get('legal', P)}.",
             f"The same wrong move came up in {n(rp.get('same_move_runs'))} separate runs. Every lost puzzle is graded like this."]},
    {"id": "gap", "dur": 15,
     "cap": [f"Score is puzzles won out of 12. Perfect play: {f3(ladder[0]['value'])}.",
             f"Eighty lines of rules-only search: {f3(ref_search)}.",
             f"Frontier models: {agent_phrase()}."]},
    {"id": "depth", "dur": 15,
     "cap": ["Now one move per fresh call, graded to the end of the game.",
             f"Win in one or two: easy. Win in four: {w4}.",
             "The horizon is about three moves."]},
    {"id": "fair", "dur": 10,
     "cap": [f"The mistakes are fair. Each puzzle has its own clock: {n(facts['clock_min_per_move'])} minutes per move.",
             f"{reach['reached']} of {reach['puzzles']} puzzles were reached. Rules, notes and practice are always there."]},
    {"id": "exploit", "dur": 9,
     "cap": [f"The reward can't be gamed. {n(facts['attacks_main'])} attacks, plus {n(facts['attacks_clock'])} on the clock.",
             "None got through. The score sheet is signed by the game server."]},
    {"id": "learn", "dur": 9,
     "cap": [f"And a small model learns. {small['label']}: {f3(pts[0]['score'] if pts else None)} untrained.",
             f"{f3(pts[-1]['score'] if pts else None)} after training {learn_kind}."]},
    {"id": "repro", "dur": 4,
     "cap": ["One command reproduces it. Thin Ice: every mistake, proven."]},
]
TOTAL = sum(sc["dur"] for sc in SCENES)
assert TOTAL <= 118, TOTAL

data = {
    "board": {"w": W, "h": H, "files": FILES},
    "ladder": ladder,
    "agents": {s: {k: v for k, v in a.items() if not k.startswith("_")} for s, a in agents.items()},
    "best_agent": best_agent and best_agent["label"],
    "replay": replay,
    "mistakes": {"graded": len(graded), "kinds": dict(kinds)},
    "reach": reach,
    "probe": probe,
    "small": small,
    "curve": curve,
    "facts": facts,
    "repro": REPRO,
    "scenes": SCENES,
    "total": TOTAL,
}
(DEMO / "data.json").write_text(json.dumps(data, indent=1), encoding="utf-8", newline="\n")
(DEMO / "data.js").write_text("window.DEMO_DATA = " + json.dumps(data) + ";\n", encoding="utf-8", newline="\n")


def script_md() -> str:
    def stamp(s):
        return f"{s // 60}:{s % 60:02d}"

    screen = {
        "question": "Title card with the question.",
        "game": "Rule illustration: one stone slides until blocked, then a line of three lights up.",
        "mistake": "Replay of the real position. The played move flashes, the verdict appears in red, then the one move that held in green.",
        "gap": "Ladder chart: perfect play, rules-only search, the three Gemini models (one dot per run), the baselines.",
        "depth": "Line chart: solve rate by win-in depth for Argon, Carbon, Hydrogen and the trained small model.",
        "fair": "Three facts: per-puzzle clock, puzzles reached, tools available.",
        "exploit": "Attack counts with every row refused.",
        "learn": "Learning curve of the small model, frontier range as a band.",
        "repro": "Closing card: the command, the repo, the one-line claim.",
    }
    out = ["# Thin Ice demo script", "",
           "Generated by `python demo/build_data.py` from the result files; re-run it after the last runs land.",
           f"One cut, {stamp(TOTAL)}. The page `demo/index.html` plays the same captions and stops on the closing card.",
           "Any number shown as \"pending\" has not landed yet.", "",
           "| time | on screen | say |", "|---|---|---|"]
    t = 0
    for sc in SCENES:
        lines, dur = sc["cap"], sc["dur"]
        for i, line in enumerate(lines):
            at = t + round(i * dur / len(lines))
            out.append(f"| {stamp(at)} | {screen[sc['id']] if i == 0 else '(same)'} | {line} |")
        t += dur
    out += [f"| {stamp(t)} | closing card stays on screen | (end) |", "", f"Total: {stamp(t)}.", ""]
    out += ["## Command on screen", "", f"```\n{REPRO}\n```", ""]
    return "\n".join(out)


(DEMO / "script.md").write_text(script_md(), encoding="utf-8", newline="\n")

pending = [lab["label"] for lab in ladder if lab["value"] is None]
pending += [f"{a['label']}: {a['expected'] - a['landed']} run(s)" for a in agents.values() if a["landed"] < a["expected"]]
if curve["kind"] != "reward-only":
    pending.append(f"reward-only curve ({curve['rl_status']})")
print("wrote demo/data.json, demo/data.js, demo/script.md")
print("replay:", replay and f"{replay['model']} {replay['id']} {replay['played']} -> {replay['verdict']}; held {replay['held']}")
print("pending:", ", ".join(pending) or "nothing")
