"""Study materials -> list of topics (FR-3.5, simplified).

In the full system an LLM proposes topics and the teacher confirms them.
In this mini version one slide (or one PDF page) is one topic,
and every bullet / sentence on it is a "key point" of that topic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MIN_POINT_WORDS = 3   # shorter lines are treated as labels, not as key points
MIN_TOPIC_WORDS = 4   # slides with less text (title slide, "Thank you") are not assessed


@dataclass
class Topic:
    index: int                      # slide / page number, from 1
    title: str
    points: list[str] = field(default_factory=list)
    skipped: bool = False           # too little text to assess


def _words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+", text.strip())
    return [p.strip(" \t-–•·") for p in parts if p.strip()]


def _make_topic(index: int, title: str, lines: list[str]) -> Topic:
    points: list[str] = []
    for line in lines:
        chunks = _split_sentences(line) if _words(line) > 25 else [line.strip(" \t-–•·")]
        for c in chunks:
            if _words(c) >= MIN_POINT_WORDS and c not in points:
                points.append(c)
    total_words = _words(title) + sum(_words(p) for p in points)
    if not points and title:
        points = [title]
    title = title or (points[0][:80] if points else f"Слайд {index}")
    return Topic(index, title, points, skipped=total_words < MIN_TOPIC_WORDS)


def _shape_lines(shape) -> list[str]:
    lines: list[str] = []
    if shape.shape_type == 6 and hasattr(shape, "shapes"):          # group
        for sub in shape.shapes:
            lines += _shape_lines(sub)
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        for p in shape.text_frame.paragraphs:
            t = "".join(r.text for r in p.runs).strip()
            if t:
                lines.append(t)
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            t = " - ".join(c.text.strip() for c in row.cells if c.text.strip())
            if t:
                lines.append(t)
    return lines


def _from_pptx(path: Path) -> list[Topic]:
    from pptx import Presentation

    topics = []
    for i, slide in enumerate(Presentation(str(path)).slides, start=1):
        title_shape = slide.shapes.title
        title = title_shape.text_frame.text.strip() if title_shape is not None and title_shape.has_text_frame else ""
        lines = []
        for shape in slide.shapes:
            if title_shape is not None and shape.shape_id == title_shape.shape_id:
                continue
            lines += _shape_lines(shape)
        if not title and lines:
            title = lines.pop(0)
        if title or lines:
            topics.append(_make_topic(i, " ".join(title.split()), lines))
    return topics


def _from_pdf(path: Path) -> list[Topic]:
    from pypdf import PdfReader

    topics = []
    for i, page in enumerate(PdfReader(str(path)).pages, start=1):
        raw = [" ".join(l.split()) for l in (page.extract_text() or "").splitlines()]
        raw = [l for l in raw if l and not re.fullmatch(r"\d+", l)]   # drop page numbers
        if not raw:
            continue
        title, merged = raw[0], []
        for line in raw[1:]:
            # a PDF breaks sentences across lines: glue a line that continues the previous one
            if merged and not re.search(r"[.!?:;]$", merged[-1]) and line[:1].islower():
                merged[-1] += " " + line
            else:
                merged.append(line)
        topics.append(_make_topic(i, title, merged))
    return topics


def load_topics(path: str | Path) -> list[Topic]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pptx":
        topics = _from_pptx(path)
    elif ext == ".pdf":
        topics = _from_pdf(path)
    elif ext in (".txt", ".md"):
        blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="ignore"))
        topics = []
        for i, b in enumerate([b for b in blocks if b.strip()], start=1):
            lines = [l.strip("# \t") for l in b.splitlines() if l.strip()]
            topics.append(_make_topic(i, lines[0], lines[1:]))
    else:
        raise ValueError(f"Формат {ext} не поддерживается. Нужен .pptx, .pdf, .txt или .md")
    if not topics:
        raise ValueError("В материале не найден текст (возможно, слайды состоят только из картинок)")
    return topics
