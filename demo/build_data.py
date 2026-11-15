"""Collects every number the demo shows and writes demo/data.json, demo/data.js and demo/script.md.

    python demo/build_data.py            # re-run after the last runs land; nothing else to edit

Sources (read-only):
  jobs/final/<job>/task__*/verifier/details.json        final Harbor runs; job names and the exclusion rule are
                                                         the ones tools/replay_site.py uses (MODELS, DEEP_MODELS, sheet)
  jobs/final/practice-24d6707-*                          forced-practice side experiment
  results/probe/gemini-4-*.summary.json                  one move per fresh call (the like-for-like band for Qwen)
  results/curve-qwen3-0.6b-7x6.json                      small model, imitation
  results/curve-rl-qwen3-0.6b-7x6.json, local or on origin/reward-training   small model, reward only
  README.md (origin/reasoning-only if present, else the local file)          attack counts, clock rule
A run is left out only if it has no usable score sheet, or an API error ended it with puzzles still open.
Anything missing is written as null and shown as "pending". Nothing is invented.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from thinice.board import FILES, H, W, completes_line, key, move_name, moves, parse_move, squares  # noqa: E402
from analyze import POOL, diagnose  # noqa: E402
import replay_site as RS  # noqa: E402  (job discovery and the exclusion rule; read-only reuse)

JOBS = Path(os.environ.get("THINICE_JOBS", ROOT / "jobs" / "final"))
TIERS = [1, 2, 3, 4, 5, 6]
DEEP_TIERS = [7, 8, 9]
GEMINI4 = ("argon", "carbon", "hydrogen")
# Not measured, with the reason the README gives; shown as a footnote, never as a score.
NOT_MEASURED = [("Claude Sonnet 5.5", "provider refused the task", "clock-24d6707-sonnet55-x*"),
                ("Mistral Large 4", "hosting too slow for the move clock", "nim-24d6707-mistral-large4-x*")]
# The README tells this exact mistake; use it when a final run contains it, else the most repeated one.
PREFERRED = ("P07", "c1-g5")
REPRO = "python scripts/evaluate.py --model google/gemini-4-carbon --env modal"
RL_FILE = "results/curve-rl-qwen3-0.6b-7x6.json"  # never curve-rl-keepswin-*: that stalled run is a record only
RL_MIN_SIX_TIER = 0.10  # show the reward-only curve only once its last evaluation reaches this
PRACTICE_ARMS = [("p12", 12), ("p30", 30)]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def job_dirs(patterns) -> list:
    return sorted({d for pat in patterns for d in JOBS.glob(pat) if d.is_dir()}, key=lambda d: d.name.lower())


def collect(patterns) -> tuple:
    """(kept runs, excluded) for job-name patterns, with replay_site's exclusion rule."""
    kept, excluded = [], []
    for d in job_dirs(patterns):
        for t in sorted(d.glob("task__*"), key=lambda p: p.name.lower()):
            det, why = RS.sheet(t)
            if why:
                excluded.append({"job": d.name, "trial": t.name, "reason": why})
            else:
                kept.append({"job": d.name, "trial": t.name, "reward": det["reward"], "details": det})
    return kept, excluded


def by_tier(runs, tiers) -> dict | None:
    if not runs:
        return None
    out = {}
    for t in tiers:
        s = sum(r["details"]["by_win_in"].get(str(t), {}).get("solved", 0) for r in runs)
        n = sum(sum(r["details"]["by_win_in"].get(str(t), {}).values()) for r in runs)
        out[str(t)] = {"solved": s, "of": n}
    return out


def group(label, runs, excluded, kind, **extra) -> dict:
    solved, total = sum(r["details"]["solved"] for r in runs), sum(r["details"]["total"] for r in runs)
    rewards = [round(r["reward"], 4) for r in runs]
    return {"label": label, "kind": kind, "value": round(solved / total, 4) if total else None,
            "runs": rewards, "landed": len(runs), "excluded": len(excluded),
            "lo": min(rewards) if rewards else None, "hi": max(rewards) if rewards else None, **extra}


# ---------------------------------------------------------------- main task (final Harbor runs)
agents, refs, excluded_all = {}, {}, []
for slug, label, short, maker, kind, _actor, patterns in RS.MODELS:
    runs, excl = collect(patterns)
    excluded_all += [dict(e, model=label) for e in excl]
    if kind == "model":
        a = group(label, runs, excl, "agent", short=short, maker=maker, slug=slug)
        a["solved_by_tier"] = by_tier(runs, TIERS)
        a["_runs"] = runs
        agents[slug] = a
    else:
        refs[slug] = group(label, runs, excl, kind, slug=slug, solved_by_tier=by_tier(runs, TIERS))

