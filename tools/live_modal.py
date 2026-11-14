"""What every running thin-ice trial on Modal is doing right now.

    uvx --with modal python tools/live_modal.py           # all live thin-ice trials
    uvx --with modal python tools/live_modal.py --log 3   # also the last 3 things the model said

Reads the game server's signed score sheet and the agent's OpenCode log straight out of the
running containers (Harbor runs them with Docker inside each Modal sandbox). Read-only.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter

import modal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def job_of(session: str) -> str:
    hits = glob.glob(os.path.join(ROOT, "jobs", "**", session), recursive=True)
    return os.path.basename(os.path.dirname(hits[0])) if hits else "?"


def run(sb, *cmd: str) -> str:
    p = sb.exec(*cmd)
    out = p.stdout.read()
    p.wait()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=int, default=0, help="show the last N text/reasoning snippets")
    args = ap.parse_args()
    app = modal.App.lookup("__harbor__")
    for sb in modal.Sandbox.list(app_id=app.app_id):
        tags = sb.get_tags()
        if tags.get("harbor.environment_name") != "thin-ice":
            continue
        session = tags.get("harbor.session_id", "").replace("__env", "")
        print(f"=== {job_of(session)} / {session}")
        names = run(sb, "docker", "ps", "--format", "{{.Names}}").split()
        game = next((n for n in names if "game" in n), None)
        main_c = next((n for n in names if "main" in n), None)
        if not game or not main_c:
            print("  containers not up yet:", names)
            continue
        try:
            card = json.loads(run(sb, "docker", "exec", game, "cat", "/receipt/receipt.json"))["scorecard"]
            print(f"  score {card['score']:.3f}  solved {card['solved']}/{card['total']}  practice started {card['practice_started']}")
            print("  " + " ".join(f"{p['id']}:{p['status'][0]}{p['moves_used']}" for p in card["puzzles"] if p["status"] != "open" or p["moves_used"]) or "  no scored move yet")
        except (ValueError, KeyError):
            print("  no score sheet yet")
        tools, turns, maxthink, last_think, said, t0, t1 = Counter(), 0, 0, 0, [], None, None
        for line in run(sb, "docker", "exec", main_c, "cat", "/logs/agent/opencode.txt").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            ts = ev.get("timestamp")
            if ts:
                t0 = t0 or ts
                t1 = ts
            part = ev.get("part") or {}
            if ev.get("type") == "tool_use":
                tools[str(part.get("tool", "")).replace("thin-ice_", "")] += 1
            elif ev.get("type") == "step_finish":
                turns += 1
                last_think = (part.get("tokens") or {}).get("reasoning", 0)
                maxthink = max(maxthink, last_think)
            elif ev.get("type") in ("text", "reasoning") and part.get("text"):
                said.append(part["text"].strip().replace("\n", " "))
            elif ev.get("type") == "error":
                print("  API ERROR:", str(ev.get("error"))[:200])
        mins = (t1 - t0) / 60000 if t0 and t1 else 0
        print(f"  {mins:.0f} min, {turns} turns, longest thought {maxthink} tokens, last {last_think}")
        print("  tools: " + ", ".join(f"{k} {v}" for k, v in tools.most_common()))
        for s in said[-args.log:] if args.log else []:
            print("  > " + s[-300:])


if __name__ == "__main__":
    main()
