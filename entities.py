"""
entities.py
===========
Kelas-kelas entitas interaktif dalam simulasi:
  - Camera   : Sistem kamera 2D dengan zoom dan pan
  - Car      : Mobil yang bergerak mengikuti world path
  - Button   : Tombol UI interaktif dengan hover effect
"""

import math
from collections import deque

import pygame

from config import T, GCOLS, GROWS, C_BTN_BG, C_BTN_BD, C_BTN_TXT, C_BTN_HOV


# ══════════════════════════════════════════════════════════════
# CAMERA
# ══════════════════════════════════════════════════════════════
class Camera:
    """
    Sistem kamera 2D untuk menampilkan dunia yang lebih besar dari layar.

    Konsep:
      Kamera memiliki posisi (x, y) di koordinat dunia, dan faktor zoom.
      Saat merender, semua objek dunia ditransformasi ke koordinat layar
      menggunakan world_to_screen().

    Fitur:
      - Pan (geser) dengan drag mouse
      - Zoom in/out dengan scroll wheel, pivot di posisi kursor
      - Snap ke posisi tertentu (center_on)
      - Hitung range tile yang terlihat (untuk culling, efisiensi render)

    Atribut:
      x, y     : posisi kamera di koordinat dunia (pusat layar)
      zoom     : faktor zoom (1.0 = ukuran asli, 0.5 = 50%, 2.0 = 200%)
      sw, sh   : ukuran layar (screen width, height)
    """

    def __init__(self, world_w, world_h, screen_w, screen_h):
        self.x        = world_w / 2      # mulai di tengah dunia
        self.y        = world_h / 2
        self.zoom     = 0.45             # zoom awal (45% → tampak keseluruhan)
        self.sw       = screen_w
        self.sh       = screen_h
        self.min_zoom = 0.08             # zoom minimum (tampak keseluruhan peta)
        self.max_zoom = 2.5              # zoom maksimum (sangat dekat)
        self.drag      = False
        self.drag_start = None

    def world_to_screen(self, wx, wy):
        """
        Konversi koordinat dunia (wx, wy) ke koordinat layar (sx, sy).

        Formula:
          sx = (wx - cam_x) * zoom + screen_w / 2
          sy = (wy - cam_y) * zoom + screen_h / 2

        Objek di pusat kamera (cam_x, cam_y) akan muncul di tengah layar.
        """
        return (
            (wx - self.x) * self.zoom + self.sw / 2,
            (wy - self.y) * self.zoom + self.sh / 2
        )

    def screen_to_world(self, sx, sy):
        """
        Konversi koordinat layar (sx, sy) ke koordinat dunia (wx, wy).
        Kebalikan dari world_to_screen(), digunakan untuk hit-testing klik.
        """
        return (
            (sx - self.sw / 2) / self.zoom + self.x,
            (sy - self.sh / 2) / self.zoom + self.y
        )

    def zoom_at(self, sx, sy, factor):
        """
        Zoom in/out dengan pivot di posisi layar (sx, sy).

        Trik: simpan koordinat dunia sebelum zoom, lalu sesuaikan
        posisi kamera agar titik dunia tersebut tetap di posisi layar yang sama.
        """
        wx, wy   = self.screen_to_world(sx, sy)
        self.zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        nwx, nwy = self.screen_to_world(sx, sy)
        self.x  += wx - nwx
        self.y  += wy - nwy

    def get_visible_tiles(self):
        """
        Hitung range tile (c0, c1, r0, r1) yang terlihat di layar saat ini.
        Digunakan untuk frustum culling: hanya render tile yang terlihat.

        Return: (c0, c1, r0, r1) — range kolom dan baris yang terlihat
        """
        x0, y0 = self.screen_to_world(0,       0)
        x1, y1 = self.screen_to_world(self.sw, self.sh)
        c0 = max(0,     int(x0 / T) - 1)
        r0 = max(0,     int(y0 / T) - 1)
        c1 = min(GCOLS, int(x1 / T) + 2)
        r1 = min(GROWS, int(y1 / T) + 2)
        return c0, c1, r0, r1

    def center_on(self, wx, wy):
        """Pindahkan kamera agar (wx, wy) tepat di tengah layar."""
        self.x = wx
        self.y = wy