LADDER_LABELS = {"reference": "Perfect play (solver)", "reference-search": "Rules-only search, 80 lines",
                 "stop-early": "Stop early (2 easiest)", "do-nothing": "Do nothing"}
ladder = [dict(refs[s], label=LADDER_LABELS[s]) for s in ("reference", "reference-search") if s in refs]
ladder += sorted(({k: v for k, v in a.items() if not k.startswith("_")} for a in agents.values() if a["landed"]),
                 key=lambda r: -r["value"])
ladder += [dict(refs[s], label=LADDER_LABELS[s]) for s in ("stop-early", "do-nothing") if s in refs]
measured = [a for a in agents.values() if a["landed"]]
n_models, n_runs = len(measured), sum(a["landed"] for a in measured)
lowest = min(measured, key=lambda a: a["value"], default=None)
single_run = [a for a in measured if a["landed"] == 1]
# "best" for a sentence: the highest mean among models with more than 3 runs (fewer runs are indicative only)
best_many = max((a for a in measured if a["landed"] > 3), key=lambda a: a["value"], default=None)
not_measured = []
for label, why, pat in NOT_MEASURED:
    runs, excl = collect([pat])  # the README's call (refusal, too slow), not the exclusion rule: never scored here
    not_measured.append({"label": label, "reason": why, "jobs": [d.name for d in job_dirs([pat])],
                         "sheets": len(runs), "no_sheet_or_api_error": len(excl)})

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


graded = []  # every losing move in every kept agent run
reach = {"runs": 0, "puzzles": 0, "reached": 0, "out_of_time": 0, "skipped": 0, "lost": 0}
g4 = {"runs": 0, "lost": 0, "wrong_move": 0, "clock": 0, "skipped": 0, "other": 0}
for slug, a in agents.items():
    for r in a["_runs"]:
        d = r["details"]
        reach["runs"] += 1
        if slug in GEMINI4:
            g4["runs"] += 1
        for row in d["puzzles"]:
            reach["puzzles"] += 1
            if row["status"] != "open" or row["history"]:
                reach["reached"] += 1
            g = diagnose(row)
            if row["status"] == "failed":
                reach["lost"] += 1
                reach["out_of_time"] += row.get("reason") == "out of time"
                reach["skipped"] += row.get("reason") == "skipped"
                if slug in GEMINI4:
                    g4["lost"] += 1
                    k = "wrong_move" if g else "clock" if row.get("reason") == "out of time" else "skipped" if row.get("reason") == "skipped" else "other"
                    g4[k] += 1
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


# the featured run: the README's game (Gemini 4 Hydrogen) if it is there, else the first run that has the move
pick = next((g for g in graded if (g["id"], g["played"]) == PREFERRED and g["slug"] == "hydrogen"), None) \
    or next((g for g in graded if (g["id"], g["played"]) == PREFERRED), None)
if pick is None and graded:
    pick = max(graded, key=lambda g: (same[(g["index"], g["good_moves_before"], g["played"])], g["legal"]))
replay = build_replay(pick) if pick else None

# ---------------------------------------------------------------- depth: Gemini 4, every kept run
g4_runs = [r for s in GEMINI4 if s in agents for r in agents[s]["_runs"]]
depth = {"label": "Gemini 4", "models": [agents[s]["label"] for s in GEMINI4 if s in agents and agents[s]["landed"]],
         "runs": len(g4_runs), "by_tier": by_tier(g4_runs, TIERS)}

# ---------------------------------------------------------------- horizon: per-depth grid, main task + deep set
deep = {}
for slug, label, short, maker, kind, _actor, patterns, of in RS.DEEP_MODELS:
    runs, excl = collect(patterns)
    if runs:
        deep[of] = {"label": label, "runs": len(runs), "excluded": len(excl), "solved": sum(r["details"]["solved"] for r in runs),
                    "total": sum(r["details"]["total"] for r in runs), "by_tier": by_tier(runs, DEEP_TIERS),
                    "rewards": [round(r["reward"], 4) for r in runs]}
