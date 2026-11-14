//! Thin Ice solver: exhaustive retrograde analysis of a sliding-stone game.
//!
//! One byte per position, from the point of view of the side to move:
//!   0          draw (neither side can force a win)
//!   1..=127    side to move wins in that many plies (always odd)
//!   128..=254  side to move loses in (value - 128) plies (always even; 128 = already lost)
//!   255        illegal position
//!
//! Position index = (rank(blue) * C(n - sb, sr) + rank(red | blue)) * 2 + side_to_move,
//! where rank is the combinatorial number system (colex) rank and red is ranked among the
//! cells not taken by blue. Side to move: 0 = blue, 1 = red.

use rayon::prelude::*;
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufWriter, Read, Write};
use std::sync::atomic::{AtomicU64, AtomicU8, Ordering::Relaxed};

const ILLEGAL: u8 = 255;
const LOSS0: u8 = 128;
const DIRS8: [(i32, i32); 8] = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)];

struct Game {
    w: usize,
    h: usize,
    n: usize,
    sb: usize,
    sr: usize,
    k: usize,
    dirs: Vec<usize>,
    slide: bool,
    blocked: u64,
    rays: Vec<Vec<u8>>,
    lines: Vec<u64>,
    binom: Vec<[u64; 10]>,
    cb: u64,
    cr: u64,
    total: u64,
}

impl Game {
    #[allow(clippy::too_many_arguments)]
    fn new(w: usize, h: usize, sb: usize, sr: usize, k: usize, ndirs: usize, slide: bool, blocked: u64) -> Game {
        let n = w * h;
        assert!(n <= 63 && sb <= 8 && sr <= 8, "board or stone count too large");
        assert!(ndirs == 4 || ndirs == 8, "dirs must be 4 or 8");
        let mut binom = vec![[0u64; 10]; 64];
        for i in 0..64 {
            binom[i][0] = 1;
            for j in 1..10 {
                binom[i][j] = if i == 0 { 0 } else { binom[i - 1][j - 1] + binom[i - 1][j] };
            }
        }
        let mut rays = vec![Vec::new(); n * 8];
        for sq in 0..n {
            let (x, y) = ((sq % w) as i32, (sq / w) as i32);
            for (d, (dx, dy)) in DIRS8.iter().enumerate() {
                let (mut cx, mut cy) = (x + dx, y + dy);
                while cx >= 0 && cy >= 0 && (cx as usize) < w && (cy as usize) < h {
                    rays[sq * 8 + d].push((cy as usize * w + cx as usize) as u8);
                    cx += dx;
                    cy += dy;
                }
            }
        }
        let mut lines = Vec::new();
        for sq in 0..n {
            let (x, y) = ((sq % w) as i32, (sq / w) as i32);
            for (dx, dy) in [(1, 0), (0, 1), (1, 1), (1, -1)] {
                let mut m = 0u64;
                let mut ok = true;
                for i in 0..k as i32 {
                    let (cx, cy) = (x + dx * i, y + dy * i);
                    if cx < 0 || cy < 0 || cx as usize >= w || cy as usize >= h {
                        ok = false;
                        break;
                    }
                    m |= 1u64 << (cy as usize * w + cx as usize);
                }
                if ok && m & blocked == 0 {
                    lines.push(m);
                }
            }
        }
        let dirs: Vec<usize> = if ndirs == 8 { (0..8).collect() } else { vec![0, 2, 4, 6] };
        let cb = binom[n][sb];
        let cr = binom[n - sb][sr];
        Game { w, h, n, sb, sr, k, dirs, slide, blocked, rays, lines, binom, cb, cr, total: cb * cr * 2 }
    }

    #[inline]
    fn has_line(&self, mask: u64) -> bool {
        self.lines.iter().any(|&l| mask & l == l)
    }

    #[inline]
    fn rank_mask(&self, mut m: u64) -> u64 {
        let mut r = 0;
        let mut i = 1;
        while m != 0 {
            r += self.binom[m.trailing_zeros() as usize][i];
            i += 1;
            m &= m - 1;
        }
        r
    }

