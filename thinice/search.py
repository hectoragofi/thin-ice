"""Rules-only search for Thin Ice: finds a forced win by looking ahead. No tablebase, no hidden data.

This is the reference player. It uses nothing but the published rules, so anything it solves an
agent could in principle solve with the same information.
"""
from __future__ import annotations

import time

from .board import completes_line, moves


class Timeout(Exception):
    pass


class Searcher:
    """Proof search: can Blue force three in a row within `n` of its own moves?"""

    def __init__(self, time_limit: float | None = None):
        self.table: dict = {}
        self.nodes = 0
        self.deadline = None if time_limit is None else time.monotonic() + time_limit

    def _tick(self) -> None:
        self.nodes += 1
        if self.deadline is not None and self.nodes & 1023 == 0 and time.monotonic() > self.deadline:
            raise Timeout

    def attack(self, blue: int, red: int, n: int):
        """Blue to move. Returns a move that wins within n Blue moves, or None."""
        self._tick()
        cand = moves(blue, blue | red)
        for f, t in cand:
            if completes_line(blue ^ (1 << f) ^ (1 << t), t):
                return (f, t)
        if n <= 1:
            return None
        hit = self.table.get((blue, red, n))
        if hit is not None:
            return hit or None
        best = False
        for f, t in cand:
            if self.holds(blue ^ (1 << f) ^ (1 << t), red, n - 1):
                best = (f, t)
                break
        self.table[(blue, red, n)] = best
        return best or None

    def holds(self, blue: int, red: int, n: int) -> bool:
        """Red to move. True if Blue still wins within n more Blue moves whatever Red plays."""
        replies = moves(red, blue | red)
        if not replies:
            return True  # Red cannot move and loses
        after = []
        for f, t in replies:
            nr = red ^ (1 << f) ^ (1 << t)
            if completes_line(nr, t):
                return False
            after.append(nr)
        for nr in after:
            if self.attack(blue, nr, n) is None:
                return False
        return True


def find_win(blue: int, red: int, max_moves: int, time_limit: float | None = None):
    """Shortest forced win for Blue within max_moves, by iterative deepening.

    Returns (move, moves_needed, nodes) or (None, None, nodes) if none was found in time.
    """
    s = Searcher(time_limit)
    try:
        for n in range(1, max_moves + 1):
            mv = s.attack(blue, red, n)
            if mv is not None:
                return mv, n, s.nodes
    except Timeout:
        pass
    return None, None, s.nodes
