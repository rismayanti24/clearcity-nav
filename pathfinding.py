"""
pathfinding.py
==============
Modul algoritma pencarian jalur (pathfinding) dan konversi jalur ke dunia nyata.

Algoritma yang tersedia:
  1. A* (astar)       - Informed search dengan heuristik Manhattan Distance
  2. Dijkstra         - Uniform cost search tanpa heuristik
  3. BFS (bfs_pathfind) - Breadth-First Search, level per level

Semua algoritma hanya bergerak melalui port tile yang terhubung valid,
sehingga mobil tidak bisa "menembus" jalan yang tidak tersambung.

Fungsi tambahan:
  build_world_path()  - Konversi jalur tile → jalur dunia halus (Catmull-Rom spline)
"""

import heapq
import math
from collections import deque

from grid import EMPTY, OPPOSITE, DIR_DELTA, get_ports
from config import T


# ══════════════════════════════════════════════════════════════
# A* (A-STAR) — INFORMED SEARCH
# ══════════════════════════════════════════════════════════════
def astar(grid, start, goal, blocked=None):
    """
    Algoritma A* untuk mencari jalur terpendek di grid jalan berbasis port.

    Konsep:
      f(n) = g(n) + h(n)
        g(n) = biaya sebenarnya dari start ke node n (jumlah langkah)
        h(n) = heuristik estimasi biaya dari n ke goal
               → Manhattan Distance: |nc - gc| + |nr - gr|

    Karena heuristik Manhattan Distance bersifat admissible (tidak pernah
    melebih-lebihkan biaya sebenarnya), A* dijamin menemukan jalur optimal.

    Kompleksitas Waktu : O((V + E) log V) — V = nodes, E = edges
    Kompleksitas Ruang : O(V)

    Parameter:
      grid    : objek Grid berisi tile peta
      start   : (c, r) koordinat tile asal
      goal    : (c, r) koordinat tile tujuan
      blocked : set of (c, r) yang tidak boleh dilewati (roadblock)

    Return: (path, explored)
      path     : list[(c,r)] jalur dari start ke goal, atau None
      explored : set of (c,r) semua node yang pernah diperiksa
    """
    if blocked is None:
        blocked = set()

    sc, sr = start
    gc, gr = goal

    # Validasi: start dan goal harus berupa jalan dan tidak terblokir
    if not grid.is_road(sc, sr) or not grid.is_road(gc, gr):
        return None, set()
    if (sc, sr) in blocked or (gc, gr) in blocked:
        return None, set()

    # Min-heap: (f_score, counter, c, r)
    # counter digunakan sebagai tiebreaker agar heap tidak error saat f sama
    open_h   = [(0, 0, sc, sr)]
    g_score  = {(sc, sr): 0}
    came_from = {}
    explored  = set()
    counter   = 1

    while open_h:
        f, _, cx, cy = heapq.heappop(open_h)

        if (cx, cy) in explored:
            continue
        explored.add((cx, cy))

        # Goal tercapai → rekonstruksi jalur
        if cx == gc and cy == gr:
            path = []
            n    = (gc, gr)
            while n in came_from:
                path.append(n)
                n = came_from[n]
            path.append((sc, sr))
            path.reverse()
            return path, explored

        # Expand tetangga melalui port yang valid
        t = grid.get(cx, cy)
        if t is None:
            continue
        ports = get_ports(t.type, t.rotation)

        for d in ports:
            ddc, ddr = DIR_DELTA[d]
            nc, nr   = cx + ddc, cy + ddr

            if (nc, nr) in blocked:
                continue
            nb = grid.get(nc, nr)
            if nb is None or nb.type == EMPTY:
                continue
            opp = OPPOSITE[d]
            if opp not in get_ports(nb.type, nb.rotation):
                continue  # port tidak saling menghadap → tidak terhubung

            ng = g_score[(cx, cy)] + 1  # biaya setiap langkah = 1
            if ng < g_score.get((nc, nr), float('inf')):
                g_score[(nc, nr)]  = ng
                h                  = abs(nc - gc) + abs(nr - gr)  # Manhattan
                came_from[(nc, nr)] = (cx, cy)
                heapq.heappush(open_h, (ng + h, counter, nc, nr))
                counter += 1

    return None, explored  # tidak ada jalur


