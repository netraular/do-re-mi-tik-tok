"""
Do Re Mi TikTok -- main application.
Webcam runs on a background thread.  Audio uses PyAudio callback.
The pygame loop never blocks.
"""

import sys
import os
import threading
import cv2
import numpy as np
import pygame

from pitch_detector import (
    PitchDetector, get_input_devices,
    GAME_NOTES, NOTE_FREQUENCIES,
)
from game_engine import (
    Game, NOTE_COLORS,
    WHITE, BLACK, GRAY, LGRAY, DGRAY, GREEN, RED, YELLOW, BLUE,
)

# ── layout constants ─────────────────────────────────────────
W, H         = 1100, 700
FPS          = 30
CAM_W, CAM_H = 320, 240
SIDE_W       = 320
GAME_W       = W - SIDE_W
GAME_H       = H

# ── load a font that supports accents ────────────────────────
def _load_font(size, bold=False):
    """Try Segoe UI (Windows) then fallback to Arial, then default."""
    for name in ("Segoe UI", "Calibri", "Arial"):
        f = pygame.font.SysFont(name, size, bold=bold)
        if f:
            return f
    return pygame.font.Font(None, size)


# ── threaded webcam ──────────────────────────────────────────
class WebcamThread:
    """Grabs frames in a daemon thread so the main loop never waits."""

    def __init__(self):
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False

    def start(self, index=0):
        if self._running:
            self.stop()
        self._cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            self._cap = None
            return
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running and self._cap is not None:
            ok, frame = self._cap.read()
            if ok:
                frame = cv2.flip(frame, 1)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                with self._lock:
                    self._frame = frame

    def get_surface(self, width=None, height=None):
        """Return a pygame Surface (optionally resized) or None."""
        with self._lock:
            f = self._frame
        if f is None:
            return None
        if width and height:
            f = cv2.resize(f, (width, height))
        return pygame.surfarray.make_surface(f.swapaxes(0, 1))

    def stop(self):
        self._running = False
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None


