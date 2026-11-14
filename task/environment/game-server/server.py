"""Thin Ice game server: holds all puzzle state and exposes it over MCP and plain HTTP.

It runs in its own container. The agent never sees this filesystem, so the only way to score
is to win puzzles through the API. Every state change is written to a signed receipt, which
is the single thing the verifier reads.
"""
import json
import os
import threading
from pathlib import Path

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from thinice.board import RULES
from thinice.session import GameError, Run, load_pack, pick, sign

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / "packs" / "manifest.json").read_text())
SEED = os.environ.get("THINICE_SEED") or "1"
SECRET = (HERE / "receipt.key").read_text().strip().encode()
RECEIPT = Path(os.environ.get("THINICE_RECEIPT", "/receipt/receipt.json"))

RUN = Run(
    pick(load_pack(HERE / "packs" / "scored.jsonl"), SEED, MANIFEST["tiers"], MANIFEST["per_tier"]),
    load_pack(HERE / "packs" / "practice.jsonl"),
    seed=SEED,
)
LOCK = threading.Lock()


def save() -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    tmp = RECEIPT.with_suffix(".tmp")
    tmp.write_text(json.dumps(sign(RUN.scorecard(), SECRET)))
    os.replace(tmp, RECEIPT)


def do_show(pid: str):
    with LOCK:
        return RUN.get(pid)


def do_move(pid: str, move: str):
    with LOCK:
        att = RUN.get(pid)
        out = att.move(move)
        if not att.practice:
            save()
        return att, out


def do_practice(win_in):
    with LOCK:
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
    with LOCK:
        return RUN.table()


@mcp.tool()
def show_puzzle(puzzle_id: str) -> str:
    """Board, stones and legal moves of one puzzle. Scored puzzles are P01, P02, ...; practice puzzles are T001, T002, ..."""
    try:
        return do_show(puzzle_id).text()
    except GameError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
def play_move(puzzle_id: str, move: str) -> str:
    """Play one Blue move in a puzzle, written from-to (for example a1-a5). Red replies at once. There is no undo."""
    try:
        att, out = do_move(puzzle_id, move)
        return att.result_text(out)
    except GameError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
def new_practice_puzzle(win_in: int) -> str:
    """Start a practice puzzle whose forced win takes `win_in` Blue moves. Practice never counts for the score, and a wrong move is answered with the move that would have won."""
    try:
        return do_practice(win_in).text()
    except GameError as exc:
        return f"ERROR: {exc}"


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
    with LOCK:
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


@mcp.custom_route("/api/practice", methods=["POST"])
async def api_practice(request: Request) -> JSONResponse:
    try:
        data = await _body(request)
        return JSONResponse({"ok": True, **do_practice(data.get("win_in")).view()})
    except GameError as exc:
        return _err(exc)


if __name__ == "__main__":
    save()
    mcp.run(transport="http", host="0.0.0.0", port=8000)
