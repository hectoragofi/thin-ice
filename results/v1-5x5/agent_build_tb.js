const { Worker, isMainThread, parentPort, workerData } = require('worker_threads');
const fs = require('fs');
const os = require('os');

function buildMetadata() {
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
      const sm = applySymMask(idToMask[i], s);
      const sid = maskToId[sm];
      if (sid < 0) throw new Error('Symmetry broke has3');
      symIdFlat[s * N + i] = sid;
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
        let found = -1;
        for (let inv = 0; inv < 8; inv++) {
          if (symIdFlat[inv * N + sid] === i) {
            found = inv;
            break;
          }
        }
        if (found < 0) throw new Error('Inverse sym not found');
        canonSym[sid] = found;
      }
    }
  }

  const numOrbits = orbitRepIdArr.length;
  const orbitRepId = new Int32Array(orbitRepIdArr);
  const canonOrbitBase = new Int32Array(N);
  for (let i = 0; i < N; i++) {
    if (symIdFlat[canonSym[i] * N + i] !== orbitRepId[canonOrbit[i]]) {
      throw new Error('Canon sym verification failed');
    }
    canonOrbitBase[i] = canonOrbit[i] * N;
  }

  // Precompute rays for each orbit representative!
  // Each ray entry: [len, b0, id0, b1, id1, b2, id2, b3, id3] -> 9 Int32s per ray
  const dirs = [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]];
  const orbRayOffset = new Int32Array(numOrbits + 1);
  const rayDataArr = [];

  for (let orb = 0; orb < numOrbits; orb++) {
    orbRayOffset[orb] = rayDataArr.length;
    const rep = idToMask[orbitRepId[orb]];
    let tmp = rep;
    while (tmp) {
      const sq = 31 - Math.clz32(tmp & -tmp);
      tmp &= tmp - 1;
      const sr = (sq / 5) | 0;
      const sc = sq % 5;
      const baseMask = rep ^ (1 << sq);
      for (const [dr, dc] of dirs) {
        const steps = [];
        let nr = sr + dr, nc = sc + dc;
        while (nr >= 0 && nr < 5 && nc >= 0 && nc < 5) {
          const nsq = nr * 5 + nc;
          const nbit = 1 << nsq;
          if (rep & nbit) break; // blocked by own stone
          steps.push([nbit, maskToId[baseMask | nbit]]);
          nr += dr;
          nc += dc;
        }
        if (steps.length > 0) {
          rayDataArr.push(steps.length);
          for (let k = 0; k < 4; k++) {
            if (k < steps.length) {
              rayDataArr.push(steps[k][0], steps[k][1]);
            } else {
              rayDataArr.push(0, 0);
            }
          }
        }
      }
    }
  }
  orbRayOffset[numOrbits] = rayDataArr.length;
  const rayData = new Int32Array(rayDataArr);

  return { N, numOrbits, idToMask, symIdFlat, canonSym, canonOrbitBase, orbitRepId, orbRayOffset, rayData };
}

