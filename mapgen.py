"""
mapgen.py
=========
Modul generasi peta jalan dan environment (bangunan/pohon).

Algoritma utama: Randomized Corridor Growth (Snake Growth)
  - Tumbuhkan koridor jalan dari seed point secara acak
  - Sambungkan komponen yang terpisah (Flood Fill + BFS)
  - Sembuhkan jalan buntu (dead-end healing)
  - Cleanup dan pertahankan komponen terbesar

Fungsi publik:
  generate_map(cols, rows, seed)       -> Grid
  generate_environment(grid, seed)     -> list[list[int]]
"""

import random
from collections import deque

from grid import (
    Grid, Tile,
    EMPTY, STRAIGHT, CURVE, DIAGONAL, TJUNCTION, CROSS,
    TILE_PORTS, OPPOSITE, DIR_DELTA,
    get_ports, _tile_degree
)

# ══════════════════════════════════════════════════════════════
# ENVIRONMENT TYPE CONSTANTS
# ══════════════════════════════════════════════════════════════
ENV_NONE  = 0   # Kosong / rumput
ENV_SW    = 1   # Trotoar (sidewalk)
ENV_TREE  = 2   # Pohon
ENV_B0    = 3   # Bangunan style 0 (biru) — legacy, masih dipakai
ENV_B1    = 4   # Bangunan style 1 (merah muda) — legacy
ENV_B2    = 5   # Bangunan style 2 (kuning) — legacy
ENV_RUMAH = 6   # Rumah tinggal — atap segitiga, jendela, halaman
ENV_RUKO  = 7   # Ruko/Toko — awning/kanopi
ENV_MASJID = 8  # Masjid — kubah + menara
ENV_SPBU  = 9   # SPBU — kanopi + pompa
ENV_TAMAN = 10  # Taman — jalur setapak, bangku, pohon kecil


# ══════════════════════════════════════════════════════════════
# HELPER: PORT VALIDATION
# ══════════════════════════════════════════════════════════════
def _neighbor_required_ports(grid, c, r):
    """
    Hitung port yang WAJIB dimiliki tile (c,r) agar terhubung ke tetangganya.
    
    Cara kerja:
      Untuk setiap 4 arah (N,E,S,W), periksa apakah tetangga di arah itu
      adalah jalan yang memiliki port menghadap ke (c,r).
      Jika iya, maka tile (c,r) HARUS punya port di arah tersebut.
    
    Return: set() berisi arah-arah yang harus ada portnya.
    """
    required = set()
    for d in range(4):
        dc, dr = DIR_DELTA[d]
        nc, nr = c + dc, r + dr
        nb = grid.get(nc, nr)
        if nb and nb.type != EMPTY:
            opp = OPPOSITE[d]
            if opp in get_ports(nb.type, nb.rotation):
                required.add(d)
    return required


def _get_valid_options(grid, c, r, extra_ports=frozenset()):
    """
    Temukan semua kombinasi (tile_type, rotation) yang valid untuk tile (c,r).
    
    Valid berarti:
      1. Memenuhi semua port yang diwajibkan oleh tetangga
      2. Memiliki semua port di extra_ports
      3. Tidak punya port yang menuju tetangga yang tidak kompatibel
    
    Return: list of (tile_type, rotation)
    """
    required = _neighbor_required_ports(grid, c, r)
    required = required | set(extra_ports)
    results  = []

    for tt in [STRAIGHT, CURVE, DIAGONAL, TJUNCTION, CROSS]:
        for ri, ps in enumerate(TILE_PORTS[tt]):
            if required <= ps:              # semua port wajib terpenuhi
                ok = True
                for d in ps:
                    if d not in required:   # port ekstra: cek kompatibilitas tetangga
                        dc, dr = DIR_DELTA[d]
                        nc, nr = c + dc, r + dr
                        nb = grid.get(nc, nr)
                        if nb and nb.type != EMPTY:
                            opp = OPPOSITE[d]
                            if opp not in get_ports(nb.type, nb.rotation):
                                ok = False
                                break
                if ok:
                    results.append((tt, ri))
    return results


