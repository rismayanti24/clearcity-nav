"""
kelompok.py
===========
Entry point utama simulasi navigasi kota.
Berisi kelas ClearCityNav (controller/aplikasi) dan main game loop.

Struktur modul:
  config.py       → Konstanta global (warna, ukuran, dll)
  grid.py         → Tile, Grid, sistem port
  mapgen.py       → Generasi peta dan environment
  pathfinding.py  → A*, Dijkstra, BFS, Catmull-Rom
  rendering.py    → Render tile, bangunan, pohon, minimap
  entities.py     → Camera, Car, Button
  kelompok.py     → ClearCityNav (main app) + entry point

Cara menjalankan:
  python kelompok.py
"""

import random
import time
import sys

import pygame

# ── Import dari modul lain ────────────────────────────────────
from config import (
    W, H, T, GCOLS, GROWS, FPS,
    C_BG, C_GRASS, C_UI, C_UIK, C_BTN_BD, C_PATH, C_EXPLORED,
    C_ORIGIN, C_DEST,
    C_PATH_ASTAR, C_PATH_BFS, C_PATH_DIJKSTRA,
    C_EXPL_ASTAR, C_EXPL_BFS, C_EXPL_DIJKSTRA,
    C_PATH_OUTLINE_ASTAR, C_PATH_OUTLINE_BFS, C_PATH_OUTLINE_DIJKSTRA,
    LOD_FAR_ZOOM, LOD_MED_ZOOM,
)
from grid import EMPTY, STRAIGHT, CURVE, DIAGONAL, TJUNCTION, CROSS, get_ports
from mapgen import (generate_map, generate_environment, _all_road_cells,
                    ENV_NONE, ENV_SW, ENV_TREE,
                    ENV_B0, ENV_B1, ENV_B2,
                    ENV_RUMAH, ENV_RUKO, ENV_MASJID, ENV_SPBU, ENV_TAMAN)
from pathfinding import astar, dijkstra, bfs_pathfind, build_world_path
from rendering import TileCache, EnvCache, build_minimap, draw_lamp
from entities import Camera, Car, Button


