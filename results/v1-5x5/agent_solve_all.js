const fs = require('fs');
const http = require('http');

function buildLookup() {
  const lines3 = [];
  for (let r = 0; r < 5; r++)
    for (let c = 0; c < 3; c++)
      lines3.push((1 << (r * 5 + c)) | (1 << (r * 5 + c + 1)) | (1 << (r * 5 + c + 2)));
  for (let c = 0; c < 5; c++)
    for (let r = 0; r < 3; r++)
      lines3.push((1 << (r * 5 + c)) | (1 << ((r + 1) * 5 + c)) | (1 << ((r + 2) * 5 + c)));
  for (let r = 0; r < 3; r++)
    for (let c = 0; c < 3; c++) {
      lines3.push((1 << (r * 5 + c)) | (1 << ((r + 1) * 5 + c + 1)) | (1 << ((r + 2) * 5 + c + 2)));
      lines3.push((1 << (r * 5 + c + 2)) | (1 << ((r + 1) * 5 + c + 1)) | (1 << ((r + 2) * 5 + c)));
    }

  function has3(m) {
    for (let i = 0; i < lines3.length; i++)
      if ((m & lines3[i]) === lines3[i]) return true;
    return false;
  }

  const symCell = Array.from({ length: 8 }, () => new Int32Array(25));
  for (let r = 0; r < 5; r++) {
    for (let c = 0; c < 5; c++) {
      const idx = r * 5 + c;
      const coords = [
        [r, c], [c, 4 - r], [4 - r, 4 - c], [4 - c, r],
        [r, 4 - c], [4 - r, c], [c, r], [4 - c, 4 - r]
      ];
      for (let s = 0; s < 8; s++) {
        symCell[s][idx] = coords[s][0] * 5 + coords[s][1];
      }
    }
  }

  function applySymMask(m, s) {
    let out = 0;
    const map = symCell[s];
    while (m) {
      const b = 31 - Math.clz32(m & -m);
      out |= (1 << map[b]);
      m &= m - 1;
    }
    return out;
  }

  const maskToId = new Int16Array(1 << 25).fill(-1);
  const idToMaskArr = [];
  for (let a = 0; a < 22; a++)
    for (let b = a + 1; b < 23; b++)
      for (let c = b + 1; c < 24; c++)
        for (let d = c + 1; d < 25; d++) {
          const m = (1 << a) | (1 << b) | (1 << c) | (1 << d);
          if (!has3(m)) {
            maskToId[m] = idToMaskArr.length;
            idToMaskArr.push(m);
          }
        }

  const N = idToMaskArr.length;
  const idToMask = new Int32Array(idToMaskArr);

  const symIdFlat = new Int16Array(8 * N);
  for (let s = 0; s < 8; s++) {
    for (let i = 0; i < N; i++) {
      symIdFlat[s * N + i] = maskToId[applySymMask(idToMask[i], s)];
    }
  }

  const canonOrbit = new Int16Array(N).fill(-1);
  const canonSym = new Uint8Array(N);
  const orbitRepIdArr = [];

  for (let i = 0; i < N; i++) {
    if (canonOrbit[i] !== -1) continue;
    const orb = orbitRepIdArr.length;
    orbitRepIdArr.push(i);
    for (let s = 0; s < 8; s++) {
      const sid = symIdFlat[s * N + i];
      if (canonOrbit[sid] === -1) {
        canonOrbit[sid] = orb;
        for (let inv = 0; inv < 8; inv++) {
          if (symIdFlat[inv * N + sid] === i) {
            canonSym[sid] = inv;
            break;
          }
        }
      }
    }
  }

  const buf = fs.readFileSync('/tmp/opencode/tb.bin');
  const TB = new Uint16Array(buf.buffer, buf.byteOffset, buf.byteLength / 2);

  function queryState(myMask, oppMask) {
    const myId = maskToId[myMask];
    const oppId = maskToId[oppMask];
    if (myId < 0 || oppId < 0) throw new Error('State already has 3 in a row');
    const orb = canonOrbit[myId];
    const s = canonSym[myId];
    return TB[orb * N + symIdFlat[s * N + oppId]];
  }

  function cellToSq(cell) {
    return (parseInt(cell[1], 10) - 1) * 5 + (cell.charCodeAt(0) - 97);
  }
  function sqToCell(sq) {
    return String.fromCharCode(97 + (sq % 5)) + String(((sq / 5) | 0) + 1);
  }
  function cellsToMask(cells) {
    let m = 0;
    for (const c of cells) m |= (1 << cellToSq(c));
    return m;
  }

  const dirs = [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]];
  function getMoves(myMask, oppMask) {
    const occ = myMask | oppMask;
    const moves = [];
    let tmp = myMask;
    while (tmp) {
      const sq = 31 - Math.clz32(tmp & -tmp);
      tmp &= tmp - 1;
      const sr = (sq / 5) | 0, sc = sq % 5;
      for (const [dr, dc] of dirs) {
        let nr = sr + dr, nc = sc + dc;
        let lastSq = -1;
        while (nr >= 0 && nr < 5 && nc >= 0 && nc < 5) {
          const nsq = nr * 5 + nc;
          if (occ & (1 << nsq)) break;
          lastSq = nsq;
          nr += dr;
          nc += dc;
        }
        if (lastSq !== -1) {
          const newMyMask = (myMask ^ (1 << sq)) | (1 << lastSq);
          const notation = `${sqToCell(sq)}-${sqToCell(lastSq)}`;
          let winInMoves = Infinity;
          if (has3(newMyMask)) {
            winInMoves = 1;
          } else {
            const cv = queryState(oppMask, newMyMask);
            if (cv > 0 && cv < 65534 && (cv & 1) === 0) {
              winInMoves = (cv / 2) + 1;
            }
          }
          moves.push({ notation, newMyMask, winInMoves });
        }
      }
    }
    return moves;
  }

  return { cellsToMask, getMoves };
}