# ══════════════════════════════════════════════════════════════
# DIJKSTRA — UNIFORM COST SEARCH
# ══════════════════════════════════════════════════════════════
def dijkstra(grid, start, goal, blocked=None):
    """
    Algoritma Dijkstra: seperti A* tetapi tanpa heuristik (h = 0).
    Menjelajahi node berdasarkan g_score (biaya aktual) saja.

    Karena semua edge berbobot 1 di grid ini, Dijkstra menghasilkan
    jalur yang sama dengan A*, tetapi umumnya menjelajahi lebih banyak node
    karena tidak ada panduan arah ke goal.

    Kompleksitas Waktu : O((V + E) log V)
    Kompleksitas Ruang : O(V)

    Parameter & Return: sama dengan astar()
    """
    if blocked is None:
        blocked = set()

    sc, sr = start
    gc, gr = goal

    if not grid.is_road(sc, sr) or not grid.is_road(gc, gr):
        return None, set()
    if (sc, sr) in blocked or (gc, gr) in blocked:
        return None, set()

    # Min-heap: (cost, counter, c, r)
    open_h    = [(0, 0, sc, sr)]
    g_score   = {(sc, sr): 0}
    came_from = {}
    explored  = set()
    counter   = 1

    while open_h:
        cost, _, cx, cy = heapq.heappop(open_h)

        if (cx, cy) in explored:
            continue
        explored.add((cx, cy))

        if cx == gc and cy == gr:
            path = []
            n    = (gc, gr)
            while n in came_from:
                path.append(n)
                n = came_from[n]
            path.append((sc, sr))
            path.reverse()
            return path, explored

        t = grid.get(cx, cy)
        if t is None:
            continue
        ports = get_ports(t.type, t.rotation)

        for d in ports:
            ddc, ddr = DIR_DELTA[d]
            nc, nr   = cx + ddc, cy + ddr

            if (nc, nr) in blocked:
                continue
            nb = grid.get(nc, nr)
            if nb is None or nb.type == EMPTY:
                continue
            opp = OPPOSITE[d]
            if opp not in get_ports(nb.type, nb.rotation):
                continue

            ng = g_score[(cx, cy)] + 1
            if ng < g_score.get((nc, nr), float('inf')):
                g_score[(nc, nr)]   = ng
                came_from[(nc, nr)] = (cx, cy)
                heapq.heappush(open_h, (ng, counter, nc, nr))
                counter += 1

    return None, explored


# ══════════════════════════════════════════════════════════════
# BFS — BREADTH-FIRST SEARCH
# ══════════════════════════════════════════════════════════════
def bfs_pathfind(grid, start, goal, blocked=None):
    """
    Algoritma BFS: menjelajahi node level per level menggunakan queue FIFO.

    Pada graf tak berbobot (semua edge = 1), BFS selalu menemukan
    jalur dengan jumlah langkah PALING SEDIKIT (jalur terpendek).

    Perbedaan dengan Dijkstra/A*:
      - Menggunakan queue biasa (deque), bukan priority queue (heapq)
      - Tidak ada g_score / f_score
      - Lebih sederhana implementasinya
      - Sama-sama O(V+E) dalam worst case, tapi tidak pakai log(V) dari heap

    Kompleksitas Waktu : O(V + E)
    Kompleksitas Ruang : O(V)

    Parameter & Return: sama dengan astar()
    """
    if blocked is None:
        blocked = set()

    sc, sr = start
    gc, gr = goal

    if not grid.is_road(sc, sr) or not grid.is_road(gc, gr):
        return None, set()
    if (sc, sr) in blocked or (gc, gr) in blocked:
        return None, set()

    visited   = {(sc, sr)}
    came_from = {}
    queue     = deque([(sc, sr)])
    explored  = set()

    while queue:
        cx, cy = queue.popleft()
        explored.add((cx, cy))

        if cx == gc and cy == gr:
            path = []
            n    = (gc, gr)
            while n in came_from:
                path.append(n)
                n = came_from[n]
            path.append((sc, sr))
            path.reverse()
            return path, explored

        t = grid.get(cx, cy)
        if t is None:
            continue
        ports = get_ports(t.type, t.rotation)

        for d in ports:
            ddc, ddr = DIR_DELTA[d]
            nc, nr   = cx + ddc, cy + ddr

            if (nc, nr) in visited or (nc, nr) in blocked:
                continue
            nb = grid.get(nc, nr)
            if nb is None or nb.type == EMPTY:
                continue
            opp = OPPOSITE[d]
            if opp not in get_ports(nb.type, nb.rotation):
                continue

            visited.add((nc, nr))
            came_from[(nc, nr)] = (cx, cy)
            queue.append((nc, nr))

    return None, explored


