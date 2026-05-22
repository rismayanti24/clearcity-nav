"""
grid.py
=======
Definisi sistem tile berbasis port, kelas Tile dan Grid.

Konsep Port:
  Setiap tile jalan memiliki 'port' (sambungan) di sisi-sisinya.
  Port 0 = Utara (North), 1 = Timur (East), 2 = Selatan (South), 3 = Barat (West)
  Dua tile terhubung jika tile A punya port ke arah D,
  dan tile B di arah D punya port OPPOSITE[D].
"""

# ══════════════════════════════════════════════════════════════
# TILE TYPE CONSTANTS
# ══════════════════════════════════════════════════════════════
EMPTY     = 0   # Bukan jalan (rumput/bangunan)
STRAIGHT  = 1   # Jalan lurus: 2 port sejajar (N-S atau E-W)
CURVE     = 2   # Tikungan 90°: 2 port tegak lurus (N-E, E-S, S-W, W-N)
TJUNCTION = 3   # Pertigaan: 3 port
CROSS     = 4   # Perempatan: 4 port ke semua arah
DIAGONAL  = 5   # Jalan diagonal 45°: secara visual miring tapi port sama seperti STRAIGHT

# ══════════════════════════════════════════════════════════════
# TILE PORT DEFINITIONS
# ══════════════════════════════════════════════════════════════
# Format: { tile_type: [port_set_rot0, port_set_rot1, ...] }
# Setiap rotasi memiliki frozenset port yang aktif.
TILE_PORTS = {
    # STRAIGHT rot0: N↔S (vertikal), rot1: E↔W (horizontal)
    STRAIGHT:  [frozenset({0, 2}), frozenset({1, 3})],

    # CURVE: tikungan, 4 rotasi masing-masing untuk pasangan sudut berbeda
    # rot0: N-E, rot1: E-S, rot2: S-W, rot3: W-N
    CURVE:     [frozenset({0, 1}), frozenset({1, 2}),
                frozenset({2, 3}), frozenset({3, 0})],

    # TJUNCTION: pertigaan, 4 rotasi (satu sisi tertutup)
    # rot0: N-E-S (barat tertutup), rot1: E-S-W, rot2: S-W-N, rot3: W-N-E
    TJUNCTION: [frozenset({0, 1, 2}), frozenset({1, 2, 3}),
                frozenset({2, 3, 0}), frozenset({3, 0, 1})],

    # CROSS: perempatan, satu rotasi (semua 4 arah terbuka)
    CROSS:     [frozenset({0, 1, 2, 3})],

    # DIAGONAL: visual miring 45°, tapi port sama seperti STRAIGHT
    # rot0: N↔S (visual NW→SE), rot1: E↔W (visual NE→SW)
    DIAGONAL:  [frozenset({0, 2}), frozenset({1, 3})],
}

# ══════════════════════════════════════════════════════════════
# DIRECTION HELPERS
# ══════════════════════════════════════════════════════════════
# Arah berlawanan dari setiap port
OPPOSITE  = {0: 2, 1: 3, 2: 0, 3: 1}

# Delta koordinat (dc, dr) untuk setiap arah
# 0=Utara (-y), 1=Timur (+x), 2=Selatan (+y), 3=Barat (-x)
DIR_DELTA = {0: (0, -1), 1: (1, 0), 2: (0, 1), 3: (-1, 0)}


# ══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════
def get_ports(tt, rot):
    """
    Kembalikan frozenset port aktif untuk tile bertipe 'tt' dan rotasi 'rot'.
    Jika tipe tidak dikenali atau rotasi di luar range, kembalikan frozenset kosong.
    """
    opts = TILE_PORTS.get(tt, [])
    return opts[rot % len(opts)] if opts else frozenset()


def _tile_degree(tt):
    """
    Kembalikan jumlah koneksi (degree) tile berdasarkan tipenya.
    Digunakan untuk memilih tile paling sederhana saat generasi peta.
    """
    if tt == STRAIGHT:  return 2
    if tt == CURVE:     return 2
    if tt == DIAGONAL:  return 2
    if tt == TJUNCTION: return 3
    if tt == CROSS:     return 4
    return 0


# ══════════════════════════════════════════════════════════════
# TILE CLASS
# ══════════════════════════════════════════════════════════════
class Tile:
    """
    Representasi satu sel/tile di peta grid.
    Menggunakan __slots__ untuk efisiensi memori karena ada 80x80 = 6400 tile.
    
    Atribut:
        type     (int): Tipe tile (EMPTY, STRAIGHT, CURVE, dll)
        rotation (int): Rotasi tile (0 = default, nilai lain tergantung tile_type)
    """
    __slots__ = ('type', 'rotation')

    def __init__(self):
        self.type     = EMPTY   # Default: kosong (bukan jalan)
        self.rotation = 0


# ══════════════════════════════════════════════════════════════
# GRID CLASS
# ══════════════════════════════════════════════════════════════
class Grid:
    """
    Grid 2D yang berisi seluruh tile peta.
    Koordinat: (c, r) di mana c = kolom (x), r = baris (y).
    
    Atribut:
        cols  (int)        : Jumlah kolom
        rows  (int)        : Jumlah baris
        cells (list[list]) : Matrix 2D berisi objek Tile
    """

    def __init__(self, cols, rows):
        self.cols  = cols
        self.rows  = rows
        # Inisialisasi semua tile sebagai EMPTY
        self.cells = [[Tile() for _ in range(cols)] for _ in range(rows)]

    def get(self, c, r):
        """
        Ambil tile di posisi (c, r).
        Kembalikan None jika koordinat di luar batas grid.
        """
        if 0 <= c < self.cols and 0 <= r < self.rows:
            return self.cells[r][c]
        return None

    def set_tile(self, c, r, tt, rot=0):
        """
        Set tipe dan rotasi tile di posisi (c, r).
        Tidak melakukan apa-apa jika koordinat di luar batas.
        """
        if 0 <= c < self.cols and 0 <= r < self.rows:
            self.cells[r][c].type     = tt
            self.cells[r][c].rotation = rot

    def is_road(self, c, r):
        """
        Cek apakah tile di (c, r) adalah jalan (bukan EMPTY).
        Kembalikan False jika koordinat di luar batas.
        """
        t = self.get(c, r)
        return t is not None and t.type != EMPTY

    def in_bounds(self, c, r):
        """Cek apakah koordinat (c, r) berada di dalam batas grid."""
        return 0 <= c < self.cols and 0 <= r < self.rows
