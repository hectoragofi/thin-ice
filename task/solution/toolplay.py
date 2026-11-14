"""Tools-only reference player for Thin Ice.

It plays through exactly the interface the agent has: the puzzle view, the two rules-only
look-ahead tools (explore_position / explore_lines, here their HTTP twin POST /api/explore) and
play_move. It imports no game code, reads no solver data and knows no rules of its own: every
legal move and every three in a row it uses comes back from a tool call. Every explored
position is paid for from the run's look-ahead budget, exactly as the agent pays.

The method is one a careful player can follow by hand, one small tool call at a time:

  1. If one of my moves makes three in a row, play it.
  2. Otherwise look, in one call, at the position after each of my moves: can Red then make
     three in a row (discard the move), and how many three-in-a-row moves do I threaten?
  3. Try my moves, most threats first. For a move, look at every Red reply in one call. A reply
     after which I make three in a row at once is no defence. The others are real defences;
     each must again be beaten, with one move fewer (go to 1 from that position).
  4. Moves that threaten nothing come last, and only when few moves are left, because then
     every Red reply is a real defence.

HORIZON sets how far each decision is checked against every defence. 99 means a full proof
before the first move (the exhaustive habit: certain, but it pays for every branch Red could
choose). A small horizon checks a few moves deep, plays, sees Red's actual reply and looks
again from there, so it only pays for the branch the game really takes. PUZZLE_CAP gives each
puzzle an allowance of positions by depth; a puzzle that would need more is left open, not
lost. Everything explored is remembered and never paid for twice.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = os.environ.get("THINICE_URL", "http://game:8000").rstrip("/")
# The reference's settings are published with the task (manifest.json, "tools_reference"):
# search settings only, no puzzle data. Environment variables override them.
try:
    _REF = json.loads((Path(__file__).resolve().parent / "manifest.json").read_text()).get("tools_reference", {})
except (OSError, ValueError):
    _REF = {}
QUIET_DEPTH = int(os.environ.get("QUIET_DEPTH") or _REF.get("quiet_depth", 2))  # non-threat moves only this near the end
HORIZON = int(os.environ.get("HORIZON") or _REF.get("horizon", 99))  # 99 = full proof first (exhaustive)
PUZZLE_CAP = os.environ.get("PUZZLE_CAP", ",".join(f"{k}:{v}" for k, v in _REF.get("cap", {}).items()))
MODE = os.environ.get("MODE") or _REF.get("mode", "elim")  # elim: narrow candidates by deepening checks
MIN_CHECK = int(os.environ.get("MIN_CHECK") or _REF.get("min_check", 2))
MAX_LINES = 40


class OutOfBudget(Exception):
    """This puzzle's allowance (or the time) is used up; the puzzle is left open."""


class BudgetRefused(OutOfBudget):
    """The game refused a look-ahead request: the run's budget is used up."""


