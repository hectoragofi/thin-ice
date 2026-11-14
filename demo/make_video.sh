#!/usr/bin/env bash
# Rebuilds the data, records the page (1:50 plus a short hold on the closing card) and prints the deck.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8 NODE_PATH="$(npm root -g)"
python demo/build_data.py
node demo/record.cjs video
start=$(cat demo/start.txt)
# trim the page-load lead-in; cap at 1:58 so the file can never break the 2-minute limit
ffmpeg -y -loglevel error -ss "$start" -i demo/raw.webm -t 117 -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart -an demo/thin-ice-demo.mp4
rm -f demo/raw.webm demo/start.txt
node demo/record.cjs deck
ffprobe -v error -show_entries format=duration,size -of default=nw=1 demo/thin-ice-demo.mp4
