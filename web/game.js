/**
 * Game engine — TikTok-style singing game (Canvas2D).
 * Walls scroll left as a GROUP; hit = ALL walls bounce back.
 * Passed walls fade out. Star explosion on successful pass.
 */

// ── colours ─────────────────────────────────────────────────
const WHITE  = "#ffffff";
const BLACK  = "#000000";
const GRAY   = "#646464";
const DGRAY  = "#3c3c3c";
const LGRAY  = "#b4b4b4";
const RED    = "#dc3c3c";
const GREEN  = "#3cc850";
const BLUE   = "#508cff";
const YELLOW = "#ffdc3c";
const ORANGE = "#ffa028";
const CYAN   = "#3cdcdc";
const PURPLE = "#b450dc";

const NOTE_COLORS_MAP = {
    Do: RED, Re: ORANGE, Mi: YELLOW, Fa: GREEN,
    Sol: CYAN, La: BLUE, Si: PURPLE,
};
const NOTE_RGB = {
    Do: [220,60,60], Re: [255,160,40], Mi: [255,220,60], Fa: [60,200,80],
    Sol: [60,220,220], La: [80,140,255], Si: [180,80,220],
};

const WALL_W     = 40;
const HOLE_H     = 65;
const BALL_R     = 18;
const SPEED0     = 4.5;
const SPEED_INC  = 0.15;
const SPAWN0     = 70;
const SPAWN_MIN  = 35;
const BOUNCE_VEL = 8.0;


// ── Particle ────────────────────────────────────────────────
class Particle {
    constructor(x, y, rgb) {
        this.x = x;
        this.y = y;
        const angle = Math.random() * Math.PI * 2;
        const speed = 2 + Math.random() * 6;
        this.vx = Math.cos(angle) * speed;
        this.vy = Math.sin(angle) * speed;
        this.life = 18 + Math.floor(Math.random() * 20);
        this.maxLife = this.life;
        this.rgb = rgb;
        this.size = 2 + Math.random() * 4;
        this.star = Math.random() < 0.5;
    }

    update() {
        this.x += this.vx;
        this.y += this.vy;
        this.vy += 0.12;
        this.vx *= 0.97;
        this.life--;
        return this.life > 0;
    }

