"""Tools-only reference player for Thin Ice.

It plays through exactly the interface the agent has: the puzzle view, the two rules-only
look-ahead tools (explore_position / explore_lines, here their HTTP twin POST /api/explore) and
play_move. It imports no game code, reads no solver data and knows no rules of its own: every
legal move and every three in a row it uses comes back from a tool call.

The method is one a careful player can follow by hand, one small tool call at a time:

  1. If one of my moves makes three in a row, play it.
  2. Otherwise look, in one call, at the position after each of my moves: can Red then make
     three in a row (discard the move), and how many three-in-a-row moves do I threaten?
  3. Try my moves, most threats first. For a move, look at every Red reply in one call. A reply
     after which I make three in a row at once is no defence. The others are real defences;
     each must again be beaten, with one move fewer (go to 1 from that position).
  4. Moves that threaten nothing come last, and only when few moves are left, because then
     every Red reply is a real defence.

Everything found is remembered (like notes), so once the first move is proven the rest of the
puzzle is played from memory, with no further look-ahead.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

URL = os.environ.get("THINICE_URL", "http://game:8000").rstrip("/")
QUIET_DEPTH = int(os.environ.get("QUIET_DEPTH", "2"))  # allow non-threat moves when this few Blue moves remain
MAX_LINES = 40


class OutOfBudget(Exception):
    pass


class Tools:
    """The agent's tools over HTTP, with a call counter."""

    def __init__(self, url: str = URL):
        self.url = url
        self.calls = 0
        self.lines = 0

    def _call(self, method: str, path: str, body=None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        self.calls += 1
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())

    def puzzles(self) -> list:
        return self._call("GET", "/api/puzzles")["puzzles"]

    def show(self, pid: str) -> dict:
        return self._call("GET", f"/api/puzzle/{pid}")

    def move(self, pid: str, move: str) -> dict:
        return self._call("POST", "/api/move", {"id": pid, "move": move})

    def explore(self, pid: str, lines: list) -> list:
        out = []
        for i in range(0, len(lines), MAX_LINES):
            chunk = lines[i : i + MAX_LINES]
            self.lines += len(chunk)
            out += self._call("POST", "/api/explore", {"id": pid, "lines": chunk})["results"]
        return out


class Prover:
    """Proves a forced win for Blue from a puzzle's current position, by tool calls only."""

    def __init__(self, tools: Tools, pid: str, budget_calls: int, deadline: float):
        self.t = tools
        self.pid = pid
        self.budget = tools.calls + budget_calls
        self.deadline = deadline
        self.rows: dict = {}  # line (tuple of moves) -> explore row, Blue to move after it
        self.proof: dict = {}  # (line, n) -> winning Blue move or None
        self.root: tuple = ()  # moves already played for real; lines are kept from the start

    def look(self, seqs: list) -> list:
        """Explores lines given from the puzzle's start, as lines from its current position."""
        k = len(self.root)
        return self.t.explore(self.pid, [" ".join(s[k:]) for s in seqs])

    def _spend(self) -> None:
        if self.t.calls >= self.budget or time.monotonic() > self.deadline:
            raise OutOfBudget

    def row(self, line: tuple) -> dict:
        if line not in self.rows:
            self._spend()
            self.rows[line] = self.look([line])[0]
        return self.rows[line]

    def attack(self, line: tuple, n: int):
        """Blue to move after `line`: a Blue move that wins within n Blue moves, or None."""
        key = (line, n)
        if key in self.proof:
            return self.proof[key]
        here = self.row(line)
        if here["three_in_a_row"]["blue"]:
            return here["three_in_a_row"]["blue"][0]
        if n <= 1:
            return None
        for k in range(2, n):  # a shorter win found earlier also wins here
            if self.proof.get((line, k)):
                return self.proof[(line, k)]
        self._spend()
        after = [line + (m,) for m in here["moves"]]
        view = self.look(after)  # Red to move after each of my moves
        cands = []
        for m, rv in zip(here["moves"], view):
            if rv.get("game_over"):  # Red cannot move: that move wins outright
                self.proof[key] = m
                return m
            if rv["three_in_a_row"]["red"]:
                continue  # Red would make three in a row at once
            # most threats first; among equals, the move that leaves Red fewest replies
            cands.append((-len(rv["three_in_a_row"]["blue"]), len(rv["moves"]), m, rv["moves"]))
        cands.sort(key=lambda c: c[:2])
        best = None
        for threats, _, m, replies in cands:
            if threats == 0 and n > QUIET_DEPTH:
                break  # quiet moves only near the end
            if self.defend(line + (m,), replies, n - 1):
                best = m
                break
        self.proof[key] = best
        return best

    def defend(self, line: tuple, replies: list, n: int) -> bool:
        """Red to move after `line`. True if every Red reply still loses within n Blue moves."""
        self._spend()
        seqs = [line + (r,) for r in replies]
        rows = self.look(seqs)
        real = []
        for s, row in zip(seqs, rows):
            self.rows[s] = row
            if row.get("game_over"):
                return False  # after a Red move: Red made three in a row, or I cannot move
            if row["three_in_a_row"]["blue"]:
                continue  # no defence: I win at once
            real.append(s)
        if real and n <= 1:
            return False
        # Narrowest defences first: a refutation, if there is one, tends to be among them.
        real.sort(key=lambda s: len(self.rows[s]["moves"]))
        return all(self.attack(s, n) for s in real)


def play_puzzle(tools: Tools, pid: str, budget_calls: int, seconds: float) -> dict:
    start_calls, start = tools.calls, time.monotonic()
    p = tools.show(pid)
    n = p["win_in"] - p["moves_used"]
    prover = Prover(tools, pid, budget_calls, start + seconds)
    line: tuple = ()
    result = {"id": pid, "win_in": p["win_in"], "status": p["status"]}
    try:
        while p["status"] == "open":
            mv = prover.attack(line, n)
            if mv is None:
                result["note"] = "no forced win found"
                break
            out = tools.move(pid, mv)
            p = out["puzzle"]
            if out["reply"]:
                line = line + (mv, out["reply"])
                prover.root = line
                n -= 1
    except OutOfBudget:
        result["note"] = "budget used up"
    result.update(status=tools.show(pid)["status"], calls=tools.calls - start_calls, seconds=round(time.monotonic() - start, 2), lines=tools.lines)
    return result


def main() -> None:
    budget = int(os.environ.get("CALL_BUDGET", "150"))
    seconds = float(os.environ.get("PUZZLE_SECONDS", "120"))
    tools = Tools()
    for row in tools.puzzles():
        lines0 = tools.lines
        r = play_puzzle(tools, row["id"], budget, seconds)
        r["lines"] = tools.lines - lines0
        print(json.dumps(r), flush=True)
    done = tools._call("GET", "/api/puzzles")
    print(f"solved {sum(p['status'] == 'solved' for p in done['puzzles'])} of {len(done['puzzles'])} (tools-only), {tools.calls} tool calls")


if __name__ == "__main__":
    main()