# ══════════════════════════════════════════════════════════════
# CATMULL-ROM SPLINE — SMOOTH PATH INTERPOLATION
# ══════════════════════════════════════════════════════════════
def _catmull_rom_segment(p0, p1, p2, p3, steps=20):
    """
    Hitung satu segmen Catmull-Rom spline dari p1 ke p2.
    p0 dan p3 digunakan sebagai panduan tangent (tidak dilalui).

    Formula (alpha = 0.5, Catmull-Rom standar):
      h0 = -0.5t³ + t²   - 0.5t
      h1 =  1.5t³ - 2.5t² + 1.0
      h2 = -1.5t³ + 2.0t² + 0.5t
      h3 =  0.5t³ - 0.5t²
      x  = h0·P0.x + h1·P1.x + h2·P2.x + h3·P3.x
      y  = h0·P0.y + h1·P1.y + h2·P2.y + h3·P3.y

    Menghasilkan kurva C1-continuous (tangent mulus di setiap knot).

    Parameter:
      p0, p1, p2, p3 : tuple (x, y) titik kontrol
      steps          : jumlah titik interpolasi per segmen

    Return: list of (x, y) sebanyak steps+1 titik
    """
    pts = []
    for i in range(steps + 1):
        t  = i / steps
        t2 = t * t
        t3 = t2 * t

        h0 = -0.5 * t3 + t2 - 0.5 * t
        h1 =  1.5 * t3 - 2.5 * t2 + 1.0
        h2 = -1.5 * t3 + 2.0 * t2 + 0.5 * t
        h3 =  0.5 * t3 - 0.5 * t2

        x = h0 * p0[0] + h1 * p1[0] + h2 * p2[0] + h3 * p3[0]
        y = h0 * p0[1] + h1 * p1[1] + h2 * p2[1] + h3 * p3[1]
        pts.append((x, y))
    return pts


def build_world_path(grid, tile_path):
    """
    Konversi jalur tile [(c, r), ...] ke jalur dunia yang ultra-halus
    menggunakan Catmull-Rom spline.

    Strategi:
      1. Setiap pusat tile jadi 'knot' utama
      2. Tambahkan ghost knot (refleksi) di kedua ujung agar spline
         mulai dan berakhir tepat di pusat tile pertama/terakhir
      3. Interpolasi 18 titik per segmen antar knot
      4. Hasilnya: polyline halus tanpa patahan (C1-continuous)

    Return: list of (wx, wy) dalam koordinat dunia (piksel)
    """
    if not tile_path:
        return []
    if len(tile_path) == 1:
        c, r = tile_path[0]
        return [(c * T + T // 2, r * T + T // 2)]

    # Konversi tile ke koordinat dunia (pusat tile)
    knots = [(c * T + T // 2, r * T + T // 2) for c, r in tile_path]

    # Ghost knot: refleksi titik pertama dan terakhir
    g0 = (2 * knots[0][0]  - knots[1][0],
          2 * knots[0][1]  - knots[1][1])
    gn = (2 * knots[-1][0] - knots[-2][0],
          2 * knots[-1][1] - knots[-2][1])
    full = [g0] + knots + [gn]

    STEPS = 18   # titik interpolasi per segmen (lebih tinggi = lebih halus)

    wpts = []
    for i in range(1, len(full) - 2):   # iterasi knot asli
        p0, p1, p2, p3 = full[i - 1], full[i], full[i + 1], full[i + 2]
        seg = _catmull_rom_segment(p0, p1, p2, p3, STEPS)
        if i == 1:
            wpts.extend(seg)        # sertakan titik awal segmen pertama
        else:
            wpts.extend(seg[1:])    # skip titik duplikat di sambungan segmen

    return wpts