# ══════════════════════════════════════════════════════════════
# MAIN APPLICATION CLASS
# ══════════════════════════════════════════════════════════════
class ClearCityNav:
    """
    Controller utama yang mengintegrasikan semua komponen simulasi.

    Tanggung jawab:
      - Inisialisasi pygame dan semua komponen
      - Mengelola state aplikasi (grid, path, car, kamera, dll)
      - Menangani input pengguna (klik, scroll, keyboard)
      - Menjalankan pathfinding dan membandingkan 3 algoritma
      - Merender seluruh frame setiap tick

    Keyboard shortcuts:
      SPACE  → Start/Pause/Resume mobil
      R      → Random path
      N      → New map
      C      → Clear all
      F      → Toggle follow car
      ESC    → Keluar
    """

    def __init__(self):
        pygame.init()
        self.screen  = pygame.display.set_mode((W, H))
        pygame.display.set_caption("ClearCity Nav — Smart Car Simulator")
        self.clock   = pygame.time.Clock()
        self.font    = pygame.font.SysFont("consolas", 13)
        self.font_b  = pygame.font.SysFont("consolas", 15, bold=True)
        self.font_t  = pygame.font.SysFont("consolas", 20, bold=True)

        self.panel_w = 200
        self.seed       = random.randint(0, 999999)
        self.grid       = None
        self.env        = None
        self.tile_cache = TileCache()
        self.env_cache  = EnvCache()
        self.minimap_surf = None

        world_w = GCOLS * T
        world_h = GROWS * T
        self.camera = Camera(world_w, world_h, W, H)

        self.car          = Car()
        self.origin       = None
        self.dest         = None
        self.path         = None
        self.explored     = set()
        self.blocked      = set()
        self.follow_car   = False
        self.placing_mode = "origin"

        self.astar_time  = 0
        self.astar_nodes = 0
        self.tile_counts = {}
        self._last_drag  = None
        self._click_start = None

        # ── Performance caches ────────────────────────────────
        self._cached_wpath  = None   # cached world path (list of (wx,wy))
        self._cached_path_key = None # key to detect path changes
        self._env_scale_cache = {}   # {(env_type, c, r, isz): Surface}
        self._block_overlay_cache = {}  # {isz: Surface}
        self._map_surf_cache = None
        self._map_surf_zoom = None
        self._map_surf_lod = None
        self._map_surf_blocked_hash = None

        self.current_algo = "astar"
        self.algo_stats   = {
            "astar":    {"nodes": 0, "ms": 0.0, "path_len": 0},
            "dijkstra": {"nodes": 0, "ms": 0.0, "path_len": 0},
            "bfs":      {"nodes": 0, "ms": 0.0, "path_len": 0},
        }

        # Warna berbeda tiap algoritma
        self.algo_colors = {
            "astar":    {"path": C_PATH_ASTAR,    "explored": C_EXPL_ASTAR,    "outline": C_PATH_OUTLINE_ASTAR},
            "dijkstra": {"path": C_PATH_DIJKSTRA, "explored": C_EXPL_DIJKSTRA, "outline": C_PATH_OUTLINE_DIJKSTRA},
            "bfs":      {"path": C_PATH_BFS,      "explored": C_EXPL_BFS,      "outline": C_PATH_OUTLINE_BFS},
        }

        bx, bw, bh = 10, 180, 28
        by, gap    = 80, 34
        self.btn_car = Button(bx, by, bw, bh, "Start Car", self._toggle_car)
        self.buttons = [
            self.btn_car,
            Button(bx, by + gap,     bw, bh, "Random Path", self._random_path),
            Button(bx, by + gap * 2, bw, bh, "New Map",     self._new_map),
            Button(bx, by + gap * 3, bw, bh, "Clear All",   self._clear_all),
            Button(bx, by + gap * 4, bw, bh, "Follow Car",  self._toggle_follow),
            Button(bx, by + gap * 5, bw, bh, "Center View", self._center_view),
        ]

        abw, abh, aby = 57, 22, 282
        self.algo_btns = [
            Button(10,               aby, abw, abh, "A*",       lambda: self._set_algo("astar")),
            Button(10 + abw + 3,     aby, abw, abh, "Dijkstra", lambda: self._set_algo("dijkstra")),
            Button(10 + abw * 2 + 6, aby, abw, abh, "BFS",      lambda: self._set_algo("bfs")),
        ]
        self.algo_btns[0].is_active = True

        self._rebuild_map()

    def _show_loading(self, msg="Generating map..."):
        self.screen.fill(C_BG)
        t = self.font_b.render(msg, True, C_UI)
        self.screen.blit(t, (W // 2 - t.get_width() // 2, H // 2 - 10))
        pygame.display.flip()

    def _rebuild_map(self):
        self._show_loading("Generating road network...")
        self.grid = generate_map(GCOLS, GROWS, self.seed)
        self._show_loading("Generating environment...")
        self.env = generate_environment(self.grid, self.seed)
        self._show_loading("Building tile cache...")
        self.tile_cache.build()
        self.env_cache.build()
        self.minimap_surf = build_minimap(self.grid)
        self.origin = None
        self.dest   = None
        self.path   = None
        self.explored = set()
        self.blocked  = set()
        self.car      = Car()
        self.btn_car.text = "Start Car"
        self.algo_stats = {
            "astar":    {"nodes": 0, "ms": 0.0, "path_len": 0},
            "dijkstra": {"nodes": 0, "ms": 0.0, "path_len": 0},
            "bfs":      {"nodes": 0, "ms": 0.0, "path_len": 0},
        }
        self.tile_counts = {STRAIGHT: 0, CURVE: 0, DIAGONAL: 0, TJUNCTION: 0, CROSS: 0}
        for r in range(GROWS):
            for c in range(GCOLS):
                tt = self.grid.cells[r][c].type
                if tt in self.tile_counts:
                    self.tile_counts[tt] += 1
        self._map_surf_cache = None

    def _toggle_car(self):
        if self.car.active and not self.car.arrived:
            self.car.paused   = not self.car.paused
            self.btn_car.text = "Resume Car" if self.car.paused else "Pause Car"
        elif self.path and len(self.path) >= 2:
            wpath = build_world_path(self.grid, self.path)
            self.car.set_path(wpath)
            self.btn_car.text = "Pause Car"

    def _random_path(self):
        roads = _all_road_cells(self.grid)
        roads = [rc for rc in roads if rc not in self.blocked]
        if len(roads) < 2:
            return
        rng         = random.Random()
        a, b        = rng.sample(roads, 2)
        self.origin = a
        self.dest   = b
        self._do_pathfind()

    def _new_map(self):
        self.seed = random.randint(0, 999999)
        self._rebuild_map()

    def _clear_all(self):
        self.origin       = None
        self.dest         = None
        self.path         = None
        self.explored     = set()
        self.blocked      = set()
        self.car          = Car()
        self.btn_car.text = "Start Car"
        self.placing_mode = "origin"
        self.algo_stats   = {
            "astar":    {"nodes": 0, "ms": 0.0, "path_len": 0},
            "dijkstra": {"nodes": 0, "ms": 0.0, "path_len": 0},
            "bfs":      {"nodes": 0, "ms": 0.0, "path_len": 0},
        }
        self._map_surf_cache = None

    def _toggle_follow(self):
        self.follow_car = not self.follow_car

    def _center_view(self):
        self.camera.center_on(GCOLS * T / 2, GROWS * T / 2)
        self.camera.zoom = 0.45

    def _set_algo(self, algo):
        self.current_algo = algo
        algo_map = {"A*": "astar", "Dijkstra": "dijkstra", "BFS": "bfs"}
        for b in self.algo_btns:
            b.is_active = (algo_map.get(b.text) == algo)
        if self.origin and self.dest:
            self._do_pathfind()

    def _do_pathfind(self):
        if not (self.origin and self.dest):
            return
        _algos = [
            ("astar",    astar),
            ("dijkstra", dijkstra),
            ("bfs",      bfs_pathfind),
        ]
        _results = {}
        for name, fn in _algos:
            t0       = time.time()
            res, exp = fn(self.grid, self.origin, self.dest, self.blocked)
            elapsed  = (time.time() - t0) * 1000
            self.algo_stats[name] = {
                "nodes":    len(exp),
                "ms":       elapsed,
                "path_len": len(res) if res else 0,
            }
            _results[name] = (res, exp)
        sel_res, sel_exp = _results[self.current_algo]
        self.explored     = sel_exp
        self.path         = sel_res
        self.astar_nodes  = self.algo_stats[self.current_algo]["nodes"]
        self.astar_time   = self.algo_stats[self.current_algo]["ms"]

    def _reroute_car(self):
        """
        Reroute mobil dari POSISI SAAT INI ke tujuan (bukan dari origin).
        Dipanggil setiap kali roadblock berubah (tambah/hapus).

        Langkah:
          1. Hitung tile jalan terdekat dari posisi piksel mobil saat ini
          2. Jalankan pathfinding dari tile itu ke self.dest
          3. Bangun world path: [posisi mobil sekarang] + jalur baru
          4. Set ke mobil tanpa reset posisi → gerakan mulus
          5. Fallback ke rute dari origin jika tile terdekat tidak ditemukan
        """
        was_paused = self.car.paused

        if not self.dest:
            return

        # ── Cari tile jalan terdekat dari posisi mobil ────────
        car_c = int(self.car.x // T)
        car_r = int(self.car.y // T)
        nearest = None
        best_d  = float('inf')

        # Cari dalam radius 4 tile
        for sr in range(max(0, car_r - 4), min(GROWS, car_r + 5)):
            for sc in range(max(0, car_c - 4), min(GCOLS, car_c + 5)):
                if self.grid.is_road(sc, sr) and (sc, sr) not in self.blocked:
                    d = abs(sc - car_c) + abs(sr - car_r)
                    if d < best_d:
                        best_d   = d
                        nearest  = (sc, sr)

        if nearest is None:
            # Tidak ada tile valid di sekitar mobil → berhenti
            self.car.active   = False
            self.car.arrived  = False
            self.btn_car.text = "Start Car"
            return

        # ── Pathfind dari tile terdekat ke destination ────────
        algo_fn = {"astar": astar, "dijkstra": dijkstra, "bfs": bfs_pathfind}
        fn       = algo_fn[self.current_algo]
        new_path, _ = fn(self.grid, nearest, self.dest, self.blocked)

        if new_path and len(new_path) >= 1:
            # Bangun world path dari tile terdekat
            new_wpath = build_world_path(self.grid, new_path)
            # Gabungkan: posisi mobil saat ini + jalur baru
            # → gerakan seamless tanpa lompat ke origin
            full_wpath = [(self.car.x, self.car.y)] + new_wpath

            # Update car path langsung tanpa reset posisi
            self.car.world_path = full_wpath
            self.car.path_idx   = 0
            self.car.arrived    = False
            self.car.active     = True

            if was_paused:
                self.car.paused   = True
                self.btn_car.text = "Resume Car"
            else:
                self.car.paused   = False
                self.btn_car.text = "Pause Car"
        else:
            # Tidak ada jalur alternatif → berhentikan mobil
            self.car.active   = False
            self.car.arrived  = False
            self.btn_car.text = "Start Car"

    def _handle_map_click(self, pos, button):
        wx, wy = self.camera.screen_to_world(pos[0], pos[1])
        c = int(wx // T)
        r = int(wy // T)
        if not self.grid.in_bounds(c, r):
            return
        if button == 1:
            target = None
            if self.grid.is_road(c, r):
                target = (c, r)
            else:
                best, best_d = None, 999
                for d2 in range(1, 4):
                    for dr2 in range(-d2, d2 + 1):
                        for dc2 in range(-d2, d2 + 1):
                            nc, nr = c + dc2, r + dr2
                            if self.grid.is_road(nc, nr):
                                dd = abs(dc2) + abs(dr2)
                                if dd < best_d:
                                    best_d, best = dd, (nc, nr)
                    if best:
                        break
                target = best
            if target:
                if self.placing_mode == "origin":
                    self.origin       = target
                    self.placing_mode = "dest"
                    self.path         = None
                    self.explored     = set()
                else:
                    self.dest         = target
                    self.placing_mode = "origin"
                    self._do_pathfind()
        elif button == 3:
            if self.grid.is_road(c, r):
                if (c, r) in self.blocked:
                    self.blocked.discard((c, r))
                else:
                    if (c, r) != self.origin and (c, r) != self.dest:
                        self.blocked.add((c, r))
                self._map_surf_cache = None
                if self.origin and self.dest:
                    self._do_pathfind()
                    # Jika mobil sedang aktif/paused → reroute ke jalur baru
                    if self.car.active or self.car.paused:
                        self._reroute_car()

    def _draw_panel(self, lod=2):
        panel = pygame.Surface((self.panel_w, H), pygame.SRCALPHA)
        panel.fill((12, 16, 24, 230))
        self.screen.blit(panel, (0, 0))
        pygame.draw.line(self.screen, C_BTN_BD, (self.panel_w, 0), (self.panel_w, H), 1)
        t = self.font_t.render("NAV SIM", True, C_UI)
        self.screen.blit(t, (self.panel_w // 2 - t.get_width() // 2, 12))
        pygame.draw.line(self.screen, C_BTN_BD, (10, 42), (self.panel_w - 10, 42), 1)
        st = self.font.render("Snake Growth Engine", True, C_UIK)
        self.screen.blit(st, (self.panel_w // 2 - st.get_width() // 2, 50))
        for b in self.buttons:
            b.draw(self.screen, self.font)
        pygame.draw.line(self.screen, C_BTN_BD, (10, 276), (self.panel_w - 10, 276), 1)
        albl = self.font.render("ALGORITHM:", True, C_UIK)
        self.screen.blit(albl, (10, 279))
        for b in self.algo_btns:
            b.draw(self.screen, self.font)
        total_road = sum(self.tile_counts.values())
        str_count  = self.tile_counts.get(STRAIGHT, 0)
        str_pct    = (str_count / total_road * 100) if total_road else 0
        str_ok     = str_pct <= 10.0  # aturan: straight ≤ 10%
        _complexity = {
            "astar":    ("O((V+E)logV)", "O(V)"),
            "dijkstra": ("O((V+E)logV)", "O(V)"),
            "bfs":      ("O(V+E)",       "O(V)"),
        }
        time_o, space_o = _complexity[self.current_algo]
        sy    = 312
        stats = [
            ("Seed",      str(self.seed)),
            ("Total Road", str(total_road)),
            ("Straight",  f"{str_count} ({str_pct:.1f}%)", "STRAIGHT"),
            ("Diagonal",  str(self.tile_counts.get(DIAGONAL, 0))),
            ("Curve",     str(self.tile_counts.get(CURVE, 0))),
            ("T-junc",    str(self.tile_counts.get(TJUNCTION, 0))),
            ("Cross",     str(self.tile_counts.get(CROSS, 0))),
            ("", ""),
            ("Mode",      self.placing_mode.upper()),
            ("Blocks",    str(len(self.blocked))),
            ("Nodes",     str(self.astar_nodes)),
            ("Time ms",   f"{self.astar_time:.2f}"),
            ("Path len",  str(len(self.path)) if self.path else "\u2014"),
            ("Time O",    time_o),
            ("Space O",   space_o),
            ("", ""),
            ("Car",    "ARRIVED" if self.car.arrived else
                       "PAUSED"  if self.car.paused  else
                       "ACTIVE"  if self.car.active  else "IDLE"),
            ("Follow", "ON" if self.follow_car else "OFF"),
            ("Speed",  f"{self.car.speed:.1f} px/f"),
            ("LOD",    ["FAR", "MED", "CLOSE"][lod]),
            ("Zoom",   f"{self.camera.zoom:.2f}"),
            ("FPS",    str(int(self.clock.get_fps()))),
        ]
        C_BIGOH     = (80, 255, 180)
        C_STR_OK    = (0, 220, 100)   # hijau: ≤ 10% terpenuhi
        C_STR_OVER  = (255, 80, 60)   # merah: > 10% melebihi batas
        for item in stats:
            if len(item) == 2:
                key, val = item
                tag = None
            else:
                key, val, tag = item
            if key == "":
                sy += 4
                continue
            kt = self.font.render(f"{key}:", True, C_UIK)
            if tag == "STRAIGHT":
                vc = C_STR_OK if str_ok else C_STR_OVER
            elif key in ("Time O", "Space O"):
                vc = C_BIGOH
            else:
                vc = C_UI
            vt = self.font.render(val, True, vc)
            self.screen.blit(kt, (14, sy))
            self.screen.blit(vt, (self.panel_w - 14 - vt.get_width(), sy))
            sy += 15
        sy += 4
        pygame.draw.line(self.screen, C_BTN_BD, (10, sy), (self.panel_w - 10, sy), 1)
        sy += 5
        hdr = self.font.render("ALGO COMPARISON", True, C_UIK)
        self.screen.blit(hdr, (self.panel_w // 2 - hdr.get_width() // 2, sy))
        sy += 14
        _algo_labels = [("A*", "astar"), ("Dijk", "dijkstra"), ("BFS", "bfs")]
        for label, key in _algo_labels:
            s      = self.algo_stats[key]
            is_sel = (key == self.current_algo)
            # Warna teks = warna jalur algoritma masing-masing
            algo_col = self.algo_colors[key]["path"]
            col      = algo_col if is_sel else tuple(c // 2 for c in algo_col)
            prefix   = "\u25b6" if is_sel else " "
            nodes_s  = str(s["nodes"]) if s["nodes"] else "-"
            ms_s     = f"{s['ms']:.1f}" if s["nodes"] else "-"
            row      = f"{prefix}{label:<5} {nodes_s:>5}n {ms_s:>7}ms"
            rt       = self.font.render(row, True, col)
            self.screen.blit(rt, (8, sy))
            sy += 14
        cy = H - 185
        pygame.draw.line(self.screen, C_BTN_BD, (10, cy - 4), (self.panel_w - 10, cy - 4), 1)
        for line in ["L-Click: Set origin/dest", "R-Click: Toggle block",
                     "Scroll: Zoom in/out", "Up/Down Key: Car speed",
                     "Drag: Pan camera"]:
            ct = self.font.render(line, True, (100, 120, 140))
            self.screen.blit(ct, (14, cy))
            cy += 15
        if self.minimap_surf:
            mm = pygame.transform.scale(self.minimap_surf, (90, 90))
            mx = self.panel_w // 2 - 45
            my = cy + 4
            self.screen.blit(mm, (mx, my))
            cs   = 90 / max(GCOLS, GROWS)
            x0, y0 = self.camera.screen_to_world(self.panel_w, 0)
            x1, y1 = self.camera.screen_to_world(W, H)
            rx = mx + int(x0 / T * cs)
            ry = my + int(y0 / T * cs)
            rw = max(2, int((x1 - x0) / T * cs))
            rh = max(2, int((y1 - y0) / T * cs))
            pygame.draw.rect(self.screen, C_ORIGIN, (rx, ry, rw, rh), 1)

    def _draw_marker(self, c, r, col, label):
        wx, wy = c * T + T // 2, r * T + T // 2
        sx, sy = self.camera.world_to_screen(wx, wy)
        sz     = max(4, int(8 * self.camera.zoom))
        pygame.draw.line(self.screen, col,
                         (int(sx), int(sy)), (int(sx), int(sy) - sz * 3), 2)
        pts = [(int(sx), int(sy) - sz * 3),
               (int(sx) + sz * 2, int(sy) - sz * 2),
               (int(sx), int(sy) - sz)]
        pygame.draw.polygon(self.screen, col, pts)
        if self.camera.zoom > 0.3:
            t = self.font.render(label, True, col)
            self.screen.blit(t, (int(sx) + 6, int(sy) - sz * 3 - 4))
        glow = pygame.Surface((sz * 4, sz * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*col, 40), (sz * 2, sz * 2), sz * 2)
        self.screen.blit(glow, (int(sx) - sz * 2, int(sy) - sz * 2))

    def _get_block_overlay(self, isz):
        """Ambil/buat overlay roadblock dari cache. Hindari alokasi Surface tiap frame."""
        if isz not in self._block_overlay_cache:
            overlay = pygame.Surface((isz, isz), pygame.SRCALPHA)
            overlay.fill((255, 30, 30, 80))
            lw = max(1, isz // 20)
            pygame.draw.line(overlay, (255, 60, 60), (0, 0), (isz, isz), lw)
            pygame.draw.line(overlay, (255, 60, 60), (isz, 0), (0, isz), lw)
            self._block_overlay_cache[isz] = overlay
        return self._block_overlay_cache[isz]

    def _get_scaled_env(self, ev, c, r, isz):
        """Ambil env surface yang sudah di-scale dari cache."""
        key = (ev, c, r, isz)
        if key not in self._env_scale_cache:
            # Eviction: bersihkan jika terlalu besar (zoom berubah → stale entries)
            if len(self._env_scale_cache) > 2000:
                self._env_scale_cache.clear()
            esurf = self.env_cache.get(ev, c, r)
            if esurf:
                if isz != T:
                    self._env_scale_cache[key] = pygame.transform.smoothscale(esurf, (isz, isz))
                else:
                    self._env_scale_cache[key] = esurf
            else:
                self._env_scale_cache[key] = None
        return self._env_scale_cache[key]

    def _get_cached_wpath(self):
        """Ambil world path dari cache. Hanya rebuild jika path berubah."""
        path_key = tuple(self.path) if self.path else None
        if path_key != self._cached_path_key:
            self._cached_path_key = path_key
            if self.path and len(self.path) >= 2:
                self._cached_wpath = build_world_path(self.grid, self.path)
            else:
                self._cached_wpath = None
        return self._cached_wpath

    def _render_map_to_surface(self, zoom, lod):
        # Calculate size of the map in pixels at this zoom
        map_w = int(GCOLS * T * zoom)
        map_h = int(GROWS * T * zoom)
        
        # Create a surface for the entire map
        surf = pygame.Surface((map_w, map_h))
        # Fill with grass color
        surf.fill(C_GRASS)
        
        C_ROAD_LOD0       = (55,  62,  85)
        C_INTERSECT_LOD0  = (75,  85, 115)
        _BLDG_TYPES = (ENV_B0, ENV_B1, ENV_B2,
                       ENV_RUMAH, ENV_RUKO, ENV_MASJID,
                       ENV_SPBU, ENV_TAMAN)
                       
        sz = T * zoom
        isz = int(sz)
        if isz < 1:
            return surf
            
        for r in range(GROWS):
            for c in range(GCOLS):
                tx = int(c * sz)
                ty = int(r * sz)
                
                t = self.grid.get(c, r)
                if t and t.type != EMPTY:
                    # ── Render jalan ──────────────────────────
                    if lod == 0:
                        col = C_INTERSECT_LOD0 if t.type in (TJUNCTION, CROSS) else C_ROAD_LOD0
                        pygame.draw.rect(surf, col, (tx, ty, isz, isz))
                    else:
                        tsurf = self.tile_cache.get(t.type, t.rotation, isz, lod)
                        if tsurf:
                            surf.blit(tsurf, (tx, ty))
                            
                    # Draw roadblock overlay
                    if (c, r) in self.blocked:
                        surf.blit(self._get_block_overlay(isz), (tx, ty))
                        
                    # Draw street lamps (LOD 1)
                    if lod == 1 and t.type in (TJUNCTION, CROSS):
                        lamp_offsets = [
                            (tx + 2,       ty + 2),
                            (tx + isz - 2, ty + 2),
                            (tx + 2,       ty + isz - 2),
                            (tx + isz - 2, ty + isz - 2),
                        ]
                        for lx, ly in lamp_offsets:
                            draw_lamp(surf, lx, ly, zoom, lod)
                else:
                    ev = self.env[r][c] if self.env else ENV_NONE
                    if lod == 0:
                        if ev in _BLDG_TYPES:
                            pygame.draw.rect(surf, (22, 28, 40), (tx, ty, isz, isz))
                    elif lod == 1:
                        if ev != ENV_TREE:
                            scaled = self._get_scaled_env(ev, c, r, isz)
                            if scaled:
                                surf.blit(scaled, (tx, ty))
        return surf

    def draw(self):
        self.screen.fill(C_BG)

        # ── Hitung LOD berdasarkan zoom ──────────────────────
        zoom = self.camera.zoom
        if zoom >= LOD_MED_ZOOM:
            lod = 2      # dekat: full detail
        elif zoom >= LOD_FAR_ZOOM:
            lod = 1      # sedang: bangunan, jalan, lampu
        else:
            lod = 0      # jauh: blok warna saja

        c0, c1, r0, r1 = self.camera.get_visible_tiles()

        # ── Draw map background (cached when lod < 2, direct when lod == 2) ──
        if lod < 2:
            blocked_hash = hash(tuple(sorted(list(self.blocked))))
            if (self._map_surf_cache is None or 
                self._map_surf_zoom != zoom or 
                self._map_surf_lod != lod or 
                self._map_surf_blocked_hash != blocked_hash):
                
                self._map_surf_cache = self._render_map_to_surface(zoom, lod)
                self._map_surf_zoom = zoom
                self._map_surf_lod = lod
                self._map_surf_blocked_hash = blocked_hash
            
            mx, my = self.camera.world_to_screen(0, 0)
            self.screen.blit(self._map_surf_cache, (int(mx), int(my)))
        else:
            # Direct rendering (lod == 2, zoom >= 0.55, very few tiles visible)
            sz = T * zoom
            isz = int(sz)
            for r in range(r0, r1):
                for c in range(c0, c1):
                    sx, sy = self.camera.world_to_screen(c * T, r * T)
                    if sx + sz < 0 or sy + sz < 0 or sx > W or sy > H:
                        continue

                    t = self.grid.get(c, r)
                    if t and t.type != EMPTY:
                        # ── Render jalan ──────────────────────────
                        surf = self.tile_cache.get(t.type, t.rotation, isz, lod)
                        if surf:
                            self.screen.blit(surf, (int(sx), int(sy)))

                        # Roadblock overlay (dari cache)
                        if (c, r) in self.blocked:
                            self.screen.blit(self._get_block_overlay(isz), (int(sx), int(sy)))

                        # ── Lampu jalan di persimpangan (LOD 2) ───
                        if t.type in (TJUNCTION, CROSS):
                            lamp_offsets = [
                                (sx + 2,       sy + 2),
                                (sx + sz - 2,  sy + 2),
                                (sx + 2,       sy + sz - 2),
                                (sx + sz - 2,  sy + sz - 2),
                            ]
                            for lx, ly in lamp_offsets:
                                draw_lamp(self.screen, lx, ly, zoom, lod)

                    else:
                        # ── Render environment ────────────────────
                        ev = self.env[r][c] if self.env else ENV_NONE
                        scaled = self._get_scaled_env(ev, c, r, isz)
                        if scaled:
                            self.screen.blit(scaled, (int(sx), int(sy)))

        # ── Explored nodes (LOD 1+, max 500 visible) ─────────
        _expl_col = self.algo_colors[self.current_algo]["explored"]
        if self.explored and lod >= 1 and zoom > 0.15:
            r2 = max(2, int(T * zoom * 0.15))
            count = 0
            for ec, er in self.explored:
                if ec < c0 or ec >= c1 or er < r0 or er >= r1:
                    continue
                sx, sy = self.camera.world_to_screen(
                    ec * T + T // 2, er * T + T // 2)
                pygame.draw.circle(self.screen, _expl_col, (int(sx), int(sy)), r2)
                count += 1
                if count > 500:
                    break

        # ── Path line (cached world path) ────────────────────
        _path_col    = self.algo_colors[self.current_algo]["path"]
        _outline_col = self.algo_colors[self.current_algo]["outline"]
        wpath = self._get_cached_wpath()
        if wpath and len(wpath) >= 2 and zoom > 0.05:
            pts  = []
            step = max(1, len(wpath) // 800)
            for i in range(0, len(wpath), step):
                wx, wy = wpath[i]
                sx, sy = self.camera.world_to_screen(wx, wy)
                pts.append((int(sx), int(sy)))
            wx, wy = wpath[-1]
            sx, sy = self.camera.world_to_screen(wx, wy)
            if not pts or pts[-1] != (int(sx), int(sy)):
                pts.append((int(sx), int(sy)))
            lw = max(2, int(3 * zoom))
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, _outline_col, False, pts, lw + 3)
                pygame.draw.lines(self.screen, _path_col,    False, pts, lw)

        # ── Markers (semua LOD) ──────────────────────────────
        if self.origin:
            self._draw_marker(self.origin[0], self.origin[1], C_ORIGIN, "A")
        if self.dest:
            self._draw_marker(self.dest[0], self.dest[1], C_DEST, "B")

        # ── Car (semua LOD) ──────────────────────────────────
        self.car.draw(self.screen, self.camera)

        self._draw_panel(lod)

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.1)  # Batasi lompatan jika FPS drop drastis
            mx, my = pygame.mouse.get_pos()
            for b in self.buttons:   b.handle((mx, my))
            for b in self.algo_btns: b.handle((mx, my))
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:  running = False
                    elif ev.key == pygame.K_SPACE: self._toggle_car()
                    elif ev.key == pygame.K_r:     self._random_path()
                    elif ev.key == pygame.K_n:     self._new_map()
                    elif ev.key == pygame.K_c:     self._clear_all()
                    elif ev.key == pygame.K_f:     self._toggle_follow()
                    elif ev.key == pygame.K_UP:    self.car.speed = min(15.0, self.car.speed + 1.0)
                    elif ev.key == pygame.K_DOWN:  self.car.speed = max(1.0, self.car.speed - 1.0)
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    if ev.pos[0] <= self.panel_w:
                        for b in self.buttons:   b.clicked(ev.pos)
                        for b in self.algo_btns: b.clicked(ev.pos)
                    else:
                        if ev.button == 1:
                            self._click_start = ev.pos
                            self._last_drag   = ev.pos
                        elif ev.button == 3:
                            self._handle_map_click(ev.pos, 3)
                        elif ev.button == 2:
                            self.camera.drag       = True
                            self.camera.drag_start = ev.pos
                elif ev.type == pygame.MOUSEBUTTONUP:
                    if ev.button == 2:
                        self.camera.drag = False
                    elif ev.button == 1:
                        if self._click_start is not None:
                            ddx = ev.pos[0] - self._click_start[0]
                            ddy = ev.pos[1] - self._click_start[1]
                            if abs(ddx) + abs(ddy) < 8:
                                self._handle_map_click(ev.pos, 1)
                        self._click_start = None
                        self._last_drag   = None
                elif ev.type == pygame.MOUSEMOTION:
                    if ev.buttons[1]:
                        if self.camera.drag_start:
                            dx = ev.pos[0] - self.camera.drag_start[0]
                            dy = ev.pos[1] - self.camera.drag_start[1]
                            self.camera.x         -= dx / self.camera.zoom
                            self.camera.y         -= dy / self.camera.zoom
                            self.camera.drag_start = ev.pos
                    elif ev.buttons[0] and ev.pos[0] > self.panel_w:
                        if self._last_drag is not None:
                            dx = ev.pos[0] - self._last_drag[0]
                            dy = ev.pos[1] - self._last_drag[1]
                            self.camera.x -= dx / self.camera.zoom
                            self.camera.y -= dy / self.camera.zoom
                        self._last_drag = ev.pos
                    else:
                        self._last_drag = None
                elif ev.type == pygame.MOUSEWHEEL:
                    factor = 1.15 if ev.y > 0 else 1 / 1.15
                    self.camera.zoom_at(mx, my, factor)
            self.car.update(dt)
            if self.car.arrived and self.btn_car.text != "Start Car":
                self.btn_car.text = "Start Car"
            if self.follow_car and self.car.active and not self.car.paused:
                self.camera.center_on(self.car.x, self.car.y)
            self.draw()
            pygame.display.flip()
        pygame.quit()
        sys.exit()


# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = ClearCityNav()
    app.run()
