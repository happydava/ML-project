"""The whole path of one recording: file -> audio -> text -> topics -> analysis -> report data."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Callable

from . import analysis, asr, audio, diarize, materials


def scored_segments(segments: list[dict]) -> list[dict]:
    """In a dialogue only the student's speech is assessed: the teacher's own explanation
    must not count as the student's knowledge. With one voice everything is assessed."""
    student = [s for s in segments if s.get("speaker") == "student"]
    return student or segments


def run(media_path: str | Path, material_path: str | Path | None = None, model_name: str = "small",
        language: str | None = None, threshold: float = 0.65,
        on_stage: Callable[[str], None] = lambda msg: None,
        topics: list | None = None, workdir: str | Path | None = None) -> dict:
    """`topics` can be passed directly (web app: topics confirmed by the teacher);
    otherwise they are read from `material_path`."""
    timings: dict[str, float] = {}

    def timed(name: str, fn):
        t0 = time.time()
        out = fn()
        timings[name] = round(time.time() - t0, 1)
        return out

    on_stage("Этап 0. Подготовка аудио (ffmpeg: моно, 16 кГц)")
    wav = Path(workdir or tempfile.mkdtemp(prefix="datera_")) / "audio.wav"
    timed("audio", lambda: audio.prepare_audio(media_path, wav))
    duration = audio.duration_seconds(wav)

    if topics is None:
        on_stage("Материалы: выделение тем из презентации")
        topics = timed("materials", lambda: materials.load_topics(material_path))

    on_stage(f"Загрузка нейросети Whisper ({model_name})")
    model = timed("load_whisper", lambda: asr.load_model(model_name))
    mel, lang_probs = asr.first_window(model, str(wav))

    on_stage("Этап 2. Распознавание речи (Whisper)")
    tr = timed("asr", lambda: asr.transcribe(model, str(wav), language))
    if not tr["segments"]:
        raise ValueError("В записи не найдена речь")

    on_stage("Этап 3. Разделение говорящих (WavLM)")
    speakers = timed("diarization", lambda: diarize.assign_speakers(str(wav), tr["segments"]))
    segments = asr.merge_sentences(tr["segments"])

    on_stage("Загрузка нейросети эмбеддингов")
    timed("load_embedder", analysis.load_embedder)

    on_stage("Этап 4. Анализ: сопоставление речи с темами (эмбеддинги)")
    res = timed("analysis", lambda: analysis.analyse(topics, scored_segments(segments), threshold))

    return {
        "media_name": Path(media_path).name,
        "material_name": Path(material_path).name if material_path else "",
        "wav_path": str(wav),
        "duration": duration,
        "language": tr["language"],
        "language_probs": lang_probs,
        "segments": segments,
        "speakers": speakers,
        "analysis": res,
        "whisper": {"name": model_name, **asr.model_info(model)},
        "timings": timings,
        "mel": mel,   # numpy array for the "how the model works" tab; not saved to JSON
    }