horizon = []
for slug in ("reference", "fable52", "opus55", "carbon"):
    src = refs.get(slug) or agents.get(slug)
    if not src or not src["landed"]:
        continue
    horizon.append({"slug": slug, "label": src["label"], "main_runs": src["landed"], "main": src["solved_by_tier"],
                    "deep_runs": deep.get(slug, {}).get("runs"), "deep": deep.get(slug, {}).get("by_tier")})

# ---------------------------------------------------------------- forced-practice side experiment
practice = []
for slug in ("haiku55", "argon", "carbon"):
    a = agents.get(slug)
    if not a or not a["landed"]:
        continue
    for arm, told in PRACTICE_ARMS:
        runs, _ = collect([f"practice-24d6707-{slug}-{arm}-x*"])
        if runs:
            v = sum(r["details"]["solved"] for r in runs) / sum(r["details"]["total"] for r in runs)
            practice.append({"model": a["label"], "told": told, "runs": len(runs), "mean": round(v, 4), "base": a["value"],
                             "base_runs": a["landed"], "diff_puzzles": round((v - a["value"]) * 12, 2)})
practice_max = max((abs(p["diff_puzzles"]) for p in practice), default=None)

# ---------------------------------------------------------------- one move per call (probe) + small model
probe = {}
for slug in GEMINI4:
    f = ROOT / "results" / "probe" / f"gemini-4-{slug}.summary.json"
    label = agents[slug]["label"] if slug in agents else slug
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
            hits = [(h.get("policy_hit_rate"), h.get("random_hit_rate")) for h in hist if h.get("policy_hit_rate") is not None]
            curve = {"kind": "reward-only", "source": rl_src, "x_label": "thousands: moves played (reward only), examples seen (imitation)",
                     "points": rl_pts, "rl_status": "landed", "imitation": imit_pts,
                     "policy_hit_last": hits[-1][0] if hits else None, "random_hit_last": hits[-1][1] if hits else None}
    except ValueError:
        curve["rl_status"] = "file present, not parseable"

# ---------------------------------------------------------------- README facts (rules and attack counts)
_rm = subprocess.run(["git", "-C", str(ROOT), "show", "origin/reasoning-only:README.md"], capture_output=True)
readme = _rm.stdout.decode("utf-8") if _rm.returncode == 0 else (ROOT / "README.md").read_text(encoding="utf-8")
README_SRC = "origin/reasoning-only:README.md" if _rm.returncode == 0 else "README.md"


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


def n(x):
    return P if x is None else str(x)


def frac(tiers, t):
    c = (tiers or {}).get(str(t))
    return P if not c else f"{c['solved']} of {c['of']}"


def runs_word(k):
    return f"{k} run" + ("" if k == 1 else "s")


rp = replay or {}
ref_v = refs.get("reference", {}).get("value")
search_v = refs.get("reference-search", {}).get("value")
dt = depth["by_tier"]
dz = {k: (deep.get(k) or {}) for k in ("opus55", "carbon", "reference")}
fable = agents.get("fable52") or {}
fable_t = fable.get("solved_by_tier")
fable_upto4 = fable_t and all(fable_t[str(t)]["solved"] == fable_t[str(t)]["of"] for t in (1, 2, 3, 4))
fable_deeper = fable_t and (sum(fable_t[str(t)]["solved"] for t in (5, 6)), sum(fable_t[str(t)]["of"] for t in (5, 6)))
probe_means = [p["mean"] for p in probe.values() if p["mean"] is not None]
pts = curve["points"]
rec_models = len(rp.get("same_move_models") or [])


def mean_of(slug):
    a = agents.get(slug)
    return f3(a and a["value"])


if curve["kind"] == "reward-only":
    learn_first = (f"Training does. {small['label']}, one move per call: {f3(imit_pts[0]['score'])} untrained, "
                   f"{f3(imit_pts[-1]['score'])} trained, {f3(pts[-1]['score'])} on reward alone.")
else:
    learn_first = f"Training does. {small['label']}, one move per call on new puzzles: {f3(imit_pts[0]['score'])} untrained, {f3(imit_pts[-1]['score'])} trained."
LEARN_CAP = [
    "Can a model learn here? Practising inside the session does not move the score." if practice else "Can a model learn here?",
    learn_first,
    f"Gemini 4 scores {min(probe_means):.2f} to {max(probe_means):.2f} in that same one-move setting." if probe_means else "Gemini 4 in that same setting: pending.",
]

