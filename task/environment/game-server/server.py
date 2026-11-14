"""Thin Ice game server: holds all puzzle state and exposes it over MCP and plain HTTP.

It runs in its own container. The agent never sees this filesystem, so the only way to score
is to win puzzles through the API. Every state change is written to a signed receipt, which
is the single thing the verifier reads.
"""
import json
import math
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from thinice.board import RULES
from thinice.session import GameError, Run, clock_text, load_pack, pick, sign

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / "packs" / "manifest.json").read_text())
SEED = os.environ.get("THINICE_SEED") or "1"
SECRET = (HERE / "receipt.key").read_text().strip().encode()
RECEIPT = Path(os.environ.get("THINICE_RECEIPT", "/receipt/receipt.json"))

# Every scored puzzle has its own clock: base_sec plus per_move_sec for each move of its forced win.
# It starts when the puzzle is first looked at; when it runs out the puzzle is lost and the next
# one unlocks. run_sec is the whole run's time limit, shown to the player as time left.
# THINICE_CLOCK (the same JSON object) replaces the manifest's clock, for local tests.
CLOCK = json.loads(os.environ["THINICE_CLOCK"]) if os.environ.get("THINICE_CLOCK") else (MANIFEST.get("clock") or {})


def clock_for(win_in: int) -> float:
    return CLOCK.get("base_sec", 0) + CLOCK["per_move_sec"] * win_in


RUN = Run(
    pick(load_pack(HERE / "packs" / "scored.jsonl"), SEED, MANIFEST["tiers"], MANIFEST["per_tier"]),
    load_pack(HERE / "packs" / "practice.jsonl"),
    seed=SEED,
    clock=clock_for if CLOCK.get("per_move_sec") else None,
)
LOCK = threading.Lock()
FIRST_CALL: list = []  # when the player first used the game: the run's time left is counted from here
PENDING: list = []  # clock notices the player has not been shown yet


def save() -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    tmp = RECEIPT.with_suffix(".tmp")
    tmp.write_text(json.dumps(sign(RUN.scorecard(), SECRET)))
    os.replace(tmp, RECEIPT)


def settle() -> None:
    """With LOCK held: ends a puzzle whose clock ran out and writes that to the score sheet."""
    RUN.tick()
    while RUN.expired:
        att = RUN.expired.pop(0)
        PENDING.append(f"{att.pid} ran out of time ({clock_text(att.clock)}): it is lost and the next puzzle is unlocked.")
        save()


@contextmanager
def game():
    """Everything that touches the run happens in here: one caller at a time, clocks settled before and after."""
    with LOCK:
        if not FIRST_CALL:
            FIRST_CALL.append(time.monotonic())
        settle()
        try:
            yield
        finally:
            settle()


def reply(text: str) -> str:
    """A tool reply plus what the player must know about the clocks: what just ran out and what is left."""
    with game():
        notices = "".join(n + "\n" for n in PENDING)
        PENDING.clear()
        parts = []
        cur = RUN.current()
        if cur is not None and cur.clock is not None:
            if cur.started is None:
                parts.append(f"{cur.pid} clock: {clock_text(cur.clock)}, starts when you first look at it")
            else:
                parts.append(f"{cur.pid} clock: {clock_text(cur.time_left())} left of {clock_text(cur.clock)}")
        if CLOCK.get("run_sec"):
            left = max(0.0, CLOCK["run_sec"] - (time.monotonic() - FIRST_CALL[0]))
            parts.append(f"run: about {math.ceil(left / 60)} min left")
        return notices + text + (f"\n[{'; '.join(parts)}]" if parts else "")


def do_show(pid: str):
    with game():
        return RUN.get(pid)


def do_move(pid: str, move: str):
    with game():
        att = RUN.get(pid)
        out = att.move(move)
        if not att.practice:
            save()
        return att, out


def do_skip(pid: str):
    with game():
        att = RUN.skip(pid)
        save()
        return att


def do_practice(win_in):
    with game():
        try:
            n = int(win_in)
        except (TypeError, ValueError):
            raise GameError("win_in must be a whole number of moves, like 3") from None
        att = RUN.practice_new(n)
        save()
        return att


mcp = FastMCP("thin-ice")


@mcp.tool()
def rules() -> str:
    """The complete rules of Thin Ice."""
    return RULES


@mcp.tool()
def list_puzzles() -> str:
    """All scored puzzles: how many moves the forced win takes, status, moves used, and the score so far."""
    with game():
        table = RUN.table()
    return reply(table)


@mcp.tool()
def show_puzzle(puzzle_id: str) -> str:
    """Board, stones and legal moves of one puzzle. Scored puzzles are P01, P02, ...; practice puzzles are T001, T002, ..."""
    try:
        return reply(do_show(puzzle_id).text() + notes_text(puzzle_id))
    except GameError as exc:
        return reply(f"ERROR: {exc}")


