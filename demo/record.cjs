// Records the demo page and prints the deck, with a headless Chromium from Playwright.
//
//   NODE_PATH="$(npm root -g)" node demo/record.cjs shots    # one PNG per scene in demo/shots/ (to check)
//   NODE_PATH="$(npm root -g)" node demo/record.cjs deck     # demo/thin-ice-deck.pdf (11 slides, 16:9)
//   NODE_PATH="$(npm root -g)" node demo/record.cjs video    # demo/raw.webm + demo/start.txt (seconds to trim)
//
// Needs `npm i -g playwright` (or a local install) and its Chromium. ffmpeg turns raw.webm into the mp4.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const DEMO = __dirname;
const url = q => 'file:///' + path.join(DEMO, 'index.html').replace(/\\/g, '/') + q;
const DECK = ['title', 'mistake', 'gap', 'depth', 'horizon', 'effort', 'fair', 'exploit', 'learn', 'summary', 'repro'];
const ALL = ['title', 'question', 'game', 'mistake', 'gap', 'depth', 'horizon', 'effort', 'fair', 'exploit', 'learn', 'summary', 'repro'];
const VIEW = { width: 1920, height: 1080 };

async function stills(ids, dir) {
  fs.mkdirSync(dir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEW });
  const out = [];
  for (const id of ids) {
    await page.goto(url(`?still&scene=${id}`));
    await page.waitForTimeout(2600); // let the slide animations settle
    const f = path.join(dir, `${String(out.length + 1).padStart(2, '0')}-${id}.png`);
    await page.screenshot({ path: f });
    out.push(f);
  }
  await browser.close();
  return out;
}

(async () => {
  const mode = process.argv[2] || 'shots';
  if (mode === 'shots') {
    console.log((await stills(ALL, path.join(DEMO, 'shots'))).join('\n'));
  } else if (mode === 'deck') {
    const tmp = path.join(require('os').tmpdir(), 'thinice-deck');
    const pngs = await stills(DECK, tmp);
    const html = `<!doctype html><html><head><style>@page{size:1920px 1080px;margin:0}body{margin:0}
      img{display:block;width:1920px;height:1080px;page-break-after:always}</style></head><body>` +
      pngs.map(p => `<img src="file:///${p.replace(/\\/g, '/')}">`).join('') + '</body></html>';
    const hf = path.join(tmp, 'deck.html');
    fs.writeFileSync(hf, html);
    const browser = await chromium.launch();
    const page = await browser.newPage();
    await page.goto('file:///' + hf.replace(/\\/g, '/'));
    await page.waitForTimeout(500);
    await page.pdf({ path: path.join(DEMO, 'thin-ice-deck.pdf'), width: '1920px', height: '1080px', printBackground: true });
    await browser.close();
    console.log('wrote demo/thin-ice-deck.pdf');
  } else if (mode === 'video') {
    const browser = await chromium.launch();
    const ctx = await browser.newContext({ viewport: VIEW, recordVideo: { dir: path.join(DEMO, 'raw'), size: VIEW } });
    const t0 = Date.now();
    const page = await ctx.newPage();
    await page.goto(url('?rec'));
    const start = await page.evaluate(() => performance.timeOrigin + performance.now());
    await page.waitForFunction(() => window.__demo && window.__demo.done, null, { timeout: 240000, polling: 250 });
    await page.waitForTimeout(1500); // hold the closing card
    const video = page.video();
    await ctx.close();
    const raw = await video.path();
    fs.renameSync(raw, path.join(DEMO, 'raw.webm'));
    fs.rmSync(path.join(DEMO, 'raw'), { recursive: true, force: true });
    fs.writeFileSync(path.join(DEMO, 'start.txt'), String(Math.max(0, (start - t0) / 1000)));
    await browser.close();
    console.log('wrote demo/raw.webm; trim', (start - t0) / 1000, 's');
  }
})();