def _find_tile_for_ports(grid, c, r, *ports):
    """
    Temukan tile paling sederhana (degree terkecil) yang mengandung
    semua port yang diminta dan kompatibel dengan tetangganya.
    
    Return: (tile_type, rotation) atau None jika tidak ada yang cocok.
    """
    need    = frozenset(ports)
    options = _get_valid_options(grid, c, r, need)
    if not options:
        return None
    options.sort(key=lambda x: _tile_degree(x[0]))  # pilih yang paling sederhana
    return options[0]


def _upgrade_tile_port(grid, c, r, port):
    """
    Tambahkan satu port baru ke tile yang sudah ada di (c,r).
    Jika perlu, upgrade tipe tile (misal STRAIGHT → TJUNCTION).
    
    Contoh:
      Tile STRAIGHT {N,S} + port E → TJUNCTION {N,E,S}
      Tile TJUNCTION {N,E,S} + port W → CROSS {N,E,S,W}
    
    Return: True jika berhasil, False jika gagal.
    """
    t = grid.get(c, r)
    if t is None or t.type == EMPTY:
        return False
    current = set(get_ports(t.type, t.rotation))
    if port in current:
        return True     # port sudah ada, tidak perlu upgrade

    needed = current | {port}
    for tt in [STRAIGHT, CURVE, DIAGONAL, TJUNCTION, CROSS]:
        for ri, ps in enumerate(TILE_PORTS[tt]):
            if needed <= ps:
                # Cek tidak ada clash dengan tetangga
                clash = False
                for d in ps:
                    if d not in needed:
                        dc, dr = DIR_DELTA[d]
                        nc, nr = c + dc, r + dr
                        nb = grid.get(nc, nr)
                        if nb and nb.type != EMPTY:
                            opp = OPPOSITE[d]
                            if opp not in get_ports(nb.type, nb.rotation):
                                clash = True
                                break
                if not clash:
                    grid.set_tile(c, r, tt, ri)
                    return True
    return False


# ══════════════════════════════════════════════════════════════
# HELPER: INTERSECTION DENSITY CHECK
# ══════════════════════════════════════════════════════════════
def _has_adjacent_intersection(grid, c, r):
    """Cek apakah ada T-junction atau Cross tepat di sebelah (c,r)."""
    for d in range(4):
        dc, dr = DIR_DELTA[d]
        nc, nr = c + dc, r + dr
        nb = grid.get(nc, nr)
        if nb and nb.type in (TJUNCTION, CROSS):
            return True
    return False


def _count_nearby_intersections(grid, c, r, radius=3):
    """
    Hitung jumlah T-junction/Cross dalam radius Manhattan tertentu dari (c,r).
    Digunakan untuk mencegah penumpukan persimpangan (anti-clustering).
    """
    count = 0
    for dr2 in range(-radius, radius + 1):
        for dc2 in range(-radius, radius + 1):
            if dr2 == 0 and dc2 == 0:
                continue
            nb = grid.get(c + dc2, r + dr2)
            if nb and nb.type in (TJUNCTION, CROSS):
                count += 1
    return count


