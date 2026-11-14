"""Verifier: reads the game server's signed receipt and writes the reward.

The receipt is the only input. It was written by the game server (a container the agent
cannot enter) and is signed with a key that never exists inside the agent's sandbox, so the
reward depends on nothing the agent can edit. Anything missing or invalid scores 0.
"""
import hashlib
import hmac
import json
from pathlib import Path

RECEIPT = Path("/receipt/receipt.json")
KEY = Path(__file__).resolve().parent / "receipt.key"
MANIFEST = Path(__file__).resolve().parent / "manifest.json"
OUT = Path("/logs/verifier")


def grade() -> tuple:
    receipt = json.loads(RECEIPT.read_text())
    card, sig = receipt["scorecard"], receipt["sig"]
    blob = json.dumps(card, sort_keys=True, separators=(",", ":")).encode()
    want = hmac.new(KEY.read_text().strip().encode(), blob, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, str(sig)):
        raise ValueError("receipt signature does not match")
    manifest = json.loads(MANIFEST.read_text())
    rows = card["puzzles"]
    expected = len(manifest["tiers"]) * manifest["per_tier"]
    if len(rows) != expected:
        raise ValueError(f"receipt lists {len(rows)} puzzles, expected {expected}")
    solved = sum(r["status"] == "solved" for r in rows)
    by_tier: dict = {}
    for r in rows:
        tier = by_tier.setdefault(str(r["win_in"]), {"solved": 0, "failed": 0, "open": 0})
        tier[r["status"]] += 1
    detail = {
        "reward": solved / expected,
        "solved": solved,
        "total": expected,
        "seed": card.get("seed"),
        "practice_started": card.get("practice_started"),
        "by_win_in": by_tier,
        "puzzles": rows,
    }
    return solved / expected, detail


def main() -> None:
    try:
        reward, detail = grade()
    except Exception as exc:  # fail closed: no valid receipt, no reward
        reward, detail = 0.0, {"reward": 0.0, "error": f"{type(exc).__name__}: {exc}"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "details.json").write_text(json.dumps(detail, indent=2))
    (OUT / "reward.txt").write_text(f"{reward:.4f}\n")
    print(json.dumps({k: v for k, v in detail.items() if k != "puzzles"}, indent=2))


if __name__ == "__main__":
    main()