    #[inline]
    fn rank_rel(&self, blue: u64, mut red: u64) -> u64 {
        let mut r = 0;
        let mut i = 1;
        while red != 0 {
            let s = red.trailing_zeros();
            let rel = s - (blue & ((1u64 << s) - 1)).count_ones();
            r += self.binom[rel as usize][i];
            i += 1;
            red &= red - 1;
        }
        r
    }

    #[inline]
    fn index(&self, blue: u64, red: u64, stm: u64) -> u64 {
        (self.rank_mask(blue) * self.cr + self.rank_rel(blue, red)) * 2 + stm
    }

    fn unrank(&self, mut r: u64, k: usize) -> u64 {
        let mut m = 0u64;
        for i in (1..=k).rev() {
            let mut s = i - 1;
            while self.binom[s + 1][i] <= r {
                s += 1;
            }
            m |= 1u64 << s;
            r -= self.binom[s][i];
        }
        m
    }

    fn decode(&self, idx: u64) -> (u64, u64, u64) {
        let stm = idx & 1;
        let q = idx >> 1;
        let blue = self.unrank(q / self.cr, self.sb);
        let rel = self.unrank(q % self.cr, self.sr);
        let mut red = 0u64;
        let mut j = 0;
        for sq in 0..self.n {
            if blue >> sq & 1 == 0 {
                if rel >> j & 1 == 1 {
                    red |= 1u64 << sq;
                }
                j += 1;
            }
        }
        (blue, red, stm)
    }

    /// Calls f(blue, red, base_index) for every placement whose blue stones have the given rank.
    #[inline]
    fn for_each_red<F: FnMut(u64, u64, u64)>(&self, rank_b: u64, mut f: F) {
        let blue = self.unrank(rank_b, self.sb);
        let mut free = [0u8; 64];
        let mut nf = 0;
        for sq in 0..self.n {
            if blue >> sq & 1 == 0 {
                free[nf] = sq as u8;
                nf += 1;
            }
        }
        let lim = 1u64 << nf;
        let mut rel: u64 = (1u64 << self.sr) - 1;
        let mut idx = rank_b * self.cr * 2;
        while rel < lim {
            let mut red = 0u64;
            let mut m = rel;
            while m != 0 {
                red |= 1u64 << free[m.trailing_zeros() as usize];
                m &= m - 1;
            }
            f(blue, red, idx);
            idx += 2;
            let c = rel & rel.wrapping_neg();
            let r2 = rel + c;
            rel = (((r2 ^ rel) >> 2) / c) | r2;
        }
    }

    /// Legal moves (from, to) for the stones in `mine`; `occ` is every occupied or blocked cell.
    #[inline]
    fn gen_moves(&self, mine: u64, occ: u64, out: &mut [(u8, u8); 64]) -> usize {
        let mut cnt = 0;
        let mut m = mine;
        while m != 0 {
            let s = m.trailing_zeros() as usize;
            m &= m - 1;
            for &d in &self.dirs {
                let mut cur = s as u8;
                for &nx in &self.rays[s * 8 + d] {
                    if occ >> nx & 1 != 0 {
                        break;
                    }
                    cur = nx;
                    if !self.slide {
                        break;
                    }
                }
                if cur as usize != s {
                    out[cnt] = (s as u8, cur);
                    cnt += 1;
                }
            }
        }
        cnt
    }

    #[inline]
    fn child_index(&self, blue: u64, red: u64, stm: u64, f: u8, t: u8) -> u64 {
        if stm == 0 {
            self.index(blue ^ (1u64 << f) ^ (1u64 << t), red, 1)
        } else {
            self.index(blue, red ^ (1u64 << f) ^ (1u64 << t), 0)
        }
    }
}

