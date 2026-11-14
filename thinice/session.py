"""Puzzle sessions: the environment logic shared by the game server, the local runner and training.

A puzzle pack holds, for every position Blue can reach while it still has a forced win, the
solver's verdict on each legal move and Red's fixed reply. Nothing here searches or guesses:
the pack is the single source of truth, produced by the exhaustive solver.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections import defaultdict

from .board import key, mask_of, move_name, parse_move, render, sq_name, squares

LOSS0 = 128  # child value: the opponent has already lost (three in a row, or cannot move)


class GameError(Exception):
    """A request the game refuses without changing any state."""


class Puzzle:
    __slots__ = ("index", "blue", "red", "depth", "cap", "nodes")

    def __init__(self, rec: dict):
        self.index = rec["index"]
        self.blue = mask_of(rec["blue"])
        self.red = mask_of(rec["red"])
        self.depth = rec["depth"]  # plies to the fastest forced win
        self.cap = rec["cap"]  # Blue moves allowed
        self.nodes = rec["nodes"]

    @property
    def need(self) -> int:
        """Blue moves in the fastest forced win."""
        return (self.depth + 1) // 2


def load_pack(path) -> list:
    with open(path, encoding="utf-8") as fh:
        return [Puzzle(json.loads(line)) for line in fh if line.strip()]


def pick(pool: list, seed, tiers, per_tier: int) -> list:
    """Deterministic choice of `per_tier` puzzles for each depth in `tiers`, easiest tier first."""
    chosen = []
    for depth in tiers:
        cands = [p for p in pool if p.depth == depth]
        cands.sort(key=lambda p: hashlib.sha256(f"{seed}:{p.index}".encode()).hexdigest())
        if len(cands) < per_tier:
            raise ValueError(f"pool has only {len(cands)} puzzles of depth {depth}, need {per_tier}")
        chosen.extend(cands[:per_tier])
    return chosen


class Attempt:
    """One play-through of one puzzle. There is no undo and no second attempt."""

    def __init__(self, pid: str, puzzle: Puzzle, practice: bool = False):
        self.pid = pid
        self.puzzle = puzzle
        self.practice = practice
        self.blue = puzzle.blue
        self.red = puzzle.red
        self.used = 0
        self.status = "open"  # open | solved | failed
        self.reason = ""
        self.history: list = []  # [blue move, red reply or None]

    def _entries(self) -> list:
        return self.puzzle.nodes[key(self.blue, self.red)]

    def legal(self) -> list:
        return [move_name(e) for e in self._entries()] if self.status == "open" else []

    def view(self) -> dict:
        return {
            "id": self.pid,
            "practice": self.practice,
            "status": self.status,
            "reason": self.reason,
            "win_in": self.puzzle.need,
            "moves_used": self.used,
            "moves_allowed": self.puzzle.cap,
            "board": render(self.blue, self.red),
            "blue": [sq_name(s) for s in squares(self.blue)],
            "red": [sq_name(s) for s in squares(self.red)],
            "legal_moves": self.legal(),
            "history": self.history,
        }

    def text(self) -> str:
        v = self.view()
        kind = "Practice puzzle" if self.practice else "Puzzle"
        head = f"{kind} {self.pid}: Blue has a forced win in {v['win_in']} move(s). Moves used: {v['moves_used']} of {v['moves_allowed']} allowed."
        lines = [head, v["board"], f"Blue stones: {' '.join(v['blue'])}   Red stones: {' '.join(v['red'])}"]
        if self.status == "open":
            lines.append("Blue (you) to move. Legal moves: " + " ".join(v["legal_moves"]))
        else:
            lines.append(f"Status: {self.status.upper()}" + (f" ({self.reason})" if self.reason else ""))
        return "\n".join(lines)

    def move(self, text: str) -> dict:
        """Play a Blue move. Returns what happened; raises GameError if nothing was played."""
        if self.status != "open":
            raise GameError(f"{self.pid} is already {self.status}; it cannot be played again")
        try:
            f, t = parse_move(text)
        except ValueError as exc:
            raise GameError(str(exc)) from None
        entry = next((e for e in self._entries() if e[0] == f and e[1] == t), None)
        if entry is None:
            raise GameError(f"{text.strip()!r} is not a legal move here. Legal moves: {' '.join(self.legal())}")
        out = {"id": self.pid, "played": move_name(entry), "reply": None, "feedback": None}
        if self.practice and entry[2] <= LOSS0 - 1:
            out["feedback"] = self._lesson()
        cv = entry[2]
        self.used += 1
        self.blue ^= (1 << f) | (1 << t)
        if cv == LOSS0:
            self.status = "solved"
            self.history.append([out["played"], None])
        elif cv > LOSS0:
            df, dt = entry[3], entry[4]
            self.red ^= (1 << df) | (1 << dt)
            out["reply"] = move_name((df, dt))
            self.history.append([out["played"], out["reply"]])
            if self.used >= self.puzzle.cap:
                self.status, self.reason = "failed", "out of moves"
        else:
            self.status = "failed"
            self.history.append([out["played"], None])
            if cv == 0:
                self.reason = "that move gave up the forced win; with best play the game is now a draw"
            else:
                self.reason = f"that move loses; Red now has a forced win in {(cv + 1) // 2} move(s)"
        out["status"], out["reason"] = self.status, self.reason
        return out

    def _lesson(self) -> str:
        wins = sorted((e[2], move_name(e)) for e in self._entries() if e[2] >= LOSS0)
        best = [name for cv, name in wins if cv == wins[0][0]]
        return f"Winning move(s) in that position: {' '.join(name for _, name in wins)}. Fastest: {' '.join(best)}."

    def result_text(self, out: dict) -> str:
        if self.status == "solved":
            msg = f"You played {out['played']}: three in a row. {self.pid} SOLVED."
        elif self.status == "failed":
            msg = f"You played {out['played']}. {self.pid} FAILED: {self.reason}."
            if out["reply"]:
                msg = f"You played {out['played']}. Red replied {out['reply']}. {self.pid} FAILED: {self.reason}."
        else:
            msg = f"You played {out['played']}. Red replied {out['reply']}.\n{self.text()}"
        if out["feedback"]:
            msg += "\n" + out["feedback"]
        return msg


class Run:
    """A scored episode: a fixed set of puzzles plus an unlimited-feedback practice pool."""

    def __init__(self, scored: list, practice: list, seed=0):
        self.seed = seed
        self.attempts = {f"P{i + 1:02d}": Attempt(f"P{i + 1:02d}", p) for i, p in enumerate(scored)}
        self._practice = defaultdict(list)
        for p in practice:
            self._practice[p.need].append(p)
        self._practice_next = defaultdict(int)
        self.practice_attempts: dict = {}

    def get(self, pid: str) -> Attempt:
        pid = str(pid).strip().upper()
        att = self.attempts.get(pid) or self.practice_attempts.get(pid)
        if att is None:
            raise GameError(f"unknown puzzle id {pid!r}; scored puzzles are {next(iter(self.attempts))}..{list(self.attempts)[-1]}")
        return att

    def practice_new(self, win_in: int) -> Attempt:
        pool = self._practice.get(int(win_in))
        if not pool:
            raise GameError(f"no practice puzzles with a win in {win_in} move(s); available: {sorted(self._practice)}")
        i = self._practice_next[int(win_in)]
        if i >= len(pool):
            raise GameError(f"all {len(pool)} practice puzzles with a win in {win_in} move(s) have been used")
        self._practice_next[int(win_in)] = i + 1
        pid = f"T{len(self.practice_attempts) + 1:03d}"
        self.practice_attempts[pid] = Attempt(pid, pool[i], practice=True)
        return self.practice_attempts[pid]

    def scorecard(self) -> dict:
        rows = [
            {
                "id": a.pid,
                "win_in": a.puzzle.need,
                "depth": a.puzzle.depth,
                "index": a.puzzle.index,
                "status": a.status,
                "reason": a.reason,
                "moves_used": a.used,
                "moves_allowed": a.puzzle.cap,
                "history": a.history,
            }
            for a in self.attempts.values()
        ]
        solved = sum(r["status"] == "solved" for r in rows)
        return {
            "version": 1,
            "seed": self.seed,
            "total": len(rows),
            "solved": solved,
            "score": round(solved / len(rows), 6) if rows else 0.0,
            "practice_started": len(self.practice_attempts),
            "puzzles": rows,
        }

    def table(self) -> str:
        card = self.scorecard()
        lines = ["id   win-in  status  moves"]
        for r in card["puzzles"]:
            lines.append(f"{r['id']:<4} {r['win_in']:<7} {r['status']:<7} {r['moves_used']}/{r['moves_allowed']}")
        lines.append(f"Solved {card['solved']} of {card['total']}. Score: {card['score']:.3f}")
        return "\n".join(lines)


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sign(scorecard: dict, secret: bytes) -> dict:
    return {"scorecard": scorecard, "sig": hmac.new(secret, _canonical(scorecard), hashlib.sha256).hexdigest()}


def verify(receipt: dict, secret: bytes) -> dict:
    """Returns the scorecard if the signature is valid, else raises ValueError."""
    card = receipt.get("scorecard")
    sig = receipt.get("sig")
    if not isinstance(card, dict) or not isinstance(sig, str):
        raise ValueError("malformed receipt")
    want = hmac.new(secret, _canonical(card), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, sig):
        raise ValueError("bad signature")
    return card