if (isMainThread) {
  (async () => {
    const t0 = Date.now();
    const meta = buildMetadata();
    const { N, numOrbits } = meta;
    console.log(`Metadata built in ${Date.now() - t0}ms: N=${N}, numOrbits=${numOrbits}, TB entries=${numOrbits * N}`);

    const tbSab = new SharedArrayBuffer(numOrbits * N * 2); // Uint16Array
    const TB = new Uint16Array(tbSab);

    // Copy metadata into SharedArrayBuffers so workers start instantaneously
    function toShared(typedArr) {
      const sab = new SharedArrayBuffer(typedArr.byteLength);
      new typedArr.constructor(sab).set(typedArr);
      return sab;
    }

    const sharedMeta = {
      N,
      numOrbits,
      idToMaskSab: toShared(meta.idToMask),
      symIdFlatSab: toShared(meta.symIdFlat),
      canonSymSab: toShared(meta.canonSym),
      canonOrbitBaseSab: toShared(meta.canonOrbitBase),
      orbitRepIdSab: toShared(meta.orbitRepId),
      orbRayOffsetSab: toShared(meta.orbRayOffset),
      rayDataSab: toShared(meta.rayData),
      tbSab
    };

    const numWorkers = Math.min(os.cpus().length, 16);
    const workers = [];
    for (let w = 0; w < numWorkers; w++) {
      const orbStart = Math.floor((w * numOrbits) / numWorkers);
      const orbEnd = Math.floor(((w + 1) * numOrbits) / numWorkers);
      workers.push(new Worker(__filename, {
        workerData: { ...sharedMeta, orbStart, orbEnd }
      }));
    }

    function runPly(ply) {
      return Promise.all(workers.map(w => new Promise((resolve, reject) => {
        w.once('message', resolve);
        w.once('error', reject);
        w.postMessage({ ply });
      })));
    }

    // Ply 1: immediate 3-in-a-row wins (and mark overlapping rep & opp as 65535 so we skip them instantly!)
    for (let ply = 1; ply <= 30; ply++) {
      const tp = Date.now();
      const results = await runPly(ply);
      let totalChanged = 0;
      for (const marks of results) {
        totalChanged += marks.length;
        for (let i = 0; i < marks.length; i++) {
          TB[marks[i]] = ply;
        }
      }
      console.log(`Ply ${ply} (${ply % 2 === 1 ? 'WIN in ' + ((ply + 1) / 2) : 'LOSS in ' + (ply / 2)}): ${totalChanged} states (${Date.now() - tp}ms)`);
      if (totalChanged === 0) break;
    }

    for (const w of workers) w.terminate();

    fs.writeFileSync('/tmp/opencode/tb.bin', Buffer.from(tbSab));
    console.log(`Saved /tmp/opencode/tb.bin in total ${Date.now() - t0}ms`);
  })();
} else {
  const {
    N, idToMaskSab, symIdFlatSab, canonSymSab, canonOrbitBaseSab,
    orbitRepIdSab, orbRayOffsetSab, rayDataSab, tbSab, orbStart, orbEnd
  } = workerData;

  const idToMask = new Int32Array(idToMaskSab);
  const symIdFlat = new Int16Array(symIdFlatSab);
  const canonSym = new Uint8Array(canonSymSab);
  const canonOrbitBase = new Int32Array(canonOrbitBaseSab);
  const orbitRepId = new Int32Array(orbitRepIdSab);
  const orbRayOffset = new Int32Array(orbRayOffsetSab);
  const rayData = new Int32Array(rayDataSab);
  const TB = new Uint16Array(tbSab);

  // Pre-mark invalid (overlapping) entries in our slice with 65535 right away!
  for (let orb = orbStart; orb < orbEnd; orb++) {
    const rep = idToMask[orbitRepId[orb]];
    const rowBase = orb * N;
    for (let opp = 0; opp < N; opp++) {
      if ((rep & idToMask[opp]) !== 0) {
        TB[rowBase + opp] = 65535;
      }
    }
  }

  parentPort.on('message', ({ ply }) => {
    const found = [];
    if (ply === 1) {
      for (let orb = orbStart; orb < orbEnd; orb++) {
        const rowBase = orb * N;
        const rStart = orbRayOffset[orb];
        const rEnd = orbRayOffset[orb + 1];
        for (let opp = 0; opp < N; opp++) {
          const idx = rowBase + opp;
          if (TB[idx] !== 0) continue;
          const oppMask = idToMask[opp];
          let win1 = false;
          for (let r = rStart; r < rEnd; r += 9) {
            const b0 = rayData[r + 1];
            if ((oppMask & b0) !== 0) continue;
            const len = rayData[r];
            let destId;
            if (len === 1 || (oppMask & rayData[r + 3]) !== 0) destId = rayData[r + 2];
            else if (len === 2 || (oppMask & rayData[r + 5]) !== 0) destId = rayData[r + 4];
            else if (len === 3 || (oppMask & rayData[r + 7]) !== 0) destId = rayData[r + 6];
            else destId = rayData[r + 8];
            if (destId < 0) {
              win1 = true;
              break;
            }
          }
          if (win1) found.push(idx);
        }
      }
    } else if ((ply & 1) === 1) {
      // Odd ply >= 3: WIN if ANY child === ply - 1
      const target = ply - 1;
      for (let orb = orbStart; orb < orbEnd; orb++) {
        const rowBase = orb * N;
        const rStart = orbRayOffset[orb];
        const rEnd = orbRayOffset[orb + 1];
        for (let opp = 0; opp < N; opp++) {
          const idx = rowBase + opp;
          if (TB[idx] !== 0) continue;
          const oppMask = idToMask[opp];
          const oppOrbBase = canonOrbitBase[opp];
          const symBase = canonSym[opp] * N;
          let isWin = false;
          for (let r = rStart; r < rEnd; r += 9) {
            const b0 = rayData[r + 1];
            if ((oppMask & b0) !== 0) continue;
            const len = rayData[r];
            let destId;
            if (len === 1 || (oppMask & rayData[r + 3]) !== 0) destId = rayData[r + 2];
            else if (len === 2 || (oppMask & rayData[r + 5]) !== 0) destId = rayData[r + 4];
            else if (len === 3 || (oppMask & rayData[r + 7]) !== 0) destId = rayData[r + 6];
            else destId = rayData[r + 8];
            if (TB[oppOrbBase + symIdFlat[symBase + destId]] === target) {
              isWin = true;
              break;
            }
          }
          if (isWin) found.push(idx);
        }
      }
    } else {
      // Even ply >= 2: LOSS if ALL legal moves lead to an ODD value (1, 3, ..., ply - 1)
      // Note: 65535 is odd, wait!! 65535 IS ODD! Make sure child is NEVER overlapping!
      // Wait: child is (opp, destId), where destId = (rep ^ sq) | destSq, and destSq was checked !(oppMask & b_dest),
      // and rep & oppMask === 0, so destMask & oppMask === 0 ALWAYS!
      // STILL, let's use INVALID = 65534 (EVEN!) so even a bug could never mistake INVALID for WIN!
      for (let orb = orbStart; orb < orbEnd; orb++) {
        const rowBase = orb * N;
        const rStart = orbRayOffset[orb];
        const rEnd = orbRayOffset[orb + 1];
        for (let opp = 0; opp < N; opp++) {
          const idx = rowBase + opp;
          if (TB[idx] !== 0) continue;
          const oppMask = idToMask[opp];
          const oppOrbBase = canonOrbitBase[opp];
          const symBase = canonSym[opp] * N;
          let allWin = true;
          for (let r = rStart; r < rEnd; r += 9) {
            const b0 = rayData[r + 1];
            if ((oppMask & b0) !== 0) continue;
            const len = rayData[r];
            let destId;
            if (len === 1 || (oppMask & rayData[r + 3]) !== 0) destId = rayData[r + 2];
            else if (len === 2 || (oppMask & rayData[r + 5]) !== 0) destId = rayData[r + 4];
            else if (len === 3 || (oppMask & rayData[r + 7]) !== 0) destId = rayData[r + 6];
            else destId = rayData[r + 8];
            const cv = TB[oppOrbBase + symIdFlat[symBase + destId]];
            if ((cv & 1) === 0) {
              allWin = false;
              break;
            }
          }
          if (allWin) found.push(idx);
        }
      }
    }
    const out = new Int32Array(found);
    parentPort.postMessage(out, [out.buffer]);
  });
}
