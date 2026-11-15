"""Builds the "deep" Thin Ice variant (win in 7, 8, 9) from the main task, without touching it.

    python experiments/deep/build_deep.py

Copies <repo>/task to ./task and changes only what differs: the manifest's tiers and run clock,
task.toml's agent timeout and name, and the facts in instruction.md. The puzzle packs and the
oracle's book are reused as they are: the main build's scored pool already holds 30 sharp,
mutually position-disjoint puzzles per tier up to win in 16, the main run only ever serves
win in 1-6 from it, and the build guarantees none of them shares a position with the practice pool.
"""
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent.parent).resolve()
SRC, DST = REPO / "task", HERE / "task"
WIN_IN = [7, 8, 9]
PER_TIER = 2

main_manifest = json.loads((SRC / "environment" / "game-server" / "packs" / "manifest.json").read_text())
clock = main_manifest["clock"]
main_clocks = main_manifest["per_tier"] * sum(clock["base_sec"] + clock["per_move_sec"] * n for n in main_manifest["win_in"])
margin = clock["run_sec"] - main_clocks  # 90 min run over 84 min of clocks: 6 min
deep_clocks = PER_TIER * sum(clock["base_sec"] + clock["per_move_sec"] * n for n in WIN_IN)
run_sec = deep_clocks + margin

if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns("__pycache__"))

manifest = dict(main_manifest)
manifest["tiers"] = [2 * n - 1 for n in WIN_IN]
manifest["win_in"] = WIN_IN
manifest["per_tier"] = PER_TIER
manifest["clock"] = {**clock, "run_sec": run_sec}
text = json.dumps(manifest, indent=2) + "\n"
for rel in ("environment/game-server/packs/manifest.json", "tests/manifest.json", "solution/manifest.json"):
    (DST / rel).write_text(text, encoding="utf-8", newline="\n")


def replace(rel: str, pairs: list) -> None:
    path = DST / rel
    body = path.read_text(encoding="utf-8")
    for old, new in pairs:
        assert body.count(old) == 1, f"{rel}: expected exactly one {old!r}"
        body = body.replace(old, new)
    path.write_text(body, encoding="utf-8", newline="\n")


n = PER_TIER * len(WIN_IN)
replace("task.toml", [
    (f"timeout_sec = {float(clock['run_sec'])}", f"timeout_sec = {float(run_sec)}"),
    ('name = "thin-ice/thin-ice"', 'name = "thin-ice/thin-ice-deep"'),
])
replace("instruction.md", [
    ("There are 12 puzzles, `P01` to `P12`.", f"There are {n} puzzles, `P01` to `P{n:02d}`."),
    ("divided by 12.**", f"divided by {n}.**"),
    ("`P01`-`P02` are a win in 1 move, `P11`-`P12` a win in 6.",
     f"`P01`-`P02` are a win in {WIN_IN[0]} moves, `P{n - 1:02d}`-`P{n:02d}` a win in {WIN_IN[-1]}."),
    (f"You have {clock['run_sec'] // 60} minutes in total", f"You have {run_sec // 60} minutes in total"),
])
print(f"built {DST}: win in {WIN_IN}, {n} puzzles, clocks {deep_clocks // 60} min + margin {margin // 60} min = run {run_sec // 60} min")
