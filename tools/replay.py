"""Turns a trial into a self-contained HTML replay with the solver's verdict on every move.

    python tools/replay.py jobs/evaluate/agent-<model>/<trial> results/replay.html

Open the file in a browser: pick a puzzle, step through the moves, and see for each one
whether it kept the forced win, what it should have been, and how Red answered.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from thinice.board import FILES, H, W, key, move_name, parse_move, squares  # noqa: E402
from thinice.session import LOSS0, load_pack  # noqa: E402

POOL = {p.index: p for p in load_pack(ROOT / "task" / "environment" / "game-server" / "packs" / "scored.jsonl")}


def frames(row: dict) -> list:
    puzzle = POOL[row["index"]]
    blue, red = puzzle.blue, puzzle.red
    out = [{"blue": squares(blue), "red": squares(red), "text": f"Start. Blue to move and win in {row['win_in']}.", "kind": "start"}]
    for played, reply in row["history"]:
        entries = puzzle.nodes[key(blue, red)]
        f, t = parse_move(played)
        cv = next(e[2] for e in entries if e[0] == f and e[1] == t)
        wins = [move_name(e) for e in entries if e[2] >= LOSS0]
        blue ^= (1 << f) | (1 << t)
        if cv == LOSS0:
            text, kind = f"Blue {played}: three in a row. Solved.", "good"
        elif cv > LOSS0:
            text, kind = f"Blue {played}: keeps the win ({len(wins)} of {len(entries)} legal moves did).", "good"
        elif cv == 0:
            text, kind = f"Blue {played}: throws the win away, the game is now a draw. Winning: {' '.join(wins)} ({len(wins)} of {len(entries)}).", "bad"
        else:
            text, kind = f"Blue {played}: loses, Red wins in {(cv + 1) // 2}. Winning: {' '.join(wins)} ({len(wins)} of {len(entries)}).", "bad"
        out.append({"blue": squares(blue), "red": squares(red), "text": text, "kind": kind, "move": [f, t]})
        if reply:
            f, t = parse_move(reply)
            red ^= (1 << f) | (1 << t)
            out.append({"blue": squares(blue), "red": squares(red), "text": f"Red {reply}: the longest defence.", "kind": "reply", "move": [f, t]})
    if row["status"] == "failed" and row["reason"] == "out of moves":
        out.append({"blue": squares(blue), "red": squares(red), "text": "Out of moves. Still winning, but too slow.", "kind": "bad"})
    return out


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thin Ice replay</title>
<style>
:root { --bg:#f6f7f9; --ink:#15181d; --dim:#6b7280; --line:#d8dce3; --cell:#ffffff; --blue:#2563eb; --red:#dc2626; --good:#15803d; --bad:#b91c1c; --hi:#fde68a; }
@media (prefers-color-scheme: dark) { :root { --bg:#0f1115; --ink:#e7e9ee; --dim:#9aa3b2; --line:#2a2f3a; --cell:#181c24; --hi:#6b5a12; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.45 system-ui, sans-serif; }
main { max-width: 880px; margin: 0 auto; padding: 20px 16px 40px; }
h1 { font-size: 20px; margin: 0 0 2px; } .sub { color: var(--dim); margin-bottom: 14px; }
.tabs { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px; }
.tab { border:1px solid var(--line); background:var(--cell); color:var(--ink); border-radius:6px; padding:5px 8px; cursor:pointer; font:inherit; font-size:13px; font-variant-numeric: tabular-nums; }
.tab.solved { border-color: var(--good); } .tab.failed { border-color: var(--bad); } .tab.open { opacity:.55; }
.tab.on { outline:2px solid var(--ink); }
.wrap { display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start; }
.board { display:grid; grid-template-columns: 20px repeat(__W__, 52px); grid-auto-rows:52px; gap:4px; }
.lab { color:var(--dim); font-size:12px; display:flex; align-items:center; justify-content:center; }
.cell { background:var(--cell); border:1px solid var(--line); border-radius:8px; display:flex; align-items:center; justify-content:center; }
.cell.hi { background:var(--hi); }
.stone { width:36px; height:36px; border-radius:50%; } .stone.b { background:var(--blue); } .stone.r { background:var(--red); }
.side { flex:1; min-width:260px; }
.note { min-height:66px; padding:10px 12px; border-radius:8px; border:1px solid var(--line); background:var(--cell); }
.note.good { border-color:var(--good); } .note.bad { border-color:var(--bad); }
.ctl { display:flex; gap:8px; margin-top:12px; align-items:center; }
button.nav { font:inherit; padding:6px 14px; border-radius:6px; border:1px solid var(--line); background:var(--cell); color:var(--ink); cursor:pointer; }
.meta { color:var(--dim); margin-top:12px; font-size:13px; }
</style></head><body><main>
<h1>Thin Ice replay</h1>
<div class="sub" id="sub"></div>
<div class="tabs" id="tabs"></div>
<div class="wrap"><div class="board" id="board"></div>
<div class="side"><div class="note" id="note"></div>
<div class="ctl"><button class="nav" id="prev">&larr; back</button><button class="nav" id="next">next &rarr;</button><span id="pos" class="meta"></span></div>
<div class="meta" id="meta"></div></div></div>
</main><script>
const DATA = __DATA__;
let p = 0, f = 0;
const el = id => document.getElementById(id);
function draw() {
  const pz = DATA.puzzles[p], fr = pz.frames[f];
  el('sub').textContent = DATA.title + ': ' + DATA.solved + ' of ' + DATA.total + ' solved, reward ' + DATA.reward.toFixed(3);
  el('tabs').innerHTML = '';
  DATA.puzzles.forEach((q, i) => { const b = document.createElement('button'); b.className = 'tab ' + q.status + (i === p ? ' on' : ''); b.textContent = q.id + ' \\u00b7 win in ' + q.win_in; b.onclick = () => { p = i; f = 0; draw(); }; el('tabs').appendChild(b); });
  const bd = el('board'); bd.innerHTML = '';
  for (let y = DATA.h - 1; y >= 0; y--) { const l = document.createElement('div'); l.className = 'lab'; l.textContent = y + 1; bd.appendChild(l);
    for (let x = 0; x < DATA.w; x++) { const s = y * DATA.w + x, c = document.createElement('div'); c.className = 'cell' + (fr.move && fr.move.includes(s) ? ' hi' : '');
      if (fr.blue.includes(s) || fr.red.includes(s)) { const st = document.createElement('div'); st.className = 'stone ' + (fr.blue.includes(s) ? 'b' : 'r'); c.appendChild(st); } bd.appendChild(c); } }
  bd.appendChild(document.createElement('div'));
  DATA.files.split('').forEach(ch => { const l = document.createElement('div'); l.className = 'lab'; l.textContent = ch; bd.appendChild(l); });
  el('note').className = 'note ' + fr.kind; el('note').textContent = fr.text;
  el('pos').textContent = 'step ' + f + ' of ' + (pz.frames.length - 1);
  el('meta').textContent = pz.id + ': ' + pz.status + (pz.reason ? ' (' + pz.reason + ')' : '') + '. Blue is the agent, Red the perfect defender.';
}
el('prev').onclick = () => { if (f > 0) { f--; draw(); } };
el('next').onclick = () => { if (f < DATA.puzzles[p].frames.length - 1) { f++; draw(); } };
document.addEventListener('keydown', e => { if (e.key === 'ArrowLeft') el('prev').click(); if (e.key === 'ArrowRight') el('next').click(); });
draw();
</script></body></html>
"""


def main() -> None:
    trial = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "results" / "replay.html"
    d = json.loads((trial / "verifier" / "details.json").read_text())
    data = {
        "title": sys.argv[3] if len(sys.argv) > 3 else trial.parent.name,
        "w": W,
        "h": H,
        "files": FILES,
        "reward": d["reward"],
        "solved": d["solved"],
        "total": d["total"],
        "puzzles": [{"id": r["id"], "win_in": r["win_in"], "status": r["status"], "reason": r["reason"], "frames": frames(r)} for r in d["puzzles"]],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PAGE.replace("__W__", str(W)).replace("__DATA__", json.dumps(data)), encoding="utf-8", newline="\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
