"""Stage 2. Speech recognition with OpenAI Whisper (FR-6.1).

Whisper is an encoder-decoder Transformer:
  audio -> log-Mel spectrogram -> 2 conv layers + Transformer encoder
        -> Transformer decoder that generates text tokens with timestamps.
The original `openai-whisper` package (PyTorch) is used here.
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

import numpy as np
import torch
import whisper

# "base-ru-finetuned" is the Whisper-base network fine-tuned on Russian speech in ../whisper-finetune/ (exported by 08_export_openai.py)
FINETUNED = "base-ru-finetuned"
FINETUNED_PATH = Path(__file__).resolve().parent.parent.parent / "whisper-finetune" / "models" / "whisper-base-ru.pt"
MODELS = ["tiny", "base", "small", "medium", "turbo", "large-v3", FINETUNED]


def pick_device() -> str:
    # CPU is the safe default for openai-whisper on a Mac. Override with DATERA_DEVICE=cuda|mps.
    forced = os.environ.get("DATERA_DEVICE")
    if forced:
        return forced
    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=2)
def load_model(name: str = "small"):
    if name == FINETUNED:
        if not FINETUNED_PATH.exists():
            raise FileNotFoundError("Дообученная модель Whisper ещё не создана: запустите шаги 05 и 08 в папке whisper-finetune (инструкция в whisper-finetune/README.md)")
        model = whisper.load_model(str(FINETUNED_PATH), device=pick_device())
        model.set_alignment_heads(whisper._ALIGNMENT_HEADS["base"])        # word timestamps use the alignment heads of the original base model
        return model
    return whisper.load_model(name, device=pick_device())


def model_info(model) -> dict:
    d = model.dims
    return {
        "parameters": sum(p.numel() for p in model.parameters()),
        "device": str(model.device),
        "n_mels": d.n_mels,
        "encoder_layers": d.n_audio_layer,
        "decoder_layers": d.n_text_layer,
        "hidden_size": d.n_audio_state,
        "attention_heads": d.n_audio_head,
        "vocab_size": d.n_vocab,
        "multilingual": bool(model.is_multilingual),
    }


def first_window(model, wav_path: str):
    """What the network actually sees: log-Mel spectrogram of the first 30 s,
    and the language probabilities predicted by the decoder from it."""
    audio = whisper.pad_or_trim(whisper.load_audio(wav_path))
    mel = whisper.log_mel_spectrogram(audio, n_mels=model.dims.n_mels).to(model.device)
    probs: dict[str, float] = {}
    if model.is_multilingual:
        _, probs = model.detect_language(mel)
    top = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return mel.cpu().numpy(), top


def transcribe(model, wav_path: str, language: str | None = None) -> dict:
    result = model.transcribe(
        wav_path,
        language=language,                 # None = detect automatically
        fp16=str(model.device) == "cuda",
        condition_on_previous_text=False,  # fewer "looping" hallucinations on long audio
        word_timestamps=True,              # exact start and end of speech, needed for pauses before answers
        verbose=None,
    )
    segments = []
    for s in result["segments"]:
        text = s["text"].strip()
        if not text:
            continue
        words = s.get("words") or []
        segments.append({
            # a segment's own borders include the silence around it; the words give the real ones
            "start": float(words[0]["start"] if words else s["start"]),
            "end": float(words[-1]["end"] if words else s["end"]),
            "text": text,
            # exp(mean token log-probability): a rough confidence of the decoder
            "confidence": float(np.exp(s["avg_logprob"])),
            "no_speech_prob": float(s["no_speech_prob"]),
        })
    return {"language": result["language"], "text": result["text"].strip(), "segments": segments}


def merge_sentences(segments: list[dict], max_seconds: float = 30.0) -> list[dict]:
    """Whisper cuts audio into short pieces, often in the middle of a sentence.
    Glue pieces together until a sentence ends, so the analysis compares whole thoughts."""
    out: list[dict] = []
    for s in segments:
        last = out[-1] if out else None
        if (last and not last["text"].rstrip().endswith((".", "!", "?", "…"))
                and last.get("speaker") == s.get("speaker")      # never glue two different voices
                and s["end"] - last["start"] <= max_seconds):
            n_old, n_new = len(last["text"].split()), len(s["text"].split())
            last["confidence"] = (last["confidence"] * n_old + s["confidence"] * n_new) / max(n_old + n_new, 1)
            last["no_speech_prob"] = max(last["no_speech_prob"], s["no_speech_prob"])
            last["text"] += " " + s["text"]
            last["end"] = s["end"]
        else:
            out.append(dict(s))
    return out
