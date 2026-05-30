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
        Render mobil ke surface layar.

        Elemen yang digambar:
          1. Trail: polyline pudar (semakin tua semakin transparan)
          2. Bodi mobil: quadrilateral (trapesoid) yang dirotasi sesuai angle
          3. Headlight: lingkaran kecil putih di depan mobil
        """
        if not self.active:
            return

        # ── Trail ─────────────────────────────────────────────
        if len(self.trail) > 1:
            pts = []
            for wx, wy in self.trail:
                sx, sy = camera.world_to_screen(wx, wy)
                pts.append((int(sx), int(sy)))
            if len(pts) >= 2:
                for i in range(len(pts) - 1):
                    pygame.draw.line(
                        surf, (0, 200, 100),
                        pts[i], pts[i + 1],
                        max(1, int(2 * camera.zoom))
                    )

        # ── Bodi mobil ────────────────────────────────────────
        sx, sy  = camera.world_to_screen(self.x, self.y)
        sz       = max(6, int(14 * camera.zoom))
        cos_a    = math.cos(self.angle)
        sin_a    = math.sin(self.angle)

        # 4 titik sudut bodi (trapesoid yang menunjuk ke depan)
        bpts = [
            (sx + cos_a * sz       - sin_a * sz * 0.5,
             sy + sin_a * sz       + cos_a  * sz * 0.5),   # depan-kiri
            (sx + cos_a * sz       + sin_a * sz * 0.5,
             sy + sin_a * sz       - cos_a  * sz * 0.5),   # depan-kanan
            (sx - cos_a * sz * 0.7 + sin_a * sz * 0.5,
             sy - sin_a * sz * 0.7 - cos_a  * sz * 0.5),   # belakang-kanan
            (sx - cos_a * sz * 0.7 - sin_a * sz * 0.5,
             sy - sin_a * sz * 0.7 + cos_a  * sz * 0.5),   # belakang-kiri
        ]
        pygame.draw.polygon(surf, (0, 220, 255), [(int(x), int(y)) for x, y in bpts])
        pygame.draw.polygon(surf, (0, 255, 255), [(int(x), int(y)) for x, y in bpts], 1)

        # ── Headlight ─────────────────────────────────────────
        hx = sx + cos_a * sz * 1.1
        hy = sy + sin_a * sz * 1.1
        pygame.draw.circle(surf, (255, 255, 200),
                           (int(hx), int(hy)),
                           max(2, int(3 * camera.zoom)))


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
