"""Runs the post-training experiment on a Modal GPU instead of the laptop.

    uvx modal setup                                   # once: log in
    uvx modal run training/modal_train.py             # Qwen3-1.7B on an A100, about 30 minutes
    uvx modal run training/modal_train.py --model Qwen/Qwen3-0.6B --name qwen3-0.6b
    uvx modal volume get thinice-runs / data/modal-runs    # fetch the curves and adapters

It is the same training/train.py that runs locally; Modal only supplies the GPU. Training
progress and every in-environment evaluation are printed as the job runs.
"""
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
    .add_local_file(ROOT / "data" / "labels.jsonl", remote_path="/repo/data/labels.jsonl")
)
app = modal.App("thin-ice-train", image=image)
runs = modal.Volume.from_name("thinice-runs", create_if_missing=True)
weights = modal.Volume.from_name("thinice-hf-cache", create_if_missing=True)


@app.function(gpu="A100", timeout=5 * 60 * 60, volumes={"/runs": runs, "/root/.cache/huggingface": weights})
def train(model: str, name: str, examples: int, bs: int, accum: int, lr: float, rank: int, eval_at: str) -> str:
    import subprocess

    cmd = [
        "python", "-u", "/repo/training/train.py",
        "--model", model, "--labels", "/repo/data/labels.jsonl", "--out", f"/runs/{name}",
        "--examples", str(examples), "--bs", str(bs), "--accum", str(accum),
        "--lr", str(lr), "--rank", str(rank), "--eval-at", eval_at,
    ]  # fmt: skip
    subprocess.run(cmd, check=True, cwd="/repo")
    runs.commit()
    return Path(f"/runs/{name}/curve.json").read_text()


@app.local_entrypoint()
def main(
    model: str = "Qwen/Qwen3-1.7B",
    name: str = "",
    examples: int = 400_000,
    bs: int = 64,
    accum: int = 1,
    lr: float = 2e-4,
    rank: int = 64,
    eval_at: str = "0,1000,3000,10000,30000,100000,200000,400000",
):
    name = name or model.split("/")[-1].lower()
    curve = train.remote(model, name, examples, bs, accum, lr, rank, eval_at)
    out = ROOT / "results" / f"curve-{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(curve, encoding="utf-8", newline="\n")
    print(f"curve written to {out}")
