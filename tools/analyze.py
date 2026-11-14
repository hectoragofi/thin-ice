"""Explains an agent run move by move, using the solver's verdicts.

    python tools/analyze.py jobs/evaluate/agent-<model>      # one report per trial in the job

For every puzzle the agent lost it shows the position, the move played, what the solver says
about that move, and the move that would have kept the win. It then sums the mistakes up by
kind and reports the planning horizon: how deep the agent's wins go before they stop.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from thinice.board import key, move_name, parse_move, render  # noqa: E402
from thinice.session import LOSS0, load_pack  # noqa: E402

POOL = {p.index: p for p in load_pack(ROOT / "task" / "environment" / "game-server" / "packs" / "scored.jsonl")}


def diagnose(row: dict) -> dict | None:
    """Replays a lost puzzle and judges the losing move. Returns None for puzzles not lost."""
    if row["status"] != "failed" or not row["history"] or row.get("reason") in ("out of time", "skipped"):
        return None  # no losing move to judge: never lost, clock ran out, or given up
    puzzle = POOL[row["index"]]
    blue, red = puzzle.blue, puzzle.red
    for played, reply in row["history"][:-1]:
        f, t = parse_move(played)
        blue ^= (1 << f) | (1 << t)
        f, t = parse_move(reply)
        red ^= (1 << f) | (1 << t)
    played = row["history"][-1][0]
    entries = puzzle.nodes[key(blue, red)]
    f, t = parse_move(played)
    cv = next(e[2] for e in entries if e[0] == f and e[1] == t)
    wins = sorted((e[2], move_name(e)) for e in entries if e[2] >= LOSS0)
    if cv > LOSS0:
        kind, verdict = "too slow", "still winning, but the allowed moves ran out"
    elif cv == 0:
        kind, verdict = "threw the win away", "draw with best play"
    elif cv == 1:
        kind, verdict = "overlooked Red's immediate win", "Red completes three in a row next move"
    else:
        kind, verdict = "walked into a forced loss", f"Red wins in {(cv + 1) // 2} moves"
    return {
        "board": render(blue, red),
        "played": played,
        "kind": kind,
        "verdict": verdict,
        "winning": [name for _, name in wins],
        "legal": len(entries),
        "good_moves_before": len(row["history"]) - 1,
    }


def tool_use(trial: Path) -> str:
    """Rough count of what the agent did, from its own log: game calls, shell commands, files written."""
    log = trial / "agent" / "opencode.txt"
    if not log.exists():
        return ""
    counts, tokens, wrote = Counter(), 0, set()
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        part = ev.get("part", {})
        if ev.get("type") == "tool_use":
            counts[part.get("tool", "?")] += 1
            inp = part.get("state", {}).get("input", {})
            for path in re.findall(r"[\w./-]+\.(?:py|js|mjs|c|cpp|rs|go)\b", json.dumps(inp)):
                wrote.add(path.rsplit("/", 1)[-1])
        elif ev.get("type") == "step_finish":
            tokens += part.get("tokens", {}).get("total", 0)
    if not counts:
        return ""
    out = ", ".join(f"{n} x{c}" for n, c in counts.most_common(8)) + f"; {tokens:,} tokens"
    if wrote:
        out += "; programs it touched: " + " ".join(sorted(wrote)[:12])
    return out


def report(trial: Path) -> str:
    detail_file = trial / "verifier" / "details.json"
    if not detail_file.exists():
        return f"## {trial.name}\nno verifier output\n"
    d = json.loads(detail_file.read_text())
    if "puzzles" not in d:
        return f"## {trial.name}\nreward 0: {d.get('error', 'no score sheet')}\n"
    rows = d["puzzles"]
    out = [f"## {trial.name}: reward {d['reward']:.3f} ({d['solved']} of {d['total']} puzzles)"]
    tiers = {}
    for r in rows:
        tiers.setdefault(r["win_in"], []).append(r["status"])
    out.append("")
    out.append("| win in | " + " | ".join(str(n) for n in sorted(tiers)) + " |")
    out.append("|---|" + "---|" * len(tiers))
    out.append("| solved | " + " | ".join(f"{s.count('solved')}/{len(s)}" for _, s in sorted(tiers.items())) + " |")
    horizon = 0
    for n, s in sorted(tiers.items()):
        if s.count("solved") * 2 < len(s):
            break
        horizon = n
    out.append("")
    out.append(f"**Planning horizon: {horizon} moves** (deepest tier, counted from the easiest, where it still wins at least half).")
    used = tool_use(trial)
    if used:
        out.append(f"Tool calls: {used}.")
    out.append(f"Practice puzzles started: {d.get('practice_started', 0)}.")
    kinds = Counter()
    blocks = []
    for r in rows:
        if r["status"] == "open":
            kinds["never attempted" if not r["history"] else "left unfinished"] += 1
            continue
        g = diagnose(r)
        if g is None:
            continue
        kinds[g["kind"]] += 1
        blocks.append(
            f"### {r['id']} (win in {r['win_in']}): {g['kind']}\n"
            f"```\n{g['board']}\n```\n"
            f"After {g['good_moves_before']} correct move(s) it played **{g['played']}**: {g['verdict']}. "
            f"{len(g['winning'])} of {g['legal']} legal moves kept the win: {' '.join(g['winning'])}.\n"
        )
    if kinds:
        out.append("")
        out.append("Mistakes by kind: " + ", ".join(f"{k} x{c}" for k, c in kinds.most_common()) + ".")
    out.append("")
    out.extend(blocks)
    return "\n".join(out) + "\n"


def main() -> None:
    job = Path(sys.argv[1])
    trials = [job] if (job / "verifier").exists() else sorted(p for p in job.iterdir() if p.is_dir())
    text = "\n".join(report(t) for t in trials)
    print(text)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