function apiReq(method, path, body = null) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req = http.request({
      hostname: 'game',
      port: 8000,
      path,
      method,
      headers: data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {}
    }, res => {
      let chunks = '';
      res.on('data', d => chunks += d);
      res.on('end', () => resolve(JSON.parse(chunks)));
    });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

(async () => {
  const { cellsToMask, getMoves } = buildLookup();
  const list = await apiReq('GET', '/api/puzzles');

  for (const item of list.puzzles) {
    let p = await apiReq('GET', `/api/puzzle/${item.id}`);
    if (p.status !== 'open') {
      console.log(`${item.id} already ${p.status}`);
      continue;
    }
    const line = [];
    while (p.status === 'open') {
      const bm = cellsToMask(p.blue);
      const rm = cellsToMask(p.red);
      const moves = getMoves(bm, rm);
      moves.sort((a, b) => a.winInMoves - b.winInMoves);
      const best = moves[0];
      if (!Number.isFinite(best.winInMoves)) {
        throw new Error(`No winning move found for ${item.id}`);
      }
      if (!p.legal_moves.includes(best.notation)) {
        throw new Error(`Chosen move ${best.notation} not in legal_moves for ${item.id}`);
      }
      const res = await apiReq('POST', '/api/move', { id: item.id, move: best.notation });
      if (res.ok === false) {
        throw new Error(`API error on ${item.id}: ${JSON.stringify(res)}`);
      }
      line.push(res.reply ? `${best.notation} (${res.reply})` : best.notation);
      p = res.puzzle;
    }
    console.log(`${item.id} [win_in=${p.win_in}]: ${p.status} in ${p.moves_used}/${p.moves_allowed} moves | ${line.join(' -> ')}`);
    if (p.status !== 'solved') {
      throw new Error(`STOPPING: ${item.id} ended with status=${p.status}`);
    }
  }

  const final = await apiReq('GET', '/api/puzzles');
  console.log(`\nFINAL SCORE: ${final.solved} / ${final.total} = ${final.score}`);
})();
