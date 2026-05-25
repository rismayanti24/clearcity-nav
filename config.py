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
# CYBERPUNK COLOUR PALETTE
# ══════════════════════════════════════════════════════════════
C_BG       = (13,  15,  23)    # Warna latar belakang layar
C_GRASS    = (16,  20,  30)    # Warna rumput / tanah
C_SW       = (42,  48,  65)    # Warna trotoar (sidewalk) 
C_ROAD     = (55,  62,  85)    # Warna badan jalan — kontras jelas dari rumput
C_DASH     = (90, 100, 140)    # Warna garis putus-putus di tengah jalan
C_PATH     = (0,   210, 110)   # Warna overlay jalur hasil pathfinding
C_EXPLORED = (40,  80,  140)   # Warna overlay node yang dijelajahi algoritma
C_ORIGIN   = (0,   220, 80)    # Warna marker titik asal / origin
C_DEST     = (220, 50,  50)    # Warna marker titik tujuan / destination
C_UI       = (100, 130, 200)   # Warna teks utama UI
C_UIK      = (70,  90,  140)   # Warna teks label/key UI
C_PANEL    = (12,  16,  24)    # Warna latar panel kiri
C_BTN_BG   = (18,  22,  32)    # Warna latar tombol (normal)
C_BTN_BD   = (0,   180, 255)   # Warna border tombol
C_BTN_TXT  = (200, 220, 255)   # Warna teks tombol
C_BTN_HOV  = (30,  50,  70)    # Warna latar tombol saat hover

# ══════════════════════════════════════════════════════════════
# BUILDING STYLES
# ══════════════════════════════════════════════════════════════
# Tiga gaya bangunan berbeda (biru, merah muda/pink, kuning)
# Setiap style mendefinisikan: warna dinding, highlight, atap, jendela, neon sign
BLDG_STYLES = [
    # Style 0: Biru (gedung korporat / office)
    dict(
        wall    = (30,  55,  75),   # Warna dinding utama
        light   = (45,  65,  85),   # Highlight dinding (sisi terang)
        roof    = (25,  40,  55),   # Warna atap / cornice
        win     = (100, 200, 255),  # Warna jendela menyala
        win_off = (30,  50,  70),   # Warna jendela mati / gelap
        neon    = (0,   150, 210),  # Warna aksen neon (border, garis)
    ),
    # Style 1: Merah muda / Magenta (hiburan / entertainment)
    dict(
        wall    = (65,  30,  50),
        light   = (75,  40,  60),
        roof    = (45,  18,  35),
        win     = (255, 120, 200),
        win_off = (55,  25,  45),
        neon    = (200, 50,  150),
    ),
    # Style 2: Kuning / Amber (perdagangan / commercial)
    dict(
        wall    = (60,  55,  25),
        light   = (70,  65,  35),
        roof    = (40,  35,  12),
        win     = (255, 230, 80),
        win_off = (50,  45,  18),
        neon    = (200, 170, 0), 
    ),
]
