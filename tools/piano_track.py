"""A gentle piano-style background track, synthesized here: an arpeggiated I-vi-IV-V progression in C major
with a soft left hand, decaying harmonics and a little room. Nothing sampled or borrowed, so it is free to
publish. usage: python piano.py <seconds> <out.wav>"""
import math
import struct
import sys
import wave

import numpy as np

SR = 44100
seconds = float(sys.argv[1])
out = sys.argv[2]
rng = np.random.default_rng(7)


def note_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def piano_tone(midi, dur, vel=1.0):
    """Hammer-like attack, harmonics that decay faster the higher they are, slight detune for warmth."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = note_hz(midi)
    sig = np.zeros(n)
    for k, amp in ((1, 1.0), (2, 0.45), (3, 0.22), (4, 0.11), (5, 0.06), (6, 0.03)):
        decay = np.exp(-t * (1.3 + 0.9 * k) * (f / 220) ** 0.35)
        detune = 1 + rng.normal(0, 0.0006)
        sig += amp * decay * np.sin(2 * math.pi * f * k * detune * t)
    attack = np.minimum(1.0, t / 0.008)
    hammer = np.exp(-t * 60) * rng.normal(0, 0.03, n)
    return vel * attack * (sig + hammer) * (0.25 / (f / 261.6) ** 0.3)


# progression: C  Am  F  G  (two bars each), 70 bpm, eighth-note arpeggios
bpm = 70
beat = 60.0 / bpm
chords = [(48, [60, 64, 67, 72]), (45, [57, 60, 64, 69]), (41, [53, 57, 60, 65]), (43, [55, 59, 62, 67])]
total = int(SR * seconds) + SR * 6
mix = np.zeros(total)
t0 = 0.0
bar = 0
while t0 < seconds:
    bass, arp = chords[bar % 4]
    # left hand: root and fifth held for the bar
    for midi, vel in ((bass, 0.9), (bass + 7, 0.5)):
        tone = piano_tone(midi, beat * 4 + 1.5, vel)
        i = int(t0 * SR)
        mix[i:i + len(tone)] += tone
    # right hand: eighth notes up and down with a human touch
    pattern = arp + arp[::-1][1:-1]
    for k, midi in enumerate(pattern):
        t = t0 + k * beat / 2 + rng.normal(0, 0.012)
        if t < 0:
            t = 0
        vel = 0.55 + 0.25 * (k == 0) + rng.normal(0, 0.05)
        if rng.random() < 0.12:  # the odd rest
            continue
        tone = piano_tone(midi, 1.8, vel)
        i = int(t * SR)
        mix[i:i + len(tone)] += tone
    t0 += beat * 4
    bar += 1

# a little room: three early reflections and a soft tail
room = np.zeros_like(mix)
for delay_ms, gain in ((23, 0.25), (41, 0.18), (67, 0.12), (113, 0.08), (181, 0.05)):
    d = int(SR * delay_ms / 1000)
    room[d:] += gain * mix[:-d]
mix = mix + room
mix = mix[: int(SR * seconds)]

# fade in 3 s, fade out 6 s, level around -20 dBFS peak-limited
fade_in = np.minimum(1.0, np.arange(len(mix)) / (3 * SR))
fade_out = np.minimum(1.0, (len(mix) - np.arange(len(mix))) / (6 * SR))
mix *= fade_in * fade_out
peak = np.max(np.abs(mix)) or 1.0
mix = mix / peak * 0.35
stereo = np.stack([mix * 0.95 + np.roll(mix, 9) * 0.05, mix * 0.95 + np.roll(mix, -9) * 0.05], axis=1)
pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
with wave.open(out, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote", out, "%.1f s" % (len(mix) / SR))
