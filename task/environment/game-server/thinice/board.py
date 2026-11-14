"""Thin Ice rules: board geometry, moves and rendering. Pure Python, no dependencies.

Squares are numbered 0..24, square = row * 5 + column, with a1 = 0 in the bottom-left corner.
A set of stones is an int bitmask over those squares.
"""
from __future__ import annotations

W, H, K = 5, 5, 3
N = W * H
FILES = "abcde"
DIRS = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))


def _build_rays() -> tuple:
    rays = []
    for sq in range(N):
        x, y = sq % W, sq // W
        per_dir = []
        for dx, dy in DIRS:
            ray, cx, cy = [], x + dx, y + dy
            while 0 <= cx < W and 0 <= cy < H:
                ray.append(cy * W + cx)
                cx, cy = cx + dx, cy + dy
            per_dir.append(tuple(ray))
        rays.append(tuple(per_dir))
    return tuple(rays)


def _build_lines() -> tuple:
    lines = []
    for sq in range(N):
        x, y = sq % W, sq // W
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            cells = [(x + dx * i, y + dy * i) for i in range(K)]
            if all(0 <= cx < W and 0 <= cy < H for cx, cy in cells):
                lines.append(sum(1 << (cy * W + cx) for cx, cy in cells))
    return tuple(lines)


RAYS = _build_rays()
LINES = _build_lines()
LINES_THROUGH = tuple(tuple(line for line in LINES if line >> sq & 1) for sq in range(N))


def has_line(mask: int) -> bool:
    """True if the stones in `mask` contain three in a row."""
    return any(mask & line == line for line in LINES)


def completes_line(mask: int, sq: int) -> bool:
    """Like has_line, but only checks lines through `sq` (the stone that just moved)."""
    return any(mask & line == line for line in LINES_THROUGH[sq])


def moves(mine: int, occupied: int) -> list:
    """Legal moves as (from, to) pairs, sorted. A stone slides until the next cell is taken or off the board."""
    out = []
    rest = mine
    while rest:
        low = rest & -rest
        sq = low.bit_length() - 1
        rest ^= low
        for ray in RAYS[sq]:
            cur = sq
            for nxt in ray:
                if occupied >> nxt & 1:
                    break
                cur = nxt
            if cur != sq:
                out.append((sq, cur))
    out.sort()
    return out


def squares(mask: int) -> list:
    return [sq for sq in range(N) if mask >> sq & 1]


def mask_of(sqs) -> int:
    return sum(1 << s for s in sqs)


def sq_name(sq: int) -> str:
    return FILES[sq % W] + str(sq // W + 1)


def parse_sq(text: str) -> int:
    text = text.strip().lower()
    if len(text) != 2 or text[0] not in FILES or not text[1].isdigit() or not 1 <= int(text[1]) <= H:
        raise ValueError(f"bad square {text!r}: use a letter a-e and a digit 1-5, like c3")
    return (int(text[1]) - 1) * W + FILES.index(text[0])


def move_name(move) -> str:
    return f"{sq_name(move[0])}-{sq_name(move[1])}"


def parse_move(text: str) -> tuple:
    parts = text.strip().lower().replace(" ", "").replace("->", "-").split("-")
    if len(parts) != 2:
        raise ValueError(f"bad move {text!r}: write it as from-to, like a1-a5")
    return parse_sq(parts[0]), parse_sq(parts[1])


def render(blue: int, red: int) -> str:
    """Board as text, rank 5 on top. B = Blue, R = Red, . = empty."""
    rows = []
    for y in range(H - 1, -1, -1):
        cells = ["B" if blue >> (y * W + x) & 1 else "R" if red >> (y * W + x) & 1 else "." for x in range(W)]
        rows.append(f"{y + 1} " + " ".join(cells))
    rows.append("  " + " ".join(FILES))
    return "\n".join(rows)


def key(blue: int, red: int) -> str:
    """Position key used by the puzzle packs (matches the solver's output)."""
    return f"[{','.join(map(str, squares(blue)))}]|[{','.join(map(str, squares(red)))}]"


RULES = """\
THIN ICE - rules

Board: 5x5. Columns a-e (left to right), rows 1-5 (bottom to top). a1 is the bottom-left corner.
Stones: Blue has 4, Red has 4. Players alternate; a turn moves exactly one of your own stones.
Move: pick a stone and one of the 8 directions (up, down, left, right, 4 diagonals).
      The stone slides in that direction and cannot stop early: it stops only on the last
      empty cell before the edge of the board or before another stone. It must move at least
      one cell. Stones never jump, capture or push.
Win:  the first player whose stones have 3 in a row (adjacent cells in a horizontal, vertical or
      diagonal line) after their own move wins at once.
      A player who has no legal move on their turn loses.
Notation: from-to, for example a1-a5 means the stone on a1 slid up until it stopped on a5.
"""
