"""Reference players for Thin Ice. They talk to the game server exactly like an agent does.

book    Perfect play. Each move is looked up in book.json, which the exhaustive solver wrote:
        it lists the fastest winning move for every position Blue can reach while winning.
search  Rules-only look-ahead (thinice/search.py). No precomputed answers: it knows the rules
        and nothing else, and skips a puzzle when it cannot prove a win in time.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
URL = os.environ.get("THINICE_URL", "http://game:8000").rstrip("/")

# Ask the game how big the board is before loading the rules module.
with urllib.request.urlopen(URL + "/api/rules", timeout=60) as _resp:
    _info = json.loads(_resp.read())
os.environ["THINICE_W"], os.environ["THINICE_H"] = str(_info["width"]), str(_info["height"])

sys.path.insert(0, str(HERE))
from thinice.board import key, mask_of, move_name, parse_sq  # noqa: E402
from thinice.search import find_win  # noqa: E402
MODE = os.environ.get("SOLUTION", "book")
SEARCH_SECONDS = float(os.environ.get("SEARCH_SECONDS", "60"))
# STOP_AFTER=4 plays only the first four puzzles and then quits: the stop-early baseline.
STOP_AFTER = int(os.environ.get("STOP_AFTER", "0"))


def call(method: str, path: str, body=None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def main() -> None:
    book = json.loads((HERE / "book.json").read_text()) if MODE == "book" else None
    for n, row in enumerate(call("GET", "/api/puzzles")["puzzles"]):
        if STOP_AFTER and n >= STOP_AFTER:
            print(f"stopping early after {STOP_AFTER} puzzles")
            break
        pid = row["id"]
        budget = time.monotonic() + SEARCH_SECONDS
        while True:
            p = call("GET", f"/api/puzzle/{pid}")
            if p["status"] != "open":
                break
            blue = mask_of(parse_sq(s) for s in p["blue"])
            red = mask_of(parse_sq(s) for s in p["red"])
            if book is not None:
                move = book[key(blue, red)]
            else:
                left = p["moves_allowed"] - p["moves_used"]
                found, _, _ = find_win(blue, red, left, max(1.0, budget - time.monotonic()))
                if found is None:
                    print(f"{pid}: no forced win proven in time, leaving it")
                    break
                move = move_name(found)
            call("POST", "/api/move", {"id": pid, "move": move})
        print(f"{pid}: {call('GET', f'/api/puzzle/{pid}')['status']}")
    done = call("GET", "/api/puzzles")
    print(f"solved {done['solved']} of {done['total']} ({MODE})")


if __name__ == "__main__":
    main()
