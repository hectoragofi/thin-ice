"""One command to reproduce every reported number through Harbor.

    python scripts/evaluate.py --model openai/<model>          # everything
    python scripts/evaluate.py                                 # references and baselines only (no API key)

Runs, in order: the reference (perfect play), the tools-only reference, a do-nothing
baseline, a stop-early baseline, and N runs of the OpenCode agent with the given model.
Prints one table and writes results/summary.md. Needs `harbor` on the PATH and Docker (or --env modal).
API keys are read from the environment or from a .env file next to this repository's README.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASK = ROOT / "task"
ENV: list = []
KEY_NAMES = ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENCODE_API_KEY", "DEEPSEEK_API_KEY")


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def harbor(name: str, jobs: Path, *args: str) -> Path:
    job = jobs / name
    if job.exists():
        print(f"== {name}: reusing {job}")
        return job
    cmd = ["harbor", "run", "-p", str(TASK), "--job-name", name, "-o", str(jobs), "-y", *ENV, *args]
    shown = " ".join(a if "API_KEY=" not in a else a.split("=")[0] + "=***" for a in cmd)
    print(f"== {name}: {shown}", flush=True)
    t0 = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, check=False)
    print(f"   done in {time.time() - t0:.0f}s", flush=True)
    return job


def trials(job: Path) -> list:
    out = []
    for d in sorted(p for p in job.iterdir() if p.is_dir()):
        reward, detail = None, {}
        if (d / "verifier" / "reward.txt").exists():
            reward = float((d / "verifier" / "reward.txt").read_text().strip() or 0)
        if (d / "verifier" / "details.json").exists():
            detail = json.loads((d / "verifier" / "details.json").read_text())
        out.append((reward, detail))
    return out


def tier_line(detail: dict) -> str:
    tiers = detail.get("by_win_in") or {}
    return " ".join(f"{t['solved']}" for _, t in sorted(tiers.items(), key=lambda kv: int(kv[0])))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", help="provider/model for the OpenCode agent, e.g. openai/gpt-...; omit to skip agent runs")
    p.add_argument("--agent", default="opencode")
    p.add_argument("--runs", type=int, default=3, help="number of agent runs")
    p.add_argument("--jobs", default=str(ROOT / "jobs" / "evaluate"), help="where Harbor writes its job folders")
    p.add_argument("--env", default="", help="Harbor environment, e.g. modal (default: local Docker)")
    p.add_argument("--fresh", action="store_true", help="do not reuse job folders from an earlier call")
    args = p.parse_args()
    load_env()
    if args.env:
        ENV[:] = ["-e", args.env]
    jobs = Path(args.jobs)
    if args.fresh and jobs.exists():
        jobs = jobs.with_name(jobs.name + time.strftime("-%H%M%S"))
    jobs.mkdir(parents=True, exist_ok=True)

    rows = [
        ("reference: perfect play (solver)", harbor("reference", jobs, "-a", "oracle")),
        ("reference: tools only (agent's own tools)", harbor("reference-tools", jobs, "-a", "oracle", "--ae", "SOLUTION=tools")),
        ("baseline: do nothing", harbor("do-nothing", jobs, "-a", "nop")),
        ("baseline: stop early (4 puzzles, then quit)", harbor("stop-early", jobs, "-a", "oracle", "--ae", "STOP_AFTER=4")),
    ]
    if args.model:
        keys = [a for k in KEY_NAMES if os.environ.get(k) for a in ("--ae", f"{k}={os.environ[k]}")]
        tag = args.model.replace("/", "_").replace(":", "_")
        rows.append((f"agent: {args.agent} + {args.model}", harbor(f"agent-{tag}", jobs, "-a", args.agent, "-m", args.model, "-k", str(args.runs), "-n", str(args.runs), *keys)))

    lines = ["| run | reward | solved per tier (win in 1..6 moves, 2 puzzles each) |", "|---|---|---|"]
    for label, job in rows:
        for reward, detail in trials(job) or [(None, {})]:
            shown = "n/a (no result)" if reward is None else f"{reward:.3f}"
            lines.append(f"| {label} | {shown} | {tier_line(detail)} |")
    table = "\n".join(lines)
    print("\n" + table)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "summary.md").write_text(table + "\n", encoding="utf-8", newline="\n")
    print(f"\nwritten to results/summary.md; job folders in {jobs}")


if __name__ == "__main__":
    sys.exit(main())