# ══════════════════════════════════════════════════════════════
# CAR
# ══════════════════════════════════════════════════════════════
class Car:
    """
    Entitas mobil yang bergerak mengikuti world path (Catmull-Rom spline).

    Cara bergerak:
      - Setiap frame, mobil bergerak 'speed' piksel ke arah waypoint berikutnya
      - Jika sudah sampai di waypoint, lanjut ke waypoint berikutnya
      - Sudut (angle) diperbarui berdasarkan arah gerakan
      - Trail disimpan dalam deque terbatas untuk efek ekor visual

    Atribut:
      world_path : list[(wx, wy)] jalur dunia hasil build_world_path()
      path_idx   : indeks waypoint berikutnya yang dituju
      x, y       : posisi mobil di koordinat dunia (piksel)
      angle      : sudut hadap dalam radian (untuk rotasi bodi)
      speed      : kecepatan dalam piksel/frame
      active     : True jika mobil sedang aktif bergerak
      paused     : True jika mobil di-pause
      arrived    : True jika mobil sudah sampai di tujuan
      trail      : deque posisi historis untuk render trail
    """

    def __init__(self):
        self.world_path = []
        self.path_idx   = 0
        self.x          = 0.0
        self.y          = 0.0
        self.angle      = 0.0
        self.speed      = 3.0          # piksel per frame
        self.active     = False
        self.paused     = False
        self.arrived    = False
        self.trail      = deque(maxlen=200)   # simpan max 200 posisi terakhir

    def set_path(self, wpath):
        """
        Set jalur baru. Reset state mobil ke titik awal jalur.

        Parameter:
          wpath : list[(wx, wy)] dari build_world_path()
        """
        self.world_path = wpath
        self.path_idx   = 0
        self.arrived    = False
        self.paused     = False
        self.trail.clear()
        if wpath:
            self.x, self.y = wpath[0]
            self.active    = True
        else:
            self.active    = False

    def update(self, dt):
        """
        Update posisi mobil berdasarkan delta-time (dt) dan traversal multi-waypoint.
        """
        if not self.active or self.arrived or self.paused or not self.world_path:
            return
        if self.path_idx >= len(self.world_path) - 1:
            self.arrived = True
            return

        # Kecepatan dalam piksel per detik (speed awal = 3.0 piksel per frame pada 60 FPS)
        dist_to_move = self.speed * 60.0 * dt

        while dist_to_move > 0 and self.path_idx < len(self.world_path) - 1:
            tx, ty   = self.world_path[self.path_idx + 1]
            dx, dy   = tx - self.x, ty - self.y
            dist     = math.hypot(dx, dy)

            if dist <= dist_to_move:
                # Snap ke waypoint ini
                self.x, self.y = tx, ty
                self.path_idx += 1
                dist_to_move -= dist
                self.trail.append((self.x, self.y))
            else:
                # Bergerak sebagian menuju waypoint
                ux, uy = dx / dist, dy / dist
                self.x += ux * dist_to_move
                self.y += uy * dist_to_move
                self.angle = math.atan2(dy, dx)
                dist_to_move = 0
                self.trail.append((self.x, self.y))

        if self.path_idx >= len(self.world_path) - 1:
            self.arrived = True

    def draw(self, surf, camera):
        """
        Render mobil ke surface layar — GoCar 3D style.

        Elemen yang digambar:
          1. Trail: polyline merah pudar
          2. Shadow: bayangan di bawah mobil
          3. Bodi: multi-layer polygon (badan bawah, badan atas, kap mesin)
          4. Kaca depan & samping (windshield & side windows)
          5. Atap dengan highlight
          6. Roda (4 buah) dengan rim
          7. Headlight ganda dengan efek glow
          8. Tail light merah di belakang
        """
        if not self.active:
            return

        # ── Trail (merah) ─────────────────────────────────────
        if len(self.trail) > 1:
            pts = []
            for wx, wy in self.trail:
                sx, sy = camera.world_to_screen(wx, wy)
                pts.append((int(sx), int(sy)))
            if len(pts) >= 2:
                trail_w = max(1, int(2 * camera.zoom))
                for i in range(len(pts) - 1):
                    alpha = int(80 + 120 * i / len(pts))
                    trail_col = (min(255, alpha + 60), 30, 25)
                    pygame.draw.line(surf, trail_col, pts[i], pts[i + 1], trail_w)

        # ── Ukuran dan rotasi ─────────────────────────────────
        sx, sy = camera.world_to_screen(self.x, self.y)
        sz     = max(6, int(14 * camera.zoom))
        cos_a  = math.cos(self.angle)
        sin_a  = math.sin(self.angle)

        def _rot(dx, dy):
            """Rotate offset (dx,dy) by car angle and add to screen pos."""
            return (sx + cos_a * dx - sin_a * dy,
                    sy + sin_a * dx + cos_a * dy)

        def _irot(dx, dy):
            p = _rot(dx, dy)
            return (int(p[0]), int(p[1]))

        # Faktor skala relatif terhadap sz
        s = sz  # unit scale

        # ── 1. Shadow (bayangan) ──────────────────────────────
        sh_off = max(1, int(s * 0.12))
        shadow_pts = [
            (sx + sh_off + cos_a * s * 1.1  - sin_a * s * 0.48,
             sy + sh_off + sin_a * s * 1.1  + cos_a * s * 0.48),
            (sx + sh_off + cos_a * s * 1.1  + sin_a * s * 0.48,
             sy + sh_off + sin_a * s * 1.1  - cos_a * s * 0.48),
            (sx + sh_off - cos_a * s * 0.85 + sin_a * s * 0.48,
             sy + sh_off - sin_a * s * 0.85 - cos_a * s * 0.48),
            (sx + sh_off - cos_a * s * 0.85 - sin_a * s * 0.48,
             sy + sh_off - sin_a * s * 0.85 + cos_a * s * 0.48),
        ]
        shadow_surf = pygame.Surface((int(s * 3), int(s * 3)), pygame.SRCALPHA)
        sh_pts_local = [(int(p[0] - sx + s * 1.5), int(p[1] - sy + s * 1.5)) for p in shadow_pts]
        if len(sh_pts_local) >= 3:
            pygame.draw.polygon(shadow_surf, (0, 0, 0, 55), sh_pts_local)
        surf.blit(shadow_surf, (int(sx - s * 1.5), int(sy - s * 1.5)))

        # ── 2. Bodi bawah (chassis — hijau GoCar gelap) ───────
        body_col    = (30, 160, 60)    # hijau GoCar
        body_hi     = (45, 190, 80)    # hijau lebih terang (highlight)
        body_dk     = (20, 120, 40)    # hijau gelap (shadow side)
        accent_col  = (255, 255, 255)  # aksen putih

        # Bodi utama (persegi panjang rounded-look)
        body_pts = [
            _irot(s * 1.05, -s * 0.45),   # depan-kanan
            _irot(s * 1.05,  s * 0.45),    # depan-kiri
            _irot(-s * 0.8,  s * 0.45),    # belakang-kiri
            _irot(-s * 0.8, -s * 0.45),    # belakang-kanan
        ]
        pygame.draw.polygon(surf, body_col, body_pts)

        # Panel samping kanan (gelap → efek 3D)
        side_r = [
            _irot(s * 0.95, -s * 0.46),
            _irot(s * 0.95, -s * 0.38),
            _irot(-s * 0.7, -s * 0.38),
            _irot(-s * 0.7, -s * 0.46),
        ]
        pygame.draw.polygon(surf, body_dk, side_r)

        # Panel samping kiri (terang → efek 3D)
        side_l = [
            _irot(s * 0.95, s * 0.46),
            _irot(s * 0.95, s * 0.38),
            _irot(-s * 0.7, s * 0.38),
            _irot(-s * 0.7, s * 0.46),
        ]
        pygame.draw.polygon(surf, body_hi, side_l)

        # ── 3. Kap mesin (hood) — hijau lebih cerah ──────────
        hood_pts = [
            _irot(s * 1.02, -s * 0.35),
            _irot(s * 1.02,  s * 0.35),
            _irot(s * 0.45,  s * 0.35),
            _irot(s * 0.45, -s * 0.35),
        ]
        pygame.draw.polygon(surf, (40, 180, 70), hood_pts)
        # Garis aksen di kap mesin
        pygame.draw.line(surf, (55, 200, 90),
                         _irot(s * 0.95, 0), _irot(s * 0.5, 0),
                         max(1, int(s * 0.06)))

        # ── 4. Kaca depan (windshield) ────────────────────────
        ws_pts = [
            _irot(s * 0.45, -s * 0.32),
            _irot(s * 0.45,  s * 0.32),
            _irot(s * 0.2,   s * 0.28),
            _irot(s * 0.2,  -s * 0.28),
        ]
        pygame.draw.polygon(surf, (140, 200, 235), ws_pts)
        pygame.draw.polygon(surf, (80, 140, 180), ws_pts, max(1, int(s * 0.04)))

        # ── 5. Atap (roof) ───────────────────────────────────
        roof_pts = [
            _irot(s * 0.2,  -s * 0.3),
            _irot(s * 0.2,   s * 0.3),
            _irot(-s * 0.35, s * 0.3),
            _irot(-s * 0.35,-s * 0.3),
        ]
        pygame.draw.polygon(surf, (25, 140, 55), roof_pts)
        # Highlight strip di atap
        roof_hi = [
            _irot(s * 0.15, -s * 0.15),
            _irot(s * 0.15,  s * 0.15),
            _irot(-s * 0.2,  s * 0.15),
            _irot(-s * 0.2, -s * 0.15),
        ]
        pygame.draw.polygon(surf, (50, 175, 80), roof_hi)

        # ── 6. Kaca belakang ─────────────────────────────────
        rw_pts = [
            _irot(-s * 0.35, -s * 0.26),
            _irot(-s * 0.35,  s * 0.26),
            _irot(-s * 0.5,   s * 0.28),
            _irot(-s * 0.5,  -s * 0.28),
        ]
        pygame.draw.polygon(surf, (120, 180, 210), rw_pts)
        pygame.draw.polygon(surf, (70, 120, 160), rw_pts, max(1, int(s * 0.04)))

        # ── 7. Bagasi belakang ───────────────────────────────
        trunk_pts = [
            _irot(-s * 0.5,  -s * 0.35),
            _irot(-s * 0.5,   s * 0.35),
            _irot(-s * 0.75,  s * 0.35),
            _irot(-s * 0.75, -s * 0.35),
        ]
        pygame.draw.polygon(surf, (28, 145, 55), trunk_pts)

        # ── 8. Roda (4 buah) ─────────────────────────────────
        wheel_w = max(2, int(s * 0.18))
        wheel_h = max(1, int(s * 0.12))
        wheel_positions = [
            (s * 0.65, -s * 0.48),   # depan-kanan
            (s * 0.65,  s * 0.48),   # depan-kiri
            (-s * 0.5, -s * 0.48),   # belakang-kanan
            (-s * 0.5,  s * 0.48),   # belakang-kiri
        ]
        for wdx, wdy in wheel_positions:
            wc = _rot(wdx, wdy)
            # Ban (hitam)
            w_pts = [
                _irot(wdx - wheel_w * 0.5, wdy - wheel_h * 0.5),
                _irot(wdx + wheel_w * 0.5, wdy - wheel_h * 0.5),
                _irot(wdx + wheel_w * 0.5, wdy + wheel_h * 0.5),
                _irot(wdx - wheel_w * 0.5, wdy + wheel_h * 0.5),
            ]
            pygame.draw.polygon(surf, (30, 30, 30), w_pts)
            # Rim (abu-abu)
            rim_r = max(1, int(s * 0.05))
            pygame.draw.circle(surf, (160, 165, 170), (int(wc[0]), int(wc[1])), rim_r)

        # ── 9. Headlights (lampu depan ganda + glow) ─────────
        hl_positions = [
            (s * 1.05, -s * 0.3),
            (s * 1.05,  s * 0.3),
        ]
        for hdx, hdy in hl_positions:
            hp = _rot(hdx, hdy)
            hl_r = max(2, int(s * 0.1))
            # Glow effect
            glow_r = max(4, int(s * 0.25))
            glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 255, 200, 50), (glow_r, glow_r), glow_r)
            pygame.draw.circle(glow_surf, (255, 255, 220, 100), (glow_r, glow_r), glow_r // 2)
            surf.blit(glow_surf, (int(hp[0] - glow_r), int(hp[1] - glow_r)))
            # Lampu inti
            pygame.draw.circle(surf, (255, 255, 230), (int(hp[0]), int(hp[1])), hl_r)
            pygame.draw.circle(surf, (255, 255, 255), (int(hp[0]), int(hp[1])), max(1, hl_r // 2))

        # ── 10. Tail lights (lampu belakang merah) ────────────
        tl_positions = [
            (-s * 0.78, -s * 0.35),
            (-s * 0.78,  s * 0.35),
        ]
        for tdx, tdy in tl_positions:
            tp = _rot(tdx, tdy)
            tl_r = max(1, int(s * 0.07))
            pygame.draw.circle(surf, (255, 30, 20), (int(tp[0]), int(tp[1])), tl_r)
            pygame.draw.circle(surf, (255, 100, 80), (int(tp[0]), int(tp[1])), max(1, tl_r + 1), 1)

        # ── 11. Border outline bodi ──────────────────────────
        pygame.draw.polygon(surf, (15, 100, 35), body_pts, max(1, int(s * 0.04)))


# ══════════════════════════════════════════════════════════════
# BUTTON
# ══════════════════════════════════════════════════════════════
class Button:
    """
    Tombol UI interaktif dengan tiga state visual:
      - Normal  : latar C_BTN_BG, border C_BTN_BD, teks C_BTN_TXT
      - Hover   : latar C_BTN_HOV (lebih terang), border & teks sama
      - Active  : latar biru gelap, border & teks cyan terang
                  (digunakan untuk algo-selector yang sedang aktif)

    Atribut:
      rect      : pygame.Rect posisi & ukuran tombol
      text      : label teks tombol
      action    : callable yang dipanggil saat tombol diklik
      hovered   : True jika kursor mouse di atas tombol
      is_active : True jika tombol dalam state 'active' (highlight)
    """

    def __init__(self, x, y, w, h, text, action=None):
        self.rect      = pygame.Rect(x, y, w, h)
        self.text      = text
        self.action    = action
        self.hovered   = False
        self.is_active = False

    def draw(self, surf, font):
        """Render tombol ke surface."""
        if self.is_active:
            col    = (0, 55, 90)
            bd_col = (0, 255, 200)
            tc     = (0, 255, 200)
        else:
            col    = C_BTN_HOV if self.hovered else C_BTN_BG
            bd_col = C_BTN_BD
            tc     = C_BTN_TXT

        pygame.draw.rect(surf, col,    self.rect, border_radius=4)
        pygame.draw.rect(surf, bd_col, self.rect, 1, border_radius=4)
        t = font.render(self.text, True, tc)
        surf.blit(t, (
            self.rect.x + (self.rect.w - t.get_width())  // 2,
            self.rect.y + (self.rect.h - t.get_height()) // 2
        ))

    def handle(self, pos):
        """Update state hover berdasarkan posisi kursor."""
        self.hovered = self.rect.collidepoint(pos)

    def clicked(self, pos):
        """
        Cek apakah posisi 'pos' berada di dalam tombol.
        Jika iya, panggil action() dan return True.
        """
        if self.rect.collidepoint(pos) and self.action:
            self.action()
            return True
        return False