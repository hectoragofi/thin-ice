"""Runs the post-training experiment on a Modal GPU instead of the laptop.

    uvx modal setup                                   # once: log in
    uvx modal run training/modal_train.py             # Qwen3-1.7B on an A100, about 30 minutes
    uvx modal run training/modal_train.py --model Qwen/Qwen3-0.6B --name qwen3-0.6b
    uvx modal volume get thinice-runs / data/modal-runs    # fetch the curves and adapters

It is the same training/train.py that runs locally; Modal only supplies the GPU. Training
progress and every in-environment evaluation are printed as the job runs.
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
app = modal.App("thin-ice-train", image=image)
runs = modal.Volume.from_name("thinice-runs", create_if_missing=True)
weights = modal.Volume.from_name("thinice-hf-cache", create_if_missing=True)
data = modal.Volume.from_name("thinice-data", create_if_missing=True)  # labels from tools/modal_build.py


GPU = os.environ.get("THINICE_GPU", "A100-80GB")  # read on your machine when you call `modal run`
TIMEOUT_MIN = int(os.environ.get("THINICE_TIMEOUT_MIN", 24 * 60))  # likewise


@app.function(gpu=GPU, timeout=TIMEOUT_MIN * 60, volumes={"/runs": runs, "/root/.cache/huggingface": weights, "/data": data})
def train(model: str, name: str, examples: int, bs: int, accum: int, lr: float, rank: int, eval_at: str) -> str:
    import json
    import subprocess

    game = json.loads(Path(f"/repo/{PACKS}/manifest.json").read_text())["game"]
    cmd = [
        "python", "-u", "/repo/training/train.py",
        "--model", model, "--labels", f"/data/{game['w']}x{game['h']}/labels.jsonl", "--out", f"/runs/{name}",
        "--examples", str(examples), "--bs", str(bs), "--accum", str(accum),
        "--lr", str(lr), "--rank", str(rank), "--eval-at", eval_at,
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, cwd="/repo", stdout=subprocess.PIPE, text=True, bufsize=1)
    for line in proc.stdout:
        print(line, end="", flush=True)
        if line.startswith("[eval]"):  # curve.json was just rewritten: persist it in case of a timeout
            runs.commit()
    if proc.wait():
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    runs.commit()
    return Path(f"/runs/{name}/curve.json").read_text()


@app.local_entrypoint()
def main(
    model: str = "Qwen/Qwen3-1.7B",
    name: str = "",
    examples: int = 600_000,
    bs: int = 16,  # about 1 GB of GPU memory per example for the 1.7B model
    accum: int = 4,
    lr: float = 2e-4,
    rank: int = 64,
    eval_at: str = "0,1000,3000,10000,30000,100000,200000,400000,600000",
):
    name = name or model.split("/")[-1].lower()
    curve = train.remote(model, name, examples, bs, accum, lr, rank, eval_at)
    out = ROOT / "results" / f"curve-{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(curve, encoding="utf-8", newline="\n")
    print(f"curve written to {out}")
