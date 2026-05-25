"""
rendering.py
============
Modul rendering visual: tile jalan, bangunan, pohon, dan minimap.

Tile jalan mengikuti style dari referensi "assets ref.py":
  - STRAIGHT: rectangle sederhana (sidewalk + road + dashline)
  - CURVE/T-JUNCTION/CROSS: Bézier kuadratik band

ZOOM-AWARE RENDERING:
  Semua tile draw function menerima parameter `sz` (ukuran piksel).
  TileCache menggunakan lazy caching per ukuran display yang
  dikuantisasi → Bézier selalu tajam di semua zoom level.

Kelas:
  TileCache  - Lazy zoom cache: render tile di resolusi display aktual
  EnvCache   - Pre-render environment (pohon, bangunan, trotoar)

Fungsi publik:
  build_minimap(grid, size)
"""

import math
import random

import pygame

from config import (
    T, RW, SW, MG,
    DASH_ON, DASH_OFF,
    C_GRASS, C_SW, C_ROAD, C_DASH, C_BTN_BD,
    BLDG_STYLES
)
from grid import (
    STRAIGHT, CURVE, DIAGONAL, TJUNCTION, CROSS, EMPTY,
    TILE_PORTS, get_ports
)
from mapgen import (ENV_NONE, ENV_SW, ENV_TREE, ENV_B0, ENV_B1, ENV_B2,
                     ENV_RUMAH, ENV_RUKO, ENV_MASJID, ENV_SPBU, ENV_TAMAN)


# ══════════════════════════════════════════════════════════════
# BÉZIER & POLYLINE HELPERS
# ══════════════════════════════════════════════════════════════
def _bquad(p0, p1, p2, s=24):
    """Bézier Kuadratik: B(t) = (1-t)²·P0 + 2(1-t)t·P1 + t²·P2"""
    pts = []
    for i in range(s + 1):
        t = i / s
        u = 1 - t
        pts.append((u*u*p0[0] + 2*u*t*p1[0] + t*t*p2[0],
                     u*u*p0[1] + 2*u*t*p1[1] + t*t*p2[1]))
    return pts


def _offcurve(pts, off, side="left"):
    """Offset polyline secara perpendikular sejauh 'off' piksel."""
    r = []
    n = len(pts)
    for i in range(n):
        if i == 0:
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == n - 1:
            dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        else:
            dx, dy = pts[i+1][0] - pts[i-1][0], pts[i+1][1] - pts[i-1][1]
        l = math.hypot(dx, dy) or 1
        nx, ny = -dy / l, dx / l
        if side == "right":
            nx, ny = -nx, -ny
        r.append((pts[i][0] + nx * off, pts[i][1] + ny * off))
    return r


def _fband(s, cp, hw, col):
    """Gambar polygon band di sekitar kurva cp dengan half-width hw."""
    if len(cp) < 2:
        return
    L = _offcurve(cp, hw, "left")
    R = _offcurve(cp, hw, "right")
    p = L + list(reversed(R))
    if len(p) >= 3:
        pygame.draw.polygon(s, col, [(int(a), int(b)) for a, b in p])


def _dashline(s, x1, y1, x2, y2, vert=True, da=DASH_ON, ga=DASH_OFF):
    """Garis putus-putus LURUS (dari referensi)."""
    ln = (y2 - y1) if vert else (x2 - x1)
    pos = 0
    dr = True
    while pos < ln:
        sg = min(da if dr else ga, ln - pos)
        if dr:
            if vert:
                pygame.draw.line(s, C_DASH, (x1, y1 + pos), (x1, y1 + pos + sg), 1)
            else:
                pygame.draw.line(s, C_DASH, (x1 + pos, y1), (x1 + pos + sg, y1), 1)
        pos += sg
        dr = not dr


def _bdash(s, pts, col, da=DASH_ON, ga=DASH_OFF):
    """Garis putus-putus mengikuti kurva Bézier (dari referensi)."""
    acc = 0
    dr = True
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        sg = math.hypot(bx - ax, by - ay)
        if sg < .001:
            continue
        dx, dy = (bx - ax) / sg, (by - ay) / sg
        t = 0
        while t < sg:
            p = da if dr else ga
            rm = min(p - acc, sg - t)
            if dr:
                sx2, sy2 = ax + dx * t, ay + dy * t
                ex2, ey2 = ax + dx * (t + rm), ay + dy * (t + rm)
                pygame.draw.line(s, col, (int(sx2), int(sy2)), (int(ex2), int(ey2)), 1)
            t += rm
            acc += rm
            if acc >= p:
                acc = 0
                dr = not dr