class Tools:
    """The agent's tools over HTTP, with counters for calls and explored positions."""

    def __init__(self, url: str = URL):
        self.url = url
        self.calls = 0
        self.lines = 0
        self.budget_left = None

    def _call(self, method: str, path: str, body=None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            err = json.loads(exc.read() or b"{}").get("error", "")
            if "budget" in err:
                raise BudgetRefused(err) from None
            raise

    def puzzles(self) -> dict:
        return self._call("GET", "/api/puzzles")

    def show(self, pid: str) -> dict:
        return self._call("GET", f"/api/puzzle/{pid}")

    def move(self, pid: str, move: str) -> dict:
        return self._call("POST", "/api/move", {"id": pid, "move": move})

    def explore(self, pid: str, lines: list) -> list:
        out = []
        for i in range(0, len(lines), MAX_LINES):
            chunk = lines[i : i + MAX_LINES]
            if self.budget_left is not None and len(chunk) > self.budget_left:
                raise BudgetRefused("not enough look-ahead budget left")
            reply = self._call("POST", "/api/explore", {"id": pid, "lines": chunk})
            self.lines += len(chunk)
            self.budget_left = reply.get("budget_left")
            out += reply["results"]
        return out


class Prover:
    """Finds a Blue move that keeps the forced win, by tool calls only."""

    def __init__(self, tools: Tools, pid: str, deadline: float, cap_lines=None, horizon: int = HORIZON):
        self.t = tools
        self.pid = pid
        self.deadline = deadline
        self.cap = None if cap_lines is None else tools.lines + cap_lines
        self.horizon = horizon
        self.rows: dict = {}  # line (tuple of moves from the start) -> explore row
        self.proof: dict = {}  # (line, n, k) -> Blue move or None
        self.root: tuple = ()  # moves already played for real

    def look(self, seqs: list) -> None:
        """Explores the lines not seen yet (given from the start, sent from the current position)."""
        fresh = [s for s in dict.fromkeys(seqs) if s not in self.rows]
        if not fresh:
            return
        if time.monotonic() > self.deadline or (self.cap is not None and self.t.lines + len(fresh) > self.cap):
            raise OutOfBudget
        k = len(self.root)
        for s, r in zip(fresh, self.t.explore(self.pid, [" ".join(s[k:]) for s in fresh])):
            self.rows[s] = r

    def attack(self, line: tuple, n: int, k: int):
        """Blue to move after `line`: a Blue move that wins within n Blue moves, checked k deep."""
        k = min(k, n)
        key = (line, n, k)
        if key in self.proof:
            return self.proof[key]
        self.look([line])
        here = self.rows[line]
        if here["three_in_a_row"]["blue"]:
            return here["three_in_a_row"]["blue"][0]
        if n <= 1:
            return None
        after = [line + (m,) for m in here["moves"]]
        self.look(after)  # Red to move after each of my moves
        cands = []
        for m, s in zip(here["moves"], after):
            rv = self.rows[s]
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
            if self.defend(line + (m,), replies, n - 1, k - 1):
                best = m
                break
        self.proof[key] = best
        return best

    def decide(self, line: tuple, n: int):
        """The move to play now, by elimination: check every candidate one Blue move deep, then
        the survivors two deep, and so on. A winning move exists and survives every check, so
        once a single candidate is left (after at least MIN_CHECK moves deep) it is played."""
        if self.horizon >= n or MODE != "elim":
            return self.attack(line, n, self.horizon)
        self.look([line])
        here = self.rows[line]
        if here["three_in_a_row"]["blue"]:
            return here["three_in_a_row"]["blue"][0]
        after = [line + (m,) for m in here["moves"]]
        self.look(after)
        cands = []
        for m, s in zip(here["moves"], after):
            rv = self.rows[s]
            if rv.get("game_over"):
                return m
            if not rv["three_in_a_row"]["red"]:
                cands.append((-len(rv["three_in_a_row"]["blue"]), len(rv["moves"]), m, rv["moves"]))
        cands.sort(key=lambda c: c[:2])
        if n > QUIET_DEPTH and any(c[0] < 0 for c in cands):
            cands = [c for c in cands if c[0] < 0]
        alive = cands
        for k in range(2, self.horizon + 1):
            alive = [c for c in alive if self.defend(line + (c[2],), c[3], n - 1, k - 1)]
            if not alive:
                return None
            if len(alive) == 1 and k >= MIN_CHECK:
                return alive[0][2]
        return alive[0][2]

    def defend(self, line: tuple, replies: list, n: int, k: int) -> bool:
        """Red to move after `line`. True if every Red reply still loses within n Blue moves,
        checked k Blue moves deep; past the horizon the line is trusted."""
        if k <= 0:
            return True
        seqs = [line + (r,) for r in replies]
        self.look(seqs)
        real = []
        for s in seqs:
            row = self.rows[s]
            if row.get("game_over"):
                return False  # after a Red move: Red made three in a row, or I cannot move
            if row["three_in_a_row"]["blue"]:
                continue  # no defence: I win at once
            real.append(s)
        if real and n <= 1:
            return False
        # Narrowest defences first: a refutation, if there is one, tends to be among them.
        real.sort(key=lambda s: len(self.rows[s]["moves"]))
        return all(self.attack(s, n, k) for s in real)


def play_puzzle(tools: Tools, pid: str, seconds: float = 600.0, cap_lines=None, horizon: int = HORIZON) -> dict:
    start_calls, start, lines0 = tools.calls, time.monotonic(), tools.lines
    p = tools.show(pid)
    n = p["win_in"] - p["moves_used"]
    prover = Prover(tools, pid, start + seconds, cap_lines, horizon)
    line: tuple = ()
    result = {"id": pid, "win_in": p["win_in"], "status": p["status"]}
    try:
        while p["status"] == "open":
            mv = prover.decide(line, n)
            if mv is None:
                result["note"] = "no forced win found"
                break
            out = tools.move(pid, mv)
            p = out["puzzle"]
            if out["reply"]:
                line = line + (mv, out["reply"])
                prover.root = line
                n -= 1
    except BudgetRefused:
        result["note"] = "run budget used up"
    except OutOfBudget:
        result["note"] = "puzzle allowance used up, left open"
    result.update(status=tools.show(pid)["status"], calls=tools.calls - start_calls, seconds=round(time.monotonic() - start, 2), lines=tools.lines - lines0)
    return result


def caps(text: str = PUZZLE_CAP) -> dict:
    out = {}
    for part in filter(None, text.split(",")):
        n, c = part.split(":")
        out[int(n)] = int(c)
    return out


def play_run(tools: Tools, horizon: int = HORIZON, cap_text: str = PUZZLE_CAP, quiet: bool = False) -> list:
    """All scored puzzles, easiest first (any order is allowed); each gets at most its cap."""
    info = tools.puzzles()
    tools.budget_left = info.get("explore_left")
    cap = caps(cap_text)
    results = []
    for row in sorted(info["puzzles"], key=lambda r: (r["win_in"], r["id"])):
        r = play_puzzle(tools, row["id"], 600.0, cap.get(row["win_in"]), horizon)
        results.append(r)
        if not quiet:
            print(json.dumps(r), flush=True)
    return results


def main() -> None:
    tools = Tools()
    play_run(tools)
    done = tools.puzzles()
    print(f"solved {done['solved']} of {done['total']} (tools-only, horizon {HORIZON}), {tools.calls} tool calls, {tools.lines} explored positions, budget left {done.get('explore_left')}")


if __name__ == "__main__":
    main()
