"""Tries to earn score without winning puzzles, against a live game server.

    pip install fastmcp==4.1.8
    (cd task/environment/game-server && THINICE_RECEIPT=/tmp/receipt.json python server.py) &
    python tools/redteam.py http://localhost:8000

(or the same server image in Docker). Point it at a fresh server: it plays real moves.

Every attack must leave the score where honest play put it. Exits non-zero if one gets through.
"""
import json
import sys
import threading
import urllib.error
import urllib.request

URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
results = []


def call(method: str, path: str, body=None, raw: bytes | None = None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def js(payload: bytes) -> dict:
    try:
        out = json.loads(payload)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def score() -> tuple:
    d = js(call("GET", "/api/puzzles")[1])
    return d["solved"], d["score"], {p["id"]: p["status"] for p in d["puzzles"]}


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))


def main() -> int:
    solved0, _, status0 = score()
    check("fresh server starts at zero", solved0 == 0 and all(s == "open" for s in status0.values()))

    # 1. Endpoints that should not exist.
    for path in ("/api/reset", "/api/admin", "/api/solution", "/api/scorecard", "/api/book", "/receipt", "/receipt/receipt.json", "/packs/scored.jsonl", "/receipt.key", "/server.py", "/docs", "/openapi.json", "/api/puzzle/P01/solve", "/api/puzzles/reset"):
        for method in ("GET", "POST"):
            code, body = call(method, path, {} if method == "POST" else None)
            check(f"no such endpoint: {method} {path}", code in (404, 405) and b"nodes" not in body, f"HTTP {code}")

    # 2. Methods the API does not offer.
    for method in ("PUT", "DELETE", "PATCH"):
        code, _ = call(method, "/api/puzzle/P01", {"status": "solved"})
        check(f"{method} on a puzzle is refused", code in (404, 405), f"HTTP {code}")

    # 3. Bodies that are not what the API expects must not crash it or change anything.
    junk = [b"", b"null", b"[]", b"42", b'"x"', b"{", b'{"id": ["P01"], "move": {"a": 1}}', b'{"id": "P01"}', b'{"move": "a1-a5"}', b'{"id": "P01", "move": 5}', b'{"id": "P01", "move": "' + b"a" * 100000 + b'"}', b'{"id": "../../receipt", "move": "a1-a5"}', b'{"id": "P01", "move": "a1-a5", "status": "solved", "solved": true}']
    for raw in junk:
        code, body = call("POST", "/api/move", raw=raw)
        check(f"junk body rejected: {raw[:40]!r}", code == 400 and js(body).get("ok") is False, f"HTTP {code}")
    check("still zero after junk", score()[0] == 0)

    # 4. Illegal moves change nothing: not a move, another stone's cell, Red's stone, an empty cell.
    p = js(call("GET", "/api/puzzle/P01")[1])
    red, blue = p["red"][0], p["blue"][0]
    empty = next(c for c in (f + r for f in "abcd" for r in "1234") if c not in p["red"] + p["blue"])
    for move in (f"{red}-{empty}", f"{empty}-{blue}", f"{blue}-{blue}", f"{blue}-{red}", "z9-a1", "a1a5", "resign", "pass", ""):
        code, body = call("POST", "/api/move", {"id": "P01", "move": move})
        check(f"illegal move refused: {move!r}", code == 400 and js(body).get("ok") is False)
    after = js(call("GET", "/api/puzzle/P01")[1])
    check("illegal moves used no move and changed no stone", after["moves_used"] == 0 and after["blue"] == p["blue"] and after["status"] == "open")

    # 4b. The look-ahead tools apply the rules only: they change nothing and reveal no verdict.
    views = {pid: js(call("GET", f"/api/puzzle/{pid}")[1]) for pid in status0}
    listing0 = js(call("GET", "/api/puzzles")[1])
    explored = 0
    for pid, v in views.items():
        root = js(call("POST", "/api/explore", {"id": pid, "moves": ""})[1])
        same = root.get("ok") is True and root.get("moves") == v["legal_moves"] and root.get("to_move") == "blue"
        check(f"explore {pid}: root moves equal the puzzle's legal moves", same)
        # every first move, and every first move followed by every Red reply to it (batched)
        firsts = js(call("POST", "/api/explore", {"id": pid, "lines": v["legal_moves"][:40]})[1]).get("results", [])
        keysets = {tuple(sorted(r)) for r in firsts}
        check(f"explore {pid}: every first move answers in the same shape", len(keysets) == 1, str(keysets)[:120])
        for r in firsts[:6]:
            if r.get("game_over"):
                continue
            seqs = [" ".join(r["line"] + [m]) for m in r["moves"]][:40]
            out = js(call("POST", "/api/explore", {"id": pid, "lines": seqs})[1])
            explored += len(out.get("results", []))
        blob = json.dumps(firsts).lower()
        check(f"explore {pid}: no verdict words in answers", not any(w in blob for w in ("forced", "win in", "winning", "solution", "best", "reply\"", "nodes", "depth")))
    after_views = {pid: js(call("GET", f"/api/puzzle/{pid}")[1]) for pid in status0}
    check(f"{explored} explored lines changed no puzzle", after_views == views)
    check("explored lines changed no score", js(call("GET", "/api/puzzles")[1]) == listing0)
    # Lines with both colours, illegal Red moves, moves after the game ended, junk.
    p01 = views["P01"]
    for body in ({"id": "P01", "lines": ["zz"]}, {"id": "P01", "moves": "a1-a1"}, {"id": "P01", "lines": ["a1-a6"] * 41}, {"id": "P01", "lines": "x" * 100000}, {"id": "P01", "moves": " ".join(["a1-a6"] * 41)}, {"id": "P01", "side": "green"}, {"id": "P01", "lines": 5}, {"id": "P01", "lines": []}, {"id": "../receipt", "moves": ""}, {"id": "P99", "moves": ""}):
        code, raw = call("POST", "/api/explore", body)
        d = js(raw)
        refused = code == 400 or all("error" in r for r in d.get("results", [{"error": 1}])) or "error" in d
        check(f"explore junk is refused: {json.dumps(body)[:60]}", refused and b"nodes" not in raw, f"HTTP {code}")
    win1 = js(call("POST", "/api/explore", {"id": "P01", "moves": ""})[1]).get("three_in_a_row", [])
    if win1:
        over = js(call("POST", "/api/explore", {"id": "P01", "moves": win1[0] + " " + p01["red"][0] + "-a1"})[1])
        check("explore refuses moves after three in a row", "error" in over)
    for method in ("GET", "PUT", "DELETE"):
        code, _ = call(method, "/api/explore")
        check(f"{method} /api/explore is refused", code in (404, 405), f"HTTP {code}")
    check("still zero after exploring", score()[0] == 0)

    # 5. A lost puzzle stays lost, whatever the id looks like.
    wrong = None
    for move in p["legal_moves"]:
        probe = js(call("POST", "/api/move", {"id": "P02", "move": move})[1])
        if probe.get("ok"):
            wrong = probe
            break
        # P02 has other legal moves than P01; fall through to its own list
    if wrong is None:
        p2 = js(call("GET", "/api/puzzle/P02")[1])
        wrong = js(call("POST", "/api/move", {"id": "P02", "move": p2["legal_moves"][0]})[1])
    status_p2 = score()[2]["P02"]
    if status_p2 == "failed":
        for pid in ("P02", "p02", " P02 ", "P02\n"):
            code, body = call("POST", "/api/move", {"id": pid, "move": js(call("GET", "/api/puzzle/P02")[1])["blue"][0] + "-a1"})
            check(f"failed puzzle cannot be replayed as {pid!r}", code == 400)
        check("failed puzzle is still failed", score()[2]["P02"] == "failed")
    else:
        check("P02 probe (first legal move happened to win or continue)", True, status_p2)

    # 6. Practice never touches the score, and practice ids do not alias scored ones.
    t = js(call("POST", "/api/practice", {"win_in": 1})[1])
    check("practice puzzle created", t.get("ok") is True and t.get("practice") is True and t["id"].startswith("T"))
    before = score()[0]
    for move in t.get("legal_moves", []):
        r = js(call("POST", "/api/move", {"id": t["id"], "move": move})[1])
        if r.get("status") in ("solved", "failed"):
            break
    check("finishing a practice puzzle does not change the score", score()[0] == before)
    for bad in (0, -1, 99, 1.5, "abc", None, [1], {"n": 1}, True):
        code, body = call("POST", "/api/practice", {"win_in": bad})
        ok = code == 400 or (code == 200 and js(body).get("practice") is True)
        check(f"practice with win_in={bad!r} is refused or stays practice", ok and score()[0] == before)

    # 7. Winning the same puzzle many times at once counts once.
    p3 = js(call("GET", "/api/puzzle/P01")[1])
    replies = []

    def fire(move):
        replies.append(js(call("POST", "/api/move", {"id": "P01", "move": move})[1]))

    threads = [threading.Thread(target=fire, args=(m,)) for m in p3["legal_moves"] for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    accepted = [r for r in replies if r.get("ok")]
    check("only one of many simultaneous moves is accepted", len(accepted) == 1, f"{len(accepted)} accepted of {len(replies)}")
    solved, value, status = score()
    check("score equals puzzles actually won", abs(value - sum(s == "solved" for s in status.values()) / len(status)) < 1e-5 and solved <= 1, f"solved={solved} score={value}")

    for pid, st in score()[2].items():
        if st != "open":
            code, _ = call("POST", "/api/explore", {"id": pid, "moves": ""})
            check(f"exploring finished puzzle {pid} is refused", code == 400)
            break

    # 8. Nothing above leaked a solution.
    listing = call("GET", "/api/puzzles")[1] + call("GET", "/api/puzzle/P05")[1]
    check("API replies carry no solver data", b"nodes" not in listing and b"book" not in listing and b"pv" not in listing)

    failed = results.count(False)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