# ══════════════════════════════════════════════════════════════
# CORE: CORRIDOR GROWTH (Algoritma Utama Generasi Jalan)
# ══════════════════════════════════════════════════════════════
def _grow_corridor(grid, sc, sr, sd, rng, max_len=None):
    """
    Tumbuhkan satu koridor jalan mulai dari (sc, sr) ke arah sd.
    
    Algoritma: Randomized Snake/Corridor Growth
      1. Mulai dari titik (sc, sr) dengan arah sd
      2. Setiap langkah: coba tempatkan tile di (nc, nr) = (sc+dc, sr+dr)
      3. Setelah 1-2 tile lurus, belok kiri atau kanan secara acak
      4. Jika bertemu jalan lain → sambungkan dan berhenti
      5. Anti-clustering: cegah persimpangan bersebelahan
      6. 20% chance STRAIGHT → DIAGONAL (variasi visual)
    
    Parameter:
      sc, sr  : koordinat start
      sd      : arah awal (0=N, 1=E, 2=S, 3=W)
      rng     : random.Random instance
      max_len : batas panjang koridor
    
    Return: jumlah tile yang berhasil ditempatkan
    """
    cols, rows = grid.cols, grid.rows
    if max_len is None:
        max_len = max(cols, rows) * 2

    c, r, d   = sc, sr, sd
    placed         = 0
    straight_count = 0
    turn_after     = rng.randint(1, 2)  # belok setelah 1-2 tile lurus

    for _ in range(max_len):
        dc, dr = DIR_DELTA[d]
        nc, nr = c + dc, r + dr

        if not grid.in_bounds(nc, nr):
            break   # keluar dari batas grid

        # Jika bertemu jalan → sambungkan dan berhenti
        if grid.is_road(nc, nr):
            _upgrade_tile_port(grid, c, r, d)
            _upgrade_tile_port(grid, nc, nr, OPPOSITE[d])
            placed += 1
            break

        incoming = OPPOSITE[d]
        outgoing = d    # default: tetap lurus

        # Putuskan apakah perlu belok
        if straight_count >= turn_after:
            choices = [(d + 1) % 4, (d + 3) % 4]  # kanan, kiri
            rng.shuffle(choices)
            turned = False
            for td in choices:
                tdc, tdr = DIR_DELTA[td]
                fc, fr   = nc + tdc, nr + tdr
                if grid.in_bounds(fc, fr):
                    outgoing       = td
                    straight_count = 0
                    turn_after     = rng.randint(1, 2)
                    turned         = True
                    break
            if not turned:
                outgoing = d

        # Cari tile yang bisa menampung port incoming + outgoing
        info = _find_tile_for_ports(grid, nc, nr, incoming, outgoing)
        if info is None:
            info     = _find_tile_for_ports(grid, nc, nr, incoming, d)
            outgoing = d
        if info is None:
            break

        # Anti-cluster: jika tile adalah persimpangan dan sudah ada persimpangan di sebelahnya
        if info[0] in (TJUNCTION, CROSS):
            if _has_adjacent_intersection(grid, nc, nr):
                simple = _find_tile_for_ports(grid, nc, nr, incoming, d)
                if simple and simple[0] in (STRAIGHT, CURVE, DIAGONAL):
                    info     = simple
                    outgoing = d
                else:
                    break
            elif _count_nearby_intersections(grid, nc, nr, 3) >= 1:
                simple = _find_tile_for_ports(grid, nc, nr, incoming, d)
                if simple and simple[0] in (STRAIGHT, CURVE, DIAGONAL):
                    info     = simple
                    outgoing = d

        # 20% peluang STRAIGHT → DIAGONAL (variasi visual 45°)
        if info[0] == STRAIGHT and rng.random() < 0.20:
            info = (DIAGONAL, info[1])

        grid.set_tile(nc, nr, info[0], info[1])
        placed += 1

        # Upgrade tile sebelumnya agar punya port ke arah d
        if grid.is_road(c, r):
            _upgrade_tile_port(grid, c, r, d)

        c, r = nc, nr
        actual = get_ports(info[0], info[1])
        if outgoing in actual:
            d = outgoing
            if outgoing == sd or info[0] in (STRAIGHT, DIAGONAL):
                straight_count += 1
            else:
                straight_count = 0
        else:
            break

    return placed


