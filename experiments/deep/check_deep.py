"""Checks the deep variant without Docker.

    python check_deep.py [seed ...]

1. Runs the repo's tools/selfcheck.py unchanged except that its task paths point at ./task.
2. Lists the puzzles each seed serves and checks that none shares a position (up to symmetry)
   with the practice pool, with the main task's 12 scored puzzles for the same seed, or with each other.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("THINICE_REPO", HERE.parent.parent)).resolve()
DEEP = HERE / "task"
seeds = sys.argv[1:] or ["1", "2", "3"]

src = (REPO / "tools" / "selfcheck.py").read_text(encoding="utf-8")
assert src.count('ROOT / "task"') == 3, "selfcheck.py changed; update this check"
src = src.replace('ROOT / "task"', "DEEP_TASK")
# The fake-clock test assumes P01-P02 are a win in 1 (60 s each, one book move solves P01).
# Here they are a win in 7: give them the same 60 s and play P01 out to the end.
for old, new in (
    ("clock=lambda n: 60 * n", "clock=lambda n: 60 * (n - 6)"),
    ('    run.get(" p01 ").move(book(p1))', '    while p1.status == "open":\n        run.get(" p01 ").move(book(p1))'),
):
    assert src.count(old) == 1, f"selfcheck.py changed near {old!r}"
    src = src.replace(old, new)
ns = {"__name__": "selfcheck", "__file__": str(REPO / "tools" / "selfcheck.py"), "DEEP_TASK": DEEP}
sys.argv = [sys.argv[0], *seeds]
exec(compile(src, "selfcheck.py", "exec"), ns)
ns["main"]()

from thinice.board import canonical  # noqa: E402  (path set up by selfcheck)
from thinice.session import load_pack, pick  # noqa: E402


def forms(p) -> set:
    out = set()
    for pos in p.nodes:
        b, r = pos.split("|")
        out.add(canonical(json.loads(b), json.loads(r)))
    return out


packs = DEEP / "environment" / "game-server" / "packs"
man = json.loads((packs / "manifest.json").read_text())
main_packs = REPO / "task" / "environment" / "game-server" / "packs"
main_man = json.loads((main_packs / "manifest.json").read_text())
scored, practice = load_pack(packs / "scored.jsonl"), load_pack(packs / "practice.jsonl")
main_scored = load_pack(main_packs / "scored.jsonl")
practice_forms = set().union(*(forms(p) for p in practice))
for seed in seeds:
    deep = pick(scored, seed, man["tiers"], man["per_tier"])
    main12 = pick(main_scored, seed, main_man["tiers"], main_man["per_tier"])
    main_forms = set().union(*(forms(p) for p in main12))
    seen: set = set()
    for i, p in enumerate(deep, 1):
        f = forms(p)
        assert not (f & practice_forms), f"seed {seed} P{i:02d} shares a position with the practice pool"
        assert not (f & main_forms), f"seed {seed} P{i:02d} shares a position with the main task's puzzles"
        assert not (f & seen), f"seed {seed} P{i:02d} shares a position with an earlier deep puzzle"
        assert p.index not in {q.index for q in main12}
        seen |= f
    print(f"seed {seed}: " + ", ".join(f"P{i:02d}=win in {p.need} (index {p.index}, cap {p.cap}, {len(p.nodes)} positions)" for i, p in enumerate(deep, 1)))
print("deep puzzles are disjoint from practice, from the main task's 12 and from each other")
