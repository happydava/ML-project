"""Stage 4 with a language model (FR-7.1 - FR-7.8, FR-9): checks the student's answers topic by topic.

The model sees an anonymised dialogue split into numbered turns and returns JSON. It points to turns by number;
time codes and quotes are taken from the real transcript by this code, so the model cannot invent them.
Every reference is checked: an answer must be a student's turn that comes after the teacher's question.
"""
from __future__ import annotations

import json
import re

from . import llm
from .dialogue import dialogue

PROMPT_VERSION = "2026-11-16.1"

SYSTEM = """Ты - методический помощник преподавателя. По расшифровке записи урока оцени, как ученик усвоил темы учебного материала.

Правила:
1. Опирайся только на реплики из поля turns. Ничего не выдумывай и не добавляй факты, которых там нет.
2. Знание ученика показывают только его ответы (speaker = "student"). Объяснения преподавателя (speaker = "teacher") знанием ученика не считаются. Если mode = "monologue", голос один: оцени, насколько полно выступающий раскрыл тему.
3. Для каждой темы найди вопрос преподавателя и ответ ученика на него. Ответ всегда идёт ПОСЛЕ вопроса: question_turn меньше answer_turn. Ссылайся на реплики по их id, номера не придумывай. Если на один вопрос ученик отвечал несколько раз, укажи реплику с итоговым ответом. Одному вопросу соответствует один ближайший ответ, не бери ответ из другой части урока.
4. Сверяй ответ с пунктами темы (points) по смыслу, а не по словам. Ошибки, «не помню», долгие паузы и просьбы повторить - признаки неусвоенной темы.
5. level: 100 - ответ верный и полный; 50 - частично верный или есть пробелы; 0 - неверный или ответа нет. Если тема на уроке не обсуждалась, status = "not_discussed", level = null, evidence пустой.
6. Пиши ясно и доброжелательно. В текстах для ученика и родителя не используй профессиональные термины и ярлыки вроде «слабый ученик».
7. Имена заменены метками; не пытайся их восстановить.
Верни ТОЛЬКО JSON без пояснений и без markdown, по схеме из поля schema."""

SCHEMA = """{
 "topics": [{"topic_id": <int>, "status": "learned|partial|not_learned|not_discussed", "level": 0|50|100|null,
   "covered_points": [<номера пунктов из points, которые прозвучали верно>],
   "comment": "1-2 предложения для преподавателя: что ученик понял, что нет",
   "evidence": [{"question_turn": <id реплики преподавателя или null>, "answer_turn": <id реплики ученика>,
                 "verdict": "correct|partial|wrong|unclear", "note": "коротко, почему такая оценка"}]}],
 "summary": "3-5 предложений для преподавателя об уроке в целом",
 "strengths": ["что получилось у ученика"],
 "difficulties": ["с чем у ученика сложности"],
 "next_lesson": ["конкретные рекомендации на следующий урок"],
 "student_report": {"summary": "2-3 тёплых предложения ученику",
                    "good": ["что получилось"],
                    "repeat": [{"topic_id": <int>, "what": "что повторить", "tip": "как повторить"}]},
 "parent_report": "3-4 предложения для родителя простым языком, без терминов",
 "outside_material": [{"turn": <id реплики>, "note": "о чём шла речь вне материала"}]
}"""

VERDICTS = {"correct", "partial", "wrong", "unclear"}


def anonymise(text: str, names: dict[str, str]) -> str:
    """Replaces names with labels before the text leaves the server (FR-7.6)."""
    for name, label in names.items():
        for word in re.findall(r"\w{3,}", name):
            stem = re.escape(word[: max(3, len(word) - 1)])     # catches Russian endings: Айгерим, Айгерима
            text = re.sub(rf"\b{stem}\w*", label, text, flags=re.IGNORECASE)
    return text


def _strs(value, limit: int = 8) -> list[str]:
    return [str(v).strip()[:400] for v in (value if isinstance(value, list) else []) if str(v).strip()][:limit]