# ══════════════════════════════════════════════════════════════
# HELPER: CONNECTIVITY & DEAD-END HEALING
# ══════════════════════════════════════════════════════════════
def _choose_border_exits(grid, rng, count=6):
    """
    Pilih beberapa titik di tepi peta untuk dijadikan 'pintu masuk/keluar' kota.
    Memastikan pintu keluar tidak terlalu berdekatan satu sama lain (jarak Manhattan >= 8).
    """
    cols, rows = grid.cols, grid.rows
    borders = []
    for c2 in range(cols):
        borders.append((c2, 0,        2))  # Tepi atas → arah Selatan
        borders.append((c2, rows - 1, 0))  # Tepi bawah → arah Utara
    for r2 in range(rows):
        borders.append((0,        r2, 1))  # Tepi kiri → arah Timur
        borders.append((cols - 1, r2, 3))  # Tepi kanan → arah Barat
    rng.shuffle(borders)

    chosen = []
    for bc, br, bd in borders:
        if grid.is_road(bc, br):
            continue
        too_close = any(abs(bc - pc) + abs(br - pr) < 8 for pc, pr, _ in chosen)
        if too_close:
            continue
        chosen.append((bc, br, bd))
        if len(chosen) >= count:
            break
    return chosen


def _bfs_path(grid, sc, sr, tc, tr):
    """
    BFS sederhana untuk mencari jalur antara dua titik di ruang grid bebas
    (tidak hanya mengikuti port jalan). Digunakan untuk menyambungkan
    komponen-komponen jalan yang terpisah.
    
    Optimized: menggunakan parent dict instead of copying path lists.
    Kompleksitas: O(V + E) di mana V = jumlah sel grid, E = koneksi antar sel
    Return: list koordinat [(c,r), ...] atau None jika tidak ada jalur.
    """
    if sc == tc and sr == tr:
        return [(sc, sr)]
    parent  = {(sc, sr): None}
    queue   = deque([(sc, sr)])
    while queue:
        cx, cy = queue.popleft()
        for d in range(4):
            dc, dr = DIR_DELTA[d]
            nc, nr = cx + dc, cy + dr
            if not grid.in_bounds(nc, nr):
                continue
            if (nc, nr) in parent:
                continue
            parent[(nc, nr)] = (cx, cy)
            if nc == tc and nr == tr:
                # Reconstruct path
                path = []
                node = (nc, nr)
                while node is not None:
                    path.append(node)
                    node = parent[node]
                path.reverse()
                return path
            queue.append((nc, nr))
    return None


def _build_road_along_path(grid, path, rng):
    """
    Bangun jalan mengikuti daftar koordinat 'path'.
    Setiap tile di path akan mendapat port sesuai arah dari/ke tile tetangganya di path.
    Jika tile sudah ada jalan, port-nya di-upgrade.
    """
    for i in range(len(path)):
        c, r        = path[i]
        ports_needed = set()

        if i > 0:           # port ke tile sebelumnya
            pc, pr = path[i - 1]
            for d in range(4):
                dcc, drr = DIR_DELTA[d]
                if c + dcc == pc and r + drr == pr:
                    ports_needed.add(d)

        if i < len(path) - 1:  # port ke tile berikutnya
            nc, nr = path[i + 1]
            for d in range(4):
                dcc, drr = DIR_DELTA[d]
                if c + dcc == nc and r + drr == nr:
                    ports_needed.add(d)

        if grid.is_road(c, r):
            for p in ports_needed:
                _upgrade_tile_port(grid, c, r, p)
        else:
            if len(ports_needed) >= 2:
                info = _find_tile_for_ports(grid, c, r, *ports_needed)
                if info:
                    grid.set_tile(c, r, info[0], info[1])


def _flood_fill(grid, sc, sr):
    """
    Flood Fill berbasis port: temukan semua tile jalan yang terhubung ke (sc, sr).
    Dua tile dianggap terhubung hanya jika keduanya memiliki port yang saling menghadap.
    
    Digunakan untuk: mendeteksi komponen terpisah (Phase 4 & 8).
    Return: set of (c, r) tile yang terhubung.
    """
    visited = set()
    stack   = [(sc, sr)]
    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in visited:
            continue
        visited.add((cx, cy))
        t = grid.get(cx, cy)
        if t is None or t.type == EMPTY:
            continue
        ports = get_ports(t.type, t.rotation)
        for d in ports:
            dc, dr = DIR_DELTA[d]
            nc, nr = cx + dc, cy + dr
            nb     = grid.get(nc, nr)
            if nb and nb.type != EMPTY:
                opp = OPPOSITE[d]
                if opp in get_ports(nb.type, nb.rotation):
                    stack.append((nc, nr))
    return visited


