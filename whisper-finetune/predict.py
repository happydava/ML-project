"""Demonstration: transcribe a NEW recording (any format ffmpeg reads) with the model without training and with the fine-tuned model.

    python predict.py demo/talk_ru.m4a

Whisper works on 30-second windows, so the recording is cut into 25-second pieces for BOTH models (a simple cut: a word on a border can be damaged)."""
import subprocess
import sys
import tempfile
from pathlib import Path

import soundfile as sf

from common import device, load_model, processor, transcribe
from config import MODELS

PIECE = 25 * 16000
with tempfile.TemporaryDirectory() as tmp:
    wav = Path(tmp) / "all.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", sys.argv[1], "-ar", "16000", "-ac", "1", str(wav)], check=True)
    audio, _ = sf.read(wav, dtype="float32")
    pieces = []
    for i in range(0, len(audio), PIECE):
        p = Path(tmp) / f"p{i // PIECE:03d}.wav"
        sf.write(p, audio[i:i + PIECE], 16000)
        pieces.append(str(p))
    dev, proc = device(), processor()
    print(f"{len(audio) / 16000:.0f} seconds, {len(pieces)} pieces")
    for name, where in (("Whisper-base, no training", "openai/whisper-base"), ("Whisper-base, fine-tuned", str(MODELS / "whisper-base-ru"))):
        text = " ".join(transcribe(load_model(where, dev=dev), proc, pieces, dev=dev))
        print(f"\n{name}\n  {text}")
