"""Original grainy collage art for the Thin Ice site: paper, cracked ice, horizons, a ruler, an engraved board."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.spatial import cKDTree
import sys, os

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
os.makedirs(OUT, exist_ok=True)
INK = (23, 25, 28); SAGE = (188, 211, 204); CORN = (107, 155, 209); MUSTARD = (232, 185, 49); PAPER = (241, 236, 226)
EMBER = (217, 96, 59); GREENP = (214, 226, 210)


def rng(s): return np.random.default_rng(s)


def up(a, w, h):
    return np.asarray(Image.fromarray(a.astype(np.float32), 'F').resize((w, h), Image.BICUBIC))


def fbm(w, h, seed, base=4, oct=6, gain=0.55):
    r, out, amp, tot = rng(seed), np.zeros((h, w), np.float32), 1.0, 0
    for o in range(oct):
        n = base * 2 ** o
        out += amp * up(r.random((max(2, int(n * h / max(w, h))) + 1, n + 1)), w, h); tot += amp; amp *= gain
    out /= tot
    return (out - out.min()) / (out.max() - out.min() + 1e-6)


def grain(img, amt=0.09, seed=1, chroma=0.25):
    a = np.asarray(img).astype(np.float32) / 255
    r = rng(seed)
    n = r.normal(0, amt, a.shape[:2])[..., None]
    c = r.normal(0, amt * chroma, a.shape)
    a = np.clip(a + n + c, 0, 1)
    return Image.fromarray((a * 255).astype(np.uint8))


def solid(w, h, col, seed=0, mottle=0.06):
    f = fbm(w, h, seed, base=3, oct=5)
    a = np.ones((h, w, 3), np.float32) * np.array(col, np.float32) / 255
    a *= (1 - mottle / 2 + mottle * f)[..., None]
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def paper(w, h, col, seed=0, speck=0.0006):
    im = np.asarray(solid(w, h, col, seed, 0.08)).astype(np.float32)
    r = rng(seed + 9)
    m = r.random((h, w)) < speck
    im[m] *= r.uniform(0.35, 0.7, (m.sum(), 1))
    # faint fibres
    fib = up(r.random((h // 3 + 1, 8)), w, h)
    im *= (0.97 + 0.03 * fib)[..., None]
    return Image.fromarray(np.clip(im, 0, 255).astype(np.uint8))


def cracks(w, h, seed, n=60, warp=0.04, width=2.2):
    """distance-to-edge of a warped Voronoi tiling: small near cracks."""
    r = rng(seed)
    pts = r.random((n, 2)) * [w, h]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    s = max(w, h)
    wx = (fbm(w, h, seed + 1, 3, 5) - 0.5) * warp * s; wy = (fbm(w, h, seed + 2, 3, 5) - 0.5) * warp * s
    q = np.stack([(xx + wx).ravel(), (yy + wy).ravel()], 1)
    d, i = cKDTree(pts).query(q, k=2)
    edge = (d[:, 1] - d[:, 0]).reshape(h, w)
    cell = i[:, 0].reshape(h, w)
    return edge, cell


def ice_photo(w, h, seed=3, dens=1.0):
    """black-and-white photo of cracked lake ice, harsh contrast, heavy grain"""
    r = rng(seed)
    e1, cell = cracks(w, h, seed, n=int(w * h / 40000 * dens) + int(3 + 4 * dens), warp=0.16)
    e2, _ = cracks(w, h, seed + 7, n=int(w * h / 6000 * dens) + 10, warp=0.1)
    base = fbm(w, h, seed + 3, 2, 8, 0.62)
    shade = r.random(cell.max() + 1)[cell] * 0.14
    lum = 0.12 + 0.75 * base + shade
    frost = fbm(w, h, seed + 5, 10, 5, 0.55)
    lum += 0.35 * np.clip((frost - 0.58) * 4, 0, 1)
    lum -= 0.7 * np.exp(-e1 / 1.6)                      # big dark cracks
    lum += 0.25 * np.exp(-(e1 - 4.0) ** 2 / 5)           # bright rims beside them
    mask = np.clip((fbm(w, h, seed + 8, 3, 4) - 0.5) * 5, 0, 1)
    lum -= 0.3 * np.exp(-e2 / 1.0) * mask                # hairlines, only in places
    yy, xx = np.mgrid[0:h, 0:w]
    vig = 1 - 0.45 * (((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) * 2.2)
    lum = np.clip(lum * vig, 0, 1)
    lum = np.clip((lum - 0.12) * 1.45, 0, 1) ** 1.1
    im = Image.fromarray((np.dstack([lum, lum, lum * 1.02]) * 255).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    return grain(im, 0.06, seed, 0.03)


def gradient(w, h, stops, seed=0, band=0.012):
    """vertical gradient through (pos, rgb) stops, with banding and grain"""
    y = np.linspace(0, 1, h)
    ps = [p for p, _ in stops]
    cols = np.array([c for _, c in stops], np.float32) / 255
    g = np.stack([np.interp(y, ps, cols[:, k]) for k in range(3)], 1)
    a = np.repeat(g[:, None, :], w, 1)
    r = rng(seed)
    a += r.normal(0, band, (h, 1, 1))  # scanner banding
    a *= (0.97 + 0.06 * fbm(w, h, seed, 2, 4))[..., None]
    return grain(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)), 0.045, seed, 0.12)


def painted_sky(w, h, seed=11):
    """old oil-painting clouds: ochre and grey, with craquelure"""
    f = fbm(w, h, seed, 3, 7, 0.62)
    g = fbm(w, h, seed + 1, 2, 4)
    lo = np.array([62, 58, 44], np.float32) / 255; mid = np.array([128, 118, 92], np.float32) / 255; hi = np.array([222, 198, 160], np.float32) / 255
    t = np.clip((f - 0.35) * 2.2 + (g - 0.5) * 0.6, 0, 1)[..., None]
    a = np.where(t < 0.5, lo + (mid - lo) * (t * 2), mid + (hi - mid) * ((t - 0.5) * 2))
    strokes = up(rng(seed).random((h // 2 + 1, 6)), w, h)
    a *= (0.94 + 0.08 * strokes)[..., None]
    e, _ = cracks(w, h, seed + 4, n=int(w * h / 900), warp=0.02)
    a *= (1 - 0.12 * np.exp(-e / 0.8))[..., None]
    return grain(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)), 0.05, seed, 0.2)


def ruler(w, h, seed=5):
    """a printed slide-rule card: red and black ticks on pale green, slightly soft"""
    S = 2
    im = paper(w * S, h * S, (226, 233, 216), seed, 0.0002)
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype('/usr/share/fonts/opentype/inter/Inter-Medium.otf', int(h * S * 0.075))
    except OSError:
        font = ImageFont.load_default()
    red = (214, 52, 40)
    rows = [(0.10, red, 0.15, '0.1'), (0.33, red, 0.11, '0.8'), (0.52, red, 0.09, None), (0.70, INK, 0.14, None), (0.90, INK, 0.11, '1.4')]
    W, H = w * S, h * S
    im.paste(Image.new('RGB', (W, int(H * 0.08)), (196, 222, 196)), (0, int(H * 0.60)))
    for y0, col, L, lab in rows:
        y = y0 * H
        step = W / 34
        for i in range(36):
            x = i * step + (seed % 3) * 7
            ln = L * H * (1.0 if i % 10 == 0 else 0.6 if i % 5 == 0 else 0.38)
            d.line([(x, y), (x, y + ln)], fill=col, width=int(2.2 * S))
        if lab:
            d.text((W * 0.42, y - H * 0.095), lab, fill=col, font=font)
    im = im.filter(ImageFilter.GaussianBlur(0.9)).resize((w, h), Image.LANCZOS)
    return grain(im, 0.05, seed, 0.2)


def engraving(w, h, seed=8):
    """the game board as an old engraved plate, split across white dotted paper and mustard paper"""
    S = 2; W, H = w * S, h * S
    left = paper(W // 2, H, (246, 243, 234), seed, 0.0003)
    dd = ImageDraw.Draw(left)
    g = int(W / 34)
    for yy in range(g // 2, H, g):
        for xx in range(g // 2, W // 2, g):
            dd.ellipse([xx - 1.5, yy - 1.5, xx + 1.5, yy + 1.5], fill=(120, 130, 190))
    right = paper(W - W // 2, H, (240, 198, 92), seed + 1, 0.0005)
    bg = Image.new('RGB', (W, H)); bg.paste(left, (0, 0)); bg.paste(right, (W // 2, 0))
    ink = Image.new('L', (W, H), 0); d = ImageDraw.Draw(ink)
    cols, rows = 7, 6
    cs = min(W * 0.86 / cols, H * 0.62 / rows)
    ox, oy = (W - cs * cols) / 2, H * 0.30
    lw = int(3 * S)
    for c in range(cols + 1):
        d.line([(ox + c * cs, oy), (ox + c * cs, oy + rows * cs)], fill=255, width=lw)
    for r_ in range(rows + 1):
        d.line([(ox, oy + r_ * cs), (ox + cols * cs, oy + r_ * cs)], fill=255, width=lw)
    d.rectangle([ox - 10 * S, oy - 10 * S, ox + cols * cs + 10 * S, oy + rows * cs + 10 * S], outline=255, width=int(5 * S))
    stones = [(2, 4, 'b'), (4, 4, 'b'), (0, 1, 'b'), (2, 0, 'b'), (4, 3, 'r'), (2, 2, 'r'), (3, 2, 'r'), (6, 0, 'r')]
    for (cx, cy, k) in stones:
        x, y = ox + (cx + 0.5) * cs, oy + (rows - cy - 0.5) * cs
        rr = cs * 0.34
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=255, width=int(3 * S))
        if k == 'b':   # cross-hatched
            for t in np.arange(-rr, rr, 5 * S):
                hh = np.sqrt(max(0, rr * rr - t * t))
                d.line([(x + t, y - hh), (x + t, y + hh)], fill=255, width=int(1.4 * S))
                d.line([(x - hh, y + t), (x + hh, y + t)], fill=255, width=int(1.4 * S))
        else:          # solid
            d.ellipse([x - rr * 0.8, y - rr * 0.8, x + rr * 0.8, y + rr * 0.8], fill=255)
    # radiating compass-like lines above the board: possible moves
    cx, cy = ox + 2.5 * cs, oy + (rows - 0.5) * cs
    for a in np.linspace(-np.pi, 0, 17):
        d.line([(cx, cy), (cx + np.cos(a) * cs * 3.2, cy + np.sin(a) * cs * 3.2)], fill=255, width=int(1.2 * S))
    try:
        f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf', int(cs * 0.36))
    except OSError:
        f = ImageFont.load_default()
    for i, ch in enumerate('abcdefg'):
        d.text((ox + (i + 0.38) * cs, oy + rows * cs + 16 * S), ch, fill=255, font=f)
    d.text((ox, H * 0.08), 'PL. VII', fill=255, font=f)
    # ink bleed: blur, noise, threshold
    a = np.asarray(ink.filter(ImageFilter.GaussianBlur(1.6 * S))).astype(np.float32) / 255
    a = a + rng(seed).normal(0, 0.22, a.shape) * a
    a = np.clip((a - 0.28) * 3.2, 0, 1)
    a *= 0.8 + 0.2 * fbm(W, H, seed, 6, 4)
    out = np.asarray(bg).astype(np.float32) * (1 - 0.9 * a[..., None]) + np.array(INK) * 0.9 * a[..., None] * 0.15
    # one red mark: the move that lost
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    dm = ImageDraw.Draw(im)
    x, y = ox + 6.5 * cs, oy + 1.5 * cs
    dm.ellipse([x - 7 * S, y - 7 * S, x + 7 * S, y + 7 * S], fill=(214, 52, 40))
    im = im.resize((w, h), Image.LANCZOS)
    return grain(im, 0.05, seed, 0.2)


def crop(im, w, h, fx=0.5, fy=0.5):
    W, H = im.size
    s = max(w / W, h / H)
    im = im.resize((int(W * s + 1), int(H * s + 1)), Image.LANCZOS)
    W, H = im.size
    x, y = int((W - w) * fx), int((H - h) * fy)
    return im.crop((x, y, x + w, y + h))


def mosaic(w, h, seed=21):
    """flat sage and cornflower blocks interleaved with crops of the ice photo and a painted sky"""
    ice = ice_photo(w, h, seed)
    sky = painted_sky(w, h, seed + 2)
    canvas = Image.new('RGB', (w, h))
    gx = [0, 0.22, 0.5, 0.64, 1.0]; gy = [0, 0.11, 0.33, 0.45, 0.72, 0.9, 1.0]
    r = rng(seed)
    src = [ice, sky, ice, sky]
    flats = [SAGE, CORN, SAGE]
    for j in range(len(gy) - 1):
        for i in range(len(gx) - 1):
            x0, x1, y0, y1 = int(gx[i] * w), int(gx[i + 1] * w), int(gy[j] * h), int(gy[j + 1] * h)
            k = r.random()
            if k < 0.42:
                tile = solid(x1 - x0, y1 - y0, flats[int(r.integers(0, 3))], int(r.integers(0, 999)), 0.03)
            else:
                tile = src[int(r.integers(0, 4))].crop((x0, y0, x1, y1))
            canvas.paste(tile, (x0, y0))
    return grain(canvas, 0.035, seed, 0.2)


def triptych(w, h, seed=31):
    """paper and sand | a sunset horizon | cracked ice on black: one wide strip"""
    a, b = int(w * 0.34), int(w * 0.66)
    out = Image.new('RGB', (w, h))
    left = paper(a, h, MUSTARD, seed, 0.001)
    sand = np.asarray(paper(a, h, (205, 186, 150), seed + 1)).astype(np.float32)
    rip = (0.42 + 0.06 * fbm(a, 1, seed, 4, 4)[0]) * h
    yy = np.arange(h)[:, None]
    stripes = fbm(a, h, seed + 3, 3, 6)
    stripes = np.sin((yy / h * 22 + stripes * 7)) > 0.72
    sand[stripes] *= 0.25
    L = np.asarray(left).copy(); m = yy > rip[None, :]
    L[m] = sand[m]
    out.paste(Image.fromarray(L.astype(np.uint8)), (0, 0))
    hz = gradient(b - a, h, [(0, (110, 150, 205)), (0.28, (150, 140, 175)), (0.4, (226, 130, 90)), (0.44, (234, 92, 40)), (0.47, (60, 32, 30)), (1, (28, 20, 22))], seed)
    out.paste(hz, (a, 0))
    ice = ice_photo(w - b, h, seed + 4)
    blk = solid(w - b, h, (16, 16, 16), seed, 0.04)
    yy = np.arange(h)[:, None]; xx = np.arange(w - b)[None, :]
    arc = h * 0.42 + ((xx / (w - b)) - 0.2) ** 2 * h * 0.35
    mk = np.repeat((yy > arc)[..., None], 3, 2)
    R = np.where(mk, np.asarray(ice), np.asarray(blk))
    out.paste(Image.fromarray(R.astype(np.uint8)), (b, 0))
    d = ImageDraw.Draw(out)
    d.line([(a, 0), (a, h)], fill=(240, 236, 226), width=3); d.line([(b, 0), (b, h)], fill=(240, 236, 226), width=3)
    return grain(out, 0.03, seed, 0.1)


def framed_sky(w, h, seed=41):
    """the high-altitude horizon gradient with a framed square of ice set into it"""
    sky = gradient(w, h, [(0, (26, 30, 42)), (0.45, (70, 105, 150)), (0.72, (110, 175, 245)), (0.86, (215, 232, 250)), (1, (248, 246, 250))], seed)
    fw, fh = int(h * 0.62), int(h * 0.7)
    x, y = int(w * 0.62), int(h * 0.15)
    inner = ice_photo(fw, fh, seed + 1)
    d = ImageDraw.Draw(sky)
    d.rectangle([x - 6, y - 6, x + fw + 5, y + fh + 5], fill=(240, 236, 226))
    sky.paste(inner, (x, y))
    return grain(sky, 0.03, seed, 0.2)


def ruler_over_ice(w, h, seed=51):
    base = ice_photo(w, h, seed)
    rw, rh = int(w * 0.36), int(h * 0.66)
    base.paste(ruler(rw, rh, seed), (0, int(h * 0.15)))
    sp = paper(int(w * 0.48), h, (233, 222, 200), seed + 2, 0.001)
    base.paste(sp, (int(w * 0.52), 0))
    d = ImageDraw.Draw(base); d.line([(int(w * 0.52), 0), (int(w * 0.52), h)], fill=(250, 248, 240), width=4)
    blk = ice_photo(int(w * 0.32), int(h * 0.62), seed + 3)
    g = np.asarray(blk).astype(np.float32).mean(2, keepdims=True) / 255
    dark, light = np.array([18, 70, 48], np.float32), np.array([120, 200, 150], np.float32)
    green = dark + (light - dark) * g
    base.paste(Image.fromarray(np.clip(green, 0, 255).astype(np.uint8)), (int(w * 0.64), int(h * 0.15)))
    return grain(base, 0.04, seed, 0.2)


def save(im, name, q=78):
    p = os.path.join(OUT, name + '.webp'); im.save(p, 'WEBP', quality=q, method=6)
    print(name, im.size, os.path.getsize(p) // 1024, 'KB')



MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'


def font(px, path=MONO):
    try:
        return ImageFont.truetype(path, int(px))
    except OSError:
        return ImageFont.load_default()


def duotone(im, dark, light):
    g = np.asarray(im).astype(np.float32).mean(2, keepdims=True) / 255
    d, l = np.array(dark, np.float32), np.array(light, np.float32)
    return Image.fromarray(np.clip(d + (l - d) * g, 0, 255).astype(np.uint8))


def core(w, h, seed=61):
    """an ice core laid on paper: nine layers, one per move of look-ahead, darker with depth; the crack turns red at layer four"""
    out = paper(w, h, (236, 230, 216), seed, 0.0008)
    d = ImageDraw.Draw(out)
    cx0, cx1 = int(w * 0.30), int(w * 0.80)
    top, bot = int(h * 0.06), int(h * 0.94)
    n = 9; lh = (bot - top) / n
    f = font(lh * 0.28)
    for i in range(n):
        y0, y1 = int(top + i * lh), int(top + (i + 1) * lh)
        t = i / (n - 1)
        ice = ice_photo(cx1 - cx0, y1 - y0 - 3, seed + i, 0.6 + 1.6 * t)
        light = (238 - 120 * t, 242 - 100 * t, 240 - 60 * t)
        dark = (60 - 40 * t, 82 - 55 * t, 100 - 50 * t)
        out.paste(duotone(ice, dark, light), (cx0, y0))
        d.line([(cx0 - int(w * 0.06), y0), (cx0 - 8, y0)], fill=INK, width=2)
        for k in range(1, 5):
            yy = y0 + k * lh / 5
            d.line([(cx0 - int(w * 0.03), yy), (cx0 - 8, yy)], fill=INK, width=1)
        d.text((int(w * 0.08), y0 + lh * 0.30), str(i + 1), fill=EMBER if i == 3 else INK, font=f)
    # one crack down the core, ink until layer four, then red and branching
    r = rng(seed); x = (cx0 + cx1) / 2; y = top; pts = [(x, y)]
    while y < bot:
        y += lh / 6; x += r.normal(0, (cx1 - cx0) * 0.05); x = min(max(x, cx0 + 10), cx1 - 10); pts.append((x, y))
    k4 = top + 3 * lh
    a = [p for p in pts if p[1] <= k4 + lh * 0.5]; b = [p for p in pts if p[1] >= k4 + lh * 0.3]
    d.line(a, fill=INK, width=3)
    d.line(b, fill=EMBER, width=5)
    for p in b[::3]:
        q = (p[0] + r.normal(0, 60), p[1] + r.uniform(20, 60))
        d.line([p, q], fill=EMBER, width=2)
    d.ellipse([a[-1][0] - 11, a[-1][1] - 11, a[-1][0] + 11, a[-1][1] + 11], fill=EMBER)
    d.text((cx1 + 18, top), 'CORE TI-07', fill=INK, font=font(lh * 0.16))
    d.text((cx1 + 18, top + lh * 0.25), 'depth = moves', fill=(85, 88, 92), font=font(lh * 0.14))
    return grain(out, 0.045, seed, 0.15)


def tiles(w, h, seed=71):
    """twelve puzzles as twelve squares of ice, pinned to card; the lost ones carry a red dot"""
    out = paper(w, h, (226, 232, 226), seed, 0.0008)
    d = ImageDraw.Draw(out)
    cols, rows, m, g = 3, 4, w * 0.09, w * 0.035
    tw = (w - 2 * m - (cols - 1) * g) / cols; th = (h - 2 * m - (rows - 1) * g * 1.9) / rows
    lost = {6, 8, 10, 11}
    f = font(th * 0.11)
    tints = [((30, 50, 70), (225, 235, 238)), ((25, 60, 45), (200, 228, 210)), ((20, 22, 26), (235, 235, 230))]
    for i in range(12):
        c, rr = i % cols, i // cols
        x0, y0 = int(m + c * (tw + g)), int(m + rr * (th + g * 1.9))
        dens = 0.4 + 0.25 * (i // 2)
        im = duotone(ice_photo(int(tw), int(th), seed + i * 3, dens), *tints[(i * 7) % 3])
        out.paste(im, (x0, y0))
        d.text((x0, y0 + th + 6), 'P%02d' % (i + 1), fill=INK, font=f)
        d.text((x0 + tw * 0.55, y0 + th + 6), 'win in %d' % (i // 2 + 1), fill=(110, 106, 98), font=font(th * 0.09))
        if i in lost:
            d.ellipse([x0 + tw - 30, y0 + 10, x0 + tw - 10, y0 + 30], fill=EMBER)
    return grain(out, 0.04, seed, 0.15)


def sheet(w, h, seed=81):
    """the signed score sheet: a typed card over dark ice, stamped in red"""
    base = duotone(ice_photo(w, h, seed, 1.2), (14, 18, 24), (120, 135, 150))
    W, H = int(w * 0.66), int(h * 0.74)
    card = paper(W, H, (243, 238, 226), seed + 1, 0.001)
    d = ImageDraw.Draw(card)
    f, fs = font(H * 0.038), font(H * 0.03)
    d.text((W * 0.08, H * 0.07), 'THIN ICE  -  SCORE SHEET', fill=INK, font=f)
    d.line([(W * 0.08, H * 0.13), (W * 0.92, H * 0.13)], fill=INK, width=2)
    res = ['solved', 'solved', 'solved', 'solved', 'solved', 'lost', 'lost', 'solved', 'lost', 'solved', 'lost', 'lost']
    for i, rs in enumerate(res):
        y = H * (0.17 + i * 0.052)
        d.text((W * 0.08, y), 'P%02d   win in %d   %s' % (i + 1, i // 2 + 1, rs), fill=EMBER if rs == 'lost' else INK, font=fs)
    d.line([(W * 0.08, H * 0.81), (W * 0.92, H * 0.81)], fill=INK, width=1)
    d.text((W * 0.08, H * 0.84), 'score  7 / 12', fill=INK, font=f)
    d.text((W * 0.08, H * 0.91), 'hmac  9f3a 61c0 e2b7 04d9', fill=(110, 106, 98), font=fs)
    # the stamp
    st = Image.new('L', (W, H), 0); sd = ImageDraw.Draw(st)
    cx, cy, R = W * 0.74, H * 0.80, W * 0.15
    sd.ellipse([cx - R, cy - R, cx + R, cy + R], outline=255, width=7)
    sd.ellipse([cx - R * 0.8, cy - R * 0.8, cx + R * 0.8, cy + R * 0.8], outline=255, width=3)
    sd.text((cx - R * 0.62, cy - R * 0.2), 'SIGNED', fill=255, font=font(R * 0.34))
    st = st.rotate(14, center=(cx, cy))
    a = np.asarray(st.filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32) / 255
    a *= np.clip(0.55 + 0.6 * fbm(W, H, seed, 12, 3), 0, 1)
    cd = np.asarray(card).astype(np.float32)
    cd = cd * (1 - a[..., None] * 0.85) + np.array([200, 60, 40]) * a[..., None] * 0.85
    card = Image.fromarray(np.clip(cd, 0, 255).astype(np.uint8)).convert('RGBA').rotate(-4, expand=True, resample=Image.BICUBIC)
    shadow = Image.new('RGBA', card.size, (0, 0, 0, 0)); shadow.putalpha(card.getchannel('A').point(lambda v: 90 if v else 0))
    base = base.convert('RGBA')
    px, py = int((w - card.size[0]) / 2), int((h - card.size[1]) / 2)
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)), (px + 10, py + 16))
    base.alpha_composite(card, (px, py))
    return grain(base.convert('RGB'), 0.04, seed, 0.15)


def depth(w, h, seed=91):
    """nine slices of ice, one per move to the win, cracking further and darkening; the break is marked at four"""
    out = paper(w, h, (238, 233, 220), seed, 0.0006)
    d = ImageDraw.Draw(out)
    n, gap, lab = 9, 8, int(h * 0.16)
    sw = (w - gap * (n + 1)) / n
    f = font(lab * 0.5)
    for i in range(n):
        x0 = int(gap + i * (sw + gap)); t = i / (n - 1)
        im = ice_photo(int(sw), h - lab - 2 * gap, seed + i, 0.4 + 2.6 * t)
        light = (236 - 90 * t, 240 - 80 * t, 238 - 40 * t); dark = (70 - 55 * t, 92 - 70 * t, 108 - 80 * t)
        out.paste(duotone(im, dark, light), (x0, gap))
        d.text((x0 + 4, h - lab + lab * 0.18), str(i + 1), fill=EMBER if i == 3 else INK, font=f)
    x = gap + 3 * (sw + gap) + sw / 2
    d.ellipse([x - 12, h * 0.42 - 12, x + 12, h * 0.42 + 12], fill=EMBER)
    return grain(out, 0.04, seed, 0.15)


def lake(w, h, seed=101):
    """a frozen lake to the horizon: how far ahead you can see"""
    hz = int(h * 0.42)
    sky = gradient(w, hz, [(0, (196, 210, 214)), (0.7, (226, 230, 226)), (1, (241, 236, 226))], seed, 0.004)
    src = duotone(ice_photo(w * 2, h * 2, seed, 1.4), (34, 58, 80), (226, 234, 236))
    sa = np.asarray(src); H2 = h - hz
    rows = []
    for j in range(H2):
        t = (j + 1) / H2                       # 0 at horizon, 1 at the viewer
        sy = int((1 - (1 - t) ** 0.35) * (sa.shape[0] - 1))
        scale = 0.25 + 0.75 * t
        xs = (np.arange(w) - w / 2) / scale * 0.5 + sa.shape[1] / 2
        rows.append(sa[sy, np.clip(xs.astype(int), 0, sa.shape[1] - 1)])
    ground = np.stack(rows)
    fog = np.linspace(0.65, 0, H2)[:, None, None]
    ground = ground * (1 - fog) + np.array([226, 230, 226]) * fog
    out = Image.new('RGB', (w, h)); out.paste(sky, (0, 0)); out.paste(Image.fromarray(ground.astype(np.uint8)), (0, hz))
    d = ImageDraw.Draw(out)
    for k, (fx, col) in enumerate([(0.30, (47, 93, 147)), (0.36, (217, 96, 59)), (0.45, (47, 93, 147))]):
        y = hz + H2 * (0.18 + 0.05 * k); r_ = 4 + 5 * (0.18 + 0.05 * k)
        d.ellipse([w * fx - r_, y - r_, w * fx + r_, y + r_], fill=col)
    return grain(out, 0.045, seed, 0.15)


if __name__ == '__main__':
    save(core(820, 980), 'core')
    save(tiles(900, 1000), 'tiles')
    save(sheet(900, 1000), 'sheet')
    save(depth(1500, 420), 'depth')
    save(lake(1100, 560), 'lake')
