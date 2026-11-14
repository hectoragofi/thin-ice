"""Shows what a running trial is doing right now: the score sheet and the agent's recent actions.

    python tools/live.py            # while `harbor run ... -a opencode` is in progress

Reads the game server's score sheet and the agent's log straight out of the running containers.
"""
import json
import subprocess
import sys
from collections import Counter


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def main() -> None:
    names = sh("docker", "ps", "--format", "{{.Names}}").split()
    game = next((n for n in names if "game" in n), None)
    main_c = next((n for n in names if "main" in n), None)
    if not game or not main_c:
        sys.exit("no running trial found")
    card = json.loads(sh("docker", "exec", game, "cat", "/receipt/receipt.json"))["scorecard"]
    print(f"score {card['score']:.3f}  solved {card['solved']}/{card['total']}  practice puzzles started {card['practice_started']}")
    print(" ".join(f"{p['id']}:{p['status'][0]}{p['moves_used']}" for p in card["puzzles"]))
    tools, last, tokens = Counter(), [], 0
    for line in sh("docker", "exec", main_c, "cat", "/logs/agent/opencode.txt").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        part = ev.get("part", {})
        if ev.get("type") == "tool_use":
            tools[part.get("tool", "?")] += 1
            inp = part.get("state", {}).get("input", {})
            last.append(f"{part.get('tool')}: {json.dumps(inp)[:220]}")
        elif ev.get("type") == "step_finish":
            tokens += part.get("tokens", {}).get("total", 0)
    print("tool calls:", ", ".join(f"{k} x{v}" for k, v in tools.most_common()) or "none yet")
    print(f"tokens so far: {tokens:,}")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    for item in last[-n:]:
        print("  ", item)
    print("files in /app:", sh("docker", "exec", main_c, "ls", "/app").split())


if __name__ == "__main__":
    main()