def _all_road_cells(grid):
    """Kumpulkan semua koordinat tile yang bukan EMPTY (adalah jalan)."""
    cells = []
    for r in range(grid.rows):
        for c in range(grid.cols):
            if grid.cells[r][c].type != EMPTY:
                cells.append((c, r))
    return cells


def _find_dead_ends(grid):
    """
    Temukan semua tile jalan yang hanya punya 1 koneksi valid (jalan buntu).
    Dead end = tile bukan CROSS dengan connected_neighbors <= 1.
    """
    dead = []
    for r in range(grid.rows):
        for c in range(grid.cols):
            t = grid.cells[r][c]
            if t.type == EMPTY:
                continue
            ports     = get_ports(t.type, t.rotation)
            connected = 0
            for d in ports:
                dc, dr = DIR_DELTA[d]
                nc, nr = c + dc, r + dr
                nb     = grid.get(nc, nr)
                if nb and nb.type != EMPTY:
                    opp = OPPOSITE[d]
                    if opp in get_ports(nb.type, nb.rotation):
                        connected += 1
            if connected <= 1 and t.type != CROSS:
                dead.append((c, r))
    return dead


def _heal_dead_ends(grid, rng, max_iters=8):
    """
    Iteratif sembuhkan jalan buntu:
      - Coba sambungkan ke jalan terdekat yang ada
      - Atau tumbuhkan koridor baru dari dead end
      - Jika tidak bisa, hapus tile buntu tersebut
    
    Maksimum 'max_iters' iterasi untuk menghindari loop tak terbatas.
    """
    for _ in range(max_iters):
        dead = _find_dead_ends(grid)
        if not dead:
            break
        rng.shuffle(dead)
        healed = 0
        for dc, dr in dead:
            t = grid.get(dc, dr)
            if t is None or t.type == EMPTY:
                continue
            ports     = get_ports(t.type, t.rotation)
            connected = 0
            for d in ports:
                ddx, ddy = DIR_DELTA[d]
                nc, nr   = dc + ddx, dr + ddy
                nb       = grid.get(nc, nr)
                if nb and nb.type != EMPTY:
                    opp = OPPOSITE[d]
                    if opp in get_ports(nb.type, nb.rotation):
                        connected += 1
            if connected >= 2:
                continue

            possible_dirs = list(range(4))
            rng.shuffle(possible_dirs)
            extended = False
            for d in possible_dirs:
                if d in ports:
                    continue
                ddx, ddy = DIR_DELTA[d]
                nc, nr   = dc + ddx, dr + ddy
                if not grid.in_bounds(nc, nr):
                    continue
                if grid.is_road(nc, nr):
                    if _upgrade_tile_port(grid, dc, dr, d):
                        _upgrade_tile_port(grid, nc, nr, OPPOSITE[d])
                        extended = True
                        healed  += 1
                        break
                else:
                    grew = _grow_corridor(grid, dc, dr, d, rng,
                                          max_len=rng.randint(3, 8))
                    if grew > 0:
                        extended = True
                        healed  += 1
                        break
            if not extended:
                grid.set_tile(dc, dr, EMPTY, 0)
                healed += 1
        if healed == 0:
            break