fn solve(g: &Game) -> (Vec<u8>, Vec<u64>) {
    let table: Vec<AtomicU8> = (0..g.total).into_par_iter().map(|_| AtomicU8::new(0)).collect();
    (0..g.cb).into_par_iter().for_each(|rb| {
        let mut mv = [(0u8, 0u8); 64];
        g.for_each_red(rb, |blue, red, idx| {
            let (v0, v1);
            if (blue | red) & g.blocked != 0 {
                v0 = ILLEGAL;
                v1 = ILLEGAL;
            } else {
                let bl = g.has_line(blue);
                let rl = g.has_line(red);
                let occ = blue | red | g.blocked;
                v0 = if bl {
                    ILLEGAL
                } else if rl || g.gen_moves(blue, occ, &mut mv) == 0 {
                    LOSS0
                } else {
                    0
                };
                v1 = if rl {
                    ILLEGAL
                } else if bl || g.gen_moves(red, occ, &mut mv) == 0 {
                    LOSS0
                } else {
                    0
                };
            }
            table[idx as usize].store(v0, Relaxed);
            table[idx as usize + 1].store(v1, Relaxed);
        });
    });

    let mut per_depth: Vec<u64> = vec![0];
    let mut d: u8 = 1;
    loop {
        let changed = AtomicU64::new(0);
        (0..g.cb).into_par_iter().for_each(|rb| {
            let mut mv = [(0u8, 0u8); 64];
            let mut local = 0u64;
            g.for_each_red(rb, |blue, red, idx| {
                for stm in 0..2u64 {
                    let i = (idx + stm) as usize;
                    if table[i].load(Relaxed) != 0 {
                        continue;
                    }
                    let mine = if stm == 0 { blue } else { red };
                    let cnt = g.gen_moves(mine, blue | red | g.blocked, &mut mv);
                    if d & 1 == 1 {
                        let target = LOSS0 + (d - 1);
                        for &(f, t) in &mv[..cnt] {
                            let ci = g.child_index(blue, red, stm, f, t) as usize;
                            if table[ci].load(Relaxed) == target {
                                table[i].store(d, Relaxed);
                                local += 1;
                                break;
                            }
                        }
                    } else {
                        let mut all = cnt > 0;
                        for &(f, t) in &mv[..cnt] {
                            let cv = table[g.child_index(blue, red, stm, f, t) as usize].load(Relaxed);
                            if cv == 0 || cv >= LOSS0 {
                                all = false;
                                break;
                            }
                        }
                        if all {
                            table[i].store(LOSS0 + d, Relaxed);
                            local += 1;
                        }
                    }
                }
            });
            changed.fetch_add(local, Relaxed);
        });
        let c = changed.load(Relaxed);
        eprintln!("depth {:3}: {:>12} positions", d, c);
        if c == 0 {
            break;
        }
        per_depth.push(c);
        d += 1;
        assert!(d < 126, "depth overflow");
    }
    // AtomicU8 has the same layout as u8 and no thread is writing any more, so hand the table
    // back as plain bytes without copying it (it can be most of the machine's memory).
    let mut table = std::mem::ManuallyDrop::new(table);
    let bytes = unsafe { Vec::from_raw_parts(table.as_mut_ptr() as *mut u8, table.len(), table.capacity()) };
    (bytes, per_depth)
}

struct Tb<'a> {
    g: &'a Game,
    t: &'a [u8],
}

impl Tb<'_> {
    /// (from, to, child value) for every legal move; child value is from the opponent's view.
    fn moves(&self, blue: u64, red: u64, stm: u64) -> Vec<(u8, u8, u8)> {
        let mut mv = [(0u8, 0u8); 64];
        let mine = if stm == 0 { blue } else { red };
        let cnt = self.g.gen_moves(mine, blue | red | self.g.blocked, &mut mv);
        let mut out: Vec<(u8, u8, u8)> = mv[..cnt]
            .iter()
            .map(|&(f, t)| (f, t, self.t[self.g.child_index(blue, red, stm, f, t) as usize]))
            .collect();
        out.sort();
        out
    }
}

fn apply(blue: u64, red: u64, stm: u64, f: u8, t: u8) -> (u64, u64) {
    if stm == 0 {
        (blue ^ (1u64 << f) ^ (1u64 << t), red)
    } else {
        (blue, red ^ (1u64 << f) ^ (1u64 << t))
    }
}

