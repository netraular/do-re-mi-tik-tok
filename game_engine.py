"""
Game engine – TikTok-style singing game.
Walls scroll left; each has a hole at a specific note height.
The player controls a ball vertically by singing the right note.
"""

import random
import pygame
from pitch_detector import GAME_NOTES

# ── colours ──────────────────────────────────────────────────
WHITE  = (255, 255, 255)
BLACK  = (0, 0, 0)
GRAY   = (100, 100, 100)
DGRAY  = (60, 60, 60)
LGRAY  = (180, 180, 180)
RED    = (220, 60, 60)
GREEN  = (60, 200, 80)
BLUE   = (80, 140, 255)
YELLOW = (255, 220, 60)
ORANGE = (255, 160, 40)
CYAN   = (60, 220, 220)
PURPLE = (180, 80, 220)

NOTE_COLORS = {
    "Do": RED, "Re": ORANGE, "Mi": YELLOW, "Fa": GREEN,
    "Sol": CYAN, "La": BLUE, "Si": PURPLE,
}

WALL_W       = 40
HOLE_H       = 60
BALL_R       = 18
SPEED0       = 2.0
SPEED_INC    = 0.1
SPAWN0       = 120      # frames between walls
SPAWN_MIN    = 60


# ── Wall ─────────────────────────────────────────────────────
class Wall:
    def __init__(self, x, note_idx, area_h, n_notes=7):
        self.x = float(x)
        self.note_idx = note_idx
        self.note_name = GAME_NOTES[note_idx]
        usable = area_h - 40
        slot = usable / n_notes
        cy = area_h - 20 - (note_idx * slot + slot / 2)
        self.hole_y = cy - HOLE_H / 2
        self.w = WALL_W
        self.passed = False
        self.scored = False
        self.color = NOTE_COLORS.get(self.note_name, GRAY)

    def draw(self, surf, ox=0, oy=0):
        x = int(self.x) + ox
        ah = surf.get_height() - oy
        # top part – semi-transparent so webcam shows through
        top_h = int(self.hole_y)
        if top_h > 0:
            top_s = pygame.Surface((self.w, top_h), pygame.SRCALPHA)
            top_s.fill((*self.color[:3], 140))
            surf.blit(top_s, (x, oy))
            pygame.draw.rect(surf, self.color, (x, oy, self.w, top_h), 2)
        # bottom part
        by = int(self.hole_y + HOLE_H) + oy
        bh = ah - int(self.hole_y + HOLE_H)
        if bh > 0:
            bot_s = pygame.Surface((self.w, bh), pygame.SRCALPHA)
            bot_s.fill((*self.color[:3], 140))
            surf.blit(bot_s, (x, by))
            pygame.draw.rect(surf, self.color, (x, by, self.w, bh), 2)
        # hole glow
        glow_r = pygame.Rect(x - 3, int(self.hole_y) + oy - 3, self.w + 6, HOLE_H + 6)
        pygame.draw.rect(surf, self.color, glow_r, 2, border_radius=4)
        # label
        f = pygame.font.SysFont("Segoe UI", 16, bold=True)
        lbl = f.render(self.note_name, True, WHITE)
        shadow = f.render(self.note_name, True, BLACK)
        lx = x + self.w // 2 - lbl.get_width() // 2
        ly = int(self.hole_y + HOLE_H / 2 - lbl.get_height() / 2) + oy
        surf.blit(shadow, (lx + 1, ly + 1))
        surf.blit(lbl, (lx, ly))


# ── Ball ─────────────────────────────────────────────────────
class Ball:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.ty = self.y
        self.r = BALL_R
        self.color = WHITE
        self.trail: list[tuple[int, int]] = []

    def set_target(self, idx, area_h, n=7):
        if idx < 0:
            return
        slot = (area_h - 40) / n
        self.ty = area_h - 20 - (idx * slot + slot / 2)
        self.color = NOTE_COLORS.get(GAME_NOTES[idx], WHITE)

    def update(self):
        self.y += (self.ty - self.y) * 0.15
        self.trail.append((int(self.x), int(self.y)))
        if len(self.trail) > 15:
            self.trail.pop(0)

    def draw(self, surf, oy=0):
        # trail
        for i, (tx, ty) in enumerate(self.trail):
            a = i / max(len(self.trail), 1)
            r = max(3, int(self.r * a * 0.6))
            c = tuple(min(255, v + 80) for v in self.color[:3])
            pygame.draw.circle(surf, c, (tx, ty + oy), r)
        # outer glow
        glow = pygame.Surface((self.r * 4, self.r * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*self.color[:3], 50), (self.r * 2, self.r * 2), self.r * 2)
        surf.blit(glow, (int(self.x) - self.r * 2, int(self.y) + oy - self.r * 2))
        # ball
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y) + oy), self.r)
        pygame.draw.circle(surf, WHITE, (int(self.x), int(self.y) + oy), self.r, 2)
        pygame.draw.circle(surf, WHITE, (int(self.x) - 4, int(self.y) - 4 + oy), 5)


