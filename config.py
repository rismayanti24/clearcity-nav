"""
config.py
=========
Semua konstanta global: ukuran layar, ukuran tile, warna (cyberpunk palette),
gaya bangunan, dan parameter rendering. 
"""

# ══════════════════════════════════════════════════════════════
# SCREEN & WORLD SETTINGS
# ══════════════════════════════════════════════════════════════
W, H    = 1200, 800     # Ukuran jendela layar (lebar, tinggi) dalam piksel
T       = 80            # Ukuran satu tile dalam piksel (tile size)
RW      = 34            # Lebar badan jalan (road width) dalam piksel
SW      = 6             # Lebar trotoar / sidewalk strip dalam piksel
MG      = (T - RW) // 2 # Margin dari tepi tile ke tepi jalan (grass strip)
GCOLS   = 80            # Jumlah kolom grid peta (lebar peta dalam tile)
GROWS   = 80            # Jumlah baris grid peta (tinggi peta dalam tile)
FPS     = 60            # Frame per second

# Parameter garis putus-putus di tengah jalan
DASH_ON  = 10           # Panjang segmen garis (piksel)
DASH_OFF = 8            # Panjang celah antar garis (piksel)

# ══════════════════════════════════════════════════════════════
# CYBERPUNK NEON COLOUR PALETTE
# ══════════════════════════════════════════════════════════════
# Ground colors dibuat hampir identik agar tile tidak terlihat kotak-kotak
C_BG       = (8,   6,   16)    # Latar belakang layar (hampir hitam, purple tint)
C_GRASS    = (15,  13,  25)    # Ground tile — gelap purple-gray
C_SW       = (17,  15,  27)    # Trotoar — hampir identik dengan ground (fix kotak2)
C_ROAD     = (55,  55,  68)    # Badan jalan — aspal terang (kontras dengan ground gelap)
C_DASH     = (0,   200, 255)   # Garis putus-putus — neon cyan
C_PATH     = (255, 40,  120)   # Overlay jalur pathfinding — neon magenta
C_EXPLORED = (50,  15,  65)    # Overlay node yang dijelajahi — purple gelap
C_ORIGIN   = (0,   255, 200)   # Marker titik asal — neon teal
C_DEST     = (255, 40,  80)    # Marker titik tujuan — neon pink
C_UI       = (200, 215, 240)   # Teks utama UI
C_UIK      = (120, 140, 180)   # Teks label/key UI
C_PANEL    = (12,  10,  22)    # Latar panel kiri
C_BTN_BG   = (18,  16,  32)   # Latar tombol (normal)
C_BTN_BD   = (0,   180, 255)  # Border tombol — neon cyan
C_BTN_TXT  = (180, 220, 255)  # Teks tombol
C_BTN_HOV  = (28,  24,  50)   # Latar tombol saat hover

# ══════════════════════════════════════════════════════════════
# BUILDING STYLES — CYBERPUNK NEON
# ══════════════════════════════════════════════════════════════
# Tiga gaya bangunan: dinding gelap + jendela neon menyala
BLDG_STYLES = [
    # Style 0: Gedung korporat — neon cyan
    dict(
        wall    = (25,  30,  48),     # Dinding gelap kebiruan
        light   = (32,  38,  58),     # Highlight sisi terang
        roof    = (12,  16,  30),     # Atap sangat gelap
        win     = (0,   200, 255),    # Jendela menyala — neon cyan
        win_off = (18,  22,  38),     # Jendela mati
        neon    = (0,   140, 200),    # Aksen neon cyan
    ),
    # Style 1: Apartemen / residential — neon magenta
    dict(
        wall    = (35,  22,  42),     # Dinding gelap keunguan
        light   = (45,  30,  55),     # Highlight
        roof    = (22,  12,  28),     # Atap gelap
        win     = (255, 60,  180),    # Jendela menyala — neon magenta
        win_off = (28,  18,  35),     # Jendela mati
        neon    = (200, 40,  140),    # Aksen neon magenta
    ),
    # Style 2: Komersial — neon lime/hijau
    dict(
        wall    = (22,  35,  30),     # Dinding gelap kehijauan
        light   = (28,  45,  38),     # Highlight
        roof    = (14,  24,  20),     # Atap gelap
        win     = (100, 255, 160),    # Jendela menyala — neon lime
        win_off = (16,  28,  22),     # Jendela mati
        neon    = (60,  200, 120),    # Aksen neon lime
    ),
]

# ══════════════════════════════════════════════════════════════
# LOD & PATHFINDING COLORS — CYBERPUNK NEON
# ══════════════════════════════════════════════════════════════
LOD_FAR_ZOOM = 0.20   # zoom < ini -> LOD 0 (jauh: blok warna saja)
LOD_MED_ZOOM = 0.55   # zoom < ini -> LOD 1 (sedang), >= ini -> LOD 2 (dekat)

# A* (neon magenta/pink)
C_PATH_ASTAR         = (255, 40,  120)
C_EXPL_ASTAR         = (80,  10,  40)
C_PATH_OUTLINE_ASTAR = (180, 20,  80)

# Dijkstra (neon purple)
C_PATH_DIJKSTRA         = (180, 40,  255)
C_EXPL_DIJKSTRA         = (55,  10,  80)
C_PATH_OUTLINE_DIJKSTRA = (120, 20,  180)

# BFS (neon orange)
C_PATH_BFS         = (255, 140, 20)
C_EXPL_BFS         = (80,  42,  5)
C_PATH_OUTLINE_BFS = (180, 95,  10)