# ══════════════════════════════════════════════════════════════
# POST-PROCESS: ENFORCE DIAGONAL RATIO
# ══════════════════════════════════════════════════════════════
def _enforce_straight_limit(grid, rng, max_pct=0.10):
    """
    Post-processing: jika tile STRAIGHT > max_pct dari total jalan,
    konversi sebagian STRAIGHT → DIAGONAL secara acak.
    
    Tujuan: menciptakan visual yang lebih bervariasi (tidak terlalu banyak
    jalan lurus, lebih banyak jalan diagonal yang menarik secara visual).
    """
    all_roads = [
        (c, r) for r in range(grid.rows) for c in range(grid.cols)
        if grid.cells[r][c].type != EMPTY
    ]
    total = len(all_roads)
    if total == 0:
        return

    straights = [(c, r) for c, r in all_roads
                 if grid.cells[r][c].type == STRAIGHT]
    limit  = int(total * max_pct)
    excess = len(straights) - limit
    if excess <= 0:
        return

    rng.shuffle(straights)
    for c, r in straights[:excess]:
        t = grid.cells[r][c]
        grid.set_tile(c, r, DIAGONAL, t.rotation)  # pertahankan rotasi → port sama


# ══════════════════════════════════════════════════════════════
# MAIN: GENERATE MAP
# ══════════════════════════════════════════════════════════════
def generate_map(cols, rows, seed=None):
    """
    Generate peta jalan lengkap dengan 9 fase:

    Phase 1: Tanam seed points di 13+ lokasi strategis, tumbuhkan koridor
    Phase 2: 40 iterasi branching dari jalan yang sudah ada (12% chance)
    Phase 3: Scan region kosong, tanam koridor baru di area yang kosong
    Phase 4: Flood Fill → temukan komponen terpisah → sambungkan dengan BFS
    Phase 5: Tambah border exits (pintu masuk dari tepi peta)
    Phase 6: Heal dead ends (sembuhkan jalan buntu)
    Phase 7: Hapus tile yang sama sekali tidak terhubung (0 koneksi)
    Phase 8: Pertahankan hanya komponen terbesar (hapus 'pulau' kecil)
    Phase 9: Enforce diagonal limit (max 10% tile lurus)

    Parameter:
      cols, rows (int): dimensi grid
      seed       (int): seed untuk reproducibility (None = random)
    
    Return: Grid yang sudah berisi jalan.
    """
    if seed is None:
        seed = random.randint(0, 999999)
    rng      = random.Random(seed)
    grid     = Grid(cols, rows)
    max_road = int(cols * rows * 0.45)  # maksimal 45% tile adalah jalan
    m        = 4                         # margin dari tepi grid

    # ── Phase 1: Seed points ─────────────────────────────────
    seeds = [
        (cols // 2,       rows // 2),       # center
        (m,               m),               # top-left
        (cols - m,        m),               # top-right
        (m,               rows - m),        # bottom-left
        (cols - m,        rows - m),        # bottom-right
        (cols // 2,       m),               # top-center
        (cols // 2,       rows - m),        # bottom-center
        (m,               rows // 2),       # left-center
        (cols - m,        rows // 2),       # right-center
        (cols // 4,       rows // 4),       # quadrant seeds
        (3 * cols // 4,   rows // 4),
        (cols // 4,       3 * rows // 4),
        (3 * cols // 4,   3 * rows // 4),
    ]
    for _ in range(8):  # tambah 8 seed acak
        seeds.append((rng.randint(m, cols - m), rng.randint(m, rows - m)))

    for sx, sy in seeds:
        sx = max(1, min(cols - 2, sx))
        sy = max(1, min(rows - 2, sy))
        if grid.is_road(sx, sy):
            continue
        grid.set_tile(sx, sy, STRAIGHT, rng.randint(0, 1))
        dirs = list(range(4))
        rng.shuffle(dirs)
        for d in dirs[:rng.randint(2, 4)]:
            _grow_corridor(grid, sx, sy, d, rng,
                           max_len=rng.randint(8, max(cols, rows)))

    # ── Phase 2: Branching growth ────────────────────────────
    for iteration in range(40):
        if grid.road_count >= max_road:
            break
        road_cells = _all_road_cells(grid)
        if not road_cells:
            break
        rng.shuffle(road_cells)
        for rc, rr in road_cells[:max(1, len(road_cells) // 3)]:
            if grid.road_count >= max_road:
                break
            t = grid.get(rc, rr)
            if t is None:
                continue
            ports = get_ports(t.type, t.rotation)
            free  = [d for d in range(4) if d not in ports]
            if not free:
                continue
            if rng.random() > 0.12:     # 12% chance tumbuhkan cabang
                continue
            d = rng.choice(free)
            _grow_corridor(grid, rc, rr, d, rng,
                           max_len=rng.randint(6, 25))

    # ── Phase 3: Fill empty regions ──────────────────────────
    region_size = max(8, min(cols, rows) // 5)
    for ry in range(0, rows, region_size):
        if grid.road_count >= max_road:
            break
        for rx in range(0, cols, region_size):
            if grid.road_count >= max_road:
                break
            has_road = False
            for dr in range(min(region_size, rows - ry)):
                for dc in range(min(region_size, cols - rx)):
                    if grid.is_road(rx + dc, ry + dr):
                        has_road = True
                        break
                if has_road:
                    break
            if not has_road:
                sx2 = max(1, min(cols - 2, rx + region_size // 2))
                sy2 = max(1, min(rows - 2, ry + region_size // 2))
                if not grid.is_road(sx2, sy2):
                    grid.set_tile(sx2, sy2, STRAIGHT, rng.randint(0, 1))
                    dirs = list(range(4))
                    rng.shuffle(dirs)
                    for d in dirs[:rng.randint(2, 3)]:
                        _grow_corridor(grid, sx2, sy2, d, rng,
                                       max_len=rng.randint(8, 20))

    # ── Phase 4: Connect isolated components ─────────────────
    road_cells = _all_road_cells(grid)
    if road_cells:
        visited_all = set()
        components  = []
        for rc, rr in road_cells:
            if (rc, rr) in visited_all:
                continue
            comp = _flood_fill(grid, rc, rr)
            visited_all |= comp
            components.append(comp)

        if len(components) > 1:
            components.sort(key=len, reverse=True)  # terbesar dulu
            main_comp = components[0]
            for comp in components[1:]:
                # Cari pasang tile terdekat antara comp dan main_comp
                best_dist = float('inf')
                best_a = best_b = None
                comp_list = list(comp);   rng.shuffle(comp_list)
                main_list = list(main_comp); rng.shuffle(main_list)
                for ac, ar in comp_list[:50]:
                    for bc, br in main_list[:50]:
                        dd = abs(ac - bc) + abs(ar - br)
                        if dd < best_dist:
                            best_dist = dd
                            best_a = (ac, ar)
                            best_b = (bc, br)
                if best_a and best_b:
                    path = _bfs_path(grid, best_a[0], best_a[1],
                                     best_b[0], best_b[1])
                    if path:
                        _build_road_along_path(grid, path, rng)
                        main_comp = main_comp | comp

    # ── Phase 5: Border exits ─────────────────────────────────
    exits = _choose_border_exits(grid, rng, count=12)
    road_cells = _all_road_cells(grid)  # compute once, not per exit
    for ec, er, ed in exits:
        if not road_cells:
            break
        closest = min(road_cells, key=lambda p: abs(p[0] - ec) + abs(p[1] - er))
        path    = _bfs_path(grid, ec, er, closest[0], closest[1])
        if path:
            _build_road_along_path(grid, path, rng)
            road_cells = _all_road_cells(grid)  # refresh after adding roads

    # ── Phase 6: Heal dead ends ───────────────────────────────
    _heal_dead_ends(grid, rng, max_iters=10)

    # ── Phase 7: Clean isolated tiles (0 koneksi) ────────────
    for r in range(rows):
        for c in range(cols):
            t = grid.cells[r][c]
            if t.type == EMPTY:
                continue
            ports     = get_ports(t.type, t.rotation)
            connected = 0
            for d in ports:
                ddc, ddr = DIR_DELTA[d]
                nc, nr   = c + ddc, r + ddr
                nb       = grid.get(nc, nr)
                if nb and nb.type != EMPTY:
                    opp = OPPOSITE[d]
                    if opp in get_ports(nb.type, nb.rotation):
                        connected += 1
            if connected == 0:
                grid.set_tile(c, r, EMPTY, 0)

    # ── Phase 8: Keep largest connected component ─────────────
    road_cells = _all_road_cells(grid)
    if road_cells:
        best_comp   = set()
        visited_all = set()
        for rc, rr in road_cells:
            if (rc, rr) in visited_all:
                continue
            comp = _flood_fill(grid, rc, rr)
            visited_all |= comp
            if len(comp) > len(best_comp):
                best_comp = comp
        for rc, rr in road_cells:
            if (rc, rr) not in best_comp:
                grid.set_tile(rc, rr, EMPTY, 0)

    # ── Phase 9: Enforce ≤10% straight tiles ──────────────────
    _enforce_straight_limit(grid, rng, max_pct=0.10)

    return grid


# ══════════════════════════════════════════════════════════════
# ENVIRONMENT GENERATION
# ══════════════════════════════════════════════════════════════
def generate_environment(grid, seed=0):
    """
    Isi tile non-jalan dengan elemen environment berdasarkan kedekatan ke jalan.
    
    Aturan penempatan:
      - Tepat di sebelah jalan (adjacent):
          8%  → Pohon (ENV_TREE)
          22% → Bangunan (ENV_B0/B1/B2)
          70% → Trotoar (ENV_SW)
      - Diagonal dari jalan:
          25% → Bangunan
          15% → Pohon
          60% → Trotoar
      - Jauh dari jalan:
          60% → Pohon
          40% → Rumput kosong (ENV_NONE)
    
    Return: matrix 2D [rows][cols] berisi konstanta ENV_*
    """
    rng       = random.Random(seed)
    cols, rows = grid.cols, grid.rows
    env        = [[ENV_NONE] * cols for _ in range(rows)]

    for r in range(rows):
        for c in range(cols):
            if grid.is_road(c, r):
                continue

            # Cek apakah tile langsung berbatasan dengan jalan (4 arah)
            adj = any(
                grid.is_road(c + DIR_DELTA[d][0], r + DIR_DELTA[d][1])
                for d in range(4)
            )

            if adj:
                roll = rng.random()
                if roll < 0.05:
                    env[r][c] = ENV_TREE
                elif roll < 0.15:
                    # Aset spesial kota (jarang, 10%)
                    special = rng.random()
                    if special < 0.30:
                        env[r][c] = ENV_MASJID
                    elif special < 0.55:
                        env[r][c] = ENV_SPBU
                    else:
                        env[r][c] = ENV_TAMAN
                elif roll < 0.40:
                    # Bangunan: rumah atau ruko
                    broll = rng.random()
                    if broll < 0.50:
                        env[r][c] = ENV_RUMAH
                    else:
                        env[r][c] = ENV_RUKO
                else:
                    env[r][c] = ENV_SW
            else:
                # Cek apakah tile berbatasan diagonal dengan jalan
                diag = False
                for dr2 in range(-1, 2):
                    for dc2 in range(-1, 2):
                        if dr2 == 0 and dc2 == 0:
                            continue
                        if grid.is_road(c + dc2, r + dr2):
                            diag = True
                            break
                    if diag:
                        break

                if diag:
                    roll = rng.random()
                    if roll < 0.20:
                        broll = rng.random()
                        if broll < 0.45:
                            env[r][c] = ENV_RUMAH
                        elif broll < 0.80:
                            env[r][c] = ENV_RUKO
                        else:
                            env[r][c] = ENV_B0 + rng.randint(0, 2)
                    elif roll < 0.35:
                        env[r][c] = ENV_TREE
                    else:
                        env[r][c] = ENV_SW
                else:
                    env[r][c] = ENV_TREE if rng.random() < 0.6 else ENV_NONE

    return env