    draw(ctx, ox = 0, oy = 0) {
        const alpha = this.life / this.maxLife;
        const sz = Math.max(1, this.size * alpha);
        const cx = this.x + ox;
        const cy = this.y + oy;
        const [r, g, b] = this.rgb;

        ctx.save();
        ctx.globalAlpha = alpha;
        if (this.star) {
            ctx.strokeStyle = `rgb(${r},${g},${b})`;
            ctx.lineWidth = Math.max(1, sz / 2);
            ctx.beginPath();
            ctx.moveTo(cx - sz, cy); ctx.lineTo(cx + sz, cy);
            ctx.moveTo(cx, cy - sz); ctx.lineTo(cx, cy + sz);
            const d = sz / 2;
            ctx.moveTo(cx - d, cy - d); ctx.lineTo(cx + d, cy + d);
            ctx.moveTo(cx + d, cy - d); ctx.lineTo(cx - d, cy + d);
            ctx.stroke();
        } else {
            ctx.fillStyle = `rgb(${r},${g},${b})`;
            ctx.beginPath();
            ctx.arc(cx, cy, sz, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }
}


// ── Wall ────────────────────────────────────────────────────
class Wall {
    constructor(x, noteIdx, areaH, nNotes = 7) {
        this.x = x;
        this.noteIdx = noteIdx;
        this.noteName = GAME_NOTES[noteIdx];
        const usable = areaH - 40;
        const slot = usable / nNotes;
        const cy = areaH - 20 - (noteIdx * slot + slot / 2);
        this.holeY = cy - HOLE_H / 2;
        this.w = WALL_W;
        this.passed = false;
        this.scored = false;
        this.rgb = NOTE_RGB[this.noteName] || [100, 100, 100];
        this.colorStr = NOTE_COLORS_MAP[this.noteName] || GRAY;

        this.shake = 0;
        this.fading = false;
        this.fadeAlpha = 1.0; // 1 = opaque, 0 = gone
    }

    startShake() { this.shake = 8; }

    updateFade() {
        if (this.fading) {
            this.fadeAlpha = Math.max(0, this.fadeAlpha - 0.06);
            return this.fadeAlpha > 0;
        }
        return true;
    }

    draw(ctx, ox = 0, oy = 0) {
        const x = Math.round(this.x) + ox;
        let syOff = 0;
        if (this.shake > 0) {
            syOff = Math.floor(Math.random() * this.shake * 2 - this.shake);
            this.shake--;
        }
        const [r, g, b] = this.rgb;
        const alpha = this.fading ? Math.min(0.63, this.fadeAlpha) : 0.63;

        // Top part
        const topH = Math.max(0, Math.round(this.holeY));
        if (topH > 0) {
            ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
            ctx.fillRect(x, oy + syOff, this.w, topH);
            if (!this.fading) {
                ctx.strokeStyle = this.colorStr;
                ctx.lineWidth = 2;
                ctx.strokeRect(x, oy + syOff, this.w, topH);
            }
        }

        // Bottom part
        const by = Math.round(this.holeY + HOLE_H) + oy;
        const totalH = ctx.canvas.height - oy;
        const bh = totalH - Math.round(this.holeY + HOLE_H);
        if (bh > 0) {
            ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
            ctx.fillRect(x, by + syOff, this.w, bh);
            if (!this.fading) {
                ctx.strokeStyle = this.colorStr;
                ctx.lineWidth = 2;
                ctx.strokeRect(x, by + syOff, this.w, bh);
            }
        }

        // Hole glow
        if (!this.fading) {
            ctx.strokeStyle = this.colorStr;
            ctx.lineWidth = 2;
            _roundRect(ctx, x - 3, Math.round(this.holeY) + oy - 3 + syOff,
                       this.w + 6, HOLE_H + 6, 4, false, true);
        }

        // Label
        if (this.fadeAlpha > 0.2) {
            ctx.font = "bold 16px 'Segoe UI', Calibri, Arial, sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            const lx = x + this.w / 2;
            const ly = Math.round(this.holeY + HOLE_H / 2) + oy + syOff;
            ctx.fillStyle = `rgba(0,0,0,${Math.min(1, this.fadeAlpha + 0.2)})`;
            ctx.fillText(this.noteName, lx + 1, ly + 1);
            ctx.fillStyle = `rgba(255,255,255,${Math.min(1, this.fadeAlpha + 0.2)})`;
            ctx.fillText(this.noteName, lx, ly);
            ctx.textAlign = "left";
            ctx.textBaseline = "alphabetic";
        }
    }
}


// ── Ball ────────────────────────────────────────────────────
class Ball {
    constructor(x, y) {
        this.x = x;
        this.y = y;
        this.ty = y;
        this.r = BALL_R;
        this.rgb = [255, 255, 255];
        this.colorStr = WHITE;
        this.trail = [];
    }

    setTarget(idx, areaH, n = 7) {
        if (idx < 0) return;
        const slot = (areaH - 40) / n;
        this.ty = areaH - 20 - (idx * slot + slot / 2);
        const nn = GAME_NOTES[idx];
        this.rgb = NOTE_RGB[nn] || [255, 255, 255];
        this.colorStr = NOTE_COLORS_MAP[nn] || WHITE;
    }

    update() {
        this.y += (this.ty - this.y) * 0.18;
        this.trail.push({ x: Math.round(this.x), y: Math.round(this.y) });
        if (this.trail.length > 15) this.trail.shift();
    }

    draw(ctx, oy = 0) {
        const [cr, cg, cb] = this.rgb;
        // Trail
        for (let i = 0; i < this.trail.length; i++) {
            const a = i / Math.max(this.trail.length, 1);
            const r = Math.max(3, Math.round(this.r * a * 0.6));
            ctx.globalAlpha = a * 0.5;
            ctx.fillStyle = `rgb(${Math.min(255, cr + 80)},${Math.min(255, cg + 80)},${Math.min(255, cb + 80)})`;
            ctx.beginPath();
            ctx.arc(this.trail[i].x, this.trail[i].y + oy, r, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.globalAlpha = 1;
        // Outer glow
        const grad = ctx.createRadialGradient(this.x, this.y + oy, this.r * 0.5,
                                               this.x, this.y + oy, this.r * 2);
        grad.addColorStop(0, `rgba(${cr},${cg},${cb},0.2)`);
        grad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(this.x, this.y + oy, this.r * 2, 0, Math.PI * 2);
        ctx.fill();
        // Ball
        ctx.fillStyle = this.colorStr;
        ctx.beginPath();
        ctx.arc(this.x, this.y + oy, this.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = WHITE;
        ctx.lineWidth = 2;
        ctx.stroke();
        // Specular highlight
        ctx.fillStyle = WHITE;
        ctx.beginPath();
        ctx.arc(this.x - 4, this.y - 4 + oy, 5, 0, Math.PI * 2);
        ctx.fill();
    }
}


// ── Game ────────────────────────────────────────────────────
class Game {
    constructor(w, h) {
        this.gw = w;
        this.gh = h;
        this.reset();
    }

    reset() {
        this.walls = [];
        this.ball = new Ball(100, this.gh / 2);
        this.score = 0;
        this.speed = SPEED0;
        this.stimer = 0;
        this.sint = SPAWN0;
        this.active = false;
        this.combo = 0;
        this.maxCombo = 0;
        this.frameCount = 0;
        this.particles = [];

        this.bouncing = false;
        this.bounceVel = 0;
        this.bounceTimer = 0;
        this.bounceCooldown = 0;
    }

    start() {
        this.reset();
        this.active = true;
    }

    _startBounce(hitWall) {
        if (this.bouncing || this.bounceCooldown > 0) return;
        this.bouncing = true;
        this.bounceVel = BOUNCE_VEL;
        this.bounceTimer = 25;
        hitWall.startShake();
        this.combo = 0;
    }

    _updateBounce() {
        for (const w of this.walls) {
            if (!w.fading) w.x += this.bounceVel;
        }
        this.bounceVel *= 0.88;
        this.bounceTimer--;
        if (this.bounceTimer <= 0) {
            this.bouncing = false;
            this.bounceVel = 0;
            this.bounceCooldown = 10;
            this.stimer = 0;
        }
    }

    _spawnParticles(wall) {
        const cx = wall.x + wall.w / 2;
        const cy = wall.holeY + HOLE_H / 2;
        const baseRgb = wall.rgb;
        for (let i = 0; i < 22; i++) {
            const r = Math.random();
            let c;
            if (r < 0.25) c = [255, 220, 60];
            else if (r < 0.45) c = [255, 255, 255];
            else c = baseRgb;
            this.particles.push(new Particle(cx, cy, c));
        }
    }

    update(noteIdx) {
        if (!this.active) return;

        this.frameCount++;
        this.ball.setTarget(noteIdx, this.gh);
        this.ball.update();

        if (this.bounceCooldown > 0) this.bounceCooldown--;

        // Spawn — pause while bouncing / cooldown / minimum gap
        const canSpawn = !this.bouncing
            && this.bounceCooldown <= 0
            && this.walls.every(w => w.fading || w.x < this.gw - 150);

        if (canSpawn) {
            this.stimer++;
            if (this.stimer >= this.sint) {
                this.stimer = 0;
                const ni = Math.floor(Math.random() * GAME_NOTES.length);
                this.walls.push(new Wall(this.gw, ni, this.gh));
                this.speed = Math.min(8.0, SPEED0 + this.score * SPEED_INC);
                this.sint = Math.max(SPAWN_MIN, SPAWN0 - this.score * 2);
            }
        }

        // Movement
        if (this.bouncing) {
            this._updateBounce();
        } else {
            for (const w of this.walls) {
                if (!w.passed && !w.fading) w.x -= this.speed;
            }
        }

        // Collision
        const bx = this.ball.x, by = this.ball.y, br = this.ball.r;
        if (!this.bouncing && this.bounceCooldown <= 0) {
            for (const w of this.walls) {
                if (w.passed || w.fading) continue;
                if (w.x < bx + br && w.x + w.w > bx - br) {
                    const inHole = (by - br >= w.holeY) && (by + br <= w.holeY + HOLE_H);
                    if (!inHole) {
                        this._startBounce(w);
                        break;
                    }
                }
            }
        }

        // Successful pass
        for (const w of this.walls) {
            if (w.passed || w.fading) continue;
            if (w.x + w.w < bx - br) {
                w.passed = true;
                w.scored = true;
                w.fading = true;
                this.score++;
                this.combo++;
                this.maxCombo = Math.max(this.maxCombo, this.combo);
                this._spawnParticles(w);
            }
        }

        // Fade + particles
        for (const w of this.walls) {
            if (w.fading) w.updateFade();
        }
        this.particles = this.particles.filter(p => p.update());

        // Cleanup
        this.walls = this.walls.filter(w => w.fadeAlpha > 0 && w.x + w.w > -200);
    }

    draw(ctx, ox = 0, oy = 0) {
        const usable = this.gh - 40;
        const slot = usable / GAME_NOTES.length;

        // Lane lines
        ctx.font = "bold 15px 'Segoe UI', Calibri, Arial, sans-serif";
        ctx.textBaseline = "middle";
        for (let i = 0; i < GAME_NOTES.length; i++) {
            const nn = GAME_NOTES[i];
            const ly = this.gh - 20 - (i * slot + slot / 2) + oy;
            ctx.strokeStyle = "rgba(255,255,255,0.12)";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(ox, ly);
            ctx.lineTo(ox + this.gw, ly);
            ctx.stroke();
            ctx.fillStyle = BLACK;
            ctx.fillText(nn, ox + 6, ly + 1);
            ctx.fillStyle = NOTE_COLORS_MAP[nn] || GRAY;
            ctx.fillText(nn, ox + 5, ly);
        }
        ctx.textBaseline = "alphabetic";

        // Walls (fading first)
        const sorted = [...this.walls].sort((a, b) => (a.fading ? 0 : 1) - (b.fading ? 0 : 1));
        for (const w of sorted) w.draw(ctx, ox, oy);

        // Particles
        for (const p of this.particles) p.draw(ctx, ox, oy);

        // Ball
        this.ball.draw(ctx, oy);

        // HUD
        ctx.font = "bold 24px 'Segoe UI', Calibri, Arial, sans-serif";
        ctx.textAlign = "right";
        ctx.fillStyle = BLACK;
        ctx.fillText(`Score: ${this.score}`, ox + this.gw - 19, oy + 31);
        ctx.fillStyle = WHITE;
        ctx.fillText(`Score: ${this.score}`, ox + this.gw - 20, oy + 30);

        if (this.combo > 1) {
            ctx.fillStyle = BLACK;
            ctx.fillText(`Combo x${this.combo}`, ox + this.gw - 19, oy + 61);
            ctx.fillStyle = YELLOW;
            ctx.fillText(`Combo x${this.combo}`, ox + this.gw - 20, oy + 60);
        }

        ctx.font = "bold 15px 'Segoe UI', Calibri, Arial, sans-serif";
        ctx.fillStyle = LGRAY;
        ctx.fillText(`Speed: ${this.speed.toFixed(1)}`, ox + this.gw - 20, oy + 85);
        ctx.textAlign = "left";
    }
}


// ── helper: rounded rect ────────────────────────────────────
function _roundRect(ctx, x, y, w, h, r, fill, stroke) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
    if (fill) ctx.fill();
    if (stroke) ctx.stroke();
}