@mcp.tool()
def play_move(puzzle_id: str, move: str) -> str:
    """Play one Blue move in a puzzle, written from-to (for example a1-a5). Red replies at once. There is no undo."""
    try:
        att, out = do_move(puzzle_id, move)
        return reply(att.result_text(out))
    except GameError as exc:
        return reply(f"ERROR: {exc}")


NOTES: dict = {}
NOTE_CHARS = 4000
NOTES_PER_PUZZLE = 100
NOTES_TOTAL = 2000


def notes_text(pid: str) -> str:
    rows = NOTES.get(pid.strip().upper(), [])
    if not rows:
        return ""
    return "\n\nYour notes on this puzzle:\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(rows, 1))


@mcp.tool()
def save_note(puzzle_id: str, text: str) -> str:
    """Save a note to yourself about a puzzle: candidate moves, lines you have checked, what is still open.
    Notes are shown again by show_puzzle. They are only for you: they change nothing in the game or the score."""
    pid = (puzzle_id or "").strip().upper()
    with game():
        try:
            RUN.get(pid, look=False)  # a note shows nothing of the board, so it does not start the clock
        except GameError as exc:
            out = f"ERROR: {exc}"
        else:
            rows = NOTES.get(pid, [])
            if sum(len(r) for r in NOTES.values()) >= NOTES_TOTAL:
                out = f"ERROR: at most {NOTES_TOTAL} notes in total"
            elif len(rows) >= NOTES_PER_PUZZLE:
                out = f"ERROR: at most {NOTES_PER_PUZZLE} notes per puzzle"
            else:
                NOTES.setdefault(pid, []).append(str(text)[:NOTE_CHARS])
                out = f"Saved note {len(rows) + 1} on {pid}."
    return reply(out)


@mcp.tool()
def skip_puzzle(puzzle_id: str) -> str:
    """Give up the current scored puzzle. It counts as lost (no undo) and the next puzzle unlocks."""
    try:
        att = do_skip(puzzle_id)
        nxt = RUN.current()
        return reply(f"{att.pid} given up (lost). " + (f"Next puzzle: {nxt.pid} (win in {nxt.puzzle.need})." if nxt else "No puzzles left."))
    except GameError as exc:
        return reply(f"ERROR: {exc}")


@mcp.tool()
def new_practice_puzzle(win_in: int) -> str:
    """Start a practice puzzle whose forced win takes `win_in` Blue moves. Practice never counts for the score, and a wrong move is answered with the move that would have won."""
    try:
        return reply(do_practice(win_in).text())
    except GameError as exc:
        return reply(f"ERROR: {exc}")


def _err(exc: Exception, code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=code)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


@mcp.custom_route("/api/rules", methods=["GET"])
async def api_rules(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "rules": RULES, "width": MANIFEST["game"]["w"], "height": MANIFEST["game"]["h"]})


@mcp.custom_route("/api/puzzles", methods=["GET"])
async def api_puzzles(request: Request) -> JSONResponse:
    with game():
        card = RUN.scorecard()
    rows = [{k: r[k] for k in ("id", "win_in", "status", "moves_used", "moves_allowed")} for r in card["puzzles"]]
    return JSONResponse({"ok": True, "solved": card["solved"], "total": card["total"], "score": card["score"], "puzzles": rows})


@mcp.custom_route("/api/puzzle/{pid}", methods=["GET"])
async def api_puzzle(request: Request) -> JSONResponse:
    try:
        return JSONResponse({"ok": True, **do_show(request.path_params["pid"]).view()})
    except GameError as exc:
        return _err(exc, 404)


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise GameError("request body must be a JSON object") from None
    if not isinstance(data, dict):
        raise GameError("request body must be a JSON object")
    return data


@mcp.custom_route("/api/move", methods=["POST"])
async def api_move(request: Request) -> JSONResponse:
    try:
        data = await _body(request)
        att, out = do_move(str(data.get("id", "")), str(data.get("move", "")))
        return JSONResponse({"ok": True, **out, "puzzle": att.view()})
    except GameError as exc:
        return _err(exc)


@mcp.custom_route("/api/skip", methods=["POST"])
async def api_skip(request: Request) -> JSONResponse:
    try:
        data = await _body(request)
        att = do_skip(str(data.get("id", "")))
        return JSONResponse({"ok": True, "id": att.pid, "status": att.status, "reason": att.reason})
    except GameError as exc:
        return _err(exc)


@mcp.custom_route("/api/practice", methods=["POST"])
async def api_practice(request: Request) -> JSONResponse:
    try:
        data = await _body(request)
        return JSONResponse({"ok": True, **do_practice(data.get("win_in")).view()})
    except GameError as exc:
        return _err(exc)


if __name__ == "__main__":
    save()
    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
