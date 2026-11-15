"""Builds one self-contained replay page for every final run: pick a model, a run and a puzzle, watch the moves.

    python tools/replay_site.py                  # writes demo/replays.html
    python tools/replay_site.py out.html         # or somewhere else

Reads jobs/final/clock-24d6707-<model>-x3*/task__*/verifier/{details.json,reward.txt} for the five models
(every batch: x3, x3b, x3c, ...) and the four reference rows. Trials without a score sheet in details.json
(not finished yet, or failed) are skipped and counted on stdout. Each move is graded by `frames` from
tools/replay.py and each lost puzzle by `diagnose` from tools/analyze.py.
The data is baked into the page: no fetch, no scripts from elsewhere, works from file://.
The one external resource is the Google Fonts stylesheet of the presentation deck; offline the page falls back to
Georgia, Arial and Courier New.

The page opens on a one-screen stage (board, verdict, moves), with every run of the chosen model and an
overview of all models below it. Keys: left/right step, up/down puzzle, space play, T tour, Esc leave, F fullscreen.
The tour's stops are picked from the data by rule, so they follow new runs without edits.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from analyze import diagnose  # noqa: E402
from replay import frames  # noqa: E402
from thinice.board import FILES, H, W  # noqa: E402

JOBS = ROOT / "jobs" / "final"
PREFIX = "clock-24d6707-"
# (slug, job glob, label, short label, kind); models read every batch -x3, -x3b, -x3c, ...
GROUPS = [
    ("argon", "argon-x3*", "Gemini 4 Argon", "Argon", "model"),
    ("carbon", "carbon-x3*", "Gemini 4 Carbon", "Carbon", "model"),
    ("hydrogen", "hydrogen-x3*", "Gemini 4 Hydrogen", "Hydrogen", "model"),
    ("flash38", "flash38-x3*", "Gemini 3.8 Flash", "3.8 Flash", "older"),
    ("pro31", "pro31-x3*", "Gemini 3.1 Pro", "3.1 Pro", "older"),
    ("reference", "reference", "Perfect play (solver)", "Perfect play", "ref"),
    ("reference-search", "reference-search", "Rules-only search, 20 s per puzzle", "Rules-only search", "ref"),
    ("stop-early", "stop-early", "Baseline: stop early (2 easiest)", "Stop early", "base"),
    ("do-nothing", "do-nothing", "Baseline: do nothing", "Do nothing", "base"),
]


def short(fr: dict) -> str:
    if fr["kind"] == "start":
        return "start"
    if fr["kind"] == "reply":
        return "reply"
    if fr["kind"] == "good":
        return "wins" if "Solved" in fr["text"] else "keeps the win"
    if "draw" in fr["text"]:
        return "draw"
    if "move" not in fr:
        return "too slow"
    return "loses"


def cell(row: dict) -> dict:
    fs = frames(row)
    names = [m for pair in row["history"] for m in pair if m]
    it = iter(names)
    for fr in fs:
        if "move" in fr:
            fr["name"] = next(it)
        fr["v"] = short(fr)
    last = fs[-1]
    if row["status"] == "failed" and row["reason"] == "out of time":
        fs.append({"blue": last["blue"], "red": last["red"], "kind": "bad", "v": "clock",
                   "text": "The puzzle clock ran out. The puzzle counts as lost."})
    elif row["status"] == "failed" and row["reason"] == "skipped":
        fs.append({"blue": last["blue"], "red": last["red"], "kind": "bad", "v": "skipped",
                   "text": "The agent skipped this puzzle. It counts as lost."})
    elif row["status"] == "open" and not row["history"]:
        fs[0]["text"] += " Not reached in this run."
    elif row["status"] == "open":
        fs.append({"blue": last["blue"], "red": last["red"], "kind": "bad", "v": "open",
                   "text": "The session ended before this puzzle was finished."})
    bad = next((i for i, fr in enumerate(fs) if fr["kind"] == "bad"), None)
    status = "open" if row["status"] == "open" and not row["history"] else row["status"]
    g = diagnose(row)
    return {"status": status, "reason": row["reason"], "bad": bad, "moves_used": row["moves_used"],
            "moves_allowed": row["moves_allowed"], "diag": g["kind"] if g else None, "frames": fs}


def collect():
    groups, skipped, puzzles = [], Counter(), None
    for slug, pattern, label, short_label, kind in GROUPS:
        dirs = sorted((d for d in JOBS.glob(f"{PREFIX}{pattern}") if d.is_dir()), key=lambda d: d.name.lower())
        runs = []
        for d in dirs:
            for t in sorted(d.glob("task__*"), key=lambda p: p.name.lower()):
                f = t / "verifier" / "details.json"
                if not f.exists():
                    skipped[(d.name, "no details.json")] += 1
                    continue
                try:
                    det = json.loads(f.read_text(encoding="utf-8"))
                except ValueError:
                    det = {}
                if not isinstance(det.get("puzzles"), list) or "solved" not in det or "total" not in det:
                    skipped[(d.name, "details.json without a score sheet")] += 1
                    continue
                try:
                    rt = float((t / "verifier" / "reward.txt").read_text().strip())
                    if abs(rt - det["reward"]) > 5e-5:  # reward.txt is rounded to 4 places
                        print(f"warning: {d.name}/{t.name} reward.txt {rt} != details {det['reward']}")
                except (OSError, ValueError):
                    pass
                rows = sorted(det["puzzles"], key=lambda r: r["id"])
                ids = [(r["id"], r["win_in"]) for r in rows]
                if puzzles is None:
                    puzzles = ids
                assert ids == puzzles, f"{t}: different puzzle set"
                runs.append({"n": len(runs) + 1, "job": d.name, "trial": t.name, "reward": det["reward"],
                             "solved": det["solved"], "total": det["total"], "cells": [cell(r) for r in rows]})
        if not runs:
            print(f"no runs with a score sheet for {PREFIX}{pattern}, left out")
            continue
        solved, total = sum(r["solved"] for r in runs), sum(r["total"] for r in runs)
        groups.append({"slug": slug, "label": label, "short": short_label, "kind": kind,
                       "jobs": [d.name for d in dirs], "solved": solved, "total": total,
                       "mean": round(solved / total, 4), "runs": runs})
    return groups, skipped, [{"id": i, "win_in": w} for i, w in puzzles]


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thin Ice replays</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600;700&display=swap">
<style>
/* palette and type from the presentation deck (demo deck.css); one light theme.
   type scale: 14 mono labels, 17 text, 24 tabs, 40 captions and verdicts, 48 headlines */
:root { color-scheme: light; --ink:#17191C; --paper:#F1ECE2; --soft:#55585C; --faint:#6E6A62; --card:#FAF7F0; --hair:#D8D0BF;
  --glacier:#2F5D93; --ice:#A9C4E6; --frost:#BCD3CC; --ember:#E0352B; --ember-fill:#EA6A60;
  --serif:'Instrument Serif', Georgia, serif; --sans:'Inter', Arial, sans-serif; --mono:'Courier Prime', 'Courier New', monospace;
  --slide: 800ms; }
* { box-sizing: border-box; }
html { background:var(--paper); }
body { margin:0; background:var(--paper); color:var(--ink); font:17px/1.5 var(--sans); }
p { margin:0; }
button { font:inherit; color:inherit; }
:focus-visible { outline:2px solid var(--glacier); outline-offset:3px; }
.eyebrow { font-family:var(--mono); font-weight:700; font-size:14px; letter-spacing:1px; text-transform:uppercase; color:var(--ink); }
.mono { font-family:var(--mono); font-weight:700; white-space:nowrap; }
.mark { background:var(--ember-fill); color:var(--ink); padding:0 8px; }
.tb { background:none; border:0; padding:4px 0; font:500 17px var(--sans); color:var(--ink); cursor:pointer; text-decoration:underline; text-decoration-color:var(--hair); text-decoration-thickness:2px; text-underline-offset:6px; white-space:nowrap; }
.tb:hover { text-decoration-color:var(--ink); }
.tb[disabled] { color:var(--faint); cursor:default; text-decoration-color:transparent; }
.keyhint { font-family:var(--mono); font-weight:700; font-size:14px; color:var(--soft); letter-spacing:1px; }

/* ---------------------------------------------------------------- stage: one screen */
.stage { height:100vh; height:100svh; min-height:600px; max-width:1680px; margin:0 auto; padding:28px 48px 32px; display:grid; grid-template-rows:auto auto minmax(0, 1fr); }
.top { display:flex; justify-content:space-between; align-items:flex-end; gap:32px; padding-bottom:18px; }
.top h1 { font-family:var(--serif); font-weight:400; font-size:48px; line-height:1; letter-spacing:-1px; margin:0 0 6px; }
.top h1 em { color:var(--soft); }
.top .lead { max-width:none; }
.acts { display:flex; gap:28px; align-items:baseline; }
.tabs { display:flex; flex-wrap:wrap; gap:0 36px; border-bottom:2px solid var(--hair); margin-bottom:28px; }
.tab { background:none; border:0; border-bottom:2px solid transparent; margin-bottom:-2px; padding:6px 0 10px; display:flex; align-items:baseline; gap:10px; cursor:pointer; }
.tab .tl { font-family:var(--serif); font-size:24px; line-height:1.1; color:var(--soft); }
.tab .tm { font-family:var(--mono); font-weight:700; font-size:14px; color:var(--soft); font-variant-numeric:tabular-nums; }
.tab:hover .tl { color:var(--ink); }
.tab.on { border-bottom-color:var(--ink); } .tab.on .tl { color:var(--ink); }
.area { display:grid; grid-template-columns:auto minmax(0, 1fr); grid-template-rows:auto minmax(0, 1fr); grid-template-areas:"board lede" "board side"; column-gap:56px; min-height:0; }
.lede { grid-area:lede; max-width:620px; }
.lede h2 { font-family:var(--serif); font-weight:400; font-size:48px; line-height:1.08; letter-spacing:-0.5px; margin:10px 0 24px; }
.lede h2.cap { font-size:40px; }
.lede h2 .mono, .closing h2 .mono { font-size:0.82em; }
.bcol { grid-area:board; }
.side { grid-area:side; max-width:620px; min-height:0; display:flex; flex-direction:column; }
/* board: absolute cells, stones slide between them */
.board { position:relative; }
.cell { position:absolute; background:var(--card); border:2px solid var(--hair); }
.cell.hi { background:var(--frost); border-color:var(--frost); }
.lab { position:absolute; display:flex; align-items:center; justify-content:center; font-family:var(--mono); font-weight:700; font-size:14px; color:var(--soft); }
.stone { position:absolute; border-radius:50%; }
.stone.b { background:var(--glacier); } .stone.r { background:var(--ember); }
.stone.slide { transition:left var(--slide) cubic-bezier(.3, 0, .2, 1), top var(--slide) cubic-bezier(.3, 0, .2, 1); }
/* verdict */
.verdict { min-height:148px; padding:22px 26px; display:flex; flex-direction:column; justify-content:center; gap:8px; border:2px solid var(--hair); transition:opacity 450ms ease; }
.verdict.good { background:var(--ice); border-color:var(--ice); } .verdict.bad { background:var(--ember-fill); border-color:var(--ember-fill); }
.verdict.pending { opacity:0; transition:none; }
.v-title { font-family:var(--serif); font-size:40px; line-height:1.05; }
.v-title .mono { font-size:32px; }
.v-body { font-size:17px; line-height:1.45; }
.ctl { display:flex; flex-wrap:wrap; gap:8px 28px; align-items:baseline; margin:18px 0 6px; }
.ctl .pos { margin-left:auto; font-family:var(--mono); font-weight:700; font-size:14px; letter-spacing:1px; text-transform:uppercase; color:var(--soft); font-variant-numeric:tabular-nums; }
.moves { list-style:none; margin:10px 0 0; padding:0; overflow-y:auto; min-height:0; flex:1 1 auto; border-top:2px solid var(--hair); }
.moves li { border-bottom:2px solid var(--hair); }
.moves button { width:100%; text-align:left; padding:6px 10px; border:0; border-left:3px solid transparent; background:transparent; cursor:pointer; display:flex; align-items:baseline; gap:12px; font-size:17px; font-variant-numeric:tabular-nums; }
.moves button:hover { background:var(--card); }
.moves button.on { background:var(--card); border-left-color:var(--ink); }
.moves .k { width:1.6em; font-family:var(--mono); font-weight:700; color:var(--soft); } .moves .g { color:var(--glacier); } .moves .r { color:var(--soft); }
/* tour closing screen */
.closing { display:none; grid-column:1 / -1; grid-row:1 / -1; min-height:0; overflow:auto; }
.closing h2 { font-family:var(--serif); font-weight:400; font-size:48px; line-height:1.08; letter-spacing:-0.5px; margin:10px 0 24px; max-width:980px; }
.stage.end .closing { display:block; } .stage.end .bcol, .stage.end .lede, .stage.end .side { display:none; }

/* ---------------------------------------------------------------- below the fold */
.below { max-width:1680px; margin:0 auto; padding:72px 48px 64px; }
.sec { max-width:1180px; } .sec + .sec { margin-top:88px; }
.sec h3 { font-family:var(--serif); font-weight:400; font-size:40px; line-height:1.1; margin:8px 0 6px; }
.sec .note { color:var(--soft); margin-bottom:22px; max-width:680px; }
.ph { text-align:center; font-family:var(--mono); font-weight:700; font-size:14px; line-height:1.15; padding-bottom:6px; }
.ph span { display:block; font-family:var(--sans); font-weight:400; font-size:13px; color:var(--soft); }
.c { font-family:var(--mono); font-weight:700; font-size:14px; padding:0; border-radius:0; border:2px solid var(--hair); background:var(--card); color:var(--ink); cursor:pointer; display:flex; align-items:center; justify-content:center; gap:1px; font-variant-numeric:tabular-nums; min-width:0; overflow:hidden; white-space:nowrap; }
.c.solved { background:var(--ice); border-color:var(--ice); }
.c.failed { background:var(--ember-fill); border-color:var(--ember-fill); }
.c.open { background:transparent; color:var(--soft); font-weight:400; }
.c:hover { border-color:var(--ink); }
.c.on { outline:3px solid var(--ink); outline-offset:1px; position:relative; z-index:1; }
.c small { font-size:11px; }
.c .t { font-weight:400; color:var(--soft); }
.strip { display:grid; grid-template-columns:210px repeat(12, minmax(0, 1fr)); gap:4px; }
.strip .c { height:34px; }
.strip.compact { gap:3px; } .strip.compact .c { height:26px; font-size:13px; }
.rl { display:flex; align-items:center; gap:12px; font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; min-width:0; font-size:15px; color:var(--soft); }
.rl b { color:var(--ink); font-weight:600; }
.ov { display:grid; grid-template-columns:minmax(210px, 1.7fr) repeat(12, minmax(0, 1fr)); gap:4px; }
.ov .c { height:44px; }
.ov .ol { display:flex; flex-direction:column; gap:0; min-width:0; align-self:center; padding-right:8px; }
.ov .ol .n { font-family:var(--serif); font-size:22px; line-height:1.1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ov .ol .tm { font-family:var(--mono); font-weight:700; font-size:14px; color:var(--soft); font-variant-numeric:tabular-nums; white-space:nowrap; }
.ov .k-ref .n, .ov .k-base .n { color:var(--soft); }
.ov .sep { grid-column:1 / -1; border-top:2px solid var(--hair); margin:10px 0 6px; }
.legend { display:flex; flex-wrap:wrap; gap:8px 28px; font-size:15px; color:var(--soft); margin:0 0 18px; }
.legend > span { display:inline-flex; align-items:center; gap:10px; }
.legend .c { width:40px; height:26px; cursor:default; }
footer { max-width:1680px; margin:0 auto; padding:20px 48px 56px; }
footer .in { border-top:2px solid var(--ink); padding-top:16px; display:flex; flex-direction:column; gap:8px; font-size:15px; color:var(--soft); max-width:1180px; }
.rise { animation: rise 700ms cubic-bezier(0.2, 0.7, 0.2, 1) both; animation-delay: calc(var(--i, 0) * 110ms); }
@keyframes rise { from { opacity: 0; transform: translateY(16px); } }
@media (prefers-reduced-motion: reduce) { .rise { animation:none; } .verdict { transition:none; } }

/* ---------------------------------------------------------------- narrow: the stage scrolls */
@media (max-width: 899px) {
  .stage { height:auto; min-height:0; padding:24px 16px 8px; }
  .top { flex-direction:column; align-items:flex-start; gap:12px; }
  .top h1 { font-size:44px; }
  .tabs { gap:0 22px; margin-bottom:20px; }
  .tab .tl { font-size:20px; } .tab { padding:4px 0 8px; }
  .area { grid-template-columns:minmax(0, 1fr); grid-template-rows:none; grid-template-areas:"lede" "board" "side"; }
  .lede h2 { font-size:36px; margin:8px 0 18px; } .lede h2.cap { font-size:32px; }
  .side { margin-top:22px; }
  .moves { overflow:visible; }
  .v-title { font-size:32px; } .v-title .mono { font-size:26px; }
  .closing h2 { font-size:34px; }
  .below { padding:56px 16px 40px; } footer { padding:16px 16px 40px; }
  .sec h3 { font-size:32px; }
  .strip, .ov { grid-template-columns:repeat(12, minmax(0, 1fr)); gap:3px; }
  .strip .corner, .ov .corner { display:none; }
  .rl, .ov .ol { grid-column:1 / -1; margin-top:8px; }
  .ph { font-size:11px; } .ph span, .c .t { display:none; }
  .c { font-size:12px; border-width:1px; } .c small { font-size:10px; }
  .strip .c { height:30px; } .strip.compact .c { height:26px; } .ov .c { height:32px; }
  .ov .ol .n { font-size:20px; }
}
</style></head><body>
<section class="stage" id="stage">
<header class="top rise">
<div><h1>Thin Ice <em>replays</em></h1>
<p class="lead">Blue is the model under test. Red is a perfect defender. Every Blue move is checked against the solved game.</p></div>
<div class="acts"><button class="tb" id="tourbtn">Start tour</button><button class="tb" id="fsbtn">Fullscreen</button></div>
</header>
<nav class="tabs rise" style="--i:1" id="tabs" aria-label="model"></nav>
<div class="area rise" style="--i:2" id="area">
<div class="lede"><p class="eyebrow" id="eb"></p><h2 id="hl"></h2></div>
<div class="bcol"><div class="board" id="board" aria-label="board"></div></div>
<div class="side">
<div class="verdict" id="note" aria-live="polite"><p class="v-title" id="vt"></p><p class="v-body" id="vb"></p></div>
<div class="ctl"><button class="tb" id="prev">&larr; Back</button><button class="tb" id="play">Play</button><button class="tb" id="next">Next &rarr;</button><span class="pos" id="pos"></span></div>
<ol class="moves" id="moves"></ol>
</div>
<div class="closing" id="closing"><p class="eyebrow" id="ceb"></p><h2 id="chl"></h2><div class="ov" id="cov"></div>
<div class="ctl"><button class="tb" id="cprev">&larr; Previous stop</button><button class="tb" id="cleave">Leave tour</button></div></div>
</div>
</section>
<div class="below">
<section class="sec" id="runs">
<p class="eyebrow" id="st"></p><h3 id="sh"></h3><p class="note" id="sn"></p>
<div class="strip" id="strip"></div>
</section>
<section class="sec">
<p class="eyebrow">Overview</p><h3>All models</h3>
<p class="note">Each cell counts the runs that solved the puzzle. Click one to watch that model's first lost run of it.</p>
<div class="legend"><span><span class="c" id="lg1"></span>every run solved it; lighter means fewer</span><span><span class="c"><span class="mark">0</span></span>no run solved it</span><span><span class="c solved">&#10003;</span><span class="c failed">&#10007;<small>3</small></span><span class="c open">&#9675;</span>solved, lost at step 3, not reached</span></div>
<div class="ov" id="ov"></div>
</section>
</div>
<footer><div class="in"><p id="src"></p>
<p>Keys: left and right arrows step through the moves, up and down change the puzzle, space plays or pauses, T starts or leaves the tour (in the tour, space or right arrow goes to the next stop, Esc leaves), F toggles fullscreen.</p></div></footer>
<script>
const DATA = __DATA__;
const el = id => document.getElementById(id);
const RUNS = []; DATA.groups.forEach(g => g.runs.forEach(r => RUNS.push({ g, r })));
const isModel = g => g.kind === 'model' || g.kind === 'older';
const MODELS = DATA.groups.filter(isModel), REFS = DATA.groups.filter(g => !isModel(g));
const MRUNS = RUNS.filter(x => isModel(x.g));
const TABS = MODELS.map(g => ({ id: g.slug, label: g.short, groups: [g] }));
if (REFS.length) TABS.push({ id: 'refs', label: 'References', groups: REFS });
const tabOf = g => isModel(g) ? g.slug : 'refs';
const REDUCED = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
const SLIDE = REDUCED ? 0 : 800, STEP = 1600;
let k = 0, p = 0, f = 0, shownTab = null, token = 0, playing = false, playEnd = 0, timer = null, tour = null, geo = null;
const f3 = x => x.toFixed(3);
const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
const mv = s => '<span class="mono">' + s + '</span>';
const mark = c => c.status === 'solved' ? '✓' : c.status === 'failed' ? '✗' : '○';
const word = c => c.status === 'solved' ? 'solved' : c.status === 'open' ? 'not reached' : 'lost' + (c.reason ? ' (' + c.reason + ')' : '');
const idx = r => RUNS.findIndex(x => x.r === r);
const blueMoves = c => c.frames.filter(fr => fr.name && fr.kind !== 'reply');
const lastOf = (i, j) => RUNS[i].r.cells[j].frames.length - 1;

/* ------------------------------------------------ board geometry and stones */
function layout() {
  const area = el('area'), wide = innerWidth >= 900;
  const gap = wide ? 6 : 4, lab = 24;
  let sz;
  if (wide) {
    const h = area.clientHeight, w = area.clientWidth;
    sz = Math.min((h - lab) / DATA.h - gap, (w * 0.58 - lab - gap) / DATA.w - gap, 128);
  } else sz = Math.min((area.clientWidth - lab - gap) / DATA.w - gap, 64);
  sz = Math.max(28, Math.floor(sz));
  const bd = el('board'); bd.innerHTML = '';
  bd.style.width = (lab + gap + DATA.w * (sz + gap)) + 'px'; bd.style.height = (DATA.h * (sz + gap) + lab) + 'px';
  geo = { sz, gap, lab, cells: [], d: Math.round(sz * 0.68) };
  for (let s = 0; s < DATA.w * DATA.h; s++) { const c = document.createElement('div'), q = pos(s); c.className = 'cell'; Object.assign(c.style, { left: q.x + 'px', top: q.y + 'px', width: sz + 'px', height: sz + 'px' }); bd.appendChild(c); geo.cells.push(c); }
  for (let y = 0; y < DATA.h; y++) { const l = document.createElement('div'); l.className = 'lab'; l.textContent = y + 1; Object.assign(l.style, { left: 0, top: (DATA.h - 1 - y) * (sz + gap) + 'px', width: lab + 'px', height: sz + 'px' }); bd.appendChild(l); }
  DATA.files.split('').forEach((ch, x) => { const l = document.createElement('div'); l.className = 'lab'; l.textContent = ch; Object.assign(l.style, { left: lab + gap + x * (sz + gap) + 'px', top: DATA.h * (sz + gap) + 'px', width: sz + 'px', height: lab + 'px' }); bd.appendChild(l); });
}
function pos(s) { return { x: geo.lab + geo.gap + (s % DATA.w) * (geo.sz + geo.gap), y: (DATA.h - 1 - Math.floor(s / DATA.w)) * (geo.sz + geo.gap) }; }
function place(st, s) { const q = pos(s), o = (geo.sz - geo.d) / 2; st.style.left = q.x + o + 'px'; st.style.top = q.y + o + 'px'; }
function stones(fr, prev) {
  const bd = el('board'); bd.querySelectorAll('.stone').forEach(s => s.remove());
  const base = prev || fr, at = {};
  const put = (s, cls) => { const d = document.createElement('div'); d.className = 'stone ' + cls; d.style.width = d.style.height = geo.d + 'px'; place(d, s); bd.appendChild(d); at[s] = d; };
  base.blue.forEach(s => put(s, 'b')); base.red.forEach(s => put(s, 'r'));
  if (prev && fr.move && at[fr.move[0]]) { const st = at[fr.move[0]]; void st.offsetWidth; st.classList.add('slide'); place(st, fr.move[1]); }
  geo.cells.forEach((c, s) => c.classList.toggle('hi', !!(fr.move && fr.move.includes(s))));
}

/* ------------------------------------------------ headline and verdict */
function setHTML(id, html) { el(id).innerHTML = html; }
function headline(c, q) {
  const head = 'Blue to move, win in ' + q.win_in + '. ';
  if (c.status === 'solved') { const n = blueMoves(c).length; return head + 'It won in ' + plural(n, 'move') + '.'; }
  if (c.status === 'open') return head + 'This run never reached it.';
  const b = c.bad !== null ? c.frames[c.bad] : null;
  if (b && b.name) return head + 'It played ' + mv(b.name) + '.';
  if (b && b.v === 'clock') return head + 'The puzzle clock ran out.';
  if (b && b.v === 'skipped') return head + 'It skipped the puzzle.';
  if (b && b.v === 'too slow') return head + 'It ran out of moves.';
  return head + 'It did not finish.';
}
function verdict(fr, anim) {
  const v = el('note'), t = ++token;
  v.className = 'verdict ' + fr.kind + (anim && SLIDE ? ' pending' : '');
  const sym = fr.kind === 'good' ? '✓ ' : fr.kind === 'bad' ? '✗ ' : '';
  const cut = fr.name ? fr.text.indexOf(': ') : -1;
  if (cut > 0) {
    el('vt').innerHTML = ''; el('vt').append(sym + fr.text.slice(0, cut - fr.name.length));
    const nm = document.createElement('span'); nm.className = 'mono'; nm.textContent = fr.name; el('vt').append(nm);
    const rest = fr.text.slice(cut + 2); el('vb').textContent = rest.charAt(0).toUpperCase() + rest.slice(1); el('vb').hidden = false;
  } else { el('vt').textContent = sym + fr.text; el('vb').textContent = ''; el('vb').hidden = true; }
  if (anim && SLIDE) setTimeout(() => { if (t === token) v.classList.remove('pending'); }, SLIDE + 60);
}

/* ------------------------------------------------ drawing */
function draw(anim) {
  const x = RUNS[k], c = x.r.cells[p], q = DATA.puzzles[p], fr = c.frames[f], tid = tabOf(x.g);
  if (shownTab !== tid) { strip(TABS.find(t => t.id === tid)); shownTab = tid; }
  document.querySelectorAll('.tab').forEach(b => { b.classList.toggle('on', b.dataset.t === tid); b.setAttribute('aria-pressed', b.dataset.t === tid); });
  document.querySelectorAll('#strip .c.on').forEach(b => b.classList.remove('on'));
  const cur = document.querySelector('#strip .c[data-k="' + k + '"][data-p="' + p + '"]'); if (cur) cur.classList.add('on');
  const where = (isModel(x.g) ? x.g.label + ' · run ' + x.r.n : x.g.label) + ' · puzzle ' + q.id;
  const stop = tour && tour.stops[tour.i];
  el('eb').textContent = stop ? 'Tour ' + (tour.i + 1) + ' / ' + tour.stops.length + ' · ' + where : where;
  setHTML('hl', stop ? stop.cap : headline(c, q)); el('hl').className = stop ? 'cap' : '';
  stones(fr, anim && SLIDE && f > 0 && fr.move ? c.frames[f - 1] : null);
  verdict(fr, anim && fr.move);
  el('pos').textContent = 'Step ' + f + ' of ' + (c.frames.length - 1);
  el('prev').innerHTML = tour ? '&larr; Previous stop' : '&larr; Back';
  el('next').innerHTML = tour ? 'Next stop &rarr;' : 'Next &rarr;';
  el('prev').disabled = tour ? tour.i === 0 : f === 0;
  el('next').disabled = tour ? false : f === c.frames.length - 1;
  el('play').textContent = playing ? 'Pause' : 'Play';
  const ml = el('moves'); ml.innerHTML = ''; let turn = 0;
  c.frames.forEach((g, i) => {
    if (i === 0) return;
    const li = document.createElement('li'), b = document.createElement('button');
    let label;
    if (g.kind === 'reply') label = '<span class="k"></span><span class="r">Red ' + mv(g.name) + '</span>';
    else if (g.name) { turn++; label = '<span class="k">' + turn + '</span><span class="' + (g.kind === 'good' ? 'g' : 'mark') + '">' + (g.kind === 'good' ? '✓' : '✗') + ' Blue ' + mv(g.name) + ', ' + g.v + '</span>'; }
    else label = '<span class="k"></span><span class="mark">✗ ' + g.v + '</span>';
    b.innerHTML = label; b.className = i === f ? 'on' : ''; b.onclick = () => { stopPlay(); f = i; draw(false); };
    li.appendChild(b); ml.appendChild(li);
  });
  const on = ml.querySelector('button.on'); if (on && ml.scrollHeight > ml.clientHeight) on.scrollIntoView({ block: 'nearest' });
  if (!tour) history.replaceState(null, '', '#' + x.g.slug + '/' + x.r.n + '/' + q.id + '/' + f);
}
function open(i, j) { const c = RUNS[i].r.cells[j]; k = i; p = j; f = c.status === 'failed' && c.bad !== null ? c.bad : 0; draw(false); }
function toStage() { el('stage').scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth' }); }

/* ------------------------------------------------ play */
function stopPlay() { playing = false; clearTimeout(timer); el('play').textContent = 'Play'; }
function startPlay(end) {
  const last = end === undefined ? RUNS[k].r.cells[p].frames.length - 1 : end;
  if (f >= last) { f = 0; draw(false); }
  playing = true; playEnd = last; el('play').textContent = 'Pause';
  timer = setTimeout(tick, f === 0 ? 1000 : STEP);
}
function tick() {
  if (!playing) return;
  if (f < playEnd) { f++; draw(true); }
  if (f >= playEnd) { playing = false; el('play').textContent = 'Play'; return; }
  timer = setTimeout(tick, STEP);
}

/* ------------------------------------------------ tabs, strip, overview */
function tabs() {
  const t = el('tabs'); t.innerHTML = '';
  TABS.forEach(tb => {
    const b = document.createElement('button'); b.className = 'tab'; b.dataset.t = tb.id; b.title = tb.id === 'refs' ? 'References and baselines' : tb.groups[0].label + ', ' + plural(tb.groups[0].runs.length, 'run') + ', mean ' + f3(tb.groups[0].mean);
    const n = tb.groups.reduce((s, x) => s + x.runs.length, 0);
    b.innerHTML = '<span class="tl">' + tb.label + '</span><span class="tm">' + (tb.id === 'refs' ? '' : f3(tb.groups[0].mean)) + '</span>';
    b.onclick = () => { stopPlay(); if (tour) leaveTour(true); k = idx(tb.groups[0].runs[0]); f = 0; draw(false); };
    t.appendChild(b);
  });
}
function headers(gd) {
  const corner = document.createElement('div'); corner.className = 'corner'; gd.appendChild(corner);
  DATA.puzzles.forEach(q => { const d = document.createElement('div'); d.className = 'ph'; d.innerHTML = q.id + '<span>win in ' + q.win_in + '</span>'; gd.appendChild(d); });
}
function cellBtn(c, i, j, label) {
  const b = document.createElement('button'); b.className = 'c ' + c.status; b.dataset.k = i; b.dataset.p = j;
  b.innerHTML = mark(c) + (c.status === 'failed' && c.bad !== null ? '<small>' + c.bad + '</small>' : '');
  b.title = label + ', ' + DATA.puzzles[j].id + ': ' + word(c) + (c.status === 'failed' && c.bad !== null ? ', first losing move at step ' + c.bad : '');
  b.setAttribute('aria-label', b.title);
  b.onclick = () => { stopPlay(); if (tour) leaveTour(true); open(i, j); toStage(); };
  return b;
}
function strip(tb) {
  const gd = el('strip'); gd.innerHTML = ''; headers(gd);
  const rows = tb.groups.flatMap(g => g.runs.map(r => ({ g, r })));
  gd.classList.toggle('compact', rows.length > 10);
  rows.forEach(({ g, r }) => {
    const i = idx(r), l = document.createElement('div'); l.className = 'rl';
    l.innerHTML = tb.id === 'refs' ? '<b>' + g.short + '</b>' + r.solved + ' of ' + r.total : '<b>Run ' + r.n + '</b>' + f3(r.reward) + '<span>' + r.solved + ' of ' + r.total + '</span>';
    gd.appendChild(l);
    r.cells.forEach((c, j) => gd.appendChild(cellBtn(c, i, j, tb.id === 'refs' ? g.label : g.label + ', run ' + r.n)));
  });
  if (tb.id === 'refs') { el('st').textContent = 'References and baselines'; el('sh').textContent = 'Fixed policies'; el('sn').textContent = 'Perfect play, a rules-only search and two baselines, one run each. Click a cell to watch it on the board above.'; }
  else { const g = tb.groups[0]; el('st').textContent = g.label; el('sh').textContent = 'Every run'; el('sn').textContent = plural(g.runs.length, 'run') + ', mean ' + f3(g.mean) + ' (' + g.solved + ' of ' + g.total + ' puzzles won). Click a cell to watch it on the board above.'; }
}
function mix(s) { const a = [250, 247, 240], b = [110, 155, 209]; return 'rgb(' + a.map((v, i) => Math.round(v + (b[i] - v) * s)).join(',') + ')'; }
function overview(gd, modelsOnly) {
  gd.innerHTML = ''; headers(gd);
  let sep = false;
  DATA.groups.filter(g => !modelsOnly || isModel(g)).forEach(g => {
    if (!isModel(g) && !sep) { const s = document.createElement('div'); s.className = 'sep'; gd.appendChild(s); sep = true; }
    const l = document.createElement('div'); l.className = 'ol k-' + g.kind;
    l.innerHTML = '<span class="n">' + g.label + '</span><span class="tm">' + (isModel(g) ? f3(g.mean) + ' · ' + plural(g.runs.length, 'run') : f3(g.runs[0].reward)) + '</span>';
    gd.appendChild(l);
    DATA.puzzles.forEach((q, j) => {
      if (!isModel(g)) { gd.appendChild(cellBtn(g.runs[0].cells[j], idx(g.runs[0]), j, g.label)); return; }
      const n = g.runs.length, s = g.runs.filter(r => r.cells[j].status === 'solved').length;
      const b = document.createElement('button'); b.className = 'c';
      b.style.background = mix(s / n); if (s) b.style.borderColor = mix(s / n);
      b.innerHTML = (s ? s : '<span class="mark">0</span>') + '<span class="t">/' + n + '</span>';
      b.title = g.label + ', ' + q.id + ': solved in ' + s + ' of ' + n + ' runs'; b.setAttribute('aria-label', b.title);
      b.onclick = () => { stopPlay(); if (tour) leaveTour(true); const r = g.runs.find(x => x.cells[j].status === 'failed') || g.runs[0]; open(idx(r), j); toStage(); };
      gd.appendChild(b);
    });
  });
}

/* ------------------------------------------------ tour: stops picked from the data by rule */
function stops() {
  const S = [], P = DATA.puzzles, R = MRUNS.length;
  const clean = c => c.status === 'solved' && c.frames.every(fr => fr.kind !== 'bad');
  const solvedBy = j => MRUNS.filter(x => x.r.cells[j].status === 'solved').length;
  // (a) an easy puzzle solved without a wrong move
  for (const w of [2, 1]) {
    let hit = null;
    for (const x of MRUNS) { const j = P.findIndex((q, jj) => q.win_in === w && clean(x.r.cells[jj])); if (j >= 0) { hit = { x, j }; break; } }
    if (hit) { S.push({ i: idx(hit.x.r), j: hit.j, cap: 'An easy one first: ' + P[hit.j].id + ', win in ' + w + '. ' + hit.x.g.label + ' finds it.' }); break; }
  }
  // (b) the losing first move repeated in the most runs on one puzzle
  const seen = new Map();
  MRUNS.forEach(x => x.r.cells.forEach((c, j) => { const b = blueMoves(c)[0]; if (b && b.kind === 'bad') { const key = j + ' ' + b.name; if (!seen.has(key)) seen.set(key, []); seen.get(key).push(x); } }));
  let best = null; seen.forEach((xs, key) => { if (!best || xs.length > best[1].length) best = [key, xs]; });
  let B = null;
  if (best && best[1].length > 1) {
    const [key, xs] = best, j = +key.split(' ')[0], name = key.slice(key.indexOf(' ') + 1), x = xs[0];
    const models = new Set(xs.map(y => y.g.slug)).size;
    S.push({ i: idx(x.r), j, cap: 'The most repeated mistake: ' + xs.length + ' runs from ' + plural(models, 'model') + ' opened ' + P[j].id + ' with ' + mv(name) + '. It loses.' });
    B = { j, text: blueMoves(x.r.cells[j])[0].text, at: idx(x.r) };
  }
  // (c) Blue overlooks Red's immediate win
  outer: for (const x of MRUNS) for (let j = 0; j < P.length; j++) {
    const c = x.r.cells[j];
    if (c.diag === "overlooked Red's immediate win" && !(B && B.j === j && B.at === idx(x.r))) {
      S.push({ i: idx(x.r), j, cap: 'A missed threat on ' + P[j].id + '. After ' + mv(c.frames[c.bad].name) + ', Red completes three in a row next move.' }); break outer;
    }
  }
  // (d) the deepest puzzle any model solved
  let deep = null;
  MRUNS.forEach(x => x.r.cells.forEach((c, j) => { if (c.status === 'solved' && (!deep || P[j].win_in > P[deep.j].win_in)) deep = { x, j }; }));
  if (deep) S.push({ i: idx(deep.x.r), j: deep.j, cap: 'The deepest win any model found: ' + P[deep.j].id + ', win in ' + P[deep.j].win_in + '. ' + solvedBy(deep.j) + ' of ' + R + ' runs solved it.' });
  // (e) perfect play on the puzzle of (b)
  const ref = DATA.groups.find(g => g.slug === 'reference');
  if (B && ref) {
    const m = B.text.match(/Winning: ([^()]+) \((\d+) of (\d+)\)/);
    const list = m ? m[1].trim().split(' ') : [];
    S.push({ i: idx(ref.runs[0]), j: B.j, cap: m ? 'Perfect play on ' + P[B.j].id + '. ' + (list.length === 1 ? 'Only ' + mv(list[0]) + ' keeps the win' : list.map(mv).join(', ') + ' keep the win') + ': ' + m[2] + ' of ' + m[3] + ' first moves.' : 'Perfect play on ' + P[B.j].id + ', from the solver.' });
  }
  // (f) closing: all models, shallow against deep
  const tally = lo => { let s = 0, n = 0; MRUNS.forEach(x => x.r.cells.forEach((c, j) => { const w = P[j].win_in; if (lo ? w <= 3 : w >= 4) { n++; if (c.status === 'solved') s++; } })); return [s, n]; };
  const [s1, n1] = tally(true), [s2, n2] = tally(false);
  if (n1 && n2) S.push({ end: true, who: 'all models \u00b7 ' + plural(R, 'run'), cap: 'Win in 1 to 3: ' + s1 + ' of ' + n1 + ' solved. Win in 4 to 6: ' + s2 + ' of ' + n2 + '.' });
  return S;
}
function go(i) {
  stopPlay(); tour.i = i; const s = tour.stops[i];
  el('stage').classList.toggle('end', !!s.end);
  if (s.end) {
    el('ceb').textContent = 'Tour ' + (i + 1) + ' / ' + tour.stops.length + ' · ' + s.who;
    setHTML('chl', s.cap); overview(el('cov'), true); document.querySelectorAll('.tab').forEach(b => b.classList.remove('on'));
    return;
  }
  k = s.i; p = s.j; f = 0; draw(false); startPlay();
}
function startTour() {
  const s = stops(); if (!s.length) return;
  tour = { i: 0, stops: s }; el('tourbtn').textContent = 'Leave tour'; toStage(); go(0);
}
function leaveTour(quiet) {
  stopPlay(); tour = null; el('stage').classList.remove('end'); el('tourbtn').textContent = 'Start tour';
  if (!quiet) draw(false);
}
function nextStop() { if (tour.i < tour.stops.length - 1) go(tour.i + 1); else leaveTour(); }
function prevStop() { if (tour.i > 0) go(tour.i - 1); }

/* ------------------------------------------------ hash, keys, start */
function fromHash() {
  const h = decodeURIComponent(location.hash.slice(1)).split('/'); if (h.length < 3) return false;
  const i = RUNS.findIndex(x => x.g.slug === h[0] && String(x.r.n) === h[1]); const j = DATA.puzzles.findIndex(q => q.id === h[2]);
  if (i < 0 || j < 0) return false;
  k = i; p = j; f = Math.max(0, Math.min(parseInt(h[3], 10) || 0, lastOf(i, j))); return true;
}
function firstView() {
  // the mistake the deck shows: Gemini 4 Hydrogen on P07 playing c1-g5
  const j = DATA.puzzles.findIndex(q => q.id === 'P07'), g = DATA.groups.find(x => x.slug === 'hydrogen');
  if (g && j >= 0) for (const r of g.runs) {
    const fi = r.cells[j].frames.findIndex(fr => fr.name === 'c1-g5' && fr.kind !== 'reply');
    if (fi > 0) { k = idx(r); p = j; f = fi; return; }
  }
  const m = MODELS[0] || DATA.groups[0];
  for (const r of m.runs) { const jj = r.cells.findIndex(c => c.status === 'failed'); if (jj >= 0) { k = idx(r); p = jj; f = r.cells[jj].bad || 0; return; } }
  k = idx(m.runs[0]); p = 0; f = 0;
}
function fullscreen() {
  try { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); else document.documentElement.requestFullscreen().catch(() => {}); } catch (e) {}
}
el('prev').onclick = () => { if (tour) return prevStop(); stopPlay(); if (f > 0) { f--; draw(false); } };
el('next').onclick = () => { if (tour) return nextStop(); stopPlay(); if (f < lastOf(k, p)) { f++; draw(true); } };
el('play').onclick = () => { if (playing) stopPlay(); else startPlay(); };
el('tourbtn').onclick = () => { if (tour) leaveTour(); else startTour(); };
el('fsbtn').onclick = fullscreen;
el('cprev').onclick = prevStop;
el('cleave').onclick = () => leaveTour();
document.addEventListener('keydown', e => {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  const key = e.key;
  if (key === 't' || key === 'T') { e.preventDefault(); tour ? leaveTour() : startTour(); return; }
  if (key === 'f' || key === 'F') { e.preventDefault(); fullscreen(); return; }
  if (tour) {
    if (key === 'ArrowRight' || key === ' ') { e.preventDefault(); nextStop(); }
    else if (key === 'ArrowLeft') { e.preventDefault(); prevStop(); }
    else if (key === 'Escape') { e.preventDefault(); leaveTour(); }
    return;
  }
  if (key === ' ') { e.preventDefault(); el('play').click(); }
  else if (key === 'ArrowLeft') { e.preventDefault(); el('prev').click(); }
  else if (key === 'ArrowRight') { e.preventDefault(); el('next').click(); }
  else if (key === 'ArrowUp' && p > 0) { e.preventDefault(); stopPlay(); p--; f = 0; draw(false); }
  else if (key === 'ArrowDown' && p < DATA.puzzles.length - 1) { e.preventDefault(); stopPlay(); p++; f = 0; draw(false); }
});
document.addEventListener('keyup', e => { if (e.key === ' ') e.preventDefault(); });
window.addEventListener('hashchange', () => { if (!tour && fromHash()) { stopPlay(); draw(false); } });
let rz = 0; window.addEventListener('resize', () => { cancelAnimationFrame(rz); rz = requestAnimationFrame(() => { layout(); draw(false); }); });
el('src').textContent = 'Source: ' + DATA.source + ', every batch with a score sheet. Runs per model: ' + MODELS.map(g => g.short + ' ' + g.runs.length).join(', ') +
  '. A model mean is puzzles won over puzzles played across all of its runs; one run is 12 puzzles.';
const L = el('lg1'); L.style.background = L.style.borderColor = mix(1); L.innerHTML = '6';
tabs(); overview(el('ov')); layout();
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { layout(); draw(false); });
if (!fromHash()) firstView();
draw(false);
</script></body></html>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo" / "replays.html"
    groups, skipped, puzzles = collect()
    data = {"w": W, "h": H, "files": FILES, "source": f"jobs/final/{PREFIX}*", "puzzles": puzzles, "groups": groups}
    js = json.dumps(data, separators=(",", ":"), sort_keys=True).replace("</", "<\\/")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PAGE.replace("__DATA__", js), encoding="utf-8", newline="\n")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    for g in groups:
        print(f"  {g['label']}: {len(g['runs'])} run(s), mean {g['mean']:.4f} ({g['solved']}/{g['total']}); "
              "rewards " + ", ".join(f"{r['reward']:.3f}" for r in g["runs"]))
    if skipped:
        print("skipped trials:")
        for (job, why), n in sorted(skipped.items()):
            print(f"  {job}: {n} ({why})")
    else:
        print("skipped trials: none")


if __name__ == "__main__":
    main()
