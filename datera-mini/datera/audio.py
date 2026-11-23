"""Stage 0. Audio preparation (FR-4.4, FR-5.1 of the DATERA EDU spec).

Takes any audio or video file, extracts the audio track with ffmpeg,
converts it to mono 16 kHz WAV (the format Whisper expects) and levels the volume.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def prepare_audio(src: str | Path, dst: str | Path) -> Path:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg не найден. Установите его: brew install ffmpeg")
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-vn",                # drop the video stream
        "-ac", "1",           # mono
        "-ar", "16000",       # 16 kHz
        "-af", "loudnorm",    # loudness normalisation
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dst.exists():
        raise RuntimeError(f"ffmpeg не смог обработать файл: {proc.stderr.strip()[:500]}")
    return dst


def duration_seconds(wav: str | Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(wav)],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out) if out else 0.0