# ── Application ──────────────────────────────────────────────
class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Do Re Mi TikTok")
        self.clock = pygame.time.Clock()

        # Fonts that handle accents properly
        self.fl = _load_font(32, bold=True)
        self.fm = _load_font(22, bold=True)
        self.fs = _load_font(16)
        self.fn = _load_font(64, bold=True)

        self.running = True
        self.state = "menu"

        self.devices = get_input_devices()
        self.dev_sel = 0
        self.dropdown_open = False

        self.pitch: PitchDetector | None = None
        self.cam = WebcamThread()
        self.game = Game(W, H)  # game now uses full screen

        # audio snapshot
        self._freq = 0.0
        self._note = None
        self._nidx = -1
        self._vol  = 0.0

        # calibration state
        self._cal_msg = ""
        self._cal_msg_timer = 0

        # Scale range selector
        self._range_options = [
            ("Auto",       0),
            ("Very Low",  -24),
            ("Low",       -12),
            ("Normal",      0),
            ("High",       12),
            ("Very High",  24),
        ]
        self._range_sel = 0          # index into _range_options
        self._range_open = False     # dropdown open?

        # Start webcam immediately for menu preview
        self._start_cam()

    # ── audio / cam helpers ──────────────────────────────────
    def _start_audio(self):
        self._stop_audio()
        idx = None
        if self.devices and self.dev_sel < len(self.devices):
            idx = self.devices[self.dev_sel][0]
        self.pitch = PitchDetector(device_index=idx)
        try:
            self.pitch.start()
        except Exception as e:
            print("Audio error:", e)
            self.pitch = None

    def _stop_audio(self):
        if self.pitch:
            self.pitch.stop()
            self.pitch = None

    def _start_cam(self):
        self.cam.start(0)

    def _stop_cam(self):
        self.cam.stop()

    # ── events ───────────────────────────────────────────────
    def _events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
                return
            if ev.type == pygame.KEYDOWN:
                self._key(ev.key)
            if ev.type == pygame.MOUSEBUTTONDOWN:
                self._click(*ev.pos)

    def _key(self, k):
        if k == pygame.K_ESCAPE:
            if self.state == "game":
                self.state = "playing"
                self.game.active = False
            elif self.state == "playing":
                self.state = "menu"
                self._stop_audio()
                # keep cam running for menu preview
            else:
                self.running = False
        if k == pygame.K_SPACE and self.state == "game" and not self.game.active:
            self.game.start()

    def _click(self, mx, my):
        if self.state == "menu":
            self._click_menu(mx, my)
        elif self.state == "playing":
            self._click_play(mx, my)
        elif self.state == "game":
            self._click_game(mx, my)

    # ── menu clicks ──────────────────────────────────────────
    def _click_menu(self, mx, my):
        # dropdown
        dd = pygame.Rect(50, 290, 450, 35)
        if dd.collidepoint(mx, my):
            self.dropdown_open = not self.dropdown_open
            return
        if self.dropdown_open:
            for i in range(min(len(self.devices), 8)):
                r = pygame.Rect(50, 330 + i * 30, 450, 28)
                if r.collidepoint(mx, my):
                    self.dev_sel = i
                    self.dropdown_open = False
                    return
            self.dropdown_open = False
            return
        # start button – must match _draw_menu
        left_w = W // 2
        btn = pygame.Rect(left_w // 2 - 100, 580, 200, 50)
        if btn.collidepoint(mx, my):
            self.state = "playing"
            self._start_cam()
            self._start_audio()

    def _click_play(self, mx, my):
        # ── range dropdown ──
        range_btn = pygame.Rect(20, CAM_H + 260, SIDE_W - 40, 30)
        if self._range_open:
            for i in range(len(self._range_options)):
                r = pygame.Rect(20, CAM_H + 295 + i * 28, SIDE_W - 40, 26)
                if r.collidepoint(mx, my):
                    self._range_sel = i
                    self._range_open = False
                    label, offset = self._range_options[i]
                    if label == "Auto":
                        pass  # keep whatever calibration set
                    elif self.pitch:
                        self.pitch.semitone_offset = offset
                    return
            self._range_open = False
            return
        if range_btn.collidepoint(mx, my):
            self._range_open = not self._range_open
            return

        # game button
        btn = pygame.Rect(40, H - 70, SIDE_W - 80, 45)
        if btn.collidepoint(mx, my):
            self.state = "game"
            self.game.start()
        # calibrate button
        cal_btn = pygame.Rect(20, H - 130, SIDE_W - 40, 40)
        if cal_btn.collidepoint(mx, my):
            if self.pitch and not self.pitch.calibration_active():
                self.pitch.start_calibration()
                self._cal_msg = "Sing now! Listening for 3 seconds..."
                self._cal_msg_timer = 0

    def _click_game(self, mx, my):
        # back button (bottom-left overlay)
        btn = pygame.Rect(10, H - 50, 100, 35)
        if btn.collidepoint(mx, my):
            self.state = "playing"
            self.game.active = False

    # ── update ───────────────────────────────────────────────
    def _update(self):
        if self.pitch:
            self._freq, self._note, self._nidx, self._vol = self.pitch.snapshot()

            # handle calibration completion
            if self.pitch.calibration_active():
                if self.pitch.calibration_progress() >= 1.0:
                    self.pitch.finish_calibration()
                    self._cal_msg = self.pitch.cal_result or "Calibration done."
                    self._cal_msg_timer = FPS * 6  # show for 6 seconds
        else:
            self._freq, self._note, self._nidx, self._vol = 0, None, -1, 0

        # tick calibration message timer
        if self._cal_msg_timer > 0:
            self._cal_msg_timer -= 1
            if self._cal_msg_timer <= 0:
                self._cal_msg = ""

        if self.state == "game" and self.game.active:
            self.game.update(self._nidx)

    # ── draw ─────────────────────────────────────────────────
    def _draw(self):
        self.screen.fill((25, 25, 40))
        if self.state == "menu":
            self._draw_menu()
        elif self.state == "playing":
            self._draw_play()
        elif self.state == "game":
            self._draw_game()
        pygame.display.flip()

    # ---- menu ------------------------------------------------
    def _draw_menu(self):
        s = self.screen

        # LEFT PANEL – controls
        left_w = W // 2
        # Title
        t = self.fl.render("Do Re Mi TikTok", True, WHITE)
        s.blit(t, (left_w // 2 - t.get_width() // 2, 40))
        t2 = self.fs.render("Sing to control the ball!", True, LGRAY)
        s.blit(t2, (left_w // 2 - t2.get_width() // 2, 85))

        # Microphone label (ASCII-safe to avoid font issues)
        s.blit(self.fm.render("Microphone:", True, WHITE), (50, 250))

        # Dropdown
        dd = pygame.Rect(50, 290, 450, 35)
        pygame.draw.rect(s, DGRAY, dd)
        pygame.draw.rect(s, LGRAY, dd, 2)
        if self.devices and self.dev_sel < len(self.devices):
            nm = self.devices[self.dev_sel][1]
            if len(nm) > 50:
                nm = nm[:47] + "..."
        else:
            nm = "No devices found"
        s.blit(self.fs.render(nm, True, WHITE), (60, 298))
        s.blit(self.fs.render("v", True, WHITE), (dd.right - 25, 298))

        if self.dropdown_open and self.devices:
            for i, (_, name) in enumerate(self.devices[:8]):
                r = pygame.Rect(50, 330 + i * 30, 450, 28)
                bg = (70, 70, 100) if i == self.dev_sel else (50, 50, 70)
                pygame.draw.rect(s, bg, r)
                pygame.draw.rect(s, LGRAY, r, 1)
                dn = name if len(name) <= 50 else name[:47] + "..."
                s.blit(self.fs.render(dn, True, WHITE), (60, 333 + i * 30))

        if not self.dropdown_open:
            lines = [
                ("How to play:", True),
                ("1. Select your microphone", False),
                ("2. Click 'Start' to begin", False),
                ("3. Sing notes to see them detected", False),
                ("4. Start the game and control the ball", False),
                ("5. Pass through holes by singing the right note!", False),
                ("", False),
                ("Use UP/DOWN arrows to shift scale", False),
            ]
            for i, (txt, head) in enumerate(lines):
                c = YELLOW if head else LGRAY
                f = self.fm if head else self.fs
                if txt:
                    s.blit(f.render(txt, True, c), (50, 400 + i * 26))

        # Start button
        btn = pygame.Rect(left_w // 2 - 100, 580, 200, 50)
        pygame.draw.rect(s, GREEN, btn, border_radius=10)
        bt = self.fm.render("Start", True, BLACK)
        s.blit(bt, (btn.centerx - bt.get_width() // 2, btn.centery - bt.get_height() // 2))

        # RIGHT PANEL – webcam preview
        cam_x = left_w + 20
        cam_w = W - left_w - 40
        cam_h = int(cam_w * 3 / 4)
        cam_y = H // 2 - cam_h // 2

        frame = self.cam.get_surface(cam_w, cam_h)
        if frame:
            s.blit(frame, (cam_x, cam_y))
            pygame.draw.rect(s, LGRAY, (cam_x, cam_y, cam_w, cam_h), 2)
        else:
            r = pygame.Rect(cam_x, cam_y, cam_w, cam_h)
            pygame.draw.rect(s, DGRAY, r)
            pygame.draw.rect(s, LGRAY, r, 2)
            t = self.fs.render("Webcam preview", True, LGRAY)
            s.blit(t, (r.centerx - t.get_width() // 2, r.centery - 10))
            t2 = self.fs.render("(starts when you click Start)", True, GRAY)
            s.blit(t2, (r.centerx - t2.get_width() // 2, r.centery + 12))

        # Divider
        pygame.draw.line(s, (50, 50, 70), (left_w, 20), (left_w, H - 20), 1)

    # ---- playing (free mode) ---------------------------------
    def _draw_play(self):
        s = self.screen
        pygame.draw.rect(s, (30, 30, 50), (0, 0, SIDE_W, H))

        # webcam
        frame = self.cam.get_surface(CAM_W, CAM_H)
        if frame:
            s.blit(frame, (10, 10))
        else:
            r = pygame.Rect(10, 10, CAM_W, CAM_H)
            pygame.draw.rect(s, DGRAY, r)
            t = self.fs.render("No webcam", True, LGRAY)
            s.blit(t, (r.centerx - t.get_width() // 2, r.centery))

        # note display
        ny = CAM_H + 30
        s.blit(self.fm.render("Detected Note:", True, WHITE), (20, ny))

        if self._note:
            base = self._note.replace("5", "")
            nc = NOTE_COLORS.get(base, WHITE)
            nt = self.fn.render(self._note, True, nc)
            s.blit(nt, (SIDE_W // 2 - nt.get_width() // 2, ny + 35))
            ft = self.fs.render(f"{self._freq:.1f} Hz", True, LGRAY)
            s.blit(ft, (SIDE_W // 2 - ft.get_width() // 2, ny + 110))
        else:
            d = self.fn.render("--", True, GRAY)
            s.blit(d, (SIDE_W // 2 - d.get_width() // 2, ny + 35))

        # volume
        vy = ny + 140
        s.blit(self.fs.render("Volume:", True, LGRAY), (20, vy))
        pygame.draw.rect(s, DGRAY, (20, vy + 22, SIDE_W - 40, 12))
        vw = min(1.0, self._vol * 10) * (SIDE_W - 40)
        vc = GREEN if self._vol > 0.01 else GRAY
        pygame.draw.rect(s, vc, (20, vy + 22, int(vw), 12))

        # ── Vocal range dropdown ──
        ry = CAM_H + 260
        s.blit(self.fs.render("Vocal Range:", True, LGRAY), (20, ry - 18))
        range_btn = pygame.Rect(20, ry, SIDE_W - 40, 30)
        pygame.draw.rect(s, DGRAY, range_btn, border_radius=4)
        pygame.draw.rect(s, LGRAY, range_btn, 2, border_radius=4)
        sel_label, sel_off = self._range_options[self._range_sel]
        disp = f"{sel_label}" if sel_label == "Auto" else f"{sel_label} ({sel_off:+d} st)"
        s.blit(self.fs.render(disp, True, WHITE), (28, ry + 6))
        s.blit(self.fs.render("v", True, WHITE), (range_btn.right - 22, ry + 6))

        if self._range_open:
            for i, (lbl, off) in enumerate(self._range_options):
                r = pygame.Rect(20, ry + 35 + i * 28, SIDE_W - 40, 26)
                bg = (70, 70, 100) if i == self._range_sel else (50, 50, 70)
                pygame.draw.rect(s, bg, r)
                pygame.draw.rect(s, LGRAY, r, 1)
                txt = f"{lbl}" if lbl == "Auto" else f"{lbl} ({off:+d} st)"
                s.blit(self.fs.render(txt, True, WHITE), (28, ry + 38 + i * 28))

        # Scale offset display + Calibrate button
        sy = H - 185
        offset = self.pitch.semitone_offset if self.pitch else 0
        s.blit(self.fs.render(f"Scale offset: {offset:+d} semitones", True, LGRAY), (20, sy))

        # Show raw frequency for debugging
        if self._freq > 0:
            s.blit(self.fs.render(f"Raw freq: {self._freq:.1f} Hz", True, GRAY), (20, sy + 20))

        # Calibrate button
        cal_btn = pygame.Rect(20, H - 130, SIDE_W - 40, 40)
        is_cal = self.pitch and self.pitch.calibration_active()
        cal_color = YELLOW if is_cal else (100, 60, 200)
        pygame.draw.rect(s, cal_color, cal_btn, border_radius=8)
        if is_cal:
            prog = self.pitch.calibration_progress() if self.pitch else 0
            # progress bar inside button
            fill_w = int(prog * (cal_btn.width - 4))
            pygame.draw.rect(s, (60, 200, 80), (cal_btn.x + 2, cal_btn.y + 2, fill_w, cal_btn.height - 4), border_radius=6)
            ct = self.fm.render(f"Listening... {prog*100:.0f}%", True, BLACK)
        else:
            ct = self.fm.render("Calibrate Scale", True, WHITE)
        s.blit(ct, (cal_btn.centerx - ct.get_width() // 2, cal_btn.centery - ct.get_height() // 2))

        # Calibration result message
        if self._cal_msg:
            # wrap text
            words = self._cal_msg.split()
            lines_msg = []
            line = ""
            for w in words:
                test = line + " " + w if line else w
                if self.fs.size(test)[0] > SIDE_W - 50:
                    lines_msg.append(line)
                    line = w
                else:
                    line = test
            if line:
                lines_msg.append(line)
            for i, ln in enumerate(lines_msg):
                msg_t = self.fs.render(ln, True, YELLOW)
                s.blit(msg_t, (20, H - 80 + i * 18))

        # note scale on right
        self._draw_scale()

        # game button
        btn = pygame.Rect(40, H - 70, SIDE_W - 80, 45)
        pygame.draw.rect(s, BLUE, btn, border_radius=8)
        gt = self.fm.render("Start Game", True, WHITE)
        s.blit(gt, (btn.centerx - gt.get_width() // 2, btn.centery - gt.get_height() // 2))

        s.blit(self.fs.render("ESC to go back", True, GRAY), (20, H - 20))

    def _draw_scale(self):
        """Draw 3 octaves of notes (octave 3, 4, 5) on the right panel."""
        s = self.screen
        sx = SIDE_W + 20
        sw = W - SIDE_W - 40
        sy, sh = 20, H - 40
        pygame.draw.rect(s, (20, 20, 35), (sx - 10, sy - 10, sw + 20, sh + 20), border_radius=10)

        # Build all 21 notes across 3 octaves
        octaves = [
            ("3", -12),  # octave below
            ("4", 0),    # main octave
            ("5", 12),   # octave above
        ]
        all_notes = []
        for oct_label, semitone_shift in octaves:
            for nn in GAME_NOTES:
                base_freq = NOTE_FREQUENCIES.get(nn, 0)
                freq = base_freq * (2 ** (semitone_shift / 12.0))
                label = f"{nn}{oct_label}" if oct_label != "4" else nn
                all_notes.append((label, nn, freq, oct_label))

        n_total = len(all_notes)
        slot = sh / n_total
        font_small = self.fs
        offset = self.pitch.semitone_offset if self.pitch else 0

        for i, (label, base_name, freq, oct_label) in enumerate(all_notes):
            y = sy + sh - (i + 1) * slot
            c = NOTE_COLORS.get(base_name, GRAY)
            # Dim notes in octaves 3 and 5
            if oct_label != "4":
                c = tuple(max(0, v - 60) for v in c)

            # Check if this is the currently detected note
            cur = False
            if self._note:
                cur_base = self._note.replace("5", "").replace("3", "")
                if cur_base == base_name:
                    # match octave too
                    if (oct_label == "4" and "5" not in self._note and "3" not in self._note):
                        cur = True
                    elif oct_label == "5" and "5" in self._note:
                        cur = True
                    elif oct_label == "3" and "3" in self._note:
                        cur = True

            lr = pygame.Rect(sx, int(y) + 1, sw, max(int(slot) - 2, 2))
            if cur:
                pygame.draw.rect(s, (*NOTE_COLORS.get(base_name, GRAY), 80), lr, border_radius=3)
                pygame.draw.rect(s, NOTE_COLORS.get(base_name, GRAY), lr, 2, border_radius=3)
            else:
                bg = (35, 35, 50) if oct_label == "4" else (28, 28, 42)
                pygame.draw.rect(s, bg, lr, border_radius=3)
                pygame.draw.rect(s, (50, 50, 65), lr, 1, border_radius=3)

            # Note label
            f = self.fm if cur else font_small
            tc = NOTE_COLORS.get(base_name, GRAY) if cur else c
            t = f.render(label, True, tc)
            text_y = int(y + slot / 2 - t.get_height() / 2)
            s.blit(t, (sx + 10, text_y))

            # Frequency
            if offset != 0:
                adj = freq * (2 ** (offset / 12))
                ftxt = f"{adj:.0f} Hz"
            else:
                ftxt = f"{freq:.0f} Hz"
            ft = font_small.render(ftxt, True, GRAY)
            s.blit(ft, (sx + sw - ft.get_width() - 10, text_y))

        # Octave divider labels
        for j, (oct_label, _) in enumerate(octaves):
            div_y = sy + sh - (j + 1) * len(GAME_NOTES) * slot
            oct_t = font_small.render(f"Oct {oct_label}", True, LGRAY)
            s.blit(oct_t, (sx + sw // 2 - oct_t.get_width() // 2, int(div_y) - 2))

    # ---- game (FULLSCREEN webcam + overlay) ------------------
    def _draw_game(self):
        s = self.screen

        # 1) Draw webcam as full-screen background
        frame = self.cam.get_surface(W, H)
        if frame:
            s.blit(frame, (0, 0))
            # darken slightly so game elements are visible
            overlay = pygame.Surface((W, H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 100))
            s.blit(overlay, (0, 0))
        else:
            s.fill((15, 15, 30))

        # 2) Draw game elements on top (full screen)
        self.game.draw(s, ox=0, oy=0)

        # 3) HUD overlay – note + volume (top-left, semi-transparent)
        hud = pygame.Surface((200, 120), pygame.SRCALPHA)
        hud.fill((0, 0, 0, 120))
        s.blit(hud, (10, 10))

        if self._note:
            base = self._note.replace("5", "")
            nc = NOTE_COLORS.get(base, WHITE)
            nt = self.fl.render(self._note, True, nc)
            s.blit(nt, (20, 15))
            ft = self.fs.render(f"{self._freq:.1f} Hz", True, LGRAY)
            s.blit(ft, (20, 55))
        else:
            d = self.fl.render("--", True, GRAY)
            s.blit(d, (20, 15))

        # volume bar
        pygame.draw.rect(s, DGRAY, (20, 85, 170, 8))
        vw = min(1.0, self._vol * 10) * 170
        vc = GREEN if self._vol > 0.01 else GRAY
        pygame.draw.rect(s, vc, (20, 85, int(vw), 8))

        # Scale offset display
        offset = self.pitch.semitone_offset if self.pitch else 0
        if offset != 0:
            ot = self.fs.render(f"Scale: {offset:+d} st", True, LGRAY)
            s.blit(ot, (20, 100))

        # 4) Back button (bottom-left)
        br = pygame.Rect(10, H - 50, 100, 35)
        btn_bg = pygame.Surface((100, 35), pygame.SRCALPHA)
        btn_bg.fill((0, 0, 0, 150))
        s.blit(btn_bg, (10, H - 50))
        bt = self.fs.render("<- Back", True, WHITE)
        s.blit(bt, (br.centerx - bt.get_width() // 2, br.centery - bt.get_height() // 2))

    # ── main loop ────────────────────────────────────────────
    def run(self):
        try:
            while self.running:
                self._events()
                self._update()
                self._draw()
                self.clock.tick(FPS)
        finally:
            self._stop_audio()
            self._stop_cam()
            pygame.quit()


if __name__ == "__main__":
    App().run()
