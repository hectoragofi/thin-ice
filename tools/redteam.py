"""Tries to earn score without winning puzzles, against a live game server.

    docker build -t thinice-game task/environment/game-server
    docker run --rm -d -p 8000:8000 -e THINICE_RECEIPT=/tmp/receipt.json --name thinice-game thinice-game
    python tools/redteam.py http://localhost:8000
    docker rm -f thinice-game

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

    # 5. Puzzles are played one at a time: later ones are locked, whatever the id looks like.
    for pid in ("P05", "p05", " P05 ", "P32"):
        code, body = call("GET", f"/api/puzzle/{pid.strip()}")
        check(f"locked puzzle cannot be viewed: {pid!r}", code == 404 and b"locked" in body and b"legal_moves" not in body, f"HTTP {code}")
        code, body = call("POST", "/api/move", {"id": pid, "move": "a1-a6"})
        check(f"locked puzzle cannot be played: {pid!r}", code == 400 and b"locked" in body, f"HTTP {code}")
    for pid in ("P02", "P05", "T001", "../P01", ""):
        code, body = call("POST", "/api/skip", {"id": pid})
        check(f"only the current puzzle can be skipped, not {pid!r}", code == 400, f"HTTP {code}")
    check("still zero after lock and skip probes", score()[0] == 0 and score()[2]["P01"] == "open")

    # 6. A lost puzzle stays lost: lose P01 on purpose, then try to replay it.
    from_p01 = js(call("GET", "/api/puzzle/P01")[1])
    for move in from_p01["legal_moves"]:
        r = js(call("POST", "/api/move", {"id": "P01", "move": move})[1])
        if r.get("status") == "failed":
            break
        if r.get("status") == "solved":
            break
    if score()[2]["P01"] == "failed":
        for pid in ("P01", "p01", " P01 ", "P01\n"):
            code, body = call("POST", "/api/move", {"id": pid, "move": from_p01["legal_moves"][0]})
            check(f"failed puzzle cannot be replayed as {pid!r}", code == 400)
            code, body = call("POST", "/api/skip", {"id": pid})
            check(f"failed puzzle cannot be skipped into anything else as {pid!r}", code == 400)
        check("failed puzzle is still failed", score()[2]["P01"] == "failed")
    else:
        check("P01 probe (first legal move happened to win)", True, score()[2]["P01"])

    # 7. Skipping counts as lost, unlocks only the next puzzle, and cannot be undone.
    cur = next(pid for pid, st in score()[2].items() if st == "open")
    before = score()[0]
    code, body = call("POST", "/api/skip", {"id": cur})
    check(f"skipping {cur} is accepted and counts as lost", code == 200 and score()[2][cur] == "failed" and score()[0] == before)
    code, body = call("POST", "/api/skip", {"id": cur})
    check(f"skipping {cur} twice is refused", code == 400 and score()[2][cur] == "failed")
    nxt = next(pid for pid, st in score()[2].items() if st == "open")
    later = list(score()[2])[list(score()[2]).index(nxt) + 1]
    check(f"after the skip only {nxt} is open to play, {later} stays locked", call("GET", f"/api/puzzle/{nxt}")[0] == 200 and call("GET", f"/api/puzzle/{later}")[0] == 404)

    # 8. Practice never touches the score, and practice ids do not alias scored ones.
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

    # 9. Winning the same puzzle many times at once counts once.
    cur = next(pid for pid, st in score()[2].items() if st == "open")
    p3 = js(call("GET", f"/api/puzzle/{cur}")[1])
    replies = []

    def fire(move):
        replies.append(js(call("POST", "/api/move", {"id": cur, "move": move})[1]))

    threads = [threading.Thread(target=fire, args=(m,)) for m in p3["legal_moves"] for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    accepted = [r for r in replies if r.get("ok")]
    check("only one of many simultaneous moves is accepted", len(accepted) == 1, f"{len(accepted)} accepted of {len(replies)}")
    solved, value, status = score()
    check("score equals puzzles actually won", abs(value - sum(s == "solved" for s in status.values()) / len(status)) < 1e-5 and solved <= 2, f"solved={solved} score={value}")

    # 10. Nothing above leaked a solution.
    listing = call("GET", "/api/puzzles")[1] + call("GET", "/api/puzzle/P05")[1]
    check("API replies carry no solver data", b"nodes" not in listing and b"book" not in listing and b"pv" not in listing)

    failed = results.count(False)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
