"""Build benchmark conditions from bench/clips/*: clean, 10 dB SNR, 5 dB SNR, each also through an
8 kHz mu-law telephone round trip. Output: bench/clips/derived/<stem>__<cond>.wav (16 kHz mono).

Noise: every .wav/.mp3/.ogg in bench/noise/ (record your own: wind, handpump creak, crowd, tractor, TV,
or use clearly licensed clips). If the folder is empty, synthetic white noise is used and the
condition is named `wnoise` so results say so.

  python -m bench.make_noisy
"""
from __future__ import annotations

import glob
import io
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.audio import to_wav16k  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS, NOISE, OUT = os.path.join(HERE, "clips"), os.path.join(HERE, "noise"), os.path.join(HERE, "clips", "derived")
AUDIO_EXT = (".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac", ".webm", ".opus", ".mp4")


def read(wav_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768


def write(path: str, x: np.ndarray) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def mix_at_snr(speech: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    noise = np.resize(noise, len(speech))
    ps, pn = np.mean(speech ** 2) + 1e-12, np.mean(noise ** 2) + 1e-12
    return np.clip(speech + np.sqrt(ps / (pn * 10 ** (snr_db / 10))) * noise, -1, 1)


def main():
    os.makedirs(OUT, exist_ok=True)
    noises = [(os.path.splitext(os.path.basename(f))[0], read(to_wav16k(open(f, "rb").read())))
              for f in sorted(glob.glob(os.path.join(NOISE, "*"))) if f.lower().endswith(AUDIO_EXT)]
    if not noises:
        noises = [("wnoise", np.random.default_rng(7).normal(0, 0.1, 16000 * 30).astype(np.float32))]
        print("bench/noise is empty: using synthetic white noise (condition label 'wnoise').")
    clips = [f for f in sorted(glob.glob(os.path.join(CLIPS, "*"))) if f.lower().endswith(AUDIO_EXT)]
    if not clips:
        print("No clips in bench/clips. Add consented or synthetic recordings named as in gold.csv."); return
    n = 0
    for f in clips:
        stem = os.path.splitext(os.path.basename(f))[0]
        clean = read(to_wav16k(open(f, "rb").read()))
        variants = {"clean": clean}
        for nname, noise in noises:
            for snr in (10, 5):
                variants[f"{nname}{snr}db"] = mix_at_snr(clean, noise, snr)
        for cond, x in variants.items():
            p = os.path.join(OUT, f"{stem}__{cond}.wav")
            write(p, x)
            buf = open(p, "rb").read()
            open(os.path.join(OUT, f"{stem}__{cond}_tel.wav"), "wb").write(to_wav16k(buf, telephone=True))
            n += 2
    print(f"Wrote {n} files to {OUT}")


if __name__ == "__main__":
    main()
