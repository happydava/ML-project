"""Dialogue structure: turns of one speaker and question-answer pairs."""
from __future__ import annotations


def dialogue(segments: list[dict]) -> tuple[list[dict], list[dict]]:
    """Turns: consecutive sentences of one speaker. Pairs: a teacher's turn and the student's answer that follows it."""
    turns: list[dict] = []
    for s in segments:
        if turns and turns[-1]["speaker"] == s.get("speaker"):
            t = turns[-1]
            t["end"], t["text"] = s["end"], t["text"] + " " + s["text"]
        else:
            t = {"idx": len(turns), "speaker": s.get("speaker"), "start": s["start"], "end": s["end"],
                 "text": s["text"], "topics": []}
            turns.append(t)
        if s.get("topic_slide") and s["topic_slide"] not in t["topics"]:
            t["topics"].append(s["topic_slide"])
    pairs = []
    for i, t in enumerate(turns):
        if t["speaker"] != "teacher":
            continue
        answer = turns[i + 1] if i + 1 < len(turns) and turns[i + 1]["speaker"] == "student" else None
        pairs.append({"question": t, "answer": answer, "is_question": "?" in t["text"],
                      "pause": round(answer["start"] - t["end"], 1) if answer else None})
    return turns, pairs
