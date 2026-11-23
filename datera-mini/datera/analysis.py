"""Stage 4. Analysis: which topics of the material were covered in the speech (FR-7.1, FR-7.2, FR-7.8, FR-8.1).

The second neural network of the project works here: a multilingual sentence-embedding
Transformer. Every key point of a slide and every fragment of the transcript becomes a vector;
close vectors mean close meaning, also across languages (slides in English, speech in Russian).

All numbers (index, status) are calculated by plain code from the similarities,
as in the diploma architecture: "rules instead of the language model for numbers".
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from .materials import Topic

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Colour statuses from Table 8 of the technical specification
GREEN, YELLOW = 80, 50


@lru_cache(maxsize=1)
def load_embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def status_for(index: float) -> tuple[str, str]:
    if index >= GREEN:
        return "green", "Раскрыта"
    if index >= YELLOW:
        return "yellow", "Раскрыта частично"
    return "red", "Не раскрыта"


def _units(segments: list[dict]) -> list[dict]:
    """Fragments of speech to compare with: single sentences first, then windows of 2 and 3 sentences."""
    units = []
    n = len(segments)
    for size in (1, 2, 3):
        for i in range(0, n - size + 1):
            part = segments[i:i + size]
            units.append({
                "seg_ids": list(range(i, i + size)),
                "start": part[0]["start"],
                "end": part[-1]["end"],
                "text": " ".join(s["text"] for s in part),
            })
    return units


def analyse(topics: list[Topic], segments: list[dict], threshold: float = 0.65,
            outside_threshold: float = 0.35) -> dict:
    active = [t for t in topics if not t.skipped]
    if not segments or not active:
        raise ValueError("Нечего анализировать: пустой транскрипт или в материале нет тем с текстом")

    model = load_embedder()
    units = _units(segments)

    # Each key point is embedded twice: alone and with the slide title for context.
    point_owner, point_texts = [], []
    for ti, t in enumerate(active):
        for pi, p in enumerate(t.points):
            point_owner.append((ti, pi))
            point_texts.append(p)
            point_owner.append((ti, pi))
            point_texts.append(f"{t.title}. {p}")

    enc = dict(normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False, batch_size=32)
    P = model.encode(point_texts, **enc)
    U = model.encode([u["text"] for u in units], **enc)
    sim = P @ U.T                                   # cosine similarity, points x units

    # --- per key point: the best matching fragment of speech
    results = []
    for ti, t in enumerate(active):
        points = []
        for pi, p in enumerate(t.points):
            rows = [r for r, owner in enumerate(point_owner) if owner == (ti, pi)]
            best = sim[rows].max(axis=0)
            j = int(best.argmax())
            score = float(best[j])
            points.append({
                "text": p,
                "similarity": round(score, 3),
                "covered": score >= threshold,
                "start": units[j]["start"],
                "end": units[j]["end"],
                "quote": units[j]["text"],
            })
        covered = sum(p["covered"] for p in points)
        index = round(100 * covered / len(points))
        color, label = status_for(index)
        results.append({
            "slide": t.index, "title": t.title, "points": points,
            "covered_points": covered, "total_points": len(points),
            "index": index, "color": color, "status": label,
            "seconds": 0.0, "first_mention": None,
        })

    # --- per sentence of speech: which topic it belongs to (or "outside the material").
    # Only the sentence itself is used here (the first len(segments) units), not the windows,
    # so that an off-topic sentence does not borrow the score of its neighbours.
    topic_of_row = np.array([owner[0] for owner in point_owner])
    single = sim[:, :len(segments)]
    seg_score = single.max(axis=0)
    seg_topic = topic_of_row[single.argmax(axis=0)]

    outside, current = [], None
    for i, s in enumerate(segments):
        dur = s["end"] - s["start"]
        if seg_score[i] >= threshold:
            r = results[int(seg_topic[i])]
            r["seconds"] += dur
            if r["first_mention"] is None:
                r["first_mention"] = s["start"]
        s["topic_slide"] = results[int(seg_topic[i])]["slide"] if seg_score[i] >= threshold else None
        s["similarity"] = round(float(seg_score[i]), 3)

        is_outside = seg_score[i] < outside_threshold and len(s["text"].split()) >= 6
        if is_outside:
            if current and s["start"] - current["end"] < 2.0:
                current["end"] = s["end"]
                current["text"] += " " + s["text"]
            else:
                current = {"start": s["start"], "end": s["end"], "text": s["text"]}
                outside.append(current)
        else:
            current = None
    outside = [o for o in outside if o["end"] - o["start"] >= 5.0]

    overall = round(float(np.mean([r["index"] for r in results])))
    color, label = status_for(overall)
    speech = sum(s["end"] - s["start"] for s in segments)
    return {
        "overall_index": overall, "overall_color": color, "overall_status": label,
        "topics": results,
        "skipped_slides": [{"slide": t.index, "title": t.title} for t in topics if t.skipped],
        "outside_material": outside,
        "on_topic_share": round(100 * sum(r["seconds"] for r in results) / speech) if speech else 0,
        "threshold": threshold,
        "embedding_model": EMBEDDING_MODEL,
    }
