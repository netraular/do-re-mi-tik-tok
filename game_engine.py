"""
Game engine -- TikTok-style singing game.

Walls scroll left as a GROUP.  When the ball hits ANY wall,
ALL walls bounce back together.
Walls that the ball passes through fade out and disappear.
Star / sparkle explosions on each successful pass.
"""

import random
import math
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
SPEED0       = 4.5
SPEED_INC    = 0.15
SPAWN0       = 70
SPAWN_MIN    = 35
BOUNCE_VEL   = 8.0          # px/frame push-back speed


# ── Particle (star explosion) ───────────────────────────────
class Particle:
    """A single sparkle / star particle."""

    def __init__(self, x, y, color):
        self.x, self.y = float(x), float(y)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(2, 8)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = random.randint(18, 38)
        self.max_life = self.life
        self.color = color
        self.size = random.uniform(2, 6)
        self.star = random.random() < 0.5      # star shape vs circle

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.12          # gravity
        self.vx *= 0.97
        self.life -= 1
        return self.life > 0

    def draw(self, surf, ox=0, oy=0):
        alpha = int(255 * self.life / self.max_life)
        sz = max(1, int(self.size * self.life / self.max_life))
        cx, cy = int(self.x) + ox, int(self.y) + oy
        if self.star:
            dim = sz * 2
            ps = pygame.Surface((dim * 2 + 4, dim * 2 + 4), pygame.SRCALPHA)
            c = (*self.color[:3], alpha)
            cc = (dim + 2, dim + 2)
            t = max(1, sz // 2)
            pygame.draw.line(ps, c, (cc[0] - dim, cc[1]), (cc[0] + dim, cc[1]), t)
            pygame.draw.line(ps, c, (cc[0], cc[1] - dim), (cc[0], cc[1] + dim), t)
            d = dim // 2
            pygame.draw.line(ps, c, (cc[0] - d, cc[1] - d), (cc[0] + d, cc[1] + d), max(1, t - 1))
            pygame.draw.line(ps, c, (cc[0] + d, cc[1] - d), (cc[0] - d, cc[1] + d), max(1, t - 1))
            surf.blit(ps, (cx - dim - 2, cy - dim - 2))
        else:
            ps = pygame.Surface((sz * 2 + 2, sz * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(ps, (*self.color[:3], alpha), (sz + 1, sz + 1), sz)
            surf.blit(ps, (cx - sz - 1, cy - sz - 1))


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

        # Visual shake (only the wall that was hit)
        self.shake = 0

        # Fade out after being passed
        self.fading = False
        self.fade_alpha = 255        # 255 = opaque, 0 = gone

    def start_shake(self):
        self.shake = 8

    def update_fade(self):
        """Returns True while still visible."""
        if self.fading:
            self.fade_alpha = max(0, self.fade_alpha - 15)   # ~17 frames to vanish
            return self.fade_alpha > 0
        return True

    def draw(self, surf, ox=0, oy=0):
        x = int(self.x) + ox
        sy_off = random.randint(-self.shake, self.shake) if self.shake > 0 else 0
        if self.shake > 0:
            self.shake -= 1
        ah = surf.get_height() - oy
        alpha = min(160, self.fade_alpha) if self.fading else 160

        # ── top part ──
        top_h = int(self.hole_y)
        if top_h > 0:
            top_s = pygame.Surface((self.w, top_h), pygame.SRCALPHA)
            top_s.fill((*self.color[:3], alpha))
            surf.blit(top_s, (x, oy + sy_off))
            if not self.fading:
                pygame.draw.rect(surf, self.color, (x, oy + sy_off, self.w, top_h), 2)

        # ── bottom part ──
        by = int(self.hole_y + HOLE_H) + oy
        bh = ah - int(self.hole_y + HOLE_H)
        if bh > 0:
            bot_s = pygame.Surface((self.w, bh), pygame.SRCALPHA)
            bot_s.fill((*self.color[:3], alpha))
            surf.blit(bot_s, (x, by + sy_off))
            if not self.fading:
                pygame.draw.rect(surf, self.color, (x, by + sy_off, self.w, bh), 2)

        # ── hole glow ──
        if not self.fading:
            glow_r = pygame.Rect(x - 3, int(self.hole_y) + oy - 3 + sy_off,
                                 self.w + 6, HOLE_H + 6)
            pygame.draw.rect(surf, self.color, glow_r, 2, border_radius=4)

        # ── label ──
        if alpha > 30:
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
        pygame.draw.circle(glow, (*self.color[:3], 50),
                           (self.r * 2, self.r * 2), self.r * 2)
        surf.blit(glow, (int(self.x) - self.r * 2,
                         int(self.y) + oy - self.r * 2))
        # ball
        pygame.draw.circle(surf, self.color,
                           (int(self.x), int(self.y) + oy), self.r)
        pygame.draw.circle(surf, WHITE,
                           (int(self.x), int(self.y) + oy), self.r, 2)
        pygame.draw.circle(surf, WHITE,
                           (int(self.x) - 4, int(self.y) - 4 + oy), 5)


# ── Game ─────────────────────────────────────────────────────
class Game:
    def __init__(self, w, h):
        self.gw, self.gh = w, h
        self.reset()

    def reset(self):
        self.walls: list[Wall] = []
        self.ball = Ball(100, self.gh // 2)
        self.score = 0
        self.speed = SPEED0
        self.stimer = 0
        self.sint = SPAWN0
        self.active = False
        self.combo = 0
        self.max_combo = 0
        self.frame_count = 0
        self.particles: list[Particle] = []

        # ── global bounce (all walls move together) ──
        self.bouncing = False
        self.bounce_vel = 0.0
        self.bounce_timer = 0
        self.bounce_cooldown = 0     # frames before next bounce allowed

    def start(self):
        self.reset()
        self.active = True

    # ── bounce helpers ───────────────────────────────────────
    def _start_bounce(self, hit_wall):
        """Push ALL walls back; only the struck wall shakes."""
        if self.bouncing or self.bounce_cooldown > 0:
            return
        self.bouncing = True
        self.bounce_vel = BOUNCE_VEL
        self.bounce_timer = 25
        hit_wall.start_shake()
        self.combo = 0

    def _update_bounce(self):
        """Move every non-fading wall rightward while bouncing."""
        for w in self.walls:
            if not w.fading:
                w.x += self.bounce_vel
        self.bounce_vel *= 0.88
        self.bounce_timer -= 1
        if self.bounce_timer <= 0:
            self.bouncing = False
            self.bounce_vel = 0.0
            self.bounce_cooldown = 10    # small grace period
            self.stimer = 0              # reset spawn timer so walls don't appear instantly

    # ── particle helpers ─────────────────────────────────────
    def _spawn_particles(self, wall):
        cx = wall.x + wall.w / 2
        cy = wall.hole_y + HOLE_H / 2
        base_c = wall.color
        for _ in range(22):
            r = random.random()
            if r < 0.25:
                c = YELLOW
            elif r < 0.45:
                c = WHITE
            else:
                c = base_c
            self.particles.append(Particle(cx, cy, c))

    # ── main update ──────────────────────────────────────────
    def update(self, note_idx):
        if not self.active:
            return

        self.frame_count += 1
        self.ball.set_target(note_idx, self.gh)
        self.ball.update()

        # Bounce cooldown
        if self.bounce_cooldown > 0:
            self.bounce_cooldown -= 1

        # Spawn walls -- PAUSE while bouncing or in cooldown,
        # and enforce minimum gap so walls never clump.
        can_spawn = (not self.bouncing
                     and self.bounce_cooldown <= 0
                     and all(w.x < self.gw - 150
                             for w in self.walls if not w.fading))
        if can_spawn:
            self.stimer += 1
            if self.stimer >= self.sint:
                self.stimer = 0
                ni = random.randint(0, len(GAME_NOTES) - 1)
                self.walls.append(Wall(self.gw, ni, self.gh))
                self.speed = min(8.0, SPEED0 + self.score * SPEED_INC)
                self.sint = max(SPAWN_MIN, SPAWN0 - self.score * 2)

        # ── movement ─────────────────────────────────────────
        if self.bouncing:
            self._update_bounce()
        else:
            for w in self.walls:
                if not w.passed and not w.fading:
                    w.x -= self.speed

        # ── collision ────────────────────────────────────────
        bx, by, br = self.ball.x, self.ball.y, self.ball.r
        if not self.bouncing and self.bounce_cooldown <= 0:
            for w in self.walls:
                if w.passed or w.fading:
                    continue
                # overlap on x?
                if w.x < bx + br and w.x + w.w > bx - br:
                    hole_top = w.hole_y
                    hole_bot = w.hole_y + HOLE_H
                    ball_in_hole = (by - br >= hole_top) and (by + br <= hole_bot)
                    if not ball_in_hole:
                        self._start_bounce(w)
                        break          # one bounce per frame max

        # ── successful pass ──────────────────────────────────
        for w in self.walls:
            if w.passed or w.fading:
                continue
            if w.x + w.w < bx - br:
                w.passed = True
                w.scored = True
                w.fading = True
                self.score += 1
                self.combo += 1
                self.max_combo = max(self.max_combo, self.combo)
                self._spawn_particles(w)

        # ── fade + particles ─────────────────────────────────
        for w in self.walls:
            if w.fading:
                w.update_fade()

        self.particles = [p for p in self.particles if p.update()]

        # ── cleanup ──────────────────────────────────────────
        self.walls = [w for w in self.walls
                      if w.fade_alpha > 0 and w.x + w.w > -200]

    # ── draw ─────────────────────────────────────────────────
    def draw(self, surf, ox=0, oy=0):
        # No solid background (webcam is drawn behind)

        usable = self.gh - 40
        slot = usable / len(GAME_NOTES)
        sf = pygame.font.SysFont("Segoe UI", 15, bold=True)

        # lane lines
        for i, nn in enumerate(GAME_NOTES):
            ly = self.gh - 20 - (i * slot + slot / 2) + oy
            lane_surf = pygame.Surface((self.gw, 1), pygame.SRCALPHA)
            lane_surf.fill((255, 255, 255, 30))
            surf.blit(lane_surf, (ox, int(ly)))
            c = NOTE_COLORS.get(nn, GRAY)
            shadow = sf.render(nn, True, BLACK)
            lbl = sf.render(nn, True, c)
            surf.blit(shadow, (ox + 6, int(ly) - lbl.get_height() // 2 + 1))
            surf.blit(lbl, (ox + 5, int(ly) - lbl.get_height() // 2))

        # walls (sorted so fading ones draw first)
        for w in sorted(self.walls, key=lambda w: (not w.fading,)):
            w.draw(surf, ox, oy)

        # particles (on top of walls)
        for p in self.particles:
            p.draw(surf, ox, oy)

        # ball on top of everything
        self.ball.draw(surf, oy)

        # ── HUD ──────────────────────────────────────────────
        hf = pygame.font.SysFont("Segoe UI", 24, bold=True)

        # Score (top right)
        sc_shadow = hf.render(f"Score: {self.score}", True, BLACK)
        sc_text   = hf.render(f"Score: {self.score}", True, WHITE)
        surf.blit(sc_shadow, (ox + self.gw - 159, oy + 11))
        surf.blit(sc_text,   (ox + self.gw - 160, oy + 10))

        # Combo
        if self.combo > 1:
            cb_shadow = hf.render(f"Combo x{self.combo}", True, BLACK)
            cb_text   = hf.render(f"Combo x{self.combo}", True, YELLOW)
            surf.blit(cb_shadow, (ox + self.gw - 159, oy + 41))
            surf.blit(cb_text,   (ox + self.gw - 160, oy + 40))

        # Speed
        spd_text = sf.render(f"Speed: {self.speed:.1f}", True, LGRAY)
        surf.blit(spd_text, (ox + self.gw - 160, oy + 70))
