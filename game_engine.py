"""
Game engine -- TikTok-style singing game.
Walls scroll left; each has a hole at a specific note height.
When the ball hits a wall it BOUNCES BACK and must be passed correctly.
No lives -- the wall just pushes back until you pass through.
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
HOLE_H       = 65
BALL_R       = 18
SPEED0       = 4.5          # much faster base speed
SPEED_INC    = 0.15
SPAWN0       = 70           # frames between walls (faster spawning)
SPAWN_MIN    = 35
BOUNCE_VEL   = 8.0          # speed at which wall bounces back


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

        # Bounce state
        self.bouncing = False       # True while wall is pushed back
        self.bounce_vel = 0.0       # current bounce velocity (positive = moving right)
        self.bounce_timer = 0       # frames remaining in bounce
        self.shake = 0              # visual shake effect

    def start_bounce(self):
        """Trigger a bounce-back effect."""
        if not self.bouncing:
            self.bouncing = True
            self.bounce_vel = BOUNCE_VEL
            self.bounce_timer = 25   # frames for bounce
            self.shake = 6

    def update_bounce(self):
        """Update bounce physics. Returns True if still bouncing."""
        if not self.bouncing:
            return False
        self.x += self.bounce_vel
        self.bounce_vel *= 0.88     # decelerate
        self.bounce_timer -= 1
        if self.shake > 0:
            self.shake -= 1
        if self.bounce_timer <= 0:
            self.bouncing = False
            self.bounce_vel = 0.0
        return True

    def draw(self, surf, ox=0, oy=0):
        x = int(self.x) + ox
        # shake offset
        sy_off = random.randint(-self.shake, self.shake) if self.shake > 0 else 0
        ah = surf.get_height() - oy

        # top part
        top_h = int(self.hole_y)
        if top_h > 0:
            top_s = pygame.Surface((self.w, top_h), pygame.SRCALPHA)
            top_s.fill((*self.color[:3], 160))
            surf.blit(top_s, (x, oy + sy_off))
            pygame.draw.rect(surf, self.color, (x, oy + sy_off, self.w, top_h), 2)

        # bottom part
        by = int(self.hole_y + HOLE_H) + oy
        bh = ah - int(self.hole_y + HOLE_H)
        if bh > 0:
            bot_s = pygame.Surface((self.w, bh), pygame.SRCALPHA)
            bot_s.fill((*self.color[:3], 160))
            surf.blit(bot_s, (x, by + sy_off))
            pygame.draw.rect(surf, self.color, (x, by + sy_off, self.w, bh), 2)

        # hole glow
        glow_r = pygame.Rect(x - 3, int(self.hole_y) + oy - 3 + sy_off, self.w + 6, HOLE_H + 6)
        glow_c = WHITE if self.bouncing else self.color
        pygame.draw.rect(surf, glow_c, glow_r, 2, border_radius=4)

        # label
        f = pygame.font.SysFont("Segoe UI", 16, bold=True)
        lbl = f.render(self.note_name, True, WHITE)
        shadow = f.render(self.note_name, True, BLACK)
        lx = x + self.w // 2 - lbl.get_width() // 2
        ly = int(self.hole_y + HOLE_H / 2 - lbl.get_height() / 2) + oy + sy_off
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
        self.y += (self.ty - self.y) * 0.18
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
        self.ball = Ball(100, self.gh // 2)
        self.score = 0
        self.over = False
        self.speed = SPEED0
        self.stimer = 0
        self.sint = SPAWN0
        self.active = False
        self.combo = 0
        self.max_combo = 0
        self.frame_count = 0

    def start(self):
        self.reset()
        self.active = True

    def update(self, note_idx):
        if not self.active:
            return

        self.frame_count += 1
        self.ball.set_target(note_idx, self.gh)
        self.ball.update()

        # Spawn walls
        self.stimer += 1
        if self.stimer >= self.sint:
            self.stimer = 0
            ni = random.randint(0, len(GAME_NOTES) - 1)
            self.walls.append(Wall(self.gw, ni, self.gh))
            # Increase difficulty over time
            self.speed = min(8.0, SPEED0 + self.score * SPEED_INC)
            self.sint = max(SPAWN_MIN, SPAWN0 - self.score * 2)

        # Move walls (skip bouncing ones)
        for w in self.walls:
            if w.bouncing:
                w.update_bounce()
            else:
                if not w.passed:
                    w.x -= self.speed

        # Collision detection
        bx, by, br = self.ball.x, self.ball.y, self.ball.r
        for w in self.walls:
            if w.passed:
                continue

            # Is the ball overlapping the wall's x range?
            if w.x < bx + br and w.x + w.w > bx - br:
                hole_top = w.hole_y
                hole_bot = w.hole_y + HOLE_H

                # Ball is in the hole? (fully inside)
                ball_in_hole = (by - br >= hole_top) and (by + br <= hole_bot)

                if not ball_in_hole:
                    # COLLISION -- bounce the wall back!
                    if not w.bouncing:
                        w.start_bounce()
                        self.combo = 0

            # Has the wall fully passed the ball?
            if w.x + w.w < bx - br and not w.passed:
                w.passed = True
                if not w.scored:
                    w.scored = True
                    self.score += 1
                    self.combo += 1
                    self.max_combo = max(self.max_combo, self.combo)

            # Off-screen cleanup
            if w.x + w.w < -100:
                w.passed = True

        self.walls = [w for w in self.walls if not (w.passed and w.x + w.w < -100)]

    # ── draw ─────────────────────────────────────────────────
    def draw(self, surf, ox=0, oy=0):
        # No solid background -- webcam is drawn behind

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
            shadow = sf.render(nn, True, BLACK)
            lbl = sf.render(nn, True, c)
            surf.blit(shadow, (ox + 6, int(ly) - lbl.get_height() // 2 + 1))
            surf.blit(lbl, (ox + 5, int(ly) - lbl.get_height() // 2))

        for w in self.walls:
            w.draw(surf, ox, oy)
        self.ball.draw(surf, oy)

        # HUD
        hf = pygame.font.SysFont("Segoe UI", 24, bold=True)

        # Score (top right)
        sc_shadow = hf.render(f"Score: {self.score}", True, BLACK)
        sc_text = hf.render(f"Score: {self.score}", True, WHITE)
        surf.blit(sc_shadow, (ox + self.gw - 159, oy + 11))
        surf.blit(sc_text, (ox + self.gw - 160, oy + 10))

        # Combo
        if self.combo > 1:
            cb_shadow = hf.render(f"Combo x{self.combo}", True, BLACK)
            cb_text = hf.render(f"Combo x{self.combo}", True, YELLOW)
            surf.blit(cb_shadow, (ox + self.gw - 159, oy + 41))
            surf.blit(cb_text, (ox + self.gw - 160, oy + 40))

        # Speed indicator
        spd_text = sf.render(f"Speed: {self.speed:.1f}", True, LGRAY)
        surf.blit(spd_text, (ox + self.gw - 160, oy + 70))
