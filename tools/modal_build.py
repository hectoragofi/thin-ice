"""Solves the game and builds the task's puzzle pools on a Modal CPU machine.

    uvx modal run tools/modal_build.py                 # 7x6 board, tiers up to a win in 16
    uvx modal run tools/modal_build.py --max-win 20

The 7x6 game has 16.5 billion positions and its table needs about 17 GB of memory, more than a
laptop likes to spare. This runs the same solver/ and tools/build_task.py on a 32-core machine,
keeps the table and the training labels on a Modal Volume, and brings the small outputs (puzzle
packs, book, manifest, evaluation pool) back into this repository.
"""
import io
import os
import tarfile
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ["task/environment/game-server/packs", "task/environment/game-server/thinice", "task/solution/book.json", "task/solution/manifest.json", "task/solution/thinice", "task/tests/manifest.json", "training/eval_pool.jsonl"]

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "build-essential")
    .run_commands("curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal")
    .env({"PATH": "/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "RUSTFLAGS": "-C target-cpu=x86-64-v3"})
    .add_local_dir(ROOT / "solver", remote_path="/repo/solver", copy=True, ignore=["target", "target-next"])
    .run_commands("cd /repo/solver && cargo build --release")
    .add_local_dir(ROOT / "thinice", remote_path="/repo/thinice")
    .add_local_dir(ROOT / "tools", remote_path="/repo/tools")
    .add_local_dir(ROOT / "task", remote_path="/repo/task")
)
app = modal.App("thin-ice-build", image=image)
data = modal.Volume.from_name("thinice-data", create_if_missing=True)


@app.function(cpu=32, memory=49152, timeout=6 * 60 * 60, volumes={"/data": data})
def build(w: int, h: int, max_win: int, seed: int, labels: int) -> bytes:
    import shutil
    import subprocess

    work = Path("/work")
    shutil.copytree("/repo", work, dirs_exist_ok=True)
    store, scratch = Path(f"/data/{w}x{h}"), Path(f"/tmp/{w}x{h}")
    store.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    if (store / "tb.bin").exists():  # solved on an earlier run: reuse the table
        shutil.copyfile(store / "tb.bin", scratch / "tb.bin")
    env = {**os.environ, "THINICE_W": str(w), "THINICE_H": str(h), "THINICE_DATA": str(scratch), "THINICE_SOLVER": str(work / "solver/target/release/thinice-solver")}
    cmd = ["python", "-u", "tools/build_task.py", "--seed", str(seed), "--max-win", str(max_win), "--labels", str(labels)]
    try:
        subprocess.run(cmd, check=True, cwd=work, env=env)
    finally:  # keep the solved table even if a later build step fails
        if (scratch / "tb.bin").exists() and not (store / "tb.bin").exists():
            shutil.copyfile(scratch / "tb.bin", store / "tb.bin")
            data.commit()
    if labels:
        shutil.copyfile(scratch / "labels.jsonl", store / "labels.jsonl")
    shutil.copyfile(work / "training/eval_pool.jsonl", store / "eval_pool.jsonl")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in OUTPUTS:
            tar.add(work / rel, arcname=rel)
    # Also kept on the volume, so a detached run survives the laptop going away:
    #   uvx modal volume get thinice-data 7x6/outputs.tgz . && tar -xzf outputs.tgz
    (store / "outputs.tgz").write_bytes(buf.getvalue())
    data.commit()
    return buf.getvalue()


@app.local_entrypoint()
def main(w: int = 7, h: int = 6, max_win: int = 16, seed: int = 20261114, labels: int = 20000):
    blob = build.remote(w, h, max_win, seed, labels)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        tar.extractall(ROOT)
    print(f"unpacked {len(blob) / 1e6:.1f} MB of task files into {ROOT}")