SPINE = "Every model has a planning horizon. Thin Ice measures where it is, and you can move the horizon by adding depth."

# One cut, target about 2:00 (the hard cap in make_video.sh is 2:10). Each scene: id, seconds, caption lines.
# Caption lines are spoken in order and spread evenly over the scene. The last scene is the closing card.
SCENES = [
    {"id": "question", "dur": 6,
     "cap": ["How far ahead can a frontier model plan, without a computer to do the thinking?",
             "No shell, no code. Only its own reasoning."]},
    {"id": "game", "dur": 12,
     "cap": [f"Thin Ice. A board game we invented. {W} by {H}, four stones each.",
             "A stone slides until it hits something. Three in a row wins.",
             f"We solved it completely, all {facts['positions'] or P} positions. Every move has an exact verdict."]},
    {"id": "mistake", "dur": 21,
     "cap": [f"A real game. {rp.get('model', P)}, puzzle {rp.get('id', P)}, Blue to win in {rp.get('win_in', P)}.",
             f"It played {rp.get('played', P)}.",
             f"The solver says: that loses. {rp.get('verdict', P).replace('Red wins in', 'Red now wins in')}.",
             f"Only {rp.get('held', [P])[0]} held. {rp.get('keep_win', P)} move out of {rp.get('legal', P)}.",
             f"The same wrong move came up in {n(rp.get('same_move_runs'))} runs, across {n(rec_models or None)} models."]},
    {"id": "gap", "dur": 17,
     "cap": [f"Score is puzzles won out of 12. Perfect play: {f3(ref_v)}. Eighty lines of rules-only search: {f3(search_v)}.",
             f"{n_models} models, {n_runs} runs. " + (f"Best over many runs: {best_many['label']}, {f3(best_many['value'])} in {runs_word(best_many['landed'])}." if best_many else ""),
             (f"{single_run[0]['label']} scored {f3(single_run[0]['value'])} in its one run. A data point, not a rank." if single_run else
              "Every model sits far below the search."),
             f"Older and smaller models stop earlier. {lowest['label']}: {f3(lowest['value'])}." if lowest else ""]},
    {"id": "depth", "dur": 13,
     "cap": [f"Where Gemini 4 falls through, over all {depth['runs']} runs.",
             f"Win in 1: {frac(dt, 1)}. Win in 3: {frac(dt, 3)}. Win in 4: {frac(dt, 4)}.",
             f"Win in 5: {frac(dt, 5)}. Its horizon is about three moves."]},
    {"id": "horizon", "dur": 13,
     "cap": ["Then we added depth: six puzzles at win in 7, 8 and 9.",
             f"{dz['opus55'].get('label', 'Claude Opus 5.5')}: {n(dz['opus55'].get('solved'))} of {n(dz['opus55'].get('total'))}. "
             f"{dz['carbon'].get('label', 'Gemini 4 Carbon')}: {n(dz['carbon'].get('solved'))} of {n(dz['carbon'].get('total'))}. "
             f"The solver: {n(dz['reference'].get('solved'))} of {n(dz['reference'].get('total'))}.",
             (f"Even {fable['label']}'s one run won every puzzle to win in 4, then {fable_deeper[0]} of {fable_deeper[1]} deeper."
              if fable_upto4 else "The best runs stop well short of the solver.")]},
    {"id": "fair", "dur": 10,
     "cap": [f"Is it the clock? Of {n(g4['lost'])} puzzles Gemini 4 lost, {n(g4['wrong_move'])} were wrong moves. {n(g4['clock'])} ran out of time.",
             f"{reach['reached']} of {reach['puzzles']} puzzles were reached. Rules, notes and practice are always there."]},
    {"id": "exploit", "dur": 7,
     "cap": [f"The reward can't be gamed. {n(facts['attacks_main'])} attacks, plus {n(facts['attacks_clock'])} on the clock.",
             "None got through. The score sheet is signed by the game server."]},
    {"id": "learn", "dur": 15, "cap": LEARN_CAP},
    {"id": "repro", "dur": 7,
     "cap": [SPINE]},
]
for sc in SCENES:
    sc["cap"] = [c for c in sc["cap"] if c]
    assert all("—" not in c for c in sc["cap"]), sc["id"]
TOTAL = sum(sc["dur"] for sc in SCENES)
assert TOTAL <= 128, TOTAL  # plus 1.5 s on the closing card, the video must stay under 2:10