def _level(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return 100 if v >= 75 else 50 if v >= 25 else 0


def _turn(turns, value):
    try:
        i = int(value)
    except (TypeError, ValueError):
        return None
    return turns[i] if 0 <= i < len(turns) else None


def _ref(t):
    return None if t is None else {"turn": t["idx"], "start": t["start"], "end": t["end"], "text": t["text"]}


def build(data: dict, topics: list[dict], turns: list[dict], two: bool) -> dict:
    """Validates the model's JSON against the real transcript and shapes it like the embedding analysis."""
    got = {}
    for it in data.get("topics") or []:
        try:
            got[int(it.get("topic_id"))] = it
        except (TypeError, ValueError, AttributeError):
            continue
    out, used_turns = [], set()
    for t in topics:
        it = got.get(t["id"], {})
        by_answer: dict[int, dict] = {}
        for ev in it.get("evidence") or []:
            a = _turn(turns, ev.get("answer_turn")) if isinstance(ev, dict) else None
            if a is None or (two and a["speaker"] != "student"):
                continue                                   # no such turn, or it is not the student's
            q = _turn(turns, ev.get("question_turn"))
            if q is not None and (q["start"] >= a["start"] or (two and q["speaker"] != "teacher")):
                q = None                                   # a question cannot come after its answer
            old = by_answer.get(a["idx"])
            if old and (old["question"] or q is None):
                continue                                   # one answer is shown once, with its question if known
            verdict = ev.get("verdict") if ev.get("verdict") in VERDICTS else "unclear"
            by_answer[a["idx"]] = {"question": _ref(q), "answer": _ref(a), "verdict": verdict, "note": str(ev.get("note", ""))[:300]}
        evid = sorted(by_answer.values(), key=lambda e: e["answer"]["start"])
        status = str(it.get("status", "not_discussed"))
        touched = bool(evid) and status != "not_discussed"
        level = _level(it.get("level"))
        if touched and level is None:
            level = {"learned": 100, "partial": 50, "not_learned": 0}.get(status, 50)
        covered = {int(i) for i in (it.get("covered_points") or []) if str(i).isdigit() and int(i) < len(t["points"])}
        answers = {e["answer"]["turn"]: e["answer"] for e in evid} if touched else {}
        used_turns |= set(answers)
        out.append({
            "slide": t["id"], "title": t["title"], "touched": touched, "status": status if touched else "not_discussed",
            "index": level if touched else 0, "comment": str(it.get("comment", ""))[:500] if touched else "",
            "evidence": evid if touched else [],
            "points": [{"text": p, "covered": i in covered, "similarity": None, "start": None, "end": None, "quote": ""}
                       for i, p in enumerate(t["points"])],
            "covered_points": len(covered), "total_points": len(t["points"]),
            "seconds": round(sum(a["end"] - a["start"] for a in answers.values()), 1),
            "first_mention": min((a["start"] for a in answers.values()), default=None),
        })
    outside = []
    for o in data.get("outside_material") or []:
        tr = _turn(turns, o.get("turn")) if isinstance(o, dict) else None
        if tr is not None and (not two or tr["speaker"] != "teacher") and tr["idx"] not in used_turns:
            outside.append({"start": tr["start"], "end": tr["end"], "text": tr["text"], "note": str(o.get("note", ""))[:300]})
    speech = sum(t["end"] - t["start"] for t in turns if (t["speaker"] == "student" or not two))
    sr = data.get("student_report") if isinstance(data.get("student_report"), dict) else {}
    ids = {t["id"]: t["title"] for t in topics}
    repeat = []
    for r in sr.get("repeat") or []:
        if isinstance(r, dict) and str(r.get("topic_id", "")).lstrip("-").isdigit() and int(r["topic_id"]) in ids:
            repeat.append({"topic_id": int(r["topic_id"]), "what": str(r.get("what", ""))[:300], "tip": str(r.get("tip", ""))[:300]})
    return {
        "topics": out, "outside_material": outside,
        "on_topic_share": round(100 * sum(t["seconds"] for t in out) / speech) if speech else 0,
        "llm_reports": {
            "summary": str(data.get("summary", ""))[:1200], "strengths": _strs(data.get("strengths")),
            "difficulties": _strs(data.get("difficulties")), "next_lesson": _strs(data.get("next_lesson")),
            "student": {"summary": str(sr.get("summary", ""))[:800], "good": _strs(sr.get("good")), "repeat": repeat},
            "parent": str(data.get("parent_report", ""))[:1200],
        },
    }


def run(topics: list[dict], segments: list[dict], cfg: dict, names: dict[str, str] | None = None) -> dict:
    """topics: [{"id", "title", "points": [...]}]. Returns the analysis dict plus the model description."""
    turns, _ = dialogue(segments)
    two = any(t["speaker"] == "student" for t in turns) and any(t["speaker"] == "teacher" for t in turns)
    names = names or {}
    payload = {
        "mode": "dialogue" if two else "monologue",
        "report_language": "английский" if cfg.get("report_language") == "en" else "русский",
        "topics": [{"topic_id": t["id"], "title": t["title"], "points": [f"{i}: {p}" for i, p in enumerate(t["points"])]} for t in topics],
        "turns": [{"id": t["idx"], "speaker": t["speaker"] or "speaker", "start_sec": round(t["start"]),
                   "text": anonymise(t["text"], names)} for t in turns],
        "schema": SCHEMA,
    }
    user, last = json.dumps(payload, ensure_ascii=False), None
    for _ in range(3):                                   # FR-7.5: up to 3 attempts, then the lesson gets "Error"
        raw = llm.chat(cfg, SYSTEM, user)
        try:
            result = build(llm.parse_json(raw), topics, turns, two)
            if not any(t["touched"] for t in result["topics"]) and not result["outside_material"]:
                raise ValueError("ни по одной теме нет подтверждённых ответов")
            result["llm"] = {"provider": cfg.get("llm_provider"), "model": cfg.get("llm_model"), "prompt_version": PROMPT_VERSION}
            return result
        except (ValueError, KeyError, TypeError) as e:
            last = e
            user = json.dumps(payload, ensure_ascii=False) + f"\n\nПредыдущий ответ не подошёл ({e}). Верни только корректный JSON по схеме."
    raise llm.LLMError(f"Модель трижды вернула неподходящий ответ: {last}")