def _pmids(x, y, sz):
    """Midpoint keempat sisi tile berukuran sz piksel."""
    return {
        0: (x + sz // 2, y),
        1: (x + sz,      y + sz // 2),
        2: (x + sz // 2, y + sz),
        3: (x,           y + sz // 2),
    }


# ══════════════════════════════════════════════════════════════
# TILE DRAW — zoom-aware (semua terima parameter sz)
# ══════════════════════════════════════════════════════════════
def _dsw(s, x, y, tt, rot, sz):
    """Gambar trotoar pada sisi tile yang tidak punya port. Ukuran tile = sz."""
    sf    = sz / T
    mg    = max(1, int(MG * sf))
    ports = get_ports(tt, rot)
    closed = {0, 1, 2, 3} - ports
    for d in closed:
        if d == 0:
            pygame.draw.rect(s, C_SW, (x, y, sz, mg))
        elif d == 2:
            pygame.draw.rect(s, C_SW, (x, y + sz - mg, sz, mg))
        elif d == 3:
            pygame.draw.rect(s, C_SW, (x, y, mg, sz))
        elif d == 1:
            pygame.draw.rect(s, C_SW, (x + sz - mg, y, mg, sz))


def _dstr(s, x, y, rot, sz, lod=2):
    """STRAIGHT — Rectangle sederhana, semua proporsi di-scale ke sz."""
    sf = sz / T
    rw = max(2, int(RW * sf))
    mg = (sz - rw) // 2
    da = max(2, int(DASH_ON * sf))
    ga = max(2, int(DASH_OFF * sf))
    pad = max(1, int(4 * sf))

    if rot == 0:
        pygame.draw.rect(s, C_SW, (x, y, mg, sz))
        pygame.draw.rect(s, C_SW, (x + sz - mg, y, mg, sz))
        pygame.draw.rect(s, C_ROAD, (x + mg, y, rw, sz))
        if lod >= 2:
            cx = x + sz // 2
            _dashline(s, cx, y + pad, cx, y + sz - pad, True, da, ga)
    else:
        pygame.draw.rect(s, C_SW, (x, y, sz, mg))
        pygame.draw.rect(s, C_SW, (x, y + sz - mg, sz, mg))
        pygame.draw.rect(s, C_ROAD, (x, y + mg, sz, rw))
        if lod >= 2:
            cy = y + sz // 2
            _dashline(s, x + pad, cy, x + sz - pad, cy, False, da, ga)


def _dcurv(s, x, y, rot, sz, lod=2):
    """CURVE — Tikungan 90° Bézier band, di-render di ukuran sz."""
    sf = sz / T
    rw = max(2, int(RW * sf))
    da = max(2, int(DASH_ON * sf))
    ga = max(2, int(DASH_OFF * sf))

    cx, cy = x + sz // 2, y + sz // 2
    pm = _pmids(x, y, sz)
    pp = {0: (0, 1), 1: (1, 2), 2: (2, 3), 3: (3, 0)}
    pf, pt = pp[rot]
    segs = max(12, int(32 * sf))
    cc = _bquad(pm[pf], (cx, cy), pm[pt], segs)
    _dsw(s, x, y, CURVE, rot, sz)
    _fband(s, cc, rw // 2 + max(1, int(3 * sf)), C_ROAD)
    if lod >= 2:
        _bdash(s, cc, C_DASH, da, ga)


def _ddiag(s, x, y, rot, sz, lod=2):
    """DIAGONAL — Dirender lurus (rectangle) agar peta tetap bersih."""
    sf  = sz / T
    rw  = max(2, int(RW * sf))
    mg  = (sz - rw) // 2
    da  = max(2, int(DASH_ON * sf))
    ga  = max(2, int(DASH_OFF * sf))
    pad = max(1, int(4 * sf))

    if rot == 0:
        pygame.draw.rect(s, C_SW, (x, y, mg, sz))
        pygame.draw.rect(s, C_SW, (x + sz - mg, y, mg, sz))
        pygame.draw.rect(s, C_ROAD, (x + mg, y, rw, sz))
        if lod >= 2:
            _dashline(s, x + sz // 2, y + pad, x + sz // 2, y + sz - pad, True, da, ga)
    else:
        pygame.draw.rect(s, C_SW, (x, y, sz, mg))
        pygame.draw.rect(s, C_SW, (x, y + sz - mg, sz, mg))
        pygame.draw.rect(s, C_ROAD, (x, y + mg, sz, rw))
        if lod >= 2:
            _dashline(s, x + pad, y + sz // 2, x + sz - pad, y + sz // 2, False, da, ga)


def _dtjunc(s, x, y, rot, sz, lod=2):
    """T-JUNCTION — Pertigaan, di-render di ukuran sz."""
    sf = sz / T
    rw = max(2, int(RW * sf))
    da = max(2, int(DASH_ON * sf))
    ga = max(2, int(DASH_OFF * sf))

    ports = list(get_ports(TJUNCTION, rot))
    ctr = (x + sz // 2, y + sz // 2)
    pm = _pmids(x, y, sz)
    _dsw(s, x, y, TJUNCTION, rot, sz)
    segs = max(10, int(24 * sf))
    for i, p1 in enumerate(ports):
        for p2 in ports[i + 1:]:
            c2 = _bquad(pm[p1], ctr, pm[p2], segs)
            _fband(s, c2, rw // 2 + max(1, int(3 * sf)), C_ROAD)
            if lod >= 2:
                _bdash(s, c2, C_DASH, da, ga)
    ir = max(3, rw // 2 + int(2 * sf))
    pygame.draw.circle(s, C_ROAD, (int(ctr[0]), int(ctr[1])), ir)


def _dcross(s, x, y, rot, sz, lod=2):
    """CROSS — Perempatan, di-render di ukuran sz."""
    sf = sz / T
    rw = max(2, int(RW * sf))
    da = max(2, int(DASH_ON * sf))
    ga = max(2, int(DASH_OFF * sf))
    mg = max(1, int(MG * sf))

    ctr = (x + sz // 2, y + sz // 2)
    pm = _pmids(x, y, sz)
    segs = max(10, int(24 * sf))
    for p1 in range(4):
        for p2 in range(p1 + 1, 4):
            c2 = _bquad(pm[p1], ctr, pm[p2], segs)
            _fband(s, c2, rw // 2 + max(1, int(3 * sf)), C_ROAD)
    ir = max(4, rw // 2 + int(3 * sf))
    pygame.draw.circle(s, C_ROAD, (int(ctr[0]), int(ctr[1])), ir)
    cr = max(1, mg - max(1, int(4 * sf)))
    for px, py in [(x, y), (x + sz, y), (x, y + sz), (x + sz, y + sz)]:
        pygame.draw.circle(s, C_SW, (px, py), cr)
    if lod >= 2:
        for p1, p2 in [(0, 2), (1, 3)]:
            c2 = _bquad(pm[p1], ctr, pm[p2], segs)
            _bdash(s, c2, C_DASH, da, ga)


def _draw_tile(s, x, y, tt, rot, sz, lod=2):
    """Dispatcher: render tile tipe tt rotasi rot di ukuran sz piksel."""
    if tt == STRAIGHT:    _dstr(s, x, y, rot, sz, lod)
    elif tt == CURVE:     _dcurv(s, x, y, rot, sz, lod)
    elif tt == DIAGONAL:  _ddiag(s, x, y, rot, sz, lod)
    elif tt == TJUNCTION: _dtjunc(s, x, y, rot, sz, lod)
    elif tt == CROSS:     _dcross(s, x, y, rot, sz, lod)


def draw_lamp(surf, cx, cy, zoom, lod):
    """Gambar tiang lampu jalan di posisi layar (cx, cy)."""
    if lod < 1:
        return
    
    # Ukuran lampu di-scale sesuai zoom
    base_r = max(1.5, int(4 * zoom))
    glow_r = max(4, int(15 * zoom))
    
    # Tiang lampu (kecil abu-abu)
    pygame.draw.circle(surf, (100, 100, 110), (int(cx), int(cy)), max(1, int(2 * zoom)))
    
    # Cahaya lampu
    if lod >= 2:
        # Glow semi-transparan (kuning neon hangat)
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (255, 255, 150, 40), (glow_r, glow_r), glow_r)
        pygame.draw.circle(glow_surf, (255, 255, 200, 90), (glow_r, glow_r), glow_r // 2)
        surf.blit(glow_surf, (int(cx - glow_r), int(cy - glow_r)))
    
    # Lampu inti
    pygame.draw.circle(surf, (255, 255, 200), (int(cx), int(cy)), base_r)


# ══════════════════════════════════════════════════════════════
# TILE CACHE — Lazy Zoom Cache
# ══════════════════════════════════════════════════════════════
class TileCache:
    """
    Lazy zoom-aware tile cache.

    Alih-alih menyimpan Surface T×T lalu scale saat render (→ jagged),
    cache ini menyimpan Surface yang sudah dirender di ukuran display aktual.

    Key: (tile_type, rotation, quantized_display_size, lod)
    Kuantisasi ke kelipatan 4px untuk membatasi jumlah entry cache.
    Cache otomatis dibersihkan saat terlalu besar (maks 600 entry).

    Cara pakai:
      surf = tile_cache.get(tile_type, rotation, display_size, lod)
      screen.blit(surf, (sx, sy))  # langsung blit, tanpa scale!
    """

    def __init__(self):
        self.cache = {}
        self._max_entries = 600

    def build(self):
        """Pre-build cache di ukuran native T untuk render awal yang cepat."""
        self.cache.clear()
        for lod in (1, 2):
            for tt in [STRAIGHT, CURVE, DIAGONAL, TJUNCTION, CROSS]:
                rots = len(TILE_PORTS[tt])
                for rot in range(rots):
                    s = pygame.Surface((T, T))
                    s.fill(C_GRASS)
                    _draw_tile(s, 0, 0, tt, rot, T, lod)
                    self.cache[(tt, rot, T, lod)] = s

    def get(self, tt, rot, display_size=None, lod=2):
        """
        Ambil Surface tile yang sudah dirender di ukuran display_size.
        Jika belum ada di cache → render baru, simpan, return.
        """
        if display_size is None:
            display_size = T

        # Kuantisasi ke kelipatan 4px
        qsz = max(4, ((display_size + 2) // 4) * 4)
        key = (tt, rot, qsz, lod)

        if key not in self.cache:
            # Eviction sederhana: bersihkan semua jika terlalu penuh
            if len(self.cache) > self._max_entries:
                self.cache.clear()

            if qsz < 6:
                # Terlalu kecil untuk detail → kotak warna jalan saja
                s = pygame.Surface((qsz, qsz))
                s.fill(C_ROAD)
            else:
                s = pygame.Surface((qsz, qsz))
                s.fill(C_GRASS)
                _draw_tile(s, 0, 0, tt, rot, qsz, lod)
            self.cache[key] = s

        return self.cache[key]


# ══════════════════════════════════════════════════════════════
# ENVIRONMENT RENDERING — Aset Kota Realistis
# ══════════════════════════════════════════════════════════════
def _render_building(size, style_idx, seed_v=0):
    """Render bangunan neon procedural (legacy B0/B1/B2)."""
    s   = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill(C_GRASS)
    st  = BLDG_STYLES[style_idx % 3]
    rng = random.Random(seed_v * 7919 + style_idx)

    m       = max(3, size // 12)
    bx, by  = m, m
    bw, bh  = size - m * 2, size - m * 2
    br      = max(1, size // 40)

    pygame.draw.rect(s, (10, 12, 16), (bx + 3, by + 3, bw, bh), border_radius=br)
    pygame.draw.rect(s, st['wall'], (bx, by, bw, bh), border_radius=br)
    sw2 = max(2, bw // 5)
    pygame.draw.rect(s, st['light'], (bx, by, sw2, bh), border_radius=br)
    rh = max(2, bh * 12 // 100)
    pygame.draw.rect(s, st['roof'], (bx - 1, by, bw + 2, rh), border_radius=br)
    pygame.draw.line(s, st['neon'], (bx, by + rh), (bx + bw, by + rh), 1)

    wt    = by + rh + max(2, size // 20)
    wb    = by + bh - max(4, size // 10)
    wh2   = wb - wt
    wm    = max(2, size // 20)
    inner = bw - wm * 2
    if inner > 4 and wh2 > 4:
        ww    = max(2, inner * 22 // 100)
        whh   = max(2, wh2 * 25 // 100)
        gx    = max(1, inner * 8 // 100)
        gy    = max(1, wh2 * 10 // 100)
        ncols = max(1, (inner + gx) // (ww + gx))
        nrows = max(1, (wh2 + gy) // (whh + gy))
        tw    = ncols * ww + (ncols - 1) * gx
        th    = nrows * whh + (nrows - 1) * gy
        sx    = bx + wm + (inner - tw) // 2
        sy    = wt + (wh2 - th) // 2
        for row in range(nrows):
            for col in range(ncols):
                wx = sx + col * (ww + gx)
                wy = sy + row * (whh + gy)
                lit = rng.random() > 0.25
                wc  = st['win'] if lit else st['win_off']
                pygame.draw.rect(s, wc, (wx, wy, ww, whh))
                pygame.draw.rect(s, st['neon'], (wx, wy, ww, whh), 1)

    dw = max(3, bw * 20 // 100)
    dh = max(4, bh * 18 // 100)
    dx = bx + (bw - dw) // 2
    dy = by + bh - dh
    pygame.draw.rect(s, st['wall'], (dx, dy, dw, dh), border_radius=max(1, br // 2))
    pygame.draw.rect(s, st['neon'], (dx, dy, dw, dh), 1, border_radius=max(1, br // 2))
    pygame.draw.rect(s, st['neon'], (bx, by, bw, bh), 1, border_radius=br)
    return s


def _render_rumah(size, seed_v=0):
    """Rumah tinggal: halaman hijau + dinding + atap segitiga + jendela + pintu."""
    s   = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill(C_GRASS)
    rng = random.Random(seed_v * 3331 + 7)

    # Warna variasi
    wall_cols = [(65, 72, 90), (75, 65, 55), (58, 70, 78), (80, 75, 65)]
    roof_cols = [(120, 45, 35), (50, 70, 100), (90, 60, 40), (60, 80, 65)]
    wc   = wall_cols[seed_v % len(wall_cols)]
    rc   = roof_cols[seed_v % len(roof_cols)]

    m  = max(6, size // 5)   # halaman
    bx, by = m, m + size // 8
    bw, bh = size - m * 2, size - m * 2 - size // 8

    # Halaman hijau
    pygame.draw.rect(s, (20, 30, 22), (m - 3, m - 3, size - m * 2 + 6, size - m * 2 + 6),
                     border_radius=2)

    # Bayangan
    pygame.draw.rect(s, (8, 10, 14), (bx + 2, by + 2, bw, bh), border_radius=2)
    # Dinding
    pygame.draw.rect(s, wc, (bx, by, bw, bh), border_radius=2)

    # Atap segitiga (top-down: strip di atas)
    ath = max(3, bh // 4)
    pts = [(bx - 2, by + ath), (bx + bw // 2, by - 2), (bx + bw + 2, by + ath)]
    pygame.draw.polygon(s, rc, pts)
    pygame.draw.polygon(s, tuple(max(0, c - 20) for c in rc), pts, 1)

    # Jendela (2 buah)
    ww = max(3, bw // 4)
    wh = max(3, bh // 4)
    wy = by + ath + max(2, bh // 8)
    # Kiri
    pygame.draw.rect(s, (140, 180, 220), (bx + max(2, bw // 8), wy, ww, wh))
    pygame.draw.rect(s, (80, 100, 130), (bx + max(2, bw // 8), wy, ww, wh), 1)
    # Kanan
    pygame.draw.rect(s, (100, 160, 200), (bx + bw - ww - max(2, bw // 8), wy, ww, wh))
    pygame.draw.rect(s, (80, 100, 130), (bx + bw - ww - max(2, bw // 8), wy, ww, wh), 1)

    # Pintu
    dw = max(3, bw // 5)
    dh = max(4, bh // 3)
    dx = bx + (bw - dw) // 2
    dy = by + bh - dh
    pygame.draw.rect(s, (45, 35, 25), (dx, dy, dw, dh), border_radius=1)
    pygame.draw.rect(s, (70, 55, 35), (dx, dy, dw, dh), 1, border_radius=1)
    # Knob
    pygame.draw.circle(s, (180, 160, 80), (dx + dw - max(2, dw // 4), dy + dh // 2), max(1, size // 30))
    return s


def _render_ruko(size, seed_v=0):
    """Ruko/Toko: bangunan kotak + awning/kanopi + papan toko."""
    s   = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill(C_GRASS)
    rng = random.Random(seed_v * 4447 + 11)

    awning_cols = [(180, 60, 50), (50, 130, 180), (180, 140, 40),
                   (60, 160, 80), (160, 80, 140)]
    ac = awning_cols[seed_v % len(awning_cols)]

    m  = max(4, size // 10)
    bx, by = m, m
    bw, bh = size - m * 2, size - m * 2

    # Bayangan
    pygame.draw.rect(s, (8, 10, 14), (bx + 2, by + 2, bw, bh), border_radius=2)
    # Dinding (cerah)
    pygame.draw.rect(s, (70, 75, 85), (bx, by, bw, bh), border_radius=2)

    # Awning/kanopi (strip warna di atas)
    ah = max(3, bh // 5)
    pygame.draw.rect(s, ac, (bx - 2, by, bw + 4, ah), border_radius=2)
    # Garis-garis kanopi
    for i in range(3, bw, max(4, bw // 5)):
        pygame.draw.line(s, tuple(max(0, c - 40) for c in ac),
                         (bx + i, by), (bx + i, by + ah - 1), 1)

    # Papan toko
    ph = max(2, ah // 2)
    pygame.draw.rect(s, (30, 35, 45), (bx + 3, by + ah + 1, bw - 6, ph), border_radius=1)
    # Teks toko (garis kecil)
    tx = bx + 6
    ty = by + ah + 2
    tw = max(4, (bw - 12) // 2)
    pygame.draw.line(s, ac, (tx, ty + ph // 2), (tx + tw, ty + ph // 2), 1)

    # Jendela etalase (besar, di tengah)
    wy = by + ah + ph + max(2, bh // 10)
    wh = max(5, (by + bh - wy) // 2)
    pygame.draw.rect(s, (120, 160, 200), (bx + 4, wy, bw - 8, wh))
    pygame.draw.rect(s, (60, 80, 110), (bx + 4, wy, bw - 8, wh), 1)
    # Pembagi etalase
    pygame.draw.line(s, (60, 80, 110), (bx + bw // 2, wy), (bx + bw // 2, wy + wh), 1)

    # Pintu
    dw = max(4, bw // 4)
    dh = max(4, by + bh - wy - wh - 2)
    if dh > 2:
        dx = bx + (bw - dw) // 2
        dy = by + bh - dh
        pygame.draw.rect(s, (50, 55, 65), (dx, dy, dw, dh), border_radius=1)
        pygame.draw.rect(s, (80, 90, 110), (dx, dy, dw, dh), 1, border_radius=1)

    pygame.draw.rect(s, (50, 55, 65), (bx, by, bw, bh), 1, border_radius=2)
    return s


def _render_masjid(size, seed_v=0):
    """Masjid: kubah utama + menara kecil + halaman."""
    s   = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill(C_GRASS)
    cx, cy = size // 2, size // 2

    m  = max(4, size // 10)
    bx, by = m, m + 2
    bw, bh = size - m * 2, size - m * 2 - 2

    # Halaman / lantai masjid
    pygame.draw.rect(s, (8, 10, 14), (bx + 2, by + 2, bw, bh), border_radius=2)
    pygame.draw.rect(s, (55, 60, 75), (bx, by, bw, bh), border_radius=3)

    # Kubah utama (lingkaran besar)
    dome_r = max(8, min(bw, bh) // 3)
    pygame.draw.circle(s, (40, 80, 60), (cx, cy - 2), dome_r + 2)  # bayangan
    pygame.draw.circle(s, (80, 170, 100), (cx, cy - 2), dome_r)     # kubah hijau
    pygame.draw.circle(s, (100, 200, 120), (cx - 2, cy - 4), dome_r // 2)  # highlight

    # Bulan sabit di atas kubah
    ms = max(2, dome_r // 3)
    pygame.draw.circle(s, (220, 200, 60), (cx, cy - dome_r + 2), ms)
    pygame.draw.circle(s, (80, 170, 100), (cx + ms // 2, cy - dome_r + 1), ms - 1)

    # Menara kiri
    mw = max(2, bw // 8)
    mh = max(6, bh // 2)
    pygame.draw.rect(s, (65, 70, 85), (bx + 2, by + 2, mw, mh), border_radius=1)
    pygame.draw.circle(s, (220, 200, 60), (bx + 2 + mw // 2, by + 1), max(1, mw // 2))

    # Menara kanan
    pygame.draw.rect(s, (65, 70, 85), (bx + bw - mw - 2, by + 2, mw, mh), border_radius=1)
    pygame.draw.circle(s, (220, 200, 60),
                       (bx + bw - mw - 2 + mw // 2, by + 1), max(1, mw // 2))

    # Border
    pygame.draw.rect(s, (70, 80, 100), (bx, by, bw, bh), 1, border_radius=3)
    return s


def _render_spbu(size, seed_v=0):
    """SPBU: kanopi besar + pompa bensin + area parkir."""
    s   = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill(C_GRASS)

    m  = max(3, size // 12)
    bx, by = m, m
    bw, bh = size - m * 2, size - m * 2

    # Lantai SPBU (aspal)
    pygame.draw.rect(s, (35, 38, 48), (bx, by, bw, bh), border_radius=2)

    # Kanopi (persegi besar di atas)
    kh = max(5, bh * 40 // 100)
    pygame.draw.rect(s, (180, 30, 30), (bx + 2, by + 2, bw - 4, kh), border_radius=2)
    # Strip putih kanopi
    pygame.draw.rect(s, (220, 220, 220), (bx + 2, by + kh - 2, bw - 4, 2))

    # Tiang kanopi (4 sudut)
    pw = max(2, bw // 12)
    for px, py in [(bx + 4, by + 4), (bx + bw - 4 - pw, by + 4),
                   (bx + 4, by + kh - pw), (bx + bw - 4 - pw, by + kh - pw)]:
        pygame.draw.rect(s, (100, 105, 115), (px, py, pw, pw))

    # Pompa bensin (2 buah)
    pump_w = max(3, bw // 5)
    pump_h = max(4, kh // 3)
    py_top = by + (kh - pump_h) // 2
    # Pompa kiri
    pygame.draw.rect(s, (200, 50, 40), (bx + bw // 4 - pump_w // 2, py_top, pump_w, pump_h),
                     border_radius=1)
    # Pompa kanan
    pygame.draw.rect(s, (40, 120, 200), (bx + 3 * bw // 4 - pump_w // 2, py_top, pump_w, pump_h),
                     border_radius=1)

    # Office kecil di bawah
    oh = max(4, bh - kh - 4)
    ow = max(6, bw // 3)
    ox = bx + bw - ow - 2
    oy = by + kh + 2
    if oh > 3:
        pygame.draw.rect(s, (55, 60, 72), (ox, oy, ow, oh), border_radius=1)
        pygame.draw.rect(s, (80, 160, 220), (ox + 2, oy + 2, ow - 4, oh // 2))  # jendela
        pygame.draw.rect(s, (50, 55, 65), (ox, oy, ow, oh), 1, border_radius=1)

    pygame.draw.rect(s, (60, 65, 75), (bx, by, bw, bh), 1, border_radius=2)
    return s


def _render_taman(size, seed_v=0):
    """Taman: area hijau + jalur setapak + bangku + pohon kecil."""
    s   = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill(C_GRASS)
    rng = random.Random(seed_v * 5557 + 13)

    m  = max(3, size // 12)
    bx, by = m, m
    bw, bh = size - m * 2, size - m * 2

    # Lantai taman (hijau lebih cerah dari rumput)
    pygame.draw.rect(s, (22, 35, 25), (bx, by, bw, bh), border_radius=3)

    # Jalur setapak (diagonal atau cross)
    path_col = (45, 48, 55)
    pw = max(2, size // 16)
    if rng.random() < 0.5:
        # Setapak silang
        pygame.draw.line(s, path_col, (bx, by), (bx + bw, by + bh), pw)
        pygame.draw.line(s, path_col, (bx + bw, by), (bx, by + bh), pw)
    else:
        # Setapak melengkung (H shape)
        mid_y = by + bh // 2
        pygame.draw.line(s, path_col, (bx, mid_y), (bx + bw, mid_y), pw)
        pygame.draw.line(s, path_col, (bx + bw // 4, by), (bx + bw // 4, by + bh), pw)
        pygame.draw.line(s, path_col, (bx + 3 * bw // 4, by), (bx + 3 * bw // 4, by + bh), pw)

    # Pohon kecil (2-3 buah)
    for _ in range(rng.randint(2, 3)):
        tx = bx + rng.randint(6, bw - 6)
        ty = by + rng.randint(6, bh - 6)
        tr = max(3, size // 12)
        g  = 30 + rng.randint(0, 15)
        pygame.draw.circle(s, (10, g - 10, 12), (tx + 1, ty + 1), tr + 1)  # bayangan
        pygame.draw.circle(s, (15, g, 18), (tx, ty), tr)
        pygame.draw.circle(s, (20, g + 8, 22), (tx - 1, ty - 1), tr // 2)

    # Bangku (1-2 buah)
    for _ in range(rng.randint(1, 2)):
        bkx = bx + rng.randint(8, bw - 12)
        bky = by + rng.randint(8, bh - 8)
        pygame.draw.rect(s, (80, 55, 30), (bkx, bky, max(3, size // 10), max(1, size // 25)))

    # Air mancur di tengah (50% chance)
    if rng.random() < 0.5:
        fcx, fcy = bx + bw // 2, by + bh // 2
        fr = max(3, size // 10)
        pygame.draw.circle(s, (30, 50, 70), (fcx, fcy), fr)
        pygame.draw.circle(s, (50, 80, 120), (fcx, fcy), fr - 1)
        pygame.draw.circle(s, (80, 120, 180), (fcx, fcy), max(1, fr // 2))

    pygame.draw.rect(s, (30, 45, 30), (bx, by, bw, bh), 1, border_radius=3)
    return s


def _render_tree(size, variant=0):
    """Render pohon top-down: variasi pohon besar, palem, semak."""
    s      = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill(C_GRASS)
    cx, cy = size // 2, size // 2
    rng    = random.Random(variant * 137 + 42)
    kind   = variant % 3  # 0=pohon besar, 1=palem, 2=semak

    if kind == 0:
        # Pohon besar: kanopi berlapis
        base_g   = 35 + rng.randint(-8, 8)
        canopy_r = 14 + rng.randint(-3, 5)
        pygame.draw.circle(s, (8, 10, 16), (cx + 2, cy + 2), canopy_r + 2)
        tw = max(2, canopy_r // 4)
        pygame.draw.rect(s, (50 + rng.randint(-10, 10), 35, 20),
                         (cx - tw // 2, cy - tw // 2, tw, tw + 2))
        for ox, oy in [(0, 0), (rng.randint(-3, 3), rng.randint(-3, 3))]:
            g = base_g + rng.randint(-5, 5)
            pygame.draw.circle(s, (15, g, 18), (cx + ox, cy + oy), canopy_r + rng.randint(-2, 1))
        pygame.draw.circle(s, (20, base_g + 12, 22), (cx - 3, cy - 3), canopy_r // 2)

    elif kind == 1:
        # Palem: batang tipis + daun radial
        pygame.draw.circle(s, (8, 10, 14), (cx + 1, cy + 1), 14)  # bayangan
        # Batang
        pygame.draw.rect(s, (65, 50, 30), (cx - 2, cy - 4, 4, 10))
        # Daun (4 arah)
        for angle_offset in range(4):
            import math as _m
            a = _m.radians(angle_offset * 90 + rng.randint(-15, 15))
            lx = cx + int(_m.cos(a) * 12)
            ly = cy + int(_m.sin(a) * 12)
            pygame.draw.line(s, (20, 50 + rng.randint(0, 15), 20),
                             (cx, cy), (lx, ly), 2)
            pygame.draw.circle(s, (18, 45 + rng.randint(0, 15), 18), (lx, ly), 4)

    else:
        # Semak: beberapa lingkaran kecil rendah
        pygame.draw.circle(s, (8, 10, 14), (cx + 1, cy + 1), 10)
        for _ in range(rng.randint(3, 5)):
            ox = rng.randint(-8, 8)
            oy = rng.randint(-8, 8)
            r  = rng.randint(4, 7)
            g  = 28 + rng.randint(0, 15)
            pygame.draw.circle(s, (12, g, 15), (cx + ox, cy + oy), r)

    return s


# ══════════════════════════════════════════════════════════════
# ENVIRONMENT CACHE
# ══════════════════════════════════════════════════════════════
class EnvCache:
    """Cache Surface environment: rumput, trotoar, pohon, bangunan, aset kota."""

    def __init__(self):
        self.grass_surf = None
        self.sw_surf    = None
        self.buildings  = {}   # legacy B0/B1/B2
        self.trees      = {}
        self.rumah      = {}
        self.ruko       = {}
        self.masjid     = {}
        self.spbu       = {}
        self.taman      = {}

    def build(self):
        self.grass_surf = pygame.Surface((T, T))
        self.grass_surf.fill(C_GRASS)

        self.sw_surf = pygame.Surface((T, T))
        self.sw_surf.fill(C_SW)

        # Legacy buildings
        for i in range(3):
            for v in range(4):
                self.buildings[(i, v)] = _render_building(T, i, v)

        # Pohon (6 variasi: 2 besar, 2 palem, 2 semak)
        for v in range(6):
            self.trees[v] = _render_tree(T, v)

        # Rumah tinggal (4 variasi warna)
        for v in range(4):
            self.rumah[v] = _render_rumah(T, v)

        # Ruko/Toko (5 variasi warna kanopi)
        for v in range(5):
            self.ruko[v] = _render_ruko(T, v)

        # Masjid (2 variasi)
        for v in range(2):
            self.masjid[v] = _render_masjid(T, v)

        # SPBU (2 variasi)
        for v in range(2):
            self.spbu[v] = _render_spbu(T, v)

        # Taman (4 variasi)
        for v in range(4):
            self.taman[v] = _render_taman(T, v)

    def get(self, env_type, c, r):
        if env_type == ENV_NONE:
            return self.grass_surf
        if env_type == ENV_SW:
            return self.sw_surf
        if env_type == ENV_TREE:
            return self.trees.get((c * 7 + r * 13) % 6, self.grass_surf)
        if env_type in (ENV_B0, ENV_B1, ENV_B2):
            si = env_type - ENV_B0
            vi = (c * 3 + r * 11) % 4
            return self.buildings.get((si, vi), self.grass_surf)
        if env_type == ENV_RUMAH:
            return self.rumah.get((c * 5 + r * 7) % 4, self.grass_surf)
        if env_type == ENV_RUKO:
            return self.ruko.get((c * 3 + r * 9) % 5, self.grass_surf)
        if env_type == ENV_MASJID:
            return self.masjid.get((c + r) % 2, self.grass_surf)
        if env_type == ENV_SPBU:
            return self.spbu.get((c * 2 + r) % 2, self.grass_surf)
        if env_type == ENV_TAMAN:
            return self.taman.get((c * 11 + r * 3) % 4, self.grass_surf)
        return self.grass_surf


# ══════════════════════════════════════════════════════════════
# MINIMAP
# ══════════════════════════════════════════════════════════════
def build_minimap(grid, size=150):
    """Render minimap seluruh peta."""
    s  = pygame.Surface((size, size))
    s.fill((10, 12, 18))
    cs = size / max(grid.cols, grid.rows)

    for r in range(grid.rows):
        for c in range(grid.cols):
            t = grid.cells[r][c]
            if t.type == EMPTY:
                continue
            col = (50, 60, 90)
            x = int(c * cs)
            y = int(r * cs)
            w = max(1, int(cs))
            pygame.draw.rect(s, col, (x, y, w, w))

    pygame.draw.rect(s, C_BTN_BD, (0, 0, size, size), 1)
    return s

