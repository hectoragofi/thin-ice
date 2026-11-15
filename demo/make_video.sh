#!/usr/bin/env bash
# Rebuilds the data, records the page and prints the deck.
#   bash demo/make_video.sh          # short cut (submitted, under 2:00): demo/thin-ice-demo.mp4
#   bash demo/make_video.sh --long   # long cut (2:21 plus hold):          demo/thin-ice-demo-long.mp4
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8 NODE_PATH="$(npm root -g)"
if [ "${1:-}" = "--long" ]; then cut=long; cap=145; out=demo/thin-ice-demo-long.mp4
else cut=short; cap=119; out=demo/thin-ice-demo.mp4; fi
python demo/build_data.py
node demo/record.cjs video "$cut"
start=$(cat demo/start.txt)
# trim the page-load lead-in; cap the length (short: 119 s, so the file stays under the form's 2-minute limit)
ffmpeg -y -loglevel error -ss "$start" -i demo/raw.webm -t "$cap" -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart -an "$out"
rm -f demo/raw.webm demo/start.txt
node demo/record.cjs deck
ffprobe -v error -show_entries format=duration,size -of default=nw=1 "$out"
