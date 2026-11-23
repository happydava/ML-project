"""Stage 3. Speaker separation (FR-6.2 - FR-6.4, simplified).

The third neural network of the project: WavLM with an x-vector head. It turns a piece of audio
into a "voice print" vector; pieces spoken by the same person give close vectors.
Every Whisper segment gets a voice print, the prints are clustered into two groups,
and the group that asks more questions is taken as the teacher (the teacher can swap the roles).

The diploma uses pyannote.audio; it needs a gated model and a token, so a simpler approach is used here.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

SPEAKER_MODEL = "microsoft/wavlm-base-plus-sv"
SAMPLE_RATE = 16000
MIN_SECONDS = 0.7          # shorter pieces carry too little voice to compare
SAME_VOICE = 0.80          # centroids closer than this are treated as one speaker
MIN_SHARE = 0.08           # a "second speaker" with less speech than this is noise


@lru_cache(maxsize=1)
def load_speaker_model():
    from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector

    return (Wav2Vec2FeatureExtractor.from_pretrained(SPEAKER_MODEL),
            WavLMForXVector.from_pretrained(SPEAKER_MODEL).eval())


def _voice_prints(audio: np.ndarray, segments: list[dict]) -> dict[int, np.ndarray]:
    import torch

    extractor, model = load_speaker_model()
    prints = {}
    for i, s in enumerate(segments):
        clip = audio[int(s["start"] * SAMPLE_RATE):int(s["end"] * SAMPLE_RATE)]
        if len(clip) < MIN_SECONDS * SAMPLE_RATE:
            continue
        inputs = extractor(clip, sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with torch.no_grad():
            emb = model(**inputs).embeddings[0]
        prints[i] = torch.nn.functional.normalize(emb, dim=-1).numpy()
    return prints


def assign_speakers(wav_path: str, segments: list[dict]) -> dict:
    """Adds `speaker` ("teacher" / "student" / None) to every segment. Returns a short summary."""
    import whisper
    from sklearn.cluster import AgglomerativeClustering

    for s in segments:
        s["speaker"] = None
    info = {"model": SPEAKER_MODEL, "speakers": 1, "voice_similarity": None}
    prints = _voice_prints(whisper.load_audio(wav_path), segments)
    if len(prints) < 4:
        return info

    ids = list(prints)
    X = np.stack([prints[i] for i in ids])
    labels = AgglomerativeClustering(n_clusters=2, metric="cosine", linkage="average").fit_predict(X)
    c0, c1 = X[labels == 0].mean(axis=0), X[labels == 1].mean(axis=0)
    similarity = float(c0 @ c1 / (np.linalg.norm(c0) * np.linalg.norm(c1)))
    info["voice_similarity"] = round(similarity, 3)

    dur = [sum(segments[i]["end"] - segments[i]["start"] for i, l in zip(ids, labels) if l == k) for k in (0, 1)]
    if similarity >= SAME_VOICE or min(dur) < MIN_SHARE * sum(dur):
        return info                                   # one voice: a lecture or a monologue

    by_seg = dict(zip(ids, (int(l) for l in labels)))
    raw = []
    for i, seg in enumerate(segments):                # a very short piece ("Верно.") follows the neighbour closest in time
        if i not in by_seg:
            prev = max((j for j in by_seg if j < i), default=None)
            nxt = min((j for j in by_seg if j > i), default=None)
            gap_prev = seg["start"] - segments[prev]["end"] if prev is not None else float("inf")
            gap_next = segments[nxt]["start"] - seg["end"] if nxt is not None else float("inf")
            raw.append(by_seg[prev] if gap_prev <= gap_next else by_seg[nxt])
        else:
            raw.append(by_seg[i])

    questions = [sum(segments[i]["text"].count("?") for i in range(len(segments)) if raw[i] == k) for k in (0, 1)]
    teacher = int(np.argmax(questions)) if questions[0] != questions[1] else int(np.argmax(dur))
    for s, l in zip(segments, raw):
        s["speaker"] = "teacher" if l == teacher else "student"
    info["speakers"] = 2
    return info


def swap_roles(segments: list[dict]) -> None:
    for s in segments:
        if s.get("speaker"):
            s["speaker"] = "student" if s["speaker"] == "teacher" else "teacher"
