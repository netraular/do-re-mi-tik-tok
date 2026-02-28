/**
 * Pitch detection module — YIN algorithm ported from Python.
 * Uses Web Audio API AnalyserNode for non-blocking audio capture.
 */

// ── note tables ─────────────────────────────────────────────
const GAME_NOTES = ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"];

const NOTE_FREQUENCIES = {
    Do: 261.63, Re: 293.66, Mi: 329.63, Fa: 349.23,
    Sol: 392.00, La: 440.00, Si: 493.88,
    Do5: 523.25, Re5: 587.33, Mi5: 659.25,
    Fa5: 698.46, Sol5: 783.99, La5: 880.00, Si5: 987.77,
};

const BASE_FREQS = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88];

const CHUNK = 2048;

// ── YIN pitch detection ─────────────────────────────────────
function yinPitch(signal, sr, threshold = 0.15) {
    const N = signal.length;
    const tauMax = Math.floor(N / 2);
    if (tauMax < 2) return 0;

    const W = tauMax;

    // Cumulative sum of squares
    const cum = new Float64Array(N + 1);
    for (let i = 0; i < N; i++) {
        cum[i + 1] = cum[i] + signal[i] * signal[i];
    }
    const energyStart = cum[W]; // sum x[0..W-1]^2

    // Difference function
    const d = new Float64Array(tauMax);
    for (let tau = 1; tau < tauMax; tau++) {
        const energyShifted = cum[tau + W] - cum[tau];
        let cross = 0;
        for (let j = 0; j < W; j++) {
            cross += signal[j] * signal[j + tau];
        }
        d[tau] = energyStart + energyShifted - 2.0 * cross;
    }

    // Cumulative mean normalized difference
    const dPrime = new Float64Array(tauMax);
    dPrime[0] = 1.0;
    let running = 0;
    for (let tau = 1; tau < tauMax; tau++) {
        running += d[tau];
        dPrime[tau] = running === 0 ? 1.0 : (d[tau] * tau) / running;
    }

    // Absolute threshold — find first tau where d'(tau) < threshold
    let tauBest = 0;
    for (let tau = 2; tau < tauMax; tau++) {
        if (dPrime[tau] < threshold) {
            while (tau + 1 < tauMax && dPrime[tau + 1] < dPrime[tau]) {
                tau++;
            }
            tauBest = tau;
            break;
        }
    }

    if (tauBest === 0) return 0;

    // Parabolic interpolation
    if (tauBest > 0 && tauBest < tauMax - 1) {
        const s0 = dPrime[tauBest - 1];
        const s1 = dPrime[tauBest];
        const s2 = dPrime[tauBest + 1];
        const denom = 2.0 * s1 - s2 - s0;
        if (Math.abs(denom) > 1e-10) {
            const delta = (s0 - s2) / (2.0 * denom);
            tauBest += delta;
        }
    }

    return sr / tauBest;
}

function freqToNote(freq, semitoneOffset = 0) {
    if (freq < 60 || freq > 1200) return { note: null, idx: -1 };

    let bestName = null;
    let bestIdx = -1;
    let bestDist = 999;

    for (let i = 0; i < BASE_FREQS.length; i++) {
        for (const octaveShift of [-12, 0, 12]) {
            const ref = BASE_FREQS[i] * Math.pow(2, (semitoneOffset + octaveShift) / 12.0);
            if (ref < 30) continue;
            const dist = Math.abs(12.0 * Math.log2(freq / ref));
            if (dist < bestDist) {
                bestDist = dist;
                bestIdx = i;
                const suffix = octaveShift === 0 ? "" : (octaveShift === 12 ? "5" : "3");
                bestName = GAME_NOTES[i] + suffix;
            }
        }
    }

    if (bestDist > 1.2) return { note: null, idx: -1 };
    return { note: bestName, idx: bestIdx };
}


// ── PitchDetector class ─────────────────────────────────────
class PitchDetector {
    constructor() {
        this.audioCtx = null;
        this.analyser = null;
        this.source = null;
        this.stream = null;
        this.sampleRate = 44100;

        this.currentFrequency = 0;
        this.currentNote = null;
        this.currentNoteIndex = -1;
        this.volume = 0;
        this.semitoneOffset = 0;

        // Calibration
        this._calibrating = false;
        this._calFreqs = [];
        this._calStart = 0;
        this.calResult = null;

        this._buffer = null;
        this._running = false;
    }

