"""
Pitch detection module -- YIN algorithm (much more accurate for voice).
Uses PyAudio callback mode so the main thread is never blocked.
Includes calibration support for detecting the singer's octave range.
"""

import threading
import time
import numpy as np
import pyaudio

# ── note tables ──────────────────────────────────────────────
NOTE_FREQUENCIES = {
    "Do": 261.63, "Re": 293.66, "Mi": 329.63, "Fa": 349.23,
    "Sol": 392.00, "La": 440.00, "Si": 493.88,
    "Do5": 523.25, "Re5": 587.33, "Mi5": 659.25,
    "Fa5": 698.46, "Sol5": 783.99, "La5": 880.00, "Si5": 987.77,
}

GAME_NOTES = ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"]

# Base frequencies for the 7 notes (octave 4)
BASE_FREQS = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88]

RATE = 44100
CHUNK = 2048
FORMAT = pyaudio.paFloat32
CHANNELS = 1


# ── helpers ──────────────────────────────────────────────────
def get_input_devices():
    """Return list of (index, name) for audio input devices."""
    p = pyaudio.PyAudio()
    devices = []
    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                devices.append((i, info["name"]))
        except Exception:
            pass
    p.terminate()
    return devices


# ── YIN pitch detection ─────────────────────────────────────
def _yin_pitch(signal, sr, threshold=0.15):
    """
    YIN algorithm for fundamental frequency detection.
    Returns frequency in Hz, or 0 if no clear pitch.
    """
    N = len(signal)
    tau_max = N // 2
    if tau_max < 2:
        return 0.0

    # Step 1-2: Difference function (vectorised)
    # d(tau) = sum_{j=0}^{W-1} (x[j] - x[j+tau])^2
    # We compute it efficiently using autocorrelation:
    #   d(tau) = r(0) + r_shifted(0) - 2*r(tau)
    x = signal[:tau_max].astype(np.float64)
    x_full = signal.astype(np.float64)

    # cumulative energy
    cum = np.cumsum(x_full ** 2)
    # energy of the window starting at tau
    # e(tau) = sum x[tau..tau+W-1]^2
    W = tau_max
    energy_start = cum[W - 1]  # sum x[0..W-1]^2

    d = np.zeros(tau_max, dtype=np.float64)
    for tau in range(1, tau_max):
        energy_shifted = cum[tau + W - 1] - cum[tau - 1]
        cross = np.dot(x_full[:W], x_full[tau:tau + W])
        d[tau] = energy_start + energy_shifted - 2.0 * cross

    # Step 3: Cumulative mean normalized difference
    d_prime = np.ones(tau_max, dtype=np.float64)
    running = 0.0
    for tau in range(1, tau_max):
        running += d[tau]
        if running == 0:
            d_prime[tau] = 1.0
        else:
            d_prime[tau] = d[tau] * tau / running

    # Step 4: Absolute threshold -- find first tau where d'(tau) < threshold
    tau_best = 0
    for tau in range(2, tau_max):
        if d_prime[tau] < threshold:
            # Step 5: find the local minimum from here
            while tau + 1 < tau_max and d_prime[tau + 1] < d_prime[tau]:
                tau += 1
            tau_best = tau
            break

    if tau_best == 0:
        return 0.0

    # Parabolic interpolation for sub-sample accuracy
    if 0 < tau_best < tau_max - 1:
        s0 = d_prime[tau_best - 1]
        s1 = d_prime[tau_best]
        s2 = d_prime[tau_best + 1]
        denom = 2.0 * s1 - s2 - s0
        if abs(denom) > 1e-10:
            delta = (s0 - s2) / (2.0 * denom)
            tau_best = tau_best + delta

    freq = sr / tau_best
    return freq


def _freq_to_note(freq, semitone_offset=0):
    """
    Map frequency to (note_name, game_note_index 0-6).
    semitone_offset shifts the reference frequencies (positive = references go up,
    so you need to sing higher to match).
    """
    if freq < 60 or freq > 1200:
        return None, -1

    best_name = None
    best_idx = -1
    best_dist = 999.0

    for i, base_f in enumerate(BASE_FREQS):
        # check octave 3, 4 and 5
        for octave_shift in (-12, 0, 12):
            ref = base_f * (2 ** ((semitone_offset + octave_shift) / 12.0))
            if ref < 30:
                continue
            dist = abs(12.0 * np.log2(freq / ref))
            if dist < best_dist:
                best_dist = dist
                best_idx = i
                suffix = "" if octave_shift == 0 else ("5" if octave_shift == 12 else "3")
                best_name = GAME_NOTES[i] + suffix

    if best_dist > 1.2:   # ~a whole tone tolerance
        return None, -1

    return best_name, best_idx