fn splitmix(mut x: u64) -> u64 {
    x = x.wrapping_add(0x9E3779B97F4A7C15);
    x = (x ^ (x >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94D049BB133111EB);
    x ^ (x >> 31)
}

fn squares(mask: u64) -> String {
    let mut v = Vec::new();
    let mut m = mask;
    while m != 0 {
        v.push(m.trailing_zeros().to_string());
        m &= m - 1;
    }
    format!("[{}]", v.join(","))
}

/// Principal variation from a won position with blue to move: attacker plays the first fastest
/// win, defender the longest defence (ties broken by smallest move). Returns the moves and, for
/// every attacker node, (legal moves, winning moves, fastest-winning moves).
#[allow(clippy::type_complexity)]
fn principal_variation(tb: &Tb, mut blue: u64, mut red: u64) -> (Vec<(u8, u8)>, Vec<(usize, usize, usize)>) {
    let mut pv = Vec::new();
    let mut prof = Vec::new();
    let mut cur = tb.t[tb.g.index(blue, red, 0) as usize];
    loop {
        let ms = tb.moves(blue, red, 0);
        let wins = ms.iter().filter(|m| m.2 >= LOSS0 && m.2 != ILLEGAL).count();
        let target = LOSS0 + (cur - 1);
        let best = ms.iter().filter(|m| m.2 == target).count();
        prof.push((ms.len(), wins, best));
        let m = ms.iter().find(|m| m.2 == target).expect("won position without winning move");
        pv.push((m.0, m.1));
        let (b, r) = apply(blue, red, 0, m.0, m.1);
        blue = b;
        red = r;
        if cur == 1 {
            break;
        }
        let ds = tb.moves(blue, red, 1);
        let dm = ds.iter().find(|m| m.2 == cur - 2).expect("lost position without longest defence");
        pv.push((dm.0, dm.1));
        let (b, r) = apply(blue, red, 1, dm.0, dm.1);
        blue = b;
        red = r;
        cur -= 2;
    }
    (pv, prof)
}

fn args_map() -> (String, HashMap<String, String>) {
    let mut it = std::env::args().skip(1);
    let cmd = it.next().unwrap_or_default();
    let mut m = HashMap::new();
    for a in it {
        if let Some((k, v)) = a.split_once('=') {
            m.insert(k.to_string(), v.to_string());
        }
    }
    (cmd, m)
}

fn get<T: std::str::FromStr>(m: &HashMap<String, String>, k: &str, d: T) -> T {
    m.get(k).and_then(|v| v.parse().ok()).unwrap_or(d)
}

fn game_from(m: &HashMap<String, String>) -> Game {
    Game::new(
        get(m, "w", 5),
        get(m, "h", 5),
        get(m, "sb", 4),
        get(m, "sr", 4),
        get(m, "k", 3),
        get(m, "dirs", 8),
        get(m, "slide", 1) != 0,
        get(m, "blocked", 0u64),
    )
}

fn load(path: &str, g: &Game) -> Vec<u8> {
    let mut t = Vec::new();
    File::open(path).expect("open table").read_to_end(&mut t).expect("read table");
    assert_eq!(t.len() as u64, g.total, "table size does not match game parameters");
    t
}

fn histogram(t: &[u8]) -> [[u64; 256]; 2] {
    t.par_chunks(1 << 20)
        .map(|c| {
            // chunk length is even, so the offset parity inside a chunk is the side to move
            let mut h = [[0u64; 256]; 2];
            for (i, &v) in c.iter().enumerate() {
                h[i & 1][v as usize] += 1;
            }
            h
        })
        .reduce(
            || [[0u64; 256]; 2],
            |mut a, b| {
                for s in 0..2 {
                    for v in 0..256 {
                        a[s][v] += b[s][v];
                    }
                }
                a
            },
        )
}

fn print_stats(g: &Game, t: &[u8]) {
    let h = histogram(t);
    for (s, name) in ["blue", "red"].iter().enumerate() {
        let legal: u64 = (0..255).map(|v| h[s][v]).sum();
        let win: u64 = (1..128).map(|v| h[s][v]).sum();
        let loss: u64 = (128..255).map(|v| h[s][v]).sum();
        let maxw = (1..128).rev().find(|&v| h[s][v] > 0).unwrap_or(0);
        println!(
            "{} to move: legal={} win={:.4} draw={:.4} loss={:.4} (terminal loss={:.4}) max_win_depth={}",
            name,
            legal,
            win as f64 / legal as f64,
            h[s][0] as f64 / legal as f64,
            loss as f64 / legal as f64,
            h[s][128] as f64 / legal as f64,
            maxw
        );
        let parts: Vec<String> = (1..128).step_by(2).filter(|&v| h[s][v] > 0).map(|v| format!("{}:{}", v, h[s][v])).collect();
        println!("  win-in-n counts: {}", parts.join(" "));
    }
    println!("positions={} board={}x{} stones={}v{} line={} dirs={} slide={}", g.total, g.w, g.h, g.sb, g.sr, g.k, g.dirs.len(), g.slide);
}

fn main() {
    let (cmd, m) = args_map();
    let g = game_from(&m);
    match cmd.as_str() {
        "solve" => {
            let out: String = get(&m, "out", "tb.bin".to_string());
            let t0 = std::time::Instant::now();
            let (t, _) = solve(&g);
            eprintln!("solved {} positions in {:.1}s", g.total, t0.elapsed().as_secs_f64());
            File::create(&out).expect("create table").write_all(&t).expect("write table");
            print_stats(&g, &t);
        }
        "stats" => {
            let t = load(&get(&m, "tb", "tb.bin".to_string()), &g);
            print_stats(&g, &t);
        }
        "probe" => {
            // probe tb=.. blue=0,1,2,3 red=5,6,7,8 stm=0
            let t = load(&get(&m, "tb", "tb.bin".to_string()), &g);
            let parse = |k: &str| -> u64 { get(&m, k, String::new()).split(',').filter(|s| !s.is_empty()).fold(0u64, |a, s| a | 1u64 << s.parse::<u32>().unwrap()) };
            let (blue, red, stm) = (parse("blue"), parse("red"), get(&m, "stm", 0u64));
            let tb = Tb { g: &g, t: &t };
            let ms: Vec<String> = tb.moves(blue, red, stm).iter().map(|x| format!("[{},{},{}]", x.0, x.1, x.2)).collect();
            println!("{{\"index\":{},\"value\":{},\"moves\":[{}]}}", g.index(blue, red, stm), t[g.index(blue, red, stm) as usize], ms.join(","));
        }
        "sample" => {
            // Random legal positions with every move evaluated; used to cross-check other
            // implementations and to build training data. Blue to move only (stm=0).
            let t = load(&get(&m, "tb", "tb.bin".to_string()), &g);
            let tb = Tb { g: &g, t: &t };
            let count: u64 = get(&m, "count", 1000);
            let seed: u64 = get(&m, "seed", 1);
            let only: String = get(&m, "only", "any".to_string()); // any | win | decided
            let out: String = get(&m, "out", "sample.jsonl".to_string());
            let mut w = BufWriter::new(File::create(&out).expect("create out"));
            let mut written = 0u64;
            let mut i = 0u64;
            while written < count {
                i += 1;
                let idx = (splitmix(seed.wrapping_mul(0x1000003).wrapping_add(i)) % (g.total / 2)) * 2;
                let v = t[idx as usize];
                let keep = match only.as_str() {
                    "win" => (1..128).contains(&v),
                    "decided" => v != 0 && v != ILLEGAL && v != LOSS0,
                    _ => v != ILLEGAL && v != LOSS0,
                };
                if !keep {
                    continue;
                }
                let (blue, red, _) = g.decode(idx);
                let ms: Vec<String> = tb.moves(blue, red, 0).iter().map(|x| format!("[{},{},{}]", x.0, x.1, x.2)).collect();
                writeln!(w, "{{\"blue\":{},\"red\":{},\"value\":{},\"moves\":[{}]}}", squares(blue), squares(red), v, ms.join(",")).unwrap();
                written += 1;
            }
        }
        "labels" => {
            // Won positions (blue to move), the same number for every depth, with every move
            // judged. This is the practice mode's feedback at scale: training data.
            let t = load(&get(&m, "tb", "tb.bin".to_string()), &g);
            let tb = Tb { g: &g, t: &t };
            let per: u64 = get(&m, "per", 1000);
            let seed: u64 = get(&m, "seed", 1);
            let dmin: u8 = get(&m, "dmin", 1);
            let dmax: u8 = get(&m, "dmax", 125);
            let out: String = get(&m, "out", "labels.jsonl".to_string());
            let h = histogram(&t);
            let mut w = BufWriter::new(File::create(&out).expect("create out"));
            for depth in (dmin..=dmax).step_by(2) {
                let avail = h[0][depth as usize];
                if avail == 0 {
                    continue;
                }
                let want = per + per / 4 + 64;
                let thresh = if avail <= want { u64::MAX } else { (u64::MAX / avail) * want };
                let salt = seed.wrapping_mul(0x9E3779B1).wrapping_add(depth as u64);
                let mut cands: Vec<(u64, u64)> = (0..g.total / 2)
                    .into_par_iter()
                    .filter_map(|q| {
                        let idx = q * 2;
                        if t[idx as usize] != depth {
                            return None;
                        }
                        let hsh = splitmix(idx ^ salt);
                        if hsh > thresh {
                            return None;
                        }
                        Some((hsh, idx))
                    })
                    .collect();
                cands.sort();
                cands.truncate(per as usize);
                for &(_, idx) in &cands {
                    let (blue, red, _) = g.decode(idx);
                    let ms: Vec<String> = tb.moves(blue, red, 0).iter().map(|x| format!("[{},{},{}]", x.0, x.1, x.2)).collect();
                    writeln!(w, "{{\"index\":{},\"blue\":{},\"red\":{},\"depth\":{},\"moves\":[{}]}}", idx, squares(blue), squares(red), depth, ms.join(",")).unwrap();
                }
                eprintln!("depth {:3}: available {:>10} written {}", depth, avail, cands.len());
            }
        }
        "puzzles" => {
            // Won positions with blue to move, grouped by depth, kept only if sharp enough.
            let t = load(&get(&m, "tb", "tb.bin".to_string()), &g);
            let tb = Tb { g: &g, t: &t };
            let per: usize = get(&m, "per", 200);
            let seed: u64 = get(&m, "seed", 1);
            let rootmax: usize = get(&m, "rootmax", 1);
            let pvmax: usize = get(&m, "pvmax", 2);
            let dmin: u8 = get(&m, "dmin", 1);
            let dmax: u8 = get(&m, "dmax", 125);
            let out: String = get(&m, "out", "puzzles.jsonl".to_string());
            let h = histogram(&t);
            let mut w = BufWriter::new(File::create(&out).expect("create out"));
            for depth in (dmin..=dmax).step_by(2) {
                let avail = h[0][depth as usize];
                if avail == 0 {
                    continue;
                }
                // Hash-select about 400x the quota as candidates, then filter for sharpness.
                let want = (per as u64) * 400;
                let thresh = if avail <= want { u64::MAX } else { (u64::MAX / avail) * want };
                let salt = seed.wrapping_mul(0x9E3779B1).wrapping_add(depth as u64);
                let mut cands: Vec<(u64, u64)> = (0..g.total / 2)
                    .into_par_iter()
                    .filter_map(|q| {
                        let idx = q * 2;
                        if t[idx as usize] != depth {
                            return None;
                        }
                        let hsh = splitmix(idx ^ salt);
                        if hsh > thresh {
                            return None;
                        }
                        Some((hsh, idx))
                    })
                    .collect();
                cands.sort();
                let mut kept = 0;
                for &(_, idx) in &cands {
                    if kept >= per {
                        break;
                    }
                    let (blue, red, _) = g.decode(idx);
                    let (pv, prof) = principal_variation(&tb, blue, red);
                    if prof[0].1 > rootmax || prof.iter().any(|p| p.1 > pvmax) {
                        continue;
                    }
                    let root = tb.moves(blue, red, 0);
                    let draws = root.iter().filter(|x| x.2 == 0).count();
                    let losing = root.iter().filter(|x| (1..128).contains(&x.2)).count();
                    let pvs: Vec<String> = pv.iter().map(|x| format!("[{},{}]", x.0, x.1)).collect();
                    let profs: Vec<String> = prof.iter().map(|p| format!("[{},{},{}]", p.0, p.1, p.2)).collect();
                    writeln!(
                        w,
                        "{{\"index\":{},\"blue\":{},\"red\":{},\"depth\":{},\"legal\":{},\"draw_moves\":{},\"losing_moves\":{},\"pv\":[{}],\"profile\":[{}]}}",
                        idx,
                        squares(blue),
                        squares(red),
                        depth,
                        root.len(),
                        draws,
                        losing,
                        pvs.join(","),
                        profs.join(",")
                    )
                    .unwrap();
                    kept += 1;
                }
                eprintln!("depth {:3}: available {:>10} candidates {:>7} kept {}", depth, avail, cands.len(), kept);
            }
        }
        "pack" => {
            // For each puzzle, every position the attacker can reach while it keeps a forced win
            // (within the move cap), with all of its moves judged and the defender's reply fixed.
            // A game server needs nothing else: no rules engine and no tablebase.
            let t = load(&get(&m, "tb", "tb.bin".to_string()), &g);
            let tb = Tb { g: &g, t: &t };
            let slack: u32 = get(&m, "slack", 2);
            let inp: String = get(&m, "in", "puzzles.jsonl".to_string());
            let out: String = get(&m, "out", "pack.jsonl".to_string());
            let mut text = String::new();
            File::open(&inp).expect("open puzzles").read_to_string(&mut text).expect("read puzzles");
            let mut w = BufWriter::new(File::create(&out).expect("create out"));
            let (mut total_nodes, mut max_nodes, mut count) = (0usize, 0usize, 0usize);
            for line in text.lines().filter(|l| !l.trim().is_empty()) {
                let field = |k: &str| -> u64 {
                    let pat = format!("\"{}\":", k);
                    let s = &line[line.find(&pat).expect("field") + pat.len()..];
                    s[..s.find(|c: char| !c.is_ascii_digit()).unwrap_or(s.len())].parse().expect("number")
                };
                let (idx, depth) = (field("index"), field("depth") as u32);
                let (blue0, red0, _) = g.decode(idx);
                let cap = (depth + 1) / 2 + slack;
                let mut seen: HashMap<(u64, u64), u32> = HashMap::new();
                let mut queue = std::collections::VecDeque::new();
                queue.push_back((blue0, red0, 0u32));
                let mut nodes: Vec<String> = Vec::new();
                while let Some((b, r, used)) = queue.pop_front() {
                    if seen.contains_key(&(b, r)) {
                        continue; // breadth-first, so the first visit used the fewest moves
                    }
                    seen.insert((b, r), used);
                    let mut entries: Vec<String> = Vec::new();
                    for (f, to, cv) in tb.moves(b, r, 0) {
                        if cv > LOSS0 && cv != ILLEGAL {
                            let (b2, r2) = apply(b, r, 0, f, to);
                            let want = cv - LOSS0 - 1;
                            let ds = tb.moves(b2, r2, 1);
                            let dm = ds.iter().find(|x| x.2 == want).expect("longest defence");
                            entries.push(format!("[{},{},{},{},{}]", f, to, cv, dm.0, dm.1));
                            if used + 1 < cap {
                                let (b3, r3) = apply(b2, r2, 1, dm.0, dm.1);
                                queue.push_back((b3, r3, used + 1));
                            }
                        } else {
                            entries.push(format!("[{},{},{}]", f, to, cv));
                        }
                    }
                    nodes.push(format!("\"{}|{}\":[{}]", squares(b), squares(r), entries.join(",")));
                }
                total_nodes += nodes.len();
                max_nodes = max_nodes.max(nodes.len());
                count += 1;
                writeln!(
                    w,
                    "{{\"index\":{},\"blue\":{},\"red\":{},\"depth\":{},\"cap\":{},\"nodes\":{{{}}}}}",
                    idx,
                    squares(blue0),
                    squares(red0),
                    depth,
                    cap,
                    nodes.join(",")
                )
                .unwrap();
            }
            eprintln!("packed {} puzzles: {} nodes total, {} max, slack {}", count, total_nodes, max_nodes, slack);
        }
        _ => {
            eprintln!("usage: thinice-solver <solve|stats|probe|sample|labels|puzzles|pack> key=value ...");
            eprintln!("game keys: w h sb sr k dirs slide blocked");
            std::process::exit(2);
        }
    }
}
