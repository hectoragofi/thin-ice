"""One table of how agent runs lose, graded by the solver, across one or more Harbor jobs.

    python tools/mistakes.py jobs/final/cap-*-carbon-x3 jobs/final/cap-*-argon-x3 ...

Per job (one model): mean reward, the deepest tier won, every losing move judged by the
solver (see tools/analyze.py for the kinds), puzzles never reached, and how each session
ended (the agent stopped by itself, the clock ran out, or the model's turn hit its output
limit).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import diagnose  # noqa: E402


def ending(trial: Path) -> str:
    res = trial / "result.json"
    exc = (json.loads(res.read_text()).get("exception_info") or {}) if res.exists() else {}
    if exc.get("exception_type") == "AgentTimeoutError":
        return "clock ran out"
    log = trial / "agent" / "opencode.txt"
    last = None
    if log.exists():
        for line in log.read_text(errors="ignore").splitlines():
            if line.startswith("{"):
                try:
                    x = json.loads(line)
                except ValueError:
                    continue
                if x.get("type") == "error":
                    return "API error: " + str((x.get("error") or {}).get("data", {}).get("message", ""))[:60]
                if x.get("type") == "step_finish":
                    last = (x.get("part") or {}).get("reason")
    if last == "length":
        return "output limit hit mid-turn"
    if exc:
        return exc.get("exception_type", "error")
    return "agent stopped by itself"


def job_row(job: Path) -> tuple[str, list[str]]:
    rewards, deepest, kinds, ends = [], [], Counter(), Counter()
    for t in sorted(p for p in job.iterdir() if p.is_dir()):
        f = t / "verifier" / "details.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        rows = d.get("puzzles") or []
        rewards.append(d.get("reward", 0.0))
        won = [r["win_in"] for r in rows if r["status"] == "solved"]
        deepest.append(max(won) if won else 0)
        for r in rows:
            if r["status"] == "open":
                kinds["never reached" if not r["history"] else "left unfinished"] += 1
            elif r["status"] == "failed":
                g = diagnose(r)
                kinds[g["kind"] if g else "lost"] += 1
        ends[ending(t)] += 1
    name = job.name
    n = len(rewards)
    mean = sum(rewards) / n if n else 0.0
    cells = [
        name,
        f"{mean:.3f} ({', '.join(f'{r:.3f}' for r in rewards)})",
        ", ".join(str(x) for x in deepest),
        ", ".join(f"{k} {c}" for k, c in kinds.most_common()),
        ", ".join(f"{k} {c}" for k, c in ends.most_common()),
    ]
    return name, cells


def main() -> None:
    jobs = [Path(a) for a in sys.argv[1:]]
    out = [
        "| job | reward: mean (runs) | deepest win per run (win in N) | lost puzzles, by solver verdict (all runs) | how sessions ended |",
        "|---|---|---|---|---|",
    ]
    for j in jobs:
        out.append("| " + " | ".join(job_row(j)[1]) + " |")
    print("\n".join(out))


if __name__ == "__main__":
    main()