# ── Game ─────────────────────────────────────────────────────
class Game:
    def __init__(self, w, h):
        self.gw, self.gh = w, h
        self.reset()

    def reset(self):
        self.walls: list[Wall] = []
        self.ball = Ball(80, self.gh // 2)
        self.score = 0
        self.lives = 3
        self.over = False
        self.speed = SPEED0
        self.stimer = 0
        self.sint = SPAWN0
        self.active = False
        self.combo = 0
        self.max_combo = 0

    def start(self):
        self.reset()
        self.active = True

    def update(self, note_idx):
        if not self.active or self.over:
            return
        self.ball.set_target(note_idx, self.gh)
        self.ball.update()

        self.stimer += 1
        if self.stimer >= self.sint:
            self.stimer = 0
            ni = random.randint(0, len(GAME_NOTES) - 1)
            self.walls.append(Wall(self.gw, ni, self.gh))
            self.speed = min(5.0, SPEED0 + self.score * SPEED_INC)
            self.sint = max(SPAWN_MIN, SPAWN0 - self.score * 2)

        for w in self.walls:
            w.x -= self.speed

        for w in self.walls:
            if w.passed:
                continue
            bx, by, br = self.ball.x, self.ball.y, self.ball.r
            if w.x < bx + br and w.x + w.w > bx - br:
                if by - br < w.hole_y or by + br > w.hole_y + HOLE_H:
                    if not w.scored:
                        self.lives -= 1
                        self.combo = 0
                        w.scored = True
                        if self.lives <= 0:
                            self.over = True
                if w.x + w.w < bx - br:
                    w.passed = True
                    if not w.scored:
                        self.score += 1
                        self.combo += 1
                        self.max_combo = max(self.max_combo, self.combo)
                        w.scored = True
            if w.x + w.w < 0:
                if not w.scored:
                    self.score += 1
                    self.combo += 1
                    self.max_combo = max(self.max_combo, self.combo)
                    w.scored = True
                w.passed = True

        self.walls = [w for w in self.walls if w.x + w.w > -50]

    # ── draw ─────────────────────────────────────────────────
    def draw(self, surf, ox=0, oy=0):
        # No solid background fill – webcam is drawn behind us

        usable = self.gh - 40
        slot = usable / len(GAME_NOTES)
        sf = pygame.font.SysFont("Segoe UI", 15, bold=True)
        for i, nn in enumerate(GAME_NOTES):
            ly = self.gh - 20 - (i * slot + slot / 2) + oy
            # semi-transparent lane line
            lane_surf = pygame.Surface((self.gw, 1), pygame.SRCALPHA)
            lane_surf.fill((255, 255, 255, 30))
            surf.blit(lane_surf, (ox, int(ly)))
            c = NOTE_COLORS.get(nn, GRAY)
            # note label with outline for readability
            lbl = sf.render(nn, True, c)
            # shadow
            shadow = sf.render(nn, True, BLACK)
            surf.blit(shadow, (ox + 6, int(ly) - lbl.get_height() // 2 + 1))
            surf.blit(lbl, (ox + 5, int(ly) - lbl.get_height() // 2))

        for w in self.walls:
            w.draw(surf, ox, oy)
        self.ball.draw(surf, oy)

        hf = pygame.font.SysFont("Segoe UI", 24, bold=True)
        # score with shadow
        sc_shadow = hf.render(f"Score: {self.score}", True, BLACK)
        sc_text = hf.render(f"Score: {self.score}", True, WHITE)
        surf.blit(sc_shadow, (ox + self.gw - 159, oy + 11))
        surf.blit(sc_text, (ox + self.gw - 160, oy + 10))

        for i in range(self.lives):
            hx = ox + self.gw - 160 + i * 30
            hy = oy + 45
            pygame.draw.circle(surf, RED, (hx, hy), 8)
            pygame.draw.circle(surf, RED, (hx + 10, hy), 8)
            pygame.draw.polygon(surf, RED, [(hx - 8, hy + 2), (hx + 18, hy + 2), (hx + 5, hy + 16)])

        if self.combo > 1:
            cb_shadow = hf.render(f"Combo x{self.combo}", True, BLACK)
            cb_text = hf.render(f"Combo x{self.combo}", True, YELLOW)
            surf.blit(cb_shadow, (ox + self.gw - 159, oy + 71))
            surf.blit(cb_text, (ox + self.gw - 160, oy + 70))

        if self.over:
            ov = pygame.Surface((self.gw, self.gh), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 180))
            surf.blit(ov, (ox, oy))
            gf = pygame.font.SysFont("Segoe UI", 52, bold=True)
            t = gf.render("GAME OVER", True, RED)
            surf.blit(t, (ox + self.gw // 2 - t.get_width() // 2, oy + self.gh // 2 - 60))
            t2 = hf.render(f"Final Score: {self.score}", True, WHITE)
            surf.blit(t2, (ox + self.gw // 2 - t2.get_width() // 2, oy + self.gh // 2))
            t3 = hf.render(f"Max Combo: {self.max_combo}", True, YELLOW)
            surf.blit(t3, (ox + self.gw // 2 - t3.get_width() // 2, oy + self.gh // 2 + 35))
            rf = pygame.font.SysFont("Segoe UI", 20)
            t4 = rf.render("Press SPACE to restart", True, LGRAY)
            surf.blit(t4, (ox + self.gw // 2 - t4.get_width() // 2, oy + self.gh // 2 + 80))
