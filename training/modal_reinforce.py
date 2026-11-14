"""Runs the reward-only experiment (training/reinforce.py) on a Modal GPU.

    uvx modal run --detach training/modal_reinforce.py --rounds 8 --random-first 200000 --per-round 60000
    uvx modal volume get thinice-runs rl-qwen3-0.6b/curve.json results/curve-rl-qwen3-0.6b-7x6.json

Same image and volumes as training/modal_train.py. The curve is written to the runs volume after
every round, so it can be fetched while the job runs or if the local client disconnects.
"""
import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
PACKS = "task/environment/game-server/packs"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "transformers", "peft", "accelerate")
    .add_local_dir(ROOT / "thinice", remote_path="/repo/thinice")
    .add_local_dir(ROOT / "training", remote_path="/repo/training")
    .add_local_dir(ROOT / PACKS, remote_path=f"/repo/{PACKS}")
)
app = modal.App("thin-ice-reinforce", image=image)
runs = modal.Volume.from_name("thinice-runs", create_if_missing=True)
weights = modal.Volume.from_name("thinice-hf-cache", create_if_missing=True)
data = modal.Volume.from_name("thinice-data", create_if_missing=True)

GPU = os.environ.get("THINICE_GPU", "A100-80GB")  # read on your machine when you call `modal run`


@app.function(gpu=GPU, timeout=4 * 60 * 60, volumes={"/runs": runs, "/root/.cache/huggingface": weights, "/data": data})
def reinforce(model: str, name: str, extra: list) -> str:
    import json
    import subprocess
    import threading

    game = json.loads(Path(f"/repo/{PACKS}/manifest.json").read_text())["game"]
    out = f"/runs/{name}"
    cmd = [
        "python", "-u", "/repo/training/reinforce.py",
        "--model", model, "--labels", f"/data/{game['w']}x{game['h']}/labels.jsonl", "--out", out, *extra,
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, cwd="/repo")
    stop = threading.Event()

    def commit_often() -> None:  # so the per-round curve reaches the volume while the job runs
        while not stop.wait(120):
            try:
                runs.commit()
            except Exception as exc:  # noqa: BLE001
                print(f"volume commit failed: {exc}", flush=True)

    threading.Thread(target=commit_often, daemon=True).start()
    code = proc.wait()
    stop.set()
    runs.commit()
    if code:
        raise RuntimeError(f"reinforce.py exited with {code}")
    return Path(f"{out}/curve.json").read_text()


@app.local_entrypoint()
def main(
    model: str = "Qwen/Qwen3-0.6B",
    name: str = "",
    reward: str = "progress",
    rounds: int = 8,
    random_first: int = 200_000,
    per_round: int = 60_000,
    explore: str = "0.6,0.4,0.3,0.2,0.2,0.1,0.1",
    act_bs: int = 384,
    bs: int = 32,
    accum: int = 2,
    lr: float = 2e-4,
    minutes: float = 0,
    eval_per_tier: int = 0,
):
    name = name or "rl-" + model.split("/")[-1].lower()
    extra = [
        "--reward", reward, "--rounds", str(rounds), "--random-first", str(random_first), "--per-round", str(per_round),
        "--explore", explore, "--act-bs", str(act_bs), "--bs", str(bs), "--accum", str(accum),
        "--lr", str(lr), "--minutes", str(minutes), "--eval-per-tier", str(eval_per_tier),
    ]  # fmt: skip
    curve = reinforce.remote(model, name, extra)
    out = ROOT / "results" / f"curve-{name}-7x6.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(curve, encoding="utf-8", newline="\n")
    print(f"curve written to {out}")
