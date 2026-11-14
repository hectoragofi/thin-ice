# Refresh and re-record

1. `python demo/build_data.py` refreshes every number (data.json, data.js, script.md) after the last runs land.
2. `bash demo/make_video.sh` re-records `demo/thin-ice-demo.mp4` (headless Chromium via a global `npm i -g playwright`, plus ffmpeg) and reprints `demo/thin-ice-deck.pdf`.
3. By hand instead: open `demo/index.html` in Chrome, press F11, start Win+Alt+R (Xbox Game Bar) or OBS, press F5 so it plays from the start, stop after the closing card (1:50).