    async start(deviceId) {
        const constraints = { audio: deviceId ? { deviceId: { exact: deviceId } } : true };
        this.stream = await navigator.mediaDevices.getUserMedia(constraints);

        this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        this.sampleRate = this.audioCtx.sampleRate;
        this.source = this.audioCtx.createMediaStreamSource(this.stream);

        this.analyser = this.audioCtx.createAnalyser();
        this.analyser.fftSize = CHUNK * 2;
        this.source.connect(this.analyser);

        this._buffer = new Float32Array(this.analyser.fftSize);
        this._running = true;
        this._processLoop();
    }

    _processLoop() {
        if (!this._running) return;

        this.analyser.getFloatTimeDomainData(this._buffer);

        // RMS volume
        let sum = 0;
        for (let i = 0; i < this._buffer.length; i++) {
            sum += this._buffer[i] * this._buffer[i];
        }
        const rms = Math.sqrt(sum / this._buffer.length);
        this.volume = rms;

        if (rms > 0.008) {
            const f = yinPitch(this._buffer, this.sampleRate);
            if (f > 60) {
                const { note, idx } = freqToNote(f, this.semitoneOffset);
                this.currentFrequency = f;
                this.currentNote = note;
                this.currentNoteIndex = idx;

                if (this._calibrating && f > 60) {
                    this._calFreqs.push(f);
                }
            } else {
                this.currentFrequency = 0;
                this.currentNote = null;
                this.currentNoteIndex = -1;
            }
        } else {
            this.currentFrequency = 0;
            this.currentNote = null;
            this.currentNoteIndex = -1;
        }

        // ~30 fps processing
        setTimeout(() => this._processLoop(), 33);
    }

    snapshot() {
        return {
            freq: this.currentFrequency,
            note: this.currentNote,
            noteIdx: this.currentNoteIndex,
            vol: this.volume,
        };
    }

    // ── calibration ─────────────────────────────────────────
    startCalibration() {
        this._calFreqs = [];
        this._calibrating = true;
        this._calStart = performance.now();
        this.calResult = null;
    }

    calibrationActive() {
        return this._calibrating;
    }

    calibrationProgress() {
        if (!this._calibrating) return 0;
        const elapsed = (performance.now() - this._calStart) / 1000;
        return Math.min(elapsed / 3.0, 1.0);
    }

    finishCalibration() {
        this._calibrating = false;
        const freqs = [...this._calFreqs];
        this._calFreqs = [];

        if (freqs.length < 5) {
            this.calResult = "Not enough sound detected. Sing louder!";
            return false;
        }

        freqs.sort((a, b) => a - b);
        const median = freqs[Math.floor(freqs.length / 2)];
        const low = freqs[Math.floor(freqs.length * 0.1)];
        const high = freqs[Math.floor(freqs.length * 0.9)];

        let bestOffset = 0;
        let bestErr = 999;

        for (let offset = -24; offset <= 24; offset++) {
            let totalErr = 0;
            for (const f of freqs) {
                const { idx } = freqToNote(f, offset);
                if (idx < 0) {
                    totalErr += 2.0;
                } else {
                    const dists = [-12, 0, 12].map(os2 => {
                        const r = BASE_FREQS[idx] * Math.pow(2, (offset + os2) / 12.0);
                        return Math.abs(12 * Math.log2(f / r));
                    });
                    totalErr += Math.min(...dists);
                }
            }
            const avg = totalErr / freqs.length;
            if (avg < bestErr) {
                bestErr = avg;
                bestOffset = offset;
            }
        }

        this.semitoneOffset = bestOffset;
        this.calResult = `Range: ${low.toFixed(0)}-${high.toFixed(0)} Hz (median ${median.toFixed(0)} Hz). Offset: ${bestOffset > 0 ? "+" : ""}${bestOffset} semitones.`;
        return true;
    }

    stop() {
        this._running = false;
        if (this.source) { try { this.source.disconnect(); } catch (e) {} }
        if (this.audioCtx) { try { this.audioCtx.close(); } catch (e) {} }
        if (this.stream) {
            this.stream.getTracks().forEach(t => t.stop());
        }
        this.audioCtx = null;
        this.analyser = null;
        this.source = null;
        this.stream = null;
    }
}

// ── Device enumeration ──────────────────────────────────────
async function getInputDevices() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        return devices
            .filter(d => d.kind === "audioinput")
            .map(d => ({ id: d.deviceId, name: d.label || `Microphone ${d.deviceId.slice(0, 8)}` }));
    } catch (e) {
        return [];
    }
}
