# Refresh and re-record

Two cuts come from the same page and data (`demo/index.html` + `demo/data.js`):
- **Short cut** (the submitted video, under 2:00): `demo/thin-ice-demo.mp4`, page `index.html?cut=short`, 1:55 plus a 1.5 s hold.
- **Long cut** (2:21 plus hold): `demo/thin-ice-demo-long.mp4`, page `index.html` with no parameter.

1. `python demo/build_data.py` refreshes every number (data.json, data.js, script.md, both cuts' captions) after the last runs land.
2. `bash demo/make_video.sh` re-records the short cut (headless Chromium via a global `npm i -g playwright`, plus ffmpeg) and reprints `demo/thin-ice-deck.pdf`; `bash demo/make_video.sh --long` re-records the long cut.
3. `python tools/replay_site.py` rebuilds `demo/replays.html` (every final run, move by move) from the same job files.
4. By hand instead: open `demo/index.html?cut=short` (or without `?cut=short` for the long cut) in Chrome, press F11, start Win+Alt+R (Xbox Game Bar) or OBS, press F5 so it plays from the start, stop after the closing card (1:55 short, 2:21 long).
