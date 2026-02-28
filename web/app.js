/**
 * Do Re Mi TikTok — main web application.
 * Three screens: Menu → Playing (free mode) → Game.
 * Webcam displayed via hidden <video>, drawn to canvas.
 */

const W = 1100, H = 700;
const FPS = 30;
const SIDE_W = 320;
const CAM_W = 300, CAM_H = 225;

const RANGE_OPTIONS = [
    { label: "Auto",      offset: 0   },
    { label: "Very Low",  offset: -24 },
    { label: "Low",       offset: -12 },
    { label: "Normal",    offset: 0   },
    { label: "High",      offset: 12  },
    { label: "Very High", offset: 24  },
];

class App {
    constructor() {
        this.canvas = document.getElementById("gameCanvas");
        this.ctx = this.canvas.getContext("2d");
        this.canvas.width = W;
        this.canvas.height = H;

        this.video = document.getElementById("webcamVideo");
        this.videoReady = false;

        this.state = "menu"; // menu | playing | game
        this.pitch = null;
        this.game = new Game(W, H);

        // Audio snapshot
        this._freq = 0;
        this._note = null;
        this._nidx = -1;
        this._vol = 0;

        // Devices
        this.devices = [];
        this.devSel = 0;
        this.dropdownOpen = false;

        // Vocal range
        this.rangeSel = 0;
        this.rangeOpen = false;

        // Calibration
        this._calMsg = "";
        this._calMsgTimer = 0;

        // Events
        this.canvas.addEventListener("click", e => this._click(e));
        document.addEventListener("keydown", e => this._key(e));

        this.lastTime = 0;
        this._startWebcam();
        this._enumDevices();
        requestAnimationFrame(t => this._loop(t));
    }