# ── detector class ───────────────────────────────────────────
class PitchDetector:
    """Non-blocking pitch detector using YIN + PyAudio callback."""

    def __init__(self, device_index=None):
        self.device_index = device_index
        self._pa = None
        self._stream = None
        self._lock = threading.Lock()

        # public state
        self.current_frequency = 0.0
        self.current_note = None
        self.current_note_index = -1
        self.volume = 0.0
        self.semitone_offset = 0          # set by calibration

        # calibration
        self._calibrating = False
        self._cal_freqs: list[float] = []
        self._cal_start = 0.0
        self.cal_result: str | None = None  # human-readable result

    # ── callback ─────────────────────────────────────────────
    def _callback(self, in_data, frame_count, time_info, status):
        try:
            samples = np.frombuffer(in_data, dtype=np.float32)
            rms = float(np.sqrt(np.mean(samples ** 2)))

            if rms > 0.008:
                f = _yin_pitch(samples, RATE)
                if f > 60:
                    note, idx = _freq_to_note(f, self.semitone_offset)
                else:
                    f, note, idx = 0.0, None, -1
            else:
                f, note, idx = 0.0, None, -1

            with self._lock:
                self.volume = rms
                self.current_frequency = f
                self.current_note = note
                self.current_note_index = idx

                # accumulate calibration samples
                if self._calibrating and f > 60:
                    self._cal_freqs.append(f)
        except Exception:
            pass
        return (None, pyaudio.paContinue)

    def start(self):
        self._pa = pyaudio.PyAudio()
        kw = dict(format=FORMAT, channels=CHANNELS, rate=RATE,
                  input=True, frames_per_buffer=CHUNK,
                  stream_callback=self._callback)
        if self.device_index is not None:
            kw["input_device_index"] = self.device_index
        self._stream = self._pa.open(**kw)
        self._stream.start_stream()

    def snapshot(self):
        """Return (freq, note, index, vol) -- never blocks."""
        with self._lock:
            return (self.current_frequency, self.current_note,
                    self.current_note_index, self.volume)

    # ── calibration ──────────────────────────────────────────
    def start_calibration(self):
        """Begin collecting frequency samples for 3 seconds."""
        with self._lock:
            self._cal_freqs = []
            self._calibrating = True
            self._cal_start = time.time()
            self.cal_result = None

    def calibration_active(self):
        return self._calibrating

    def calibration_progress(self):
        """Return 0.0 to 1.0"""
        if not self._calibrating:
            return 0.0
        elapsed = time.time() - self._cal_start
        return min(elapsed / 3.0, 1.0)

    def finish_calibration(self):
        """
        Analyse collected frequencies, compute best semitone offset
        so the singer's range maps to the Do-Si scale.
        Returns True if successful.
        """
        with self._lock:
            self._calibrating = False
            freqs = list(self._cal_freqs)
            self._cal_freqs = []

        if len(freqs) < 5:
            self.cal_result = "Not enough sound detected. Sing louder!"
            return False

        median_freq = float(np.median(freqs))
        low = float(np.percentile(freqs, 10))
        high = float(np.percentile(freqs, 90))

        # Find the semitone offset that makes the median map closest to
        # one of the 7 notes (minimise average error for all samples)
        best_offset = 0
        best_err = 999.0
        for offset in range(-24, 25):
            total_err = 0.0
            for f in freqs:
                _, idx = _freq_to_note(f, offset)
                if idx < 0:
                    total_err += 2.0
                else:
                    # distance in semitones to nearest note
                    ref = BASE_FREQS[idx] * (2 ** (offset / 12.0))
                    # also check octave above/below
                    dists = []
                    for os2 in (-12, 0, 12):
                        r = BASE_FREQS[idx] * (2 ** ((offset + os2) / 12.0))
                        dists.append(abs(12 * np.log2(f / r)))
                    total_err += min(dists)
            avg = total_err / len(freqs)
            if avg < best_err:
                best_err = avg
                best_offset = offset

        self.semitone_offset = best_offset
        self.cal_result = (
            f"Detected range: {low:.0f}-{high:.0f} Hz (median {median_freq:.0f} Hz). "
            f"Scale offset set to {best_offset:+d} semitones."
        )
        return True

    def stop(self):
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None
