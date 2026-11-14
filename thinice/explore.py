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


def _side(side, to_move):
    side = (side or "").strip().lower()
    if side in ("", "turn", "to_move"):
        return to_move
    if side not in ("blue", "red"):
        raise ExploreError("side must be \"blue\" or \"red\" (or empty for the side to move)")
    return side


def walk(blue: int, red: int, line, side: str = "") -> dict:
    """Plays `line` (Blue moves first, then alternating) from a position with Blue to move.

    Returns the resulting position and the legal slides of `side` (default: the side to move),
    each marked if it would make three in a row. Illegal lines are reported, not raised.
    """
    toks = _split(line)
    want = (side or "").strip().lower()
    if want not in ("", "turn", "to_move", "blue", "red"):
        raise ExploreError("side must be \"blue\" or \"red\" (or empty for the side to move)")
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
    }
    if over:
        out["moves_for"], out["moves"], out["three_in_a_row"] = None, [], []
        return out
    who = _side(want, turn)
    mine = blue if who == "blue" else red
    legal = moves(mine, blue | red)
    out["moves_for"] = who
    out["moves"] = [move_name(m) for m in legal]
    out["three_in_a_row"] = [move_name((f, t)) for f, t in legal if completes_line(mine ^ (1 << f) ^ (1 << t), t)]
    return out


def lines(blue: int, red: int, many, side: str = "") -> list:
    if isinstance(many, str):
        many = [p for p in many.replace(";", "\n").splitlines()]
    if not isinstance(many, (list, tuple)):
        raise ExploreError("lines must be a list of lines, each a string of moves like \"c3-c6 d1-a4\"")
    if len(many) > MAX_LINES:
        raise ExploreError(f"at most {MAX_LINES} lines per call")
    if not many:
        raise ExploreError("give at least one line (an empty string means the current position)")
    return [walk(blue, red, ln, side) for ln in many]


def text_one(pid: str, r: dict) -> str:
    seq = " ".join(r["line"]) or "(no moves)"
    if "error" in r:
        return f"{pid} after {seq}: ERROR {r['error']}"
    head = f"{pid} after {seq}:"
    lines_ = [head, r["board"], f"Blue stones: {' '.join(r['blue'])}   Red stones: {' '.join(r['red'])}"]
    if r["game_over"]:
        lines_.append(f"Game over: {r['game_over']}.")
        return "\n".join(lines_)
    who = r["moves_for"].capitalize()
    turn = r["to_move"].capitalize()
    note = "" if r["moves_for"] == r["to_move"] else f" (it is {turn}'s turn; listed as if {who} were to move)"
    lines_.append(f"{turn} to move. {who}'s legal moves{note}: {' '.join(r['moves'])}")
    lines_.append(f"{who} moves that make three in a row: {' '.join(r['three_in_a_row']) or 'none'}")
    return "\n".join(lines_)


def text_many(pid: str, rs: list) -> str:
    out = []
    for r in rs:
        seq = " ".join(r["line"]) or "(no moves)"
        if "error" in r:
            out.append(f"{seq}: ERROR {r['error']}")
        elif r["game_over"]:
            out.append(f"{seq}: game over, {r['game_over']}")
        else:
            who = r["moves_for"]
            mark = f"{who} moves that make three in a row: {' '.join(r['three_in_a_row']) or 'none'}"
            out.append(
                f"{seq}: {r['to_move']} to move | blue {' '.join(r['blue'])} | red {' '.join(r['red'])} | "
                f"{mark} | {who} legal moves: {' '.join(r['moves'])}"
            )
    return f"{pid}, {len(rs)} line(s), each played from the current position (Blue first):\n" + "\n".join(out)