    // ── webcam ──────────────────────────────────────────────
    async _startWebcam() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            this.video.srcObject = stream;
            this.video.play();
            this.videoReady = true;
            // After permission, we can enumerate with labels
            this._enumDevices();
        } catch (e) {
            console.warn("Webcam not available:", e);
        }
    }

    async _enumDevices() {
        this.devices = await getInputDevices();
    }

    // ── audio ───────────────────────────────────────────────
    async _startAudio() {
        this._stopAudio();
        this.pitch = new PitchDetector();
        const deviceId = this.devices.length > 0 ? this.devices[this.devSel].id : null;
        try {
            await this.pitch.start(deviceId);
        } catch (e) {
            console.error("Audio error:", e);
            this.pitch = null;
        }
    }

    _stopAudio() {
        if (this.pitch) {
            this.pitch.stop();
            this.pitch = null;
        }
    }

    // ── events ──────────────────────────────────────────────
    _key(e) {
        if (e.key === "Escape") {
            if (this.state === "game") {
                this.state = "playing";
                this.game.active = false;
            } else if (this.state === "playing") {
                this.state = "menu";
                this._stopAudio();
            }
        }
        if (e.key === " " && this.state === "game" && !this.game.active) {
            this.game.start();
        }
    }

    _click(e) {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = W / rect.width;
        const scaleY = H / rect.height;
        const mx = (e.clientX - rect.left) * scaleX;
        const my = (e.clientY - rect.top) * scaleY;

        if (this.state === "menu") this._clickMenu(mx, my);
        else if (this.state === "playing") this._clickPlay(mx, my);
        else if (this.state === "game") this._clickGame(mx, my);
    }

    _clickMenu(mx, my) {
        const leftW = Math.floor(W / 2);

        // Dropdown
        if (_inRect(mx, my, 50, 290, 450, 35)) {
            this.dropdownOpen = !this.dropdownOpen;
            return;
        }
        if (this.dropdownOpen) {
            for (let i = 0; i < Math.min(this.devices.length, 8); i++) {
                if (_inRect(mx, my, 50, 330 + i * 30, 450, 28)) {
                    this.devSel = i;
                    this.dropdownOpen = false;
                    return;
                }
            }
            this.dropdownOpen = false;
            return;
        }

        // Start button
        if (_inRect(mx, my, leftW / 2 - 100, 580, 200, 50)) {
            this.state = "playing";
            this._startAudio();
        }
    }

    _clickPlay(mx, my) {
        // Range dropdown
        const ry = CAM_H + 260;
        if (this.rangeOpen) {
            for (let i = 0; i < RANGE_OPTIONS.length; i++) {
                if (_inRect(mx, my, 20, ry + 35 + i * 28, SIDE_W - 40, 26)) {
                    this.rangeSel = i;
                    this.rangeOpen = false;
                    if (RANGE_OPTIONS[i].label !== "Auto" && this.pitch) {
                        this.pitch.semitoneOffset = RANGE_OPTIONS[i].offset;
                    }
                    return;
                }
            }
            this.rangeOpen = false;
            return;
        }
        if (_inRect(mx, my, 20, ry, SIDE_W - 40, 30)) {
            this.rangeOpen = !this.rangeOpen;
            return;
        }

        // Calibrate
        if (_inRect(mx, my, 20, H - 130, SIDE_W - 40, 40)) {
            if (this.pitch && !this.pitch.calibrationActive()) {
                this.pitch.startCalibration();
                this._calMsg = "Sing now! Listening for 3 seconds...";
                this._calMsgTimer = 0;
            }
            return;
        }

        // Start Game
        if (_inRect(mx, my, 40, H - 70, SIDE_W - 80, 45)) {
            this.state = "game";
            this.game.start();
        }
    }

    _clickGame(mx, my) {
        if (_inRect(mx, my, 10, H - 50, 100, 35)) {
            this.state = "playing";
            this.game.active = false;
        }
    }

    // ── update ──────────────────────────────────────────────
    _update() {
        if (this.pitch) {
            const s = this.pitch.snapshot();
            this._freq = s.freq;
            this._note = s.note;
            this._nidx = s.noteIdx;
            this._vol = s.vol;

            if (this.pitch.calibrationActive()) {
                if (this.pitch.calibrationProgress() >= 1.0) {
                    this.pitch.finishCalibration();
                    this._calMsg = this.pitch.calResult || "Calibration done.";
                    this._calMsgTimer = FPS * 6;
                }
            }
        } else {
            this._freq = 0; this._note = null; this._nidx = -1; this._vol = 0;
        }

        if (this._calMsgTimer > 0) {
            this._calMsgTimer--;
            if (this._calMsgTimer <= 0) this._calMsg = "";
        }

        if (this.state === "game" && this.game.active) {
            this.game.update(this._nidx);
        }
    }

    // ── draw ────────────────────────────────────────────────
    _draw() {
        const ctx = this.ctx;
        ctx.fillStyle = "#191928";
        ctx.fillRect(0, 0, W, H);

        if (this.state === "menu") this._drawMenu(ctx);
        else if (this.state === "playing") this._drawPlay(ctx);
        else if (this.state === "game") this._drawGame(ctx);
    }

    // ── menu ────────────────────────────────────────────────
    _drawMenu(ctx) {
        const leftW = Math.floor(W / 2);

        // Title
        ctx.font = "bold 32px 'Segoe UI', Calibri, Arial, sans-serif";
        ctx.fillStyle = WHITE;
        ctx.textAlign = "center";
        ctx.fillText("Do Re Mi TikTok", leftW / 2, 60);
        ctx.font = "16px 'Segoe UI', Calibri, Arial, sans-serif";
        ctx.fillStyle = LGRAY;
        ctx.fillText("Sing to control the ball!", leftW / 2, 95);
        ctx.textAlign = "left";

        // Microphone label
        ctx.font = "bold 22px 'Segoe UI', Calibri, Arial, sans-serif";
        ctx.fillStyle = WHITE;
        ctx.fillText("Microphone:", 50, 270);

        // Dropdown
        ctx.fillStyle = DGRAY;
        _fillRoundRect(ctx, 50, 290, 450, 35, 4);
        ctx.strokeStyle = LGRAY; ctx.lineWidth = 2;
        _strokeRoundRect(ctx, 50, 290, 450, 35, 4);

        ctx.font = "16px 'Segoe UI', Calibri, Arial, sans-serif";
        let nm = this.devices.length > 0 ? this.devices[this.devSel]?.name || "No devices" : "No devices found";
        if (nm.length > 50) nm = nm.slice(0, 47) + "...";
        ctx.fillStyle = WHITE;
        ctx.fillText(nm, 60, 313);
        ctx.fillText("v", 480, 313);

        if (this.dropdownOpen && this.devices.length > 0) {
            for (let i = 0; i < Math.min(this.devices.length, 8); i++) {
                const ry = 330 + i * 30;
                ctx.fillStyle = i === this.devSel ? "#464664" : "#323246";
                ctx.fillRect(50, ry, 450, 28);
                ctx.strokeStyle = LGRAY; ctx.lineWidth = 1;
                ctx.strokeRect(50, ry, 450, 28);
                let dn = this.devices[i].name;
                if (dn.length > 50) dn = dn.slice(0, 47) + "...";
                ctx.fillStyle = WHITE;
                ctx.fillText(dn, 60, ry + 19);
            }
        }

        if (!this.dropdownOpen) {
            const lines = [
                { t: "How to play:", head: true },
                { t: "1. Select your microphone", head: false },
                { t: "2. Click 'Start' to begin", head: false },
                { t: "3. Sing notes to see them detected", head: false },
                { t: "4. Start the game and control the ball", head: false },
                { t: "5. Pass through holes by singing the right note!", head: false },
            ];
            for (let i = 0; i < lines.length; i++) {
                ctx.font = lines[i].head ? "bold 22px 'Segoe UI'" : "16px 'Segoe UI'";
                ctx.fillStyle = lines[i].head ? YELLOW : LGRAY;
                ctx.fillText(lines[i].t, 50, 420 + i * 26);
            }
        }

        // Start button
        const bx = leftW / 2 - 100, by = 580;
        ctx.fillStyle = GREEN;
        _fillRoundRect(ctx, bx, by, 200, 50, 10);
        ctx.font = "bold 22px 'Segoe UI', Calibri, Arial, sans-serif";
        ctx.fillStyle = BLACK;
        ctx.textAlign = "center";
        ctx.fillText("Start", bx + 100, by + 32);
        ctx.textAlign = "left";

        // Webcam preview (right panel)
        const camX = leftW + 20;
        const camW = W - leftW - 40;
        const camH = Math.round(camW * 3 / 4);
        const camY = Math.round(H / 2 - camH / 2);

        if (this.videoReady) {
            ctx.drawImage(this.video, camX, camY, camW, camH);
            ctx.strokeStyle = LGRAY; ctx.lineWidth = 2;
            ctx.strokeRect(camX, camY, camW, camH);
        } else {
            ctx.fillStyle = DGRAY;
            ctx.fillRect(camX, camY, camW, camH);
            ctx.strokeStyle = LGRAY; ctx.lineWidth = 2;
            ctx.strokeRect(camX, camY, camW, camH);
            ctx.font = "16px 'Segoe UI'";
            ctx.fillStyle = LGRAY;
            ctx.textAlign = "center";
            ctx.fillText("Webcam preview", camX + camW / 2, camY + camH / 2 - 5);
            ctx.fillStyle = GRAY;
            ctx.fillText("(click Start to begin)", camX + camW / 2, camY + camH / 2 + 15);
            ctx.textAlign = "left";
        }

        // Divider
        ctx.strokeStyle = "#323246"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(leftW, 20); ctx.lineTo(leftW, H - 20); ctx.stroke();
    }

    // ── playing ─────────────────────────────────────────────
    _drawPlay(ctx) {
        // Sidebar background
        ctx.fillStyle = "#1e1e32";
        ctx.fillRect(0, 0, SIDE_W, H);

        // Webcam
        if (this.videoReady) {
            ctx.drawImage(this.video, 10, 10, CAM_W, CAM_H);
        } else {
            ctx.fillStyle = DGRAY;
            ctx.fillRect(10, 10, CAM_W, CAM_H);
            ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = LGRAY;
            ctx.textAlign = "center";
            ctx.fillText("No webcam", 10 + CAM_W / 2, 10 + CAM_H / 2);
            ctx.textAlign = "left";
        }

        // Detected Note
        const ny = CAM_H + 30;
        ctx.font = "bold 22px 'Segoe UI'"; ctx.fillStyle = WHITE;
        ctx.fillText("Detected Note:", 20, ny + 18);

        if (this._note) {
            const base = this._note.replace("5", "").replace("3", "");
            const nc = NOTE_COLORS_MAP[base] || WHITE;
            ctx.font = "bold 52px 'Segoe UI'";
            ctx.fillStyle = nc;
            ctx.textAlign = "center";
            ctx.fillText(this._note, SIDE_W / 2, ny + 75);
            ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = LGRAY;
            ctx.fillText(`${this._freq.toFixed(1)} Hz`, SIDE_W / 2, ny + 105);
            ctx.textAlign = "left";
        } else {
            ctx.font = "bold 52px 'Segoe UI'"; ctx.fillStyle = GRAY;
            ctx.textAlign = "center";
            ctx.fillText("--", SIDE_W / 2, ny + 75);
            ctx.textAlign = "left";
        }

        // Volume
        const vy = ny + 120;
        ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = LGRAY;
        ctx.fillText("Volume:", 20, vy + 14);
        ctx.fillStyle = DGRAY;
        ctx.fillRect(20, vy + 22, SIDE_W - 40, 12);
        const vw = Math.min(1, this._vol * 10) * (SIDE_W - 40);
        ctx.fillStyle = this._vol > 0.01 ? GREEN : GRAY;
        ctx.fillRect(20, vy + 22, vw, 12);

        // ── Vocal range dropdown ──
        const ry = CAM_H + 260;
        ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = LGRAY;
        ctx.fillText("Vocal Range:", 20, ry - 4);

        ctx.fillStyle = DGRAY;
        _fillRoundRect(ctx, 20, ry, SIDE_W - 40, 30, 4);
        ctx.strokeStyle = LGRAY; ctx.lineWidth = 2;
        _strokeRoundRect(ctx, 20, ry, SIDE_W - 40, 30, 4);

        const selOpt = RANGE_OPTIONS[this.rangeSel];
        const dispTxt = selOpt.label === "Auto" ? "Auto" : `${selOpt.label} (${selOpt.offset > 0 ? "+" : ""}${selOpt.offset} st)`;
        ctx.fillStyle = WHITE;
        ctx.fillText(dispTxt, 28, ry + 20);
        ctx.fillText("v", SIDE_W - 62, ry + 20);

        if (this.rangeOpen) {
            for (let i = 0; i < RANGE_OPTIONS.length; i++) {
                const iy = ry + 35 + i * 28;
                ctx.fillStyle = i === this.rangeSel ? "#464664" : "#323246";
                ctx.fillRect(20, iy, SIDE_W - 40, 26);
                ctx.strokeStyle = LGRAY; ctx.lineWidth = 1;
                ctx.strokeRect(20, iy, SIDE_W - 40, 26);
                const o = RANGE_OPTIONS[i];
                const txt = o.label === "Auto" ? "Auto" : `${o.label} (${o.offset > 0 ? "+" : ""}${o.offset} st)`;
                ctx.fillStyle = WHITE;
                ctx.fillText(txt, 28, iy + 18);
            }
        }

        // Scale offset + raw freq
        const sy = H - 185;
        const offset = this.pitch ? this.pitch.semitoneOffset : 0;
        ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = LGRAY;
        ctx.fillText(`Scale offset: ${offset >= 0 ? "+" : ""}${offset} semitones`, 20, sy + 14);
        if (this._freq > 0) {
            ctx.fillStyle = GRAY;
            ctx.fillText(`Raw freq: ${this._freq.toFixed(1)} Hz`, 20, sy + 34);
        }

        // Calibrate button
        const calBtn = { x: 20, y: H - 130, w: SIDE_W - 40, h: 40 };
        const isCal = this.pitch && this.pitch.calibrationActive();
        ctx.fillStyle = isCal ? YELLOW : "#6428c8";
        _fillRoundRect(ctx, calBtn.x, calBtn.y, calBtn.w, calBtn.h, 8);
        if (isCal) {
            const prog = this.pitch ? this.pitch.calibrationProgress() : 0;
            const fillW = prog * (calBtn.w - 4);
            ctx.fillStyle = GREEN;
            _fillRoundRect(ctx, calBtn.x + 2, calBtn.y + 2, fillW, calBtn.h - 4, 6);
            ctx.font = "bold 22px 'Segoe UI'"; ctx.fillStyle = BLACK;
            ctx.textAlign = "center";
            ctx.fillText(`Listening... ${(prog * 100).toFixed(0)}%`, calBtn.x + calBtn.w / 2, calBtn.y + calBtn.h / 2 + 8);
        } else {
            ctx.font = "bold 22px 'Segoe UI'"; ctx.fillStyle = WHITE;
            ctx.textAlign = "center";
            ctx.fillText("Calibrate Scale", calBtn.x + calBtn.w / 2, calBtn.y + calBtn.h / 2 + 8);
        }
        ctx.textAlign = "left";

        // Calibration result message
        if (this._calMsg) {
            ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = YELLOW;
            _wrapText(ctx, this._calMsg, 20, H - 78, SIDE_W - 50, 18);
        }

        // 3-octave scale (right panel)
        this._drawScale(ctx);

        // Start Game button
        const gbtn = { x: 40, y: H - 70, w: SIDE_W - 80, h: 45 };
        ctx.fillStyle = BLUE;
        _fillRoundRect(ctx, gbtn.x, gbtn.y, gbtn.w, gbtn.h, 8);
        ctx.font = "bold 22px 'Segoe UI'"; ctx.fillStyle = WHITE;
        ctx.textAlign = "center";
        ctx.fillText("Start Game", gbtn.x + gbtn.w / 2, gbtn.y + gbtn.h / 2 + 8);
        ctx.textAlign = "left";

        ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = GRAY;
        ctx.fillText("ESC to go back", 20, H - 8);
    }

    _drawScale(ctx) {
        const sx = SIDE_W + 20;
        const sw = W - SIDE_W - 40;
        const sy = 20, sh = H - 40;

        ctx.fillStyle = "#141423";
        _fillRoundRect(ctx, sx - 10, sy - 10, sw + 20, sh + 20, 10);

        const octaves = [
            { label: "3", shift: -12 },
            { label: "4", shift: 0 },
            { label: "5", shift: 12 },
        ];
        const allNotes = [];
        for (const oct of octaves) {
            for (const nn of GAME_NOTES) {
                const baseFreq = NOTE_FREQUENCIES[nn] || 0;
                const freq = baseFreq * Math.pow(2, oct.shift / 12.0);
                const label = oct.label !== "4" ? `${nn}${oct.label}` : nn;
                allNotes.push({ label, baseName: nn, freq, octLabel: oct.label });
            }
        }

        const nTotal = allNotes.length;
        const slot = sh / nTotal;
        const offset = this.pitch ? this.pitch.semitoneOffset : 0;

        for (let i = 0; i < allNotes.length; i++) {
            const { label, baseName, freq, octLabel } = allNotes[i];
            const y = sy + sh - (i + 1) * slot;
            let rgb = NOTE_RGB[baseName] || [100, 100, 100];
            if (octLabel !== "4") {
                rgb = rgb.map(v => Math.max(0, v - 60));
            }

            // Check if currently detected
            let cur = false;
            if (this._note) {
                const curBase = this._note.replace("5", "").replace("3", "");
                if (curBase === baseName) {
                    if (octLabel === "4" && !this._note.includes("5") && !this._note.includes("3")) cur = true;
                    else if (octLabel === "5" && this._note.includes("5")) cur = true;
                    else if (octLabel === "3" && this._note.includes("3")) cur = true;
                }
            }

            const lx = sx, lw = sw, lh = Math.max(slot - 2, 2);

            if (cur) {
                const [cr, cg, cb] = NOTE_RGB[baseName] || [100, 100, 100];
                ctx.fillStyle = `rgba(${cr},${cg},${cb},0.3)`;
                _fillRoundRect(ctx, lx, y + 1, lw, lh, 3);
                ctx.strokeStyle = `rgb(${cr},${cg},${cb})`;
                ctx.lineWidth = 2;
                _strokeRoundRect(ctx, lx, y + 1, lw, lh, 3);
            } else {
                ctx.fillStyle = octLabel === "4" ? "#232332" : "#1c1c2a";
                _fillRoundRect(ctx, lx, y + 1, lw, lh, 3);
                ctx.strokeStyle = "#323241";
                ctx.lineWidth = 1;
                _strokeRoundRect(ctx, lx, y + 1, lw, lh, 3);
            }

            // Label
            ctx.font = cur ? "bold 22px 'Segoe UI'" : "16px 'Segoe UI'";
            ctx.fillStyle = cur ? `rgb(${(NOTE_RGB[baseName]||[180,180,180]).join(",")})` : `rgb(${rgb.join(",")})`;
            ctx.fillText(label, sx + 10, y + slot / 2 + 5);

            // Frequency
            ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = GRAY;
            const adjFreq = offset !== 0 ? freq * Math.pow(2, offset / 12) : freq;
            const ftxt = `${adjFreq.toFixed(0)} Hz`;
            const tw = ctx.measureText(ftxt).width;
            ctx.fillText(ftxt, sx + sw - tw - 10, y + slot / 2 + 5);
        }

        // Octave divider labels
        ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = LGRAY;
        ctx.textAlign = "center";
        for (let j = 0; j < octaves.length; j++) {
            const divY = sy + sh - (j + 1) * GAME_NOTES.length * slot;
            ctx.fillText(`Oct ${octaves[j].label}`, sx + sw / 2, divY + 3);
        }
        ctx.textAlign = "left";
    }

    // ── game (fullscreen webcam + overlay) ───────────────────
    _drawGame(ctx) {
        // Webcam background
        if (this.videoReady) {
            ctx.drawImage(this.video, 0, 0, W, H);
            ctx.fillStyle = "rgba(0,0,0,0.4)";
            ctx.fillRect(0, 0, W, H);
        } else {
            ctx.fillStyle = "#0f0f1e";
            ctx.fillRect(0, 0, W, H);
        }

        // Game elements
        this.game.draw(ctx, 0, 0);

        // HUD overlay — note + volume (top-left)
        ctx.fillStyle = "rgba(0,0,0,0.47)";
        _fillRoundRect(ctx, 10, 10, 200, 110, 8);

        if (this._note) {
            const base = this._note.replace("5", "").replace("3", "");
            ctx.font = "bold 32px 'Segoe UI'";
            ctx.fillStyle = NOTE_COLORS_MAP[base] || WHITE;
            ctx.fillText(this._note, 20, 48);
            ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = LGRAY;
            ctx.fillText(`${this._freq.toFixed(1)} Hz`, 20, 72);
        } else {
            ctx.font = "bold 32px 'Segoe UI'"; ctx.fillStyle = GRAY;
            ctx.fillText("--", 20, 48);
        }

        // Volume bar
        ctx.fillStyle = DGRAY;
        ctx.fillRect(20, 85, 170, 8);
        const vw = Math.min(1, this._vol * 10) * 170;
        ctx.fillStyle = this._vol > 0.01 ? GREEN : GRAY;
        ctx.fillRect(20, 85, vw, 8);

        // Offset
        const off = this.pitch ? this.pitch.semitoneOffset : 0;
        if (off !== 0) {
            ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = LGRAY;
            ctx.fillText(`Scale: ${off > 0 ? "+" : ""}${off} st`, 20, 112);
        }

        // Back button
        ctx.fillStyle = "rgba(0,0,0,0.6)";
        _fillRoundRect(ctx, 10, H - 50, 100, 35, 6);
        ctx.font = "16px 'Segoe UI'"; ctx.fillStyle = WHITE;
        ctx.textAlign = "center";
        ctx.fillText("<- Back", 60, H - 28);
        ctx.textAlign = "left";
    }

    // ── main loop ───────────────────────────────────────────
    _loop(now) {
        const dt = now - this.lastTime;
        if (dt >= 1000 / FPS) {
            this.lastTime = now;
            this._update();
            this._draw();
        }
        requestAnimationFrame(t => this._loop(t));
    }
}


// ── utility functions ───────────────────────────────────────
function _inRect(mx, my, x, y, w, h) {
    return mx >= x && mx <= x + w && my >= y && my <= y + h;
}

function _fillRoundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
    ctx.fill();
}

function _strokeRoundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
    ctx.stroke();
}

function _wrapText(ctx, text, x, y, maxW, lineH) {
    const words = text.split(" ");
    let line = "";
    let cy = y;
    for (const w of words) {
        const test = line ? line + " " + w : w;
        if (ctx.measureText(test).width > maxW && line) {
            ctx.fillText(line, x, cy);
            line = w;
            cy += lineH;
        } else {
            line = test;
        }
    }
    if (line) ctx.fillText(line, x, cy);
}


// ── Boot ────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
    new App();
});
