"""
main.py
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
  main.py     → ClearCityNav (main app) + entry point

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
        pygame.display.set_caption("Snake Growth Engine — Nav Simulator")
        self.clock   = pygame.time.Clock()
        self.font    = pygame.font.SysFont("consolas", 13)
        self.font_b  = pygame.font.SysFont("consolas", 15, bold=True)
        self.font_t  = pygame.font.SysFont("consolas", 20, bold=True)

        self.panel_w = 220
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

        # ── Panel scroll state ────────────────────────────────
        self.panel_scroll     = 0
        self.panel_scroll_max = 0
        self._panel_content_h = 0     # total content height (set by _draw_panel)
        self._panel_scroll_area_top = 310   # y where scrollable area starts

        # ── Minimap interaction state ─────────────────────────
        self._mm_rect  = None         # pygame.Rect of minimap on screen
        self._mm_drag  = False        # dragging on minimap?

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
        self.btn_car = Button(bx, by, bw, bh, "Mulai Mobil", self._toggle_car)
        self.buttons = [
            self.btn_car,
            Button(bx, by + gap,     bw, bh, "Rute Acak",  self._random_path),
            Button(bx, by + gap * 2, bw, bh, "Peta Baru",  self._new_map),
            Button(bx, by + gap * 3, bw, bh, "Hapus Semua",self._clear_all),
            Button(bx, by + gap * 4, bw, bh, "Ikuti Mobil", self._toggle_follow),
            Button(bx, by + gap * 5, bw, bh, "Tengah Peta", self._center_view),
        ]

        abw, abh, aby = 57, 22, 282
        self.algo_btns = [
            Button(10,               aby, abw, abh, "A*",       lambda: self._set_algo("astar")),
            Button(10 + abw + 3,     aby, abw, abh, "Dijkstra", lambda: self._set_algo("dijkstra")),
            Button(10 + abw * 2 + 6, aby, abw, abh, "BFS",      lambda: self._set_algo("bfs")),
        ]
        self.algo_btns[0].is_active = True

        self._rebuild_map()
        
    # ── Anggota kelompok (ubah sesuai nama tim) ──────────────────
    _MEMBERS = [
        "1. Rismayanti — 2401020041",
        "2. Nikita Arzetty Siregar — 2401020030",
        "3. Erlinda Amira Putri Sudarmono — 2401020021",
        "4. Dhini Khairunnisa — 2401020016",
    ]

    # Menampilkan layar loading saat proses generate map berlangsung
    def _show_loading(self, msg="Memuat peta...", progress=0.0):
        """
        progress : float 0.0–1.0 untuk progress bar.
        """
        self.screen.fill(C_BG)

        cy = H // 2 - 90

        # ── Garis dekorasi atas ───────────────────────────────
        pygame.draw.line(self.screen, C_BTN_BD,
                         (W // 2 - 320, cy - 18), (W // 2 + 320, cy - 18), 1)

        # ── Judul aplikasi ────────────────────────────────────
        title = self.font_t.render("Snake Growth Engine — Nav Simulator", True, C_BTN_BD)
        self.screen.blit(title, (W // 2 - title.get_width() // 2, cy))
        cy += title.get_height() + 8

        # ── Garis dekorasi bawah judul ────────────────────────
        pygame.draw.line(self.screen, C_BTN_BD,
                         (W // 2 - 320, cy + 4), (W // 2 + 320, cy + 4), 1)
        cy += 18

        # ── Pesan loading ─────────────────────────────────────
        lmsg = self.font_b.render(msg, True, C_UI)
        self.screen.blit(lmsg, (W // 2 - lmsg.get_width() // 2, cy))
        cy += lmsg.get_height() + 10

        # ── Progress bar ──────────────────────────────────────
        bar_w, bar_h = 500, 12
        bar_x = W // 2 - bar_w // 2
        # Background
        pygame.draw.rect(self.screen, (30, 45, 60),
                         (bar_x, cy, bar_w, bar_h), border_radius=6)
        # Fill
        fill_w = int(bar_w * max(0.0, min(1.0, progress)))
        if fill_w > 0:
            pygame.draw.rect(self.screen, C_BTN_BD,
                             (bar_x, cy, fill_w, bar_h), border_radius=6)
        # Border
        pygame.draw.rect(self.screen, C_BTN_BD,
                         (bar_x, cy, bar_w, bar_h), 1, border_radius=6)
        # Persentase
        pct = self.font.render(f"{int(progress * 100)}%", True, C_UIK)
        self.screen.blit(pct, (W // 2 - pct.get_width() // 2, cy + bar_h + 4))
        cy += bar_h + 24

        # ── Anggota kelompok ──────────────────────────────────
        pygame.draw.line(self.screen, (30, 50, 70),
                         (W // 2 - 200, cy), (W // 2 + 200, cy), 1)
        cy += 6
        hdr = self.font.render("Anggota Kelompok", True, C_BTN_BD)
        self.screen.blit(hdr, (W // 2 - hdr.get_width() // 2, cy))
        cy += hdr.get_height() + 4
        for name in self._MEMBERS:
            nt = self.font.render(name, True, C_UIK)
            self.screen.blit(nt, (W // 2 - nt.get_width() // 2, cy))
            cy += nt.get_height() + 2

        pygame.display.flip()

    def _rebuild_map(self):
        t0 = time.time()
        self._show_loading("Membangun jaringan jalan kota...", progress=0.05)
        self.grid = generate_map(GCOLS, GROWS, self.seed)
        t1 = time.time()
        self._show_loading(
            f"Jaringan jalan selesai ({t1-t0:.1f}s) — Memuat lingkungan kota...",
            progress=0.50)
        self.env = generate_environment(self.grid, self.seed)
        t2 = time.time()
        self._show_loading(
            f"Lingkungan selesai ({t2-t1:.1f}s) — Membangun cache render...",
            progress=0.85)
        self.tile_cache.build()
        self.env_cache.build()
        self.minimap_surf = build_minimap(self.grid)
        t3 = time.time()
        self._show_loading("Peta siap! Memulai simulasi...", progress=1.0)
        print(f"Map generated in {t3-t0:.2f}s (road={t1-t0:.2f}s env={t2-t1:.2f}s cache={t3-t2:.2f}s)")
        self.origin = None
        self.dest   = None
        self.path   = None
        self.explored = set()
        self.blocked  = set()
        self.car      = Car()
        self.btn_car.text = "Mulai Mobil"
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
            self.btn_car.text = "Lanjut Mobil" if self.car.paused else "Jeda Mobil"
        elif self.path and len(self.path) >= 2:
            wpath = build_world_path(self.grid, self.path)
            self.car.set_path(wpath)
            self.btn_car.text = "Jeda Mobil"

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
        self.btn_car.text = "Mulai Mobil"
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
            self.btn_car.text = "Mulai Mobil"
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
                self.btn_car.text = "Lanjut Mobil"
            else:
                self.car.paused   = False
                self.btn_car.text = "Jeda Mobil"
        else:
            # Tidak ada jalur alternatif → berhentikan mobil
            self.car.active   = False
            self.car.arrived  = False
            self.btn_car.text = "Mulai Mobil"

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
        # ── Panel background ─────────────────────────────────
        panel = pygame.Surface((self.panel_w, H), pygame.SRCALPHA)
        panel.fill((20, 28, 38, 230))
        self.screen.blit(panel, (0, 0))
        pygame.draw.line(self.screen, C_BTN_BD, (self.panel_w, 0), (self.panel_w, H), 1)

        # ── Header ────────────────────────────────────────────
        # Latar header
        hdr_bg = pygame.Surface((self.panel_w, 62), pygame.SRCALPHA)
        hdr_bg.fill((0, 40, 70, 180))
        self.screen.blit(hdr_bg, (0, 0))
        # Garis aksen atas
        pygame.draw.line(self.screen, C_BTN_BD, (0, 0), (self.panel_w, 0), 2)
        # Judul utama
        t = self.font_t.render("NAV SIM", True, C_BTN_BD)
        self.screen.blit(t, (self.panel_w // 2 - t.get_width() // 2, 6))
        # Subjudul
        st = self.font.render("Snake Growth Engine", True, C_UI)
        self.screen.blit(st, (self.panel_w // 2 - st.get_width() // 2, 30))
        # Garis bawah header
        pygame.draw.line(self.screen, C_BTN_BD, (5, 46), (self.panel_w - 5, 46), 1)

        # ── Buttons ───────────────────────────────────────────
        for b in self.buttons:
            b.draw(self.screen, self.font)

        # ── Algorithm selector ────────────────────────────────
        pygame.draw.line(self.screen, C_BTN_BD, (10, 276), (self.panel_w - 10, 276), 1)
        for b in self.algo_btns:
            b.draw(self.screen, self.font)

        # ── Precompute stats ──────────────────────────────────
        total_road = sum(self.tile_counts.values())
        str_count  = self.tile_counts.get(STRAIGHT, 0)
        str_pct    = (str_count / total_road * 100) if total_road else 0
        str_ok     = str_pct <= 10.0

        C_BIGOH    = (80, 255, 180)
        C_STR_OK   = (0, 220, 100)
        C_STR_OVER = (255, 80, 60)
        str_col    = C_STR_OK if str_ok else C_STR_OVER

        _complexity = {
            "astar":    ("O((V+E)logV)", "O(V)"),
            "dijkstra": ("O((V+E)logV)", "O(V)"),
            "bfs":      ("O(V+E)",       "O(V)"),
        }
        time_o, space_o = _complexity[self.current_algo]

        car_status = ("ARRIVED" if self.car.arrived else
                      "PAUSED"  if self.car.paused  else
                      "ACTIVE"  if self.car.active  else "IDLE")

        # ── Build content list for scrollable area ────────────
        # Each item: ("section", title) or ("row", key, val, color)
        items = []
        items.append(("section", "STATISTIK PETA"))
        items.append(("row", "Seed",   str(self.seed), C_UI))
        items.append(("row", "Jalan",  str(total_road), C_UI))
        items.append(("row", "Lurus",    f"{str_count} ({str_pct:.1f}%)", str_col))
        items.append(("row", "Diag",   str(self.tile_counts.get(DIAGONAL, 0)), C_UI))
        items.append(("row", "Tikungan",  str(self.tile_counts.get(CURVE, 0)), C_UI))
        items.append(("row", "Pertigaan",  str(self.tile_counts.get(TJUNCTION, 0)), C_UI))
        items.append(("row", "Persimpangan",  str(self.tile_counts.get(CROSS, 0)), C_UI))
        items.append(("gap",))
        items.append(("section", "PATHFINDING"))
        items.append(("row", "Mode",     self.placing_mode.upper(), C_UI))
        items.append(("row", "Blokir",   str(len(self.blocked)), C_UI))
        items.append(("row", "Node",    str(self.astar_nodes), C_UI))
        items.append(("row", "Waktu ms",  f"{self.astar_time:.2f}", C_UI))
        items.append(("row", "Jalur",     str(len(self.path)) if self.path else "\u2014", C_UI))
        items.append(("row", "Time O",   time_o, C_BIGOH))
        items.append(("row", "Space O",  space_o, C_BIGOH))
        items.append(("gap",))
        items.append(("section", "MOBIL & TAMPILAN"))
        items.append(("row", "Mobil",    car_status, C_UI))
        items.append(("row", "Ikuti", "YA" if self.follow_car else "TIDAK", C_UI))
        items.append(("row", "Kecepatan",  f"{self.car.speed:.1f} px/f", C_UI))
        items.append(("row", "LOD",    ["JAUH", "SEDANG", "DEKAT"][lod], C_UI))
        items.append(("row", "Zoom",   f"{self.camera.zoom:.2f}", C_UI))
        items.append(("row", "FPS",    str(int(self.clock.get_fps())), C_UI))
        items.append(("gap",))
        items.append(("section", "PERBANDINGAN ALGO"))
        _algo_labels = [("A*", "astar"), ("Dijk", "dijkstra"), ("BFS", "bfs")]
        # Cari nilai max node untuk normalisasi bar
        _max_nodes = max((self.algo_stats[k]["nodes"] for _, k in _algo_labels), default=1) or 1
        for label, key in _algo_labels:
            s      = self.algo_stats[key]
            is_sel = (key == self.current_algo)
            algo_col = self.algo_colors[key]["path"]
            col      = algo_col if is_sel else tuple(c // 2 for c in algo_col)
            prefix   = "\u25b6" if is_sel else " "
            nodes_s  = str(s["nodes"]) if s["nodes"] else "-"
            ms_s     = f"{s['ms']:.1f}" if s["nodes"] else "-"
            row_txt  = f"{prefix}{label:<5} {nodes_s:>5}n {ms_s:>7}ms"
            items.append(("algo", row_txt, col))
            # Mini bar proporsi node
            items.append(("algobar", s["nodes"], _max_nodes, algo_col, is_sel))
        items.append(("gap",))

        # ── Measure total content height ──────────────────────
        total_h = 0
        for item in items:
            if item[0] == "section":
                total_h += 17
            elif item[0] == "row":
                total_h += 14
            elif item[0] == "algo":
                total_h += 14
            elif item[0] == "algobar":
                total_h += 16
            elif item[0] == "ctrl":
                total_h += 14
            elif item[0] == "gap":
                total_h += 4
        self._panel_content_h = total_h

        # ── Scrollable area dimensions ────────────────────────
        ctrl_lines = [
            "[L-Klik] Set asal/tujuan",
            "[R-Klik] Toggle blokir",
            "[Scroll] Zoom in/out",
            "[↑/↓]   Kecepatan mobil",
            "[Drag]  Geser kamera",
        ]
        footer_h   = 17 + len(ctrl_lines) * 13 + 6  # section + lines + padding
        scroll_top = self._panel_scroll_area_top
        scroll_bot = H - footer_h                    # sisakan ruang untuk footer
        visible_h  = scroll_bot - scroll_top
        self.panel_scroll_max = max(0, total_h - visible_h)
        self.panel_scroll = max(0, min(self.panel_scroll, self.panel_scroll_max))

        # ── Render scrollable content with clipping ───────────
        old_clip = self.screen.get_clip()
        self.screen.set_clip(pygame.Rect(0, scroll_top, self.panel_w, visible_h))

        sy = scroll_top - self.panel_scroll
        for item in items:
            if item[0] == "section":
                title = item[1]
                if sy + 17 > scroll_top - 20 and sy < scroll_bot + 20:
                    pygame.draw.line(self.screen, (40, 55, 70),
                                     (10, sy), (self.panel_w - 10, sy), 1)
                    hdr = self.font.render(title, True, C_BTN_BD)
                    self.screen.blit(hdr, (self.panel_w // 2 - hdr.get_width() // 2, sy + 3))
                sy += 17
            elif item[0] == "row":
                _, key, val, vc = item
                if sy + 14 > scroll_top - 20 and sy < scroll_bot + 20:
                    kt = self.font.render(f"{key}:", True, C_UIK)
                    vt = self.font.render(val, True, vc)
                    self.screen.blit(kt, (14, sy))
                    self.screen.blit(vt, (self.panel_w - 14 - vt.get_width(), sy))
                sy += 14
            elif item[0] == "algo":
                _, row_txt, col = item
                if sy + 14 > scroll_top - 20 and sy < scroll_bot + 20:
                    rt = self.font.render(row_txt, True, col)
                    self.screen.blit(rt, (8, sy))
                sy += 14
            elif item[0] == "algobar":
                _, nodes, max_n, col, is_sel = item
                if sy + 16 > scroll_top - 20 and sy < scroll_bot + 20:
                    pct_val = int(nodes / max_n * 100) if max_n else 0
                    pct_txt = self.font.render(f"{pct_val}%", True,
                                               col if is_sel else tuple(c // 2 for c in col))
                    pct_w   = pct_txt.get_width()
                    bar_x   = 14
                    bar_total = self.panel_w - bar_x - pct_w - 8
                    fill    = int(bar_total * nodes / max_n) if max_n else 0
                    bar_h   = 9
                    # Background bar
                    pygame.draw.rect(self.screen, (18, 28, 40),
                                     (bar_x, sy + 2, bar_total, bar_h), border_radius=4)
                    # Fill bar
                    if fill > 0:
                        pygame.draw.rect(self.screen, col,
                                         (bar_x, sy + 2, fill, bar_h), border_radius=4)
                        # Highlight strip
                        hi_col = tuple(min(255, c + 80) for c in col)
                        pygame.draw.rect(self.screen, hi_col,
                                         (bar_x, sy + 2, fill, 3), border_radius=4)
                    # Border
                    bd_col = col if is_sel else tuple(c // 3 for c in col)
                    pygame.draw.rect(self.screen, bd_col,
                                     (bar_x, sy + 2, bar_total, bar_h), 1, border_radius=4)
                    # Label % di kanan bar dengan jarak aman
                    self.screen.blit(pct_txt, (bar_x + bar_total + 4, sy + 1))
                sy += 16
            elif item[0] == "ctrl":
                _, line = item
                if sy + 14 > scroll_top - 20 and sy < scroll_bot + 20:
                    ct = self.font.render(line, True, (80, 100, 125))
                    self.screen.blit(ct, (14, sy))
                sy += 14
            elif item[0] == "gap":
                sy += 4

        self.screen.set_clip(old_clip)

        # ── Scroll indicator (right edge of panel) ────────────
        if self.panel_scroll_max > 0:
            bar_h  = max(20, int(visible_h * visible_h / total_h))
            bar_y  = scroll_top + int((visible_h - bar_h) * self.panel_scroll / self.panel_scroll_max)
            bar_r  = pygame.Rect(self.panel_w - 4, bar_y, 3, bar_h)
            pygame.draw.rect(self.screen, (80, 100, 130, 150), bar_r, border_radius=1)

        # ── Footer tetap: KONTROL (selalu tampil di bawah panel) ─
        fy = H - footer_h
        # Background footer
        foot_bg = pygame.Surface((self.panel_w, footer_h), pygame.SRCALPHA)
        foot_bg.fill((15, 22, 32, 240))
        self.screen.blit(foot_bg, (0, fy))
        # Garis pemisah atas footer
        pygame.draw.line(self.screen, C_BTN_BD, (5, fy), (self.panel_w - 5, fy), 1)
        fy += 3
        # Header KONTROL
        hdr = self.font.render("KONTROL", True, C_BTN_BD)
        self.screen.blit(hdr, (self.panel_w // 2 - hdr.get_width() // 2, fy))
        fy += 14
        for line in ctrl_lines:
            ct = self.font.render(line, True, (80, 100, 125))
            self.screen.blit(ct, (10, fy))
            fy += 13

    def _draw_minimap(self):
        """Draw interactive minimap at the bottom-right corner of the screen."""
        if not self.minimap_surf:
            return
        mm_size = 160
        margin  = 10
        mx = W - mm_size - margin
        my = H - mm_size - margin - 18  # extra space for title

        # ── Title ─────────────────────────────────────────────
        title = self.font.render("MINIMAP  (click to navigate)", True, C_UIK)
        title_y = my - 2
        # Background behind title
        tbg = pygame.Surface((mm_size + 8, 16), pygame.SRCALPHA)
        tbg.fill((20, 28, 38, 200))
        self.screen.blit(tbg, (mx - 4, title_y - 2))
        self.screen.blit(title, (mx, title_y))

        my += 14  # shift map down below title

        # ── Background ────────────────────────────────────────
        bg = pygame.Surface((mm_size + 8, mm_size + 8), pygame.SRCALPHA)
        bg.fill((20, 28, 38, 200))
        self.screen.blit(bg, (mx - 4, my - 4))

        # ── Minimap image ─────────────────────────────────────
        mm = pygame.transform.scale(self.minimap_surf, (mm_size, mm_size))
        self.screen.blit(mm, (mx, my))

        # ── Store rect for click detection ────────────────────
        self._mm_rect = pygame.Rect(mx, my, mm_size, mm_size)
        cs = mm_size / max(GCOLS, GROWS)

        # ── Draw path on minimap ──────────────────────────────
        wpath = self._get_cached_wpath()
        if wpath and len(wpath) >= 2:
            _path_col = self.algo_colors[self.current_algo]["path"]
            pts = []
            step = max(1, len(wpath) // 200)
            for i in range(0, len(wpath), step):
                wx, wy = wpath[i]
                px = mx + int(wx / T * cs)
                py = my + int(wy / T * cs)
                pts.append((px, py))
            # Add last point
            wx, wy = wpath[-1]
            last_pt = (mx + int(wx / T * cs), my + int(wy / T * cs))
            if not pts or pts[-1] != last_pt:
                pts.append(last_pt)
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, _path_col, False, pts, 2)

        # ── Draw origin marker ────────────────────────────────
        if self.origin:
            oc, or_ = self.origin
            ox = mx + int((oc + 0.5) * cs)
            oy = my + int((or_ + 0.5) * cs)
            pygame.draw.circle(self.screen, C_ORIGIN, (ox, oy), 4)
            pygame.draw.circle(self.screen, (255, 255, 255), (ox, oy), 4, 1)

        # ── Draw dest marker ──────────────────────────────────
        if self.dest:
            dc, dr = self.dest
            dx = mx + int((dc + 0.5) * cs)
            dy = my + int((dr + 0.5) * cs)
            pygame.draw.circle(self.screen, C_DEST, (dx, dy), 4)
            pygame.draw.circle(self.screen, (255, 255, 255), (dx, dy), 4, 1)

        # ── Draw car position ─────────────────────────────────
        if self.car.active:
            car_px = mx + int(self.car.x / T * cs)
            car_py = my + int(self.car.y / T * cs)
            pygame.draw.circle(self.screen, (255, 255, 0), (car_px, car_py), 3)

        # ── Viewport rectangle ────────────────────────────────
        x0, y0 = self.camera.screen_to_world(self.panel_w, 0)
        x1, y1 = self.camera.screen_to_world(W, H)
        rx = mx + int(x0 / T * cs)
        ry = my + int(y0 / T * cs)
        rw = max(2, int((x1 - x0) / T * cs))
        rh = max(2, int((y1 - y0) / T * cs))
        pygame.draw.rect(self.screen, (255, 255, 255), (rx, ry, rw, rh), 1)

        # ── Border ────────────────────────────────────────────
        pygame.draw.rect(self.screen, C_BTN_BD, (mx - 4, my - 4, mm_size + 8, mm_size + 8), 1)

    def _handle_minimap_click(self, pos):
        """Handle click on minimap: move camera to that world position."""
        if not self._mm_rect or not self._mm_rect.collidepoint(pos):
            return False
        mm_size = self._mm_rect.width
        cs = mm_size / max(GCOLS, GROWS)
        # Convert click position to world coordinates
        local_x = pos[0] - self._mm_rect.x
        local_y = pos[1] - self._mm_rect.y
        world_x = local_x / cs * T
        world_y = local_y / cs * T
        self.camera.center_on(world_x, world_y)
        return True

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
        
        C_ROAD_LOD0       = (50,  50,  62)
        C_INTERSECT_LOD0  = (65,  65,  78)
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
                            pygame.draw.rect(surf, (25, 22, 38), (tx, ty, isz, isz))
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
        self._draw_minimap()

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
                    # Check minimap click first (it's on top)
                    if ev.button == 1 and self._handle_minimap_click(ev.pos):
                        self._mm_drag = True
                    elif ev.pos[0] <= self.panel_w:
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
                        if self._mm_drag:
                            self._mm_drag = False
                        elif self._click_start is not None:
                            ddx = ev.pos[0] - self._click_start[0]
                            ddy = ev.pos[1] - self._click_start[1]
                            if abs(ddx) + abs(ddy) < 8:
                                self._handle_map_click(ev.pos, 1)
                        self._click_start = None
                        self._last_drag   = None
                elif ev.type == pygame.MOUSEMOTION:
                    # Minimap drag
                    if self._mm_drag and ev.buttons[0]:
                        self._handle_minimap_click(ev.pos)
                    elif ev.buttons[1]:
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
                    # Scroll panel if mouse is over it
                    if mx <= self.panel_w and my >= self._panel_scroll_area_top:
                        self.panel_scroll -= ev.y * 30
                        self.panel_scroll = max(0, min(self.panel_scroll, self.panel_scroll_max))
                    else:
                        factor = 1.15 if ev.y > 0 else 1 / 1.15
                        self.camera.zoom_at(mx, my, factor)
            self.car.update(dt)
            if self.car.arrived and self.btn_car.text != "Mulai Mobil":
                self.btn_car.text = "Mulai Mobil"
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