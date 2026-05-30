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
# REALISTIC CITY COLOUR PALETTE
# ══════════════════════════════════════════════════════════════
C_BG       = (25,  45,  28)    # Warna latar belakang layar (hijau gelap)
C_GRASS    = (52, 120,  52)    # Warna rumput — hijau cerah realistis
C_SW       = (58, 105,  50)    # Warna trotoar — hijau sedikit lebih gelap (rumput rapi)
C_ROAD     = (58,  58,  62)    # Warna badan jalan — aspal abu gelap
C_DASH     = (220, 210, 170)   # Warna garis putus-putus — kuning pucat
C_PATH     = (0,   210, 110)   # Warna overlay jalur hasil pathfinding
C_EXPLORED = (40,  80,  140)   # Warna overlay node yang dijelajahi algoritma
C_ORIGIN   = (0,   220, 80)    # Warna marker titik asal / origin
C_DEST     = (220, 50,  50)    # Warna marker titik tujuan / destination
C_UI       = (200, 220, 240)   # Warna teks utama UI
C_UIK      = (140, 160, 190)   # Warna teks label/key UI
C_PANEL    = (20,  28,  38)    # Warna latar panel kiri
C_BTN_BG   = (28,  36,  48)    # Warna latar tombol (normal)
C_BTN_BD   = (0,   180, 255)   # Warna border tombol
C_BTN_TXT  = (200, 220, 255)   # Warna teks tombol
C_BTN_HOV  = (40,  60,  80)    # Warna latar tombol saat hover

# ══════════════════════════════════════════════════════════════
# BUILDING STYLES
# ══════════════════════════════════════════════════════════════
# Tiga gaya bangunan realistis dengan warna cerah dan kontras
# Setiap style: dinding, highlight, atap, jendela menyala/mati, aksen
BLDG_STYLES = [
    # Style 0: Gedung korporat / perkantoran (abu-biru)
    dict(
        wall    = (130, 145, 160),  # Dinding abu-biru cerah
        light   = (150, 165, 180),  # Highlight sisi terang
        roof    = (70,  90,  110),  # Atap abu gelap
        win     = (140, 200, 255),  # Jendela menyala (biru cerah)
        win_off = (80,  95,  110),  # Jendela mati
        neon    = (60,  100, 140),  # Aksen border
    ),
    # Style 1: Apartemen / residential (krem-coklat)
    dict(
        wall    = (170, 140, 110),  # Dinding krem hangat
        light   = (185, 155, 125),  # Highlight
        roof    = (160, 65,  45),   # Atap merah bata
        win     = (255, 220, 160),  # Jendela menyala (kuning hangat)
        win_off = (110, 90,  70),   # Jendela mati
        neon    = (140, 100, 65),   # Aksen border
    ),
    # Style 2: Komersial / mall (abu-kuning)
    dict(
        wall    = (150, 148, 130),  # Dinding abu cerah
        light   = (165, 162, 145),  # Highlight
        roof    = (85,  110, 140),  # Atap biru-abu
        win     = (200, 230, 255),  # Jendela menyala (putih-biru)
        win_off = (100, 98,  85),   # Jendela mati
        neon    = (90,  120, 150),  # Aksen border
    ),
]

# ══════════════════════════════════════════════════════════════
# LOD & PATHFINDING COLORS
# ══════════════════════════════════════════════════════════════
LOD_FAR_ZOOM = 0.20   # zoom < ini -> LOD 0 (jauh: blok warna saja)
LOD_MED_ZOOM = 0.55   # zoom < ini -> LOD 1 (sedang: bangunan, jalan, lampu), >= ini -> LOD 2 (dekat)

# Warna pathfinding dan node eksplorasi per algoritma
# A* (cyberpunk neon green/teal)
C_PATH_ASTAR         = (0,   255, 120)
C_EXPL_ASTAR         = (0,   70,  45)
C_PATH_OUTLINE_ASTAR = (0,   100, 50)

# Dijkstra (neon cyan/blue)
C_PATH_DIJKSTRA         = (0,   220, 255)
C_EXPL_DIJKSTRA         = (0,   50,  80)
C_PATH_OUTLINE_DIJKSTRA = (0,   80,  120)

# BFS (neon pink/purple)
C_PATH_BFS         = (240, 0,   255)
C_EXPL_BFS         = (80,  0,   80)
C_PATH_OUTLINE_BFS = (120, 0,   120)

