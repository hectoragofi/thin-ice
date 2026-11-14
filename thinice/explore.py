"""Exploration tools for the agent: the rules of Thin Ice applied to lines the agent writes.

Nothing here reads a puzzle pack, a solver table or the defender. Every answer is a pure
function of the starting position and the moves given, computed with the same slide rules the
agent was told. So an answer can say what the board looks like after a line, whose turn it is,
which slides are legal and which of them would make three in a row on that very move. It can
never say whether a position is won, what Red would reply, or which move solves a puzzle,
because that information is not here to give. Exploring never changes any puzzle.
"""
from __future__ import annotations

from .board import completes_line, moves, move_name, parse_move, render, sq_name, squares

MAX_LINES = 40  # lines per explore_lines call
MAX_PLIES = 40  # moves per line
NL = chr(10)


class ExploreError(Exception):
    """A request that cannot be answered; nothing was explored."""


def _split(line) -> list:
    if isinstance(line, (list, tuple)):
        toks = [str(t) for t in line]
    elif isinstance(line, str):
        toks = line.replace(",", " ").split()
    else:
        raise ExploreError("a line is a string of moves separated by spaces, like \"c3-c6 d1-a4\"")
    toks = [t.strip() for t in toks if str(t).strip()]
    if len(toks) > MAX_PLIES:
        raise ExploreError(f"a line can have at most {MAX_PLIES} moves")
    return toks


def _completing(mine: int, occupied: int) -> list:
    return [move_name((f, t)) for f, t in moves(mine, occupied) if completes_line(mine ^ (1 << f) ^ (1 << t), t)]


def walk(blue: int, red: int, line) -> dict:
    """Plays `line` (Blue moves first, then alternating) from a position with Blue to move.

    Returns the resulting position, the legal moves of the side to move, and for each colour
    the moves that would make three in a row if it were that colour's turn (the side not to
    move gets them as threats to know about). Illegal lines are reported, not raised.
    """
    toks = _split(line)
    turn, over, played = "blue", None, []
    for i, tok in enumerate(toks):
        if over:
            return {"line": toks, "error": f"move {i + 1} ({tok}): the game is already over ({over})"}
        try:
            f, t = parse_move(tok)
        except ValueError as exc:
            return {"line": toks, "error": f"move {i + 1} ({tok}): {exc}"}
        mine = blue if turn == "blue" else red
        if (f, t) not in moves(mine, blue | red):
            who = "Blue" if turn == "blue" else "Red"
            return {"line": toks, "error": f"move {i + 1} ({tok}) is not a legal {who} move there"}
        if turn == "blue":
            blue ^= (1 << f) | (1 << t)
            mine = blue
        else:
            red ^= (1 << f) | (1 << t)
            mine = red
        played.append(move_name((f, t)))
        nxt = "red" if turn == "blue" else "blue"
        if completes_line(mine, t):
            over = f"{turn.capitalize()} made three in a row with move {i + 1} and wins"
        elif not moves(blue if nxt == "blue" else red, blue | red):
            over = f"{nxt.capitalize()} has no legal move and loses"
        turn = nxt
    out = {
        "line": played,
        "board": render(blue, red),
        "blue": [sq_name(s) for s in squares(blue)],
        "red": [sq_name(s) for s in squares(red)],
        "game_over": over,
        "to_move": None if over else turn,
        "moves": [],
        "three_in_a_row": {"blue": [], "red": []},
    }
    if over:
        return out
    occ = blue | red
    out["moves"] = [move_name(m) for m in moves(blue if turn == "blue" else red, occ)]
    out["three_in_a_row"] = {"blue": _completing(blue, occ), "red": _completing(red, occ)}
    return out


def lines(blue: int, red: int, many) -> list:
    if isinstance(many, str):
        many = [p for p in many.replace(";", "\n").splitlines()]
    if not isinstance(many, (list, tuple)):
        raise ExploreError("lines must be a list of lines, each a string of moves like \"c3-c6 d1-a4\"")
    if len(many) > MAX_LINES:
        raise ExploreError(f"at most {MAX_LINES} lines per call")
    if not many:
        raise ExploreError("give at least one line (an empty string means the current position)")
    return [walk(blue, red, ln) for ln in many]


def _threes(r: dict, who: str) -> str:
    return " ".join(r["three_in_a_row"][who]) or "none"


def text_one(pid: str, r: dict) -> str:
    seq = " ".join(r["line"]) or "(no moves)"
    if "error" in r:
        return f"{pid} after {seq}: ERROR {r['error']}"
    out = [f"{pid} after {seq}:", r["board"], f"Blue stones: {' '.join(r['blue'])}   Red stones: {' '.join(r['red'])}"]
    if r["game_over"]:
        out.append(f"Game over: {r['game_over']}.")
        return NL.join(out)
    turn = r["to_move"].capitalize()
    out.append(f"{turn} to move. Legal moves: {' '.join(r['moves'])}")
    out.append(f"Moves that would make three in a row - Blue: {_threes(r, 'blue')}; Red: {_threes(r, 'red')}")
    return NL.join(out)


def text_many(pid: str, rs: list) -> str:
    out = []
    for r in rs:
        seq = " ".join(r["line"]) or "(no moves)"
        if "error" in r:
            out.append(f"{seq}: ERROR {r['error']}")
        elif r["game_over"]:
            out.append(f"{seq}: game over, {r['game_over']}")
        else:
            out.append(
                f"{seq}: {r['to_move']} to move | blue {' '.join(r['blue'])} | red {' '.join(r['red'])} | "
                f"three in a row: blue {_threes(r, 'blue')}, red {_threes(r, 'red')} | {r['to_move']} legal moves: {' '.join(r['moves'])}"
            )
    return f"{pid}, {len(rs)} line(s), each played from the current position (Blue first):" + NL + NL.join(out)
