"""Helpers shared by all steps: data loading, batching, decoding and the WER metric (one implementation for every model)."""
import numpy as np
import pandas as pd
import soundfile as sf
import torch
from transformers import WhisperForConditionalGeneration, WhisperProcessor
from transformers.models.whisper.english_normalizer import BasicTextNormalizer

import json

from config import DATA, LANG_NAME, RESULTS, TASK, WHISPER

COLS = ["id", "file_name", "raw_transcription", "transcription", "chars", "num_samples", "gender"]
NORM = BasicTextNormalizer(remove_diacritics=False)       # lower-case, no punctuation; keeps "й" and "ё"


def device() -> torch.device:
    return torch.device("mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu")


def processor() -> WhisperProcessor:
    p = WhisperProcessor.from_pretrained(WHISPER, language=LANG_NAME, task=TASK)
    p.tokenizer.set_prefix_tokens(language=LANG_NAME, task=TASK, predict_timestamps=False)
    return p


def load_split(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / "processed" / f"{name}.csv")


def read_audio(path: str) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32")
    assert sr == 16000, f"{path}: expected 16 kHz, got {sr}"
    return audio.mean(axis=1) if audio.ndim > 1 else audio


def features(proc, paths) -> torch.Tensor:
    return proc.feature_extractor([read_audio(p) for p in paths], sampling_rate=16000, return_tensors="pt").input_features


@torch.no_grad()
def transcribe(model, proc, paths, batch_size: int = 16, dev=None) -> list[str]:
    dev = dev or next(model.parameters()).device
    model.eval()
    out = []
    for i in range(0, len(paths), batch_size):
        feats = features(proc, paths[i:i + batch_size]).to(dev)
        ids = model.generate(input_features=feats, language=LANG_NAME, task=TASK, num_beams=1, max_new_tokens=200)
        out += [t.strip() for t in proc.batch_decode(ids, skip_special_tokens=True)]
    return out


def word_errors(refs, hyps):
    """Per utterance: word errors (substitutions + deletions + insertions) and number of reference words, after normalisation."""
    import jiwer
    errs, nwords, cerr, nchars = [], [], [], []
    for r, h in zip(refs, hyps):
        r, h = NORM(r).strip(), NORM(h).strip()
        if not r:
            errs.append(0); nwords.append(0); cerr.append(0); nchars.append(0); continue
        o = jiwer.process_words(r, h if h else "<empty>")
        errs.append(o.substitutions + o.deletions + o.insertions); nwords.append(len(r.split()))
        c = jiwer.process_characters(r, h if h else "_")
        cerr.append(c.substitutions + c.deletions + c.insertions); nchars.append(len(r))
    return np.array(errs), np.array(nwords), np.array(cerr), np.array(nchars)


def wer(refs, hyps) -> float:
    e, n, _, _ = word_errors(refs, hyps)
    return float(e.sum() / max(n.sum(), 1))


def load_model(path_or_name=WHISPER, dev=None, **kw):
    m = WhisperForConditionalGeneration.from_pretrained(path_or_name, **kw)
    m.generation_config.forced_decoder_ids = None
    return m.to(dev or device())


def record(model: str, split: str, df: pd.DataFrame, hyps, seconds: float | None = None) -> dict:
    """Stores metrics in results/metrics.json and per-utterance predictions in results/predictions/<model>__<split>.csv."""
    e, n, ce, nc = word_errors(df["text"].tolist(), hyps)
    m = {"n": int(len(df)), "wer": round(float(e.sum() / max(n.sum(), 1)), 4), "cer": round(float(ce.sum() / max(nc.sum(), 1)), 4)}
    if seconds is not None:
        m["decode_seconds"] = round(seconds, 1)
    path = RESULTS / "metrics.json"
    allm = json.loads(path.read_text()) if path.exists() else {}
    allm.setdefault(model, {})[split] = m
    path.write_text(json.dumps(allm, indent=2))
    (RESULTS / "predictions").mkdir(exist_ok=True)
    out = df[["id", "text", "seconds", "gender"]].copy()
    out["hyp"], out["word_errors"], out["ref_words"] = list(hyps), e, n
    out.to_csv(RESULTS / "predictions" / f"{model}__{split}.csv", index=False)
    return m