data = {
    "board": {"w": W, "h": H, "files": FILES},
    "ladder": ladder,
    "not_measured": not_measured,
    "models_measured": n_models,
    "runs_measured": n_runs,
    "agents": {s: {k: v for k, v in a.items() if not k.startswith("_")} for s, a in agents.items()},
    "best_many": best_many and best_many["label"],
    "excluded": excluded_all,
    "replay": replay,
    "mistakes": {"graded": len(graded), "kinds": dict(kinds)},
    "reach": reach,
    "gemini4_losses": g4,
    "depth": depth,
    "deep": deep,
    "horizon": horizon,
    "practice": practice,
    "practice_max_puzzles": practice_max,
    "probe": probe,
    "small": small,
    "curve": curve,
    "facts": facts,
    "readme_source": README_SRC,
    "spine": SPINE,
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
        "gap": "Ladder chart: perfect play, rules-only search, every measured model (bar = mean, one dot per run), the baselines; footnote with the models not measured.",
        "depth": "Bar chart: Gemini 4 wins by depth over every kept run, with the counts.",
        "horizon": "Grid by depth, win in 1 to 9: perfect play, Fable 5.2's one run, Opus 5.5, Carbon; the deep set fills win in 7 to 9.",
        "fair": "Three facts: per-puzzle clock, Gemini 4 losses by cause, tools available.",
        "exploit": "Attack counts with every row refused.",
        "learn": "Small model: reward-only and imitation curves, Gemini 4 one-move band; note on in-session practice.",
        "repro": "Closing card: the spine sentence, the command, the repo.",
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

# ---------------------------------------------------------------- check against the README's table
README_MEANS = {"Perfect play (solver)": (1.000, None), "Rules-only search, 80 lines": (0.917, None),
                "Claude Fable 5.2": (0.750, 1), "Gemini 4 Carbon": (0.593, 17), "Gemini 4 Hydrogen": (0.537, 18),
                "Gemini 4 Argon": (0.536, 14), "Claude Opus 5.5": (0.531, 8), "Claude Haiku 5.5": (0.500, 3),
                "Gemini 3.8 Flash": (0.441, 17), "Gemini 3.1 Pro": (0.392, 17), "Claude Sonnet 5": (0.389, 3),
                "Nemotron 3 Ultra": (0.194, 3), "Stop early (2 easiest)": (0.167, None), "Do nothing": (0.000, None)}
print("wrote demo/data.json, demo/data.js, demo/script.md")
print(f"{'row':32s} {'here':>14s} {'README':>14s}")
bad = 0
for r in ladder:
    want = README_MEANS.get(r["label"])
    here = f"{f3(r['value'])} ({r['landed']})"
    there = "?" if not want else f"{want[0]:.3f}" + (f" ({want[1]})" if want[1] else "")
    ok = want and r["value"] is not None and round(r["value"], 3) == want[0] and (want[1] is None or want[1] == r["landed"])
    bad += not ok
    print(f"{r['label']:32s} {here:>14s} {there:>14s} {'ok' if ok else 'MISMATCH'}")
d_ok = dt and [dt[str(t)]["solved"] for t in TIERS] == [97, 97, 76, 43, 7, 7] and all(dt[str(t)]["of"] == 98 for t in TIERS) and depth["runs"] == 49
print("Gemini 4 by depth:", depth["runs"], "runs,", " ".join(frac(dt, t).replace(" of ", "/") for t in TIERS), "ok" if d_ok else "MISMATCH")
print("Gemini 4 losses:", g4, "ok" if (g4["lost"], g4["wrong_move"], g4["clock"]) == (261, 258, 3) else "MISMATCH")
print("deep set:", {k: f"{v['solved']}/{v['total']} in {v['runs']} runs" for k, v in deep.items()})
print("Fable by depth:", fable_t and " ".join(frac(fable_t, t).replace(" of ", "/") for t in TIERS))
print("practice:", [(p["model"], p["told"], p["runs"], p["mean"], p["diff_puzzles"]) for p in practice], "max", practice_max)
print("replay:", replay and f"{replay['model']} {replay['id']} {replay['played']} -> {replay['verdict']}; held {replay['held']}; "
      f"same move {replay['same_move_runs']} runs, models {replay['same_move_models']}")
print("excluded:", len(excluded_all), "; not measured:", [x["label"] for x in not_measured])
print("README source:", README_SRC, "; mismatches:", bad + (not d_ok))
