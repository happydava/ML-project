"""DATERA EDU mini: web app with a teacher cabinet and a student cabinet.

Run:  .venv/bin/uvicorn web.server:app --port 8501
Storage: SQLite (data/datera.db) and files in data/. Lessons are processed one by one in a background thread,
the same idea as the queue in the diploma architecture (upload does not wait for the analysis).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import queue
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "datera.db"
SEED = ROOT / "seed.json"
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="DATERA EDU mini")


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """The browser must re-check the page files on every load, otherwise it shows an old interface after an update."""
    response = await call_next(request)
    if not request.url.path.endswith("/audio"):
        response.headers["Cache-Control"] = "no-cache"
    return response

# ------------------------------------------------------------------ database

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, pass TEXT, role TEXT, teacher_id INTEGER);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER);
CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY, name TEXT, teacher_id INTEGER);
CREATE TABLE IF NOT EXISTS enrollments(student_id INTEGER, subject_id INTEGER, UNIQUE(student_id, subject_id));
CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY, subject_id INTEGER, filename TEXT, path TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY, subject_id INTEGER, material_id INTEGER, slide INTEGER, title TEXT, points TEXT);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, student_id INTEGER, subject_id INTEGER, title TEXT, date TEXT,
    status TEXT, stage TEXT, error TEXT, media TEXT, result TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY, lesson_id INTEGER, topic_id INTEGER, touched INTEGER,
    auto_idx INTEGER, idx INTEGER, confirmed INTEGER DEFAULT 0, changed INTEGER DEFAULT 0, comment TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS parent_students(parent_id INTEGER, student_id INTEGER, UNIQUE(parent_id, student_id));
"""

# Everything the system admin can change without touching the code (FR-7.7, FR-15.3).
DEFAULTS = {
    "whisper_model": "small", "whisper_language": "auto",
    "analysis_mode": "embeddings",            # "embeddings" (local, no key) or "llm"
    "llm_provider": "groq", "llm_base_url": "https://api.groq.com/openai/v1", "llm_model": "llama-3.3-70b-versatile",
    "llm_api_key": "", "llm_temperature": "0.2", "report_language": "ru",
    "threshold": "0.65", "pause_seconds": "5",
}


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def q(sql: str, *args) -> list[dict]:
    with db() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def one(sql: str, *args) -> dict | None:
    rows = q(sql, *args)
    return rows[0] if rows else None


def x(sql: str, *args) -> int:
    with db() as con:
        return con.execute(sql, args).lastrowid


def settings() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update({r["key"]: r["value"] for r in q("SELECT * FROM settings")})
    return cfg


def hash_pass(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def check_pass(password: str, stored: str) -> bool:
    return secrets.compare_digest(hash_pass(password, stored.split("$")[0]), stored)


# ------------------------------------------------------------------ rules: index, colours, labels

def color_of(idx: int | None) -> str:
    if idx is None:
        return "gray"
    return "green" if idx >= 80 else "yellow" if idx >= 50 else "red"


TEACHER_LABEL = {"green": "Закреплено", "yellow": "Требует закрепления", "red": "Не усвоено", "gray": "Не затрагивалась"}
STUDENT_LABEL = {"green": "Получается", "yellow": "Почти получилось", "red": "Нужно повторить", "gray": "Не было на уроке"}


def knowledge_map(student_id: int, subject_id: int) -> list[dict]:
    """Latest index of every topic, the change against the previous lesson and the date of the last review (FR-8.2)."""
    rows = q("""SELECT a.topic_id, a.idx, a.detail, l.date, l.id AS lesson_id FROM assessments a
                JOIN lessons l ON l.id = a.lesson_id
                WHERE l.student_id = ? AND l.subject_id = ? AND l.status = 'done' AND a.touched = 1
                ORDER BY l.date, l.id""", student_id, subject_id)
    history: dict[int, list[dict]] = {}
    for r in rows:
        history.setdefault(r["topic_id"], []).append(r)
    out = []
    for t in q("SELECT * FROM topics WHERE subject_id = ? ORDER BY material_id, slide", subject_id):
        h = history.get(t["id"], [])
        last = h[-1] if h else None
        miss = lambda r: [p["text"] for p in json.loads(r["detail"])["points"] if not p["covered"]]
        missing = miss(last) if last else []
        out.append({
            "topic_id": t["id"], "title": t["title"], "slide": t["slide"],
            "index": last["idx"] if last else None,
            "color": color_of(last["idx"] if last else None),
            "change": (last["idx"] - h[-2]["idx"]) if len(h) > 1 else None,
            "last_date": last["date"] if last else None,
            "last_lesson_id": last["lesson_id"] if last else None,
            "missing": missing,
            "history": [{"lesson_id": r["lesson_id"], "date": r["date"], "idx": r["idx"], "missing": miss(r)} for r in h],   # for the per-lesson filter
        })
    for m in out:
        m["teacher_label"], m["student_label"] = TEACHER_LABEL[m["color"]], STUDENT_LABEL[m["color"]]
    return out


def lesson_index(lesson_id: int) -> int | None:
    vals = [a["idx"] for a in q("SELECT idx FROM assessments WHERE lesson_id = ? AND touched = 1", lesson_id)]
    return round(sum(vals) / len(vals)) if vals else None


# ------------------------------------------------------------------ background processing

def process(lesson_id: int) -> None:
    """Stages 0-3 (audio, speech recognition, speakers), then stage 4."""
    from datera import pipeline
    from datera.materials import Topic

    lesson = one("SELECT * FROM lessons WHERE id = ?", lesson_id)
    cfg = settings()
    workdir = DATA / "lessons" / str(lesson_id)
    workdir.mkdir(parents=True, exist_ok=True)

    def stage(msg: str) -> None:
        x("UPDATE lessons SET status = 'processing', stage = ? WHERE id = ?", msg, lesson_id)

    rows = topic_rows(lesson["subject_id"])
    if not rows:
        raise ValueError("У предмета нет тем. Сначала загрузите материал в разделе «Предметы и материалы».")
    r = pipeline.run(lesson["media"], model_name=cfg["whisper_model"],
                     language=None if cfg["whisper_language"] == "auto" else cfg["whisper_language"],
                     threshold=float(cfg["threshold"]), topics=[Topic(t["id"], t["title"], t["points"]) for t in rows],
                     workdir=workdir, on_stage=stage)

    stage("Сохранение аудио")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import whisper

    audio = whisper.load_audio(r["wav_path"])
    buckets = np.array_split(np.abs(audio), 180)
    peaks = np.array([float(b.max()) if len(b) else 0.0 for b in buckets])
    peaks = (peaks / (peaks.max() or 1.0)).round(3).tolist()

    fig, ax = plt.subplots(figsize=(11, 2.6), dpi=110)
    ax.imshow(r["mel"], aspect="auto", origin="lower", cmap="magma", extent=[0, 30, 0, r["whisper"]["n_mels"]])
    ax.set_xlabel("время, с")
    ax.set_ylabel("мел-полоса")
    fig.tight_layout()
    fig.savefig(workdir / "mel.png")
    plt.close(fig)

    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", r["wav_path"], "-c:a", "aac", "-b:a", "64k",
                    str(workdir / "audio.m4a")], check=True)
    Path(r["wav_path"]).unlink(missing_ok=True)

    result = {
        "duration": r["duration"], "language": r["language"], "language_probs": r["language_probs"],
        "segments": r["segments"], "speakers": r["speakers"],
        "peaks": peaks, "whisper": r["whisper"], "timings": r["timings"],
    }
    run_analysis(lesson_id, result, stage)


def topic_rows(subject_id: int) -> list[dict]:
    rows = q("SELECT * FROM topics WHERE subject_id = ? ORDER BY material_id, slide", subject_id)
    return [{"id": r["id"], "title": r["title"], "points": json.loads(r["points"])} for r in rows]


def run_analysis(lesson_id: int, result: dict, stage=lambda msg: None, swap: bool = False) -> None:
    """Stage 4. The embedding analysis always runs (it is local and fast). If the admin switched the analysis
    to a language model, its result replaces it; when the model is unreachable the embedding result is kept
    and the reason is shown in the report, so the cabinets keep working (section 5.4 of the spec)."""
    import time

    from datera import analysis, diarize, llm, llm_analysis, pipeline
    from datera.dialogue import dialogue
    from datera.materials import Topic

    lesson = one("""SELECT l.*, u.name AS student_name, t.name AS teacher_name FROM lessons l
                    JOIN users u ON u.id = l.student_id JOIN subjects s ON s.id = l.subject_id
                    JOIN users t ON t.id = s.teacher_id WHERE l.id = ?""", lesson_id)
    cfg = settings()
    topics = topic_rows(lesson["subject_id"])
    if not topics:
        raise ValueError("У предмета нет тем. Сначала загрузите материал в разделе «Предметы и материалы».")
    segs = result["segments"]
    if swap:
        diarize.swap_roles(segs)
    for s in segs:
        s.pop("topic_slide", None)
        s.pop("similarity", None)

    stage("Этап 4. Анализ: сопоставление речи с темами (эмбеддинги)")
    a = analysis.analyse([Topic(t["id"], t["title"], t["points"]) for t in topics], pipeline.scored_segments(segs),
                         float(cfg["threshold"]))
    for t in a["topics"]:
        t["touched"] = t["covered_points"] > 0 or t["seconds"] > 0
    turns, pairs = dialogue(segs)                        # without a language model: answers in lesson order per topic
    for t in a["topics"]:
        t["evidence"] = [{"question": {k: p["question"][k] for k in ("start", "end", "text")} | {"turn": p["question"]["idx"]},
                          "answer": {k: p["answer"][k] for k in ("start", "end", "text")} | {"turn": p["answer"]["idx"]},
                          "verdict": None, "note": ""}
                         for p in pairs if p["answer"] and t["slide"] in p["answer"]["topics"]]
    for key in ("llm_reports", "llm", "llm_error", "turn_marks"):
        result.pop(key, None)
    result["engine"] = "embeddings"

    if cfg["analysis_mode"] == "llm":
        stage(f"Этап 4. Анализ ответов языковой моделью ({cfg['llm_model']})")
        t0 = time.time()
        try:
            la = llm_analysis.run(topics, segs, cfg, {lesson["student_name"]: "Ученик", lesson["teacher_name"]: "Преподаватель"})
        except llm.LLMError as e:
            result["llm_error"] = str(e)[:400]
        else:
            marks: dict[str, dict] = {}
            for t in la["topics"]:                       # which topic each answer belongs to, for the lesson flow view
                for ev in t["evidence"]:
                    m = marks.setdefault(str(ev["answer"]["turn"]), {"topics": [], "verdict": ev["verdict"], "note": ev["note"]})
                    if t["slide"] not in m["topics"]:
                        m["topics"].append(t["slide"])
            for s in segs:
                s.pop("topic_slide", None)
            a.update(topics=la["topics"], outside_material=la["outside_material"], on_topic_share=la["on_topic_share"])
            result.update(engine="llm", llm_reports=la["llm_reports"], llm=la["llm"], turn_marks=marks)
            result.setdefault("timings", {})["llm"] = round(time.time() - t0, 1)

    x("DELETE FROM assessments WHERE lesson_id = ?", lesson_id)
    for t in a["topics"]:
        detail = {"points": t["points"], "seconds": t["seconds"], "first_mention": t["first_mention"],
                  "evidence": t.get("evidence", []), "comment": t.get("comment", "")}
        x("INSERT INTO assessments(lesson_id, topic_id, touched, auto_idx, idx, detail) VALUES(?,?,?,?,?,?)",
          lesson_id, t["slide"], int(t["touched"]), t["index"], t["index"], json.dumps(detail, ensure_ascii=False))
    result.update({"outside": a["outside_material"], "on_topic_share": a["on_topic_share"],
                   "embedding_model": a["embedding_model"], "threshold": a["threshold"]})
    x("UPDATE lessons SET status = 'done', stage = '', error = '', result = ? WHERE id = ?",
      json.dumps(result, ensure_ascii=False), lesson_id)


models_lock = threading.Lock()   # the neural networks are used by one task at a time
jobs: "queue.Queue[tuple[str, int]]" = queue.Queue()


def worker() -> None:
    while True:
        kind, lesson_id = jobs.get()

        def stage(msg: str) -> None:
            x("UPDATE lessons SET status = 'processing', stage = ? WHERE id = ?", msg, lesson_id)

        try:
            with models_lock:
                if kind == "full":
                    process(lesson_id)
                else:                                    # "analysis" or "swap": stage 4 only, on the saved transcript
                    saved = one("SELECT result FROM lessons WHERE id = ?", lesson_id)
                    run_analysis(lesson_id, json.loads(saved["result"]), stage, swap=kind == "swap")
        except Exception as e:  # the lesson gets the "Error" status, the cabinet keeps working
            x("UPDATE lessons SET status = 'error', error = ? WHERE id = ?", str(e)[:500], lesson_id)


def enqueue(lesson_id: int, kind: str = "full") -> None:
    if kind != "full" and not (one("SELECT result FROM lessons WHERE id = ?", lesson_id) or {}).get("result"):
        kind = "full"
    x("UPDATE lessons SET status = 'queued', stage = 'В очереди', error = '' WHERE id = ?", lesson_id)
    jobs.put((kind, lesson_id))


# ------------------------------------------------------------------ materials

def add_material(subject_id: int, filename: str, src: Path) -> int:
    from datera.materials import load_topics

    topics = [t for t in load_topics(src) if not t.skipped]
    if not topics:
        raise ValueError("В материале не найдено тем с текстом")
    mid = x("INSERT INTO materials(subject_id, filename, path, created) VALUES(?,?,?,?)",
            subject_id, filename, str(src), dt.date.today().isoformat())
    for t in topics:
        x("INSERT INTO topics(subject_id, material_id, slide, title, points) VALUES(?,?,?,?,?)",
          subject_id, mid, t.index, t.title, json.dumps(t.points, ensure_ascii=False))
    return mid


# ------------------------------------------------------------------ seed and startup

def demo_password() -> str:
    """Password of the demo accounts: DATERA_PASSWORD if set (for a public deployment), otherwise random."""
    return os.environ.get("DATERA_PASSWORD") or secrets.token_urlsafe(6)


def seed() -> None:
    if not SEED.exists():   # demo accounts are generated once and kept in seed.json
        SEED.write_text(json.dumps({
            "organization": "Учебный центр «Bilim»",
            "teacher": {"name": "Алия Нурланова", "email": "teacher@datera.test", "password": demo_password()},
            "student": {"name": "Айгерим Садыкова", "email": "student@datera.test", "password": demo_password()},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    s = json.loads(SEED.read_text(encoding="utf-8"))
    extra = {"admin": {"name": "Системный администратор", "email": "admin@datera.test"},
             "parent": {"name": "Гульнара Садыкова", "email": "parent@datera.test"}}
    if any(k not in s for k in extra):                    # accounts added in a later version of the demo
        for k, v in extra.items():
            s.setdefault(k, {**v, "password": demo_password()})
        SEED.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    first_run = not one("SELECT id FROM users LIMIT 1")
    for role in extra:
        if not one("SELECT id FROM users WHERE role = ?", role):
            x("INSERT INTO users(name, email, pass, role) VALUES(?,?,?,?)",
              s[role]["name"], s[role]["email"], hash_pass(s[role]["password"]), role)
    if not first_run:
        link_parent(s)
        return
    tid = x("INSERT INTO users(name, email, pass, role) VALUES(?,?,?,'teacher')",
            s["teacher"]["name"], s["teacher"]["email"], hash_pass(s["teacher"]["password"]))
    sid = x("INSERT INTO users(name, email, pass, role, teacher_id) VALUES(?,?,?,'student',?)",
            s["student"]["name"], s["student"]["email"], hash_pass(s["student"]["password"]), tid)
    slides, talk = ROOT / "sample" / "slides.pptx", ROOT / "sample" / "talk.m4a"
    if slides.exists() and talk.exists():
        subj = x("INSERT INTO subjects(name, teacher_id) VALUES('Нейронные сети', ?)", tid)
        x("INSERT INTO enrollments VALUES(?, ?)", sid, subj)
        dst = DATA / "materials" / "sample_slides.pptx"
        shutil.copy(slides, dst)
        add_material(subj, "slides.pptx", dst)
        media = DATA / "uploads" / "sample_talk.m4a"
        shutil.copy(talk, media)
        lid = x("INSERT INTO lessons(student_id, subject_id, title, date, media, created) VALUES(?,?,?,?,?,?)",
                sid, subj, "Вводная лекция", dt.date.today().isoformat(), str(media), dt.datetime.now().isoformat())
        enqueue(lid)
    link_parent(s)


def link_parent(s: dict) -> None:
    parent = one("SELECT id FROM users WHERE email = ?", s["parent"]["email"])
    child = one("SELECT id FROM users WHERE email = ?", s["student"]["email"])
    if parent and child:
        x("INSERT OR IGNORE INTO parent_students VALUES(?, ?)", parent["id"], child["id"])


@app.on_event("startup")
def startup() -> None:
    for d in ("uploads", "materials", "lessons"):
        (DATA / d).mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.executescript(SCHEMA)
    seed()
    for l in q("SELECT id FROM lessons WHERE status IN ('queued', 'processing')"):   # resume after a restart
        jobs.put(("full", l["id"]))
    threading.Thread(target=worker, daemon=True).start()


# ------------------------------------------------------------------ auth

def current_user(request: Request) -> dict:
    token = request.cookies.get("datera_session", "")
    user = one("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?", token)
    if not user:
        raise HTTPException(401, "Нужно войти")
    return user


def teacher_only(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "teacher":
        raise HTTPException(403, "Только для преподавателя")
    return user


def staff(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in ("teacher", "admin"):
        raise HTTPException(403, "Недостаточно прав")
    return user


def admin_only(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Только для администратора")
    return user


def children_of(user: dict) -> list[dict]:
    return q("SELECT u.id, u.name FROM parent_students p JOIN users u ON u.id = p.student_id WHERE p.parent_id = ? ORDER BY u.name", user["id"])


def public_user(u: dict) -> dict:
    org = json.loads(SEED.read_text(encoding="utf-8")).get("organization", "") if SEED.exists() else ""
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "organization": org}


@app.get("/api/demo-accounts")
def demo_accounts():
    """Local demo only: lets the login page fill in the seeded test accounts."""
    if os.environ.get("DATERA_DEMO", "1") == "0":      # a public deployment hides the demo buttons
        raise HTTPException(404, "Демо-доступ отключён")
    s = json.loads(SEED.read_text(encoding="utf-8"))
    return {role: {k: s[role][k] for k in ("email", "password")} for role in ("teacher", "student", "parent", "admin") if role in s}


@app.post("/api/login")
async def login(request: Request, response: Response):
    body = await request.json()
    user = one("SELECT * FROM users WHERE email = ?", str(body.get("email", "")).strip().lower())
    if not user or not check_pass(str(body.get("password", "")), user["pass"]):
        raise HTTPException(401, "Неверная почта или пароль")
    token = secrets.token_urlsafe(32)
    x("INSERT INTO sessions VALUES(?, ?)", token, user["id"])
    response.set_cookie("datera_session", token, httponly=True, samesite="lax")
    return public_user(user)


@app.post("/api/logout")
def logout(request: Request, response: Response):
    x("DELETE FROM sessions WHERE token = ?", request.cookies.get("datera_session", ""))
    response.delete_cookie("datera_session")
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return public_user(user)


# ------------------------------------------------------------------ access helpers

def lesson_for(user: dict, lesson_id: int) -> dict:
    l = one("""SELECT l.*, s.name AS subject_name, s.teacher_id, u.name AS student_name FROM lessons l
               JOIN subjects s ON s.id = l.subject_id JOIN users u ON u.id = l.student_id WHERE l.id = ?""", lesson_id)
    if not l or (user["role"] == "teacher" and l["teacher_id"] != user["id"]) \
            or (user["role"] == "student" and l["student_id"] != user["id"]) \
            or (user["role"] == "parent" and l["student_id"] not in [c["id"] for c in children_of(user)]):
        raise HTTPException(404, "Урок не найден")
    return l


def lesson_card(l: dict) -> dict:
    a = q("SELECT idx FROM assessments WHERE lesson_id = ? AND touched = 1", l["id"])
    res = json.loads(l["result"]) if l.get("result") else {}
    return {
        "id": l["id"], "title": l["title"], "date": l["date"], "status": l["status"], "stage": l["stage"],
        "error": l["error"], "student_id": l["student_id"], "student_name": l.get("student_name"),
        "subject_name": l.get("subject_name"), "duration": res.get("duration"),
        "index": lesson_index(l["id"]) if l["status"] == "done" else None,
        "repeat": sum(1 for r in a if r["idx"] < 80), "ok": sum(1 for r in a if r["idx"] >= 80),
    }


LESSON_LIST = """SELECT l.*, s.name AS subject_name, u.name AS student_name FROM lessons l
                 JOIN subjects s ON s.id = l.subject_id JOIN users u ON u.id = l.student_id"""


# ------------------------------------------------------------------ teacher: students

@app.get("/api/students")
def students(user: dict = Depends(teacher_only)):
    out = []
    for s in q("SELECT * FROM users WHERE role = 'student' AND teacher_id = ? ORDER BY name", user["id"]):
        subjects = q("SELECT s.* FROM enrollments e JOIN subjects s ON s.id = e.subject_id WHERE e.student_id = ?", s["id"])
        topics = [m for subj in subjects for m in knowledge_map(s["id"], subj["id"]) if m["index"] is not None]
        last = one("SELECT date FROM lessons WHERE student_id = ? ORDER BY date DESC, id DESC LIMIT 1", s["id"])
        out.append({
            "id": s["id"], "name": s["name"], "email": s["email"],
            "subjects": [x_["name"] for x_ in subjects],
            "avg_index": round(sum(t["index"] for t in topics) / len(topics)) if topics else None,
            "red": sum(1 for t in topics if t["color"] == "red"),
            "last_lesson": last["date"] if last else None,
        })
    return out


@app.post("/api/students")
async def add_student(request: Request, user: dict = Depends(teacher_only)):
    b = await request.json()
    name, email, password = str(b.get("name", "")).strip(), str(b.get("email", "")).strip().lower(), str(b.get("password", ""))
    if not name or "@" not in email or len(password) < 6:
        raise HTTPException(400, "Укажите имя, почту и пароль не короче 6 символов")
    if one("SELECT id FROM users WHERE email = ?", email):
        raise HTTPException(400, "Пользователь с такой почтой уже есть")
    sid = x("INSERT INTO users(name, email, pass, role, teacher_id) VALUES(?,?,?,'student',?)",
            name, email, hash_pass(password), user["id"])
    subj = one("SELECT id FROM subjects WHERE id = ? AND teacher_id = ?", b.get("subject_id"), user["id"])
    if subj:
        x("INSERT OR IGNORE INTO enrollments VALUES(?, ?)", sid, subj["id"])
    return {"id": sid}


@app.get("/api/students/{student_id}")
def student_card(student_id: int, user: dict = Depends(teacher_only)):
    s = one("SELECT * FROM users WHERE id = ? AND role = 'student' AND teacher_id = ?", student_id, user["id"])
    if not s:
        raise HTTPException(404, "Ученик не найден")
    subjects = q("SELECT s.* FROM enrollments e JOIN subjects s ON s.id = e.subject_id WHERE e.student_id = ?", student_id)
    maps = [{"subject": subj["name"], "topics": knowledge_map(student_id, subj["id"])} for subj in subjects]
    lessons = [lesson_card(l) for l in q(LESSON_LIST + " WHERE l.student_id = ? ORDER BY l.date DESC, l.id DESC", student_id)]
    return {"id": s["id"], "name": s["name"], "email": s["email"], "maps": maps, "lessons": lessons,
            "trend": trend(student_id), "stuck": stuck_topics(student_id), "parents": parents_of(student_id)}


def trend(student_id: int) -> list[dict]:
    """Index of every finished lesson in time order (FR-8.3)."""
    out = []
    for l in q("SELECT id, title, date FROM lessons WHERE student_id = ? AND status = 'done' ORDER BY date, id", student_id):
        idx = lesson_index(l["id"])
        if idx is not None:
            out.append({"id": l["id"], "title": l["title"], "date": l["date"], "index": idx})
    return out


def stuck_topics(student_id: int) -> list[dict]:
    """Topics that stayed red in the last two reviews (FR-8.4): the student is stuck on them."""
    rows = q("""SELECT a.topic_id, a.idx, t.title FROM assessments a JOIN lessons l ON l.id = a.lesson_id
                JOIN topics t ON t.id = a.topic_id WHERE l.student_id = ? AND l.status = 'done' AND a.touched = 1
                ORDER BY l.date, l.id""", student_id)
    hist: dict[int, list] = {}
    for r in rows:
        hist.setdefault(r["topic_id"], []).append(r)
    out = []
    for h in hist.values():
        run = 0
        for r in reversed(h):
            if r["idx"] >= 50:
                break
            run += 1
        if run >= 2:
            out.append({"topic_id": h[-1]["topic_id"], "title": h[-1]["title"], "times": run})
    return out


def parents_of(student_id: int) -> list[dict]:
    return q("SELECT u.id, u.name, u.email FROM parent_students p JOIN users u ON u.id = p.parent_id WHERE p.student_id = ? ORDER BY u.name", student_id)


# ------------------------------------------------------------------ teacher: parents

def own_student(student_id, user: dict) -> dict:
    s = one("SELECT * FROM users WHERE id = ? AND role = 'student' AND teacher_id = ?", student_id, user["id"])
    if not s:
        raise HTTPException(404, "Ученик не найден")
    return s


def own_parent(parent_id: int, user: dict) -> dict:
    p = one("SELECT * FROM users WHERE id = ? AND role = 'parent' AND teacher_id = ?", parent_id, user["id"])
    if not p:
        raise HTTPException(404, "Родитель не найден")
    return p


@app.get("/api/parents")
def parents(user: dict = Depends(teacher_only)):
    out = []
    for p in q("SELECT * FROM users WHERE role = 'parent' AND teacher_id = ? ORDER BY name", user["id"]):
        out.append({"id": p["id"], "name": p["name"], "email": p["email"],
                    "children": q("SELECT u.id, u.name FROM parent_students ps JOIN users u ON u.id = ps.student_id WHERE ps.parent_id = ? ORDER BY u.name", p["id"])})
    return out


@app.post("/api/parents")
async def add_parent(request: Request, user: dict = Depends(teacher_only)):
    """Creates a parent account and attaches the chosen students to it."""
    b = await request.json()
    name, email, password = str(b.get("name", "")).strip(), str(b.get("email", "")).strip().lower(), str(b.get("password", ""))
    if not name or "@" not in email or len(password) < 6:
        raise HTTPException(400, "Укажите имя, почту и пароль не короче 6 символов")
    if one("SELECT id FROM users WHERE email = ?", email):
        raise HTTPException(400, "Пользователь с такой почтой уже есть")
    ids = b.get("student_ids") or ([b["student_id"]] if b.get("student_id") else [])
    kids = [own_student(i, user) for i in ids]
    if not kids:
        raise HTTPException(400, "Выберите хотя бы одного ребёнка")
    pid = x("INSERT INTO users(name, email, pass, role, teacher_id) VALUES(?,?,?,'parent',?)", name, email, hash_pass(password), user["id"])
    for k in kids:
        x("INSERT OR IGNORE INTO parent_students VALUES(?, ?)", pid, k["id"])
    return {"id": pid}


@app.post("/api/parents/{parent_id}/children")
async def attach_child(parent_id: int, request: Request, user: dict = Depends(teacher_only)):
    b = await request.json()
    own_parent(parent_id, user)
    kid = own_student(b.get("student_id"), user)
    x("INSERT OR IGNORE INTO parent_students VALUES(?, ?)", parent_id, kid["id"])
    return {"ok": True}


@app.delete("/api/parents/{parent_id}/children/{student_id}")
def detach_child(parent_id: int, student_id: int, user: dict = Depends(teacher_only)):
    own_parent(parent_id, user)
    own_student(student_id, user)
    x("DELETE FROM parent_students WHERE parent_id = ? AND student_id = ?", parent_id, student_id)
    return {"ok": True}


@app.get("/api/overview")
def overview(user: dict = Depends(teacher_only)):
    """Teacher's start page: who needs attention, which topics fail most often, latest lessons (FR-8.4, FR-8.5)."""
    people, weak = [], {}
    for s in q("SELECT * FROM users WHERE role = 'student' AND teacher_id = ? ORDER BY name", user["id"]):
        subjects = q("SELECT s.* FROM enrollments e JOIN subjects s ON s.id = e.subject_id WHERE e.student_id = ?", s["id"])
        topics = [(subj["name"], m) for subj in subjects for m in knowledge_map(s["id"], subj["id"]) if m["index"] is not None]
        avg = round(sum(m["index"] for _, m in topics) / len(topics)) if topics else None
        tr, st = trend(s["id"]), stuck_topics(s["id"])
        delta = tr[-1]["index"] - tr[-2]["index"] if len(tr) > 1 else None
        reds = sum(1 for _, m in topics if m["color"] == "red")
        risk = "high" if (avg is not None and avg < 50) or len(st) >= 2 else "mid" if st or reds or (delta is not None and delta <= -15) else "ok" if avg is not None else "none"
        people.append({"id": s["id"], "name": s["name"], "avg": avg, "delta": delta, "stuck": [t["title"] for t in st],
                       "reds": reds, "risk": risk, "lessons": len(tr), "trend": [t["index"] for t in tr][-8:]})
        for subj, m in topics:
            if m["color"] != "green":
                w = weak.setdefault((subj, m["topic_id"]), {"subject": subj, "title": m["title"], "students": []})
                w["students"].append(s["name"])
    order = {"high": 0, "mid": 1, "ok": 2, "none": 3}
    people.sort(key=lambda p: (order[p["risk"]], p["avg"] if p["avg"] is not None else 101))
    recent = [lesson_card(l) for l in q(LESSON_LIST + " WHERE s.teacher_id = ? ORDER BY l.id DESC LIMIT 5", user["id"])]
    avgs = [p["avg"] for p in people if p["avg"] is not None]
    return {"people": people, "recent": recent,
            "weak_topics": sorted(({**w, "count": len(w["students"])} for w in weak.values()), key=lambda w: -w["count"])[:6],
            "totals": {"students": len(people), "lessons": sum(p["lessons"] for p in people),
                       "avg": round(sum(avgs) / len(avgs)) if avgs else None,
                       "attention": sum(1 for p in people if p["risk"] in ("high", "mid")),
                       "parents": one("SELECT COUNT(*) AS n FROM users WHERE role = 'parent' AND teacher_id = ?", user["id"])["n"]}}


@app.post("/api/profile")
async def save_profile(request: Request, user: dict = Depends(current_user)):
    """Own name and password, for every role."""
    b = await request.json()
    name = str(b.get("name", "")).strip()
    if name:
        x("UPDATE users SET name = ? WHERE id = ?", name, user["id"])
    if b.get("new_password"):
        if not check_pass(str(b.get("old_password", "")), user["pass"]):
            raise HTTPException(400, "Текущий пароль указан неверно")
        if len(str(b["new_password"])) < 6:
            raise HTTPException(400, "Новый пароль должен быть не короче 6 символов")
        x("UPDATE users SET pass = ? WHERE id = ?", hash_pass(str(b["new_password"])), user["id"])
    return {"ok": True}


# ------------------------------------------------------------------ teacher: subjects and materials

@app.get("/api/subjects")
def subjects(user: dict = Depends(teacher_only)):
    out = []
    for s in q("SELECT * FROM subjects WHERE teacher_id = ? ORDER BY id", user["id"]):
        topics = q("SELECT * FROM topics WHERE subject_id = ? ORDER BY material_id, slide", s["id"])
        for t in topics:
            t["points"] = json.loads(t["points"])
        out.append({**s, "materials": q("SELECT id, filename, created FROM materials WHERE subject_id = ?", s["id"]),
                    "topics": topics,
                    "students": q("SELECT u.id, u.name FROM enrollments e JOIN users u ON u.id = e.student_id "
                                  "WHERE e.subject_id = ?", s["id"])})
    return out


@app.post("/api/subjects")
async def add_subject(request: Request, user: dict = Depends(teacher_only)):
    name = str((await request.json()).get("name", "")).strip()
    if not name:
        raise HTTPException(400, "Укажите название предмета")
    return {"id": x("INSERT INTO subjects(name, teacher_id) VALUES(?, ?)", name, user["id"])}


def own_subject(subject_id: int, user: dict) -> dict:
    s = one("SELECT * FROM subjects WHERE id = ? AND teacher_id = ?", subject_id, user["id"])
    if not s:
        raise HTTPException(404, "Предмет не найден")
    return s


def save_upload(file: UploadFile, folder: str, allowed: tuple[str, ...]) -> Path:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Формат {ext or 'без расширения'} не поддерживается. Допустимо: {', '.join(allowed)}")
    dst = DATA / folder / f"{secrets.token_hex(8)}{ext}"
    with dst.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return dst


@app.post("/api/subjects/{subject_id}/materials")
def upload_material(subject_id: int, file: UploadFile = File(...), user: dict = Depends(teacher_only)):
    own_subject(subject_id, user)
    dst = save_upload(file, "materials", (".pptx", ".pdf", ".txt", ".md"))
    try:
        return {"id": add_material(subject_id, file.filename, dst)}
    except Exception as e:
        dst.unlink(missing_ok=True)
        raise HTTPException(400, str(e))


@app.delete("/api/topics/{topic_id}")
def delete_topic(topic_id: int, user: dict = Depends(teacher_only)):
    t = one("SELECT t.id FROM topics t JOIN subjects s ON s.id = t.subject_id WHERE t.id = ? AND s.teacher_id = ?",
            topic_id, user["id"])
    if not t:
        raise HTTPException(404, "Тема не найдена")
    x("DELETE FROM topics WHERE id = ?", topic_id)
    x("DELETE FROM assessments WHERE topic_id = ?", topic_id)
    return {"ok": True}


# ------------------------------------------------------------------ lessons

MEDIA_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".mp4", ".mov", ".mkv", ".webm", ".avi")


@app.get("/api/lessons")
def lessons(user: dict = Depends(current_user)):
    if user["role"] == "teacher":
        rows = q(LESSON_LIST + " WHERE s.teacher_id = ? ORDER BY l.date DESC, l.id DESC", user["id"])
    elif user["role"] == "admin":
        rows = q(LESSON_LIST + " ORDER BY l.id DESC")
    elif user["role"] == "parent":
        ids = [c["id"] for c in children_of(user)] or [0]
        rows = q(LESSON_LIST + f" WHERE l.student_id IN ({','.join('?' * len(ids))}) ORDER BY l.date DESC, l.id DESC", *ids)
    else:
        rows = q(LESSON_LIST + " WHERE l.student_id = ? ORDER BY l.date DESC, l.id DESC", user["id"])
    return [lesson_card(l) for l in rows]


@app.post("/api/lessons")
def upload_lesson(student_id: int = Form(...), subject_id: int = Form(...), title: str = Form(""),
                  date: str = Form(""), file: UploadFile = File(...), user: dict = Depends(teacher_only)):
    own_subject(subject_id, user)
    if not one("SELECT id FROM users WHERE id = ? AND teacher_id = ?", student_id, user["id"]):
        raise HTTPException(404, "Ученик не найден")
    if not one("SELECT id FROM topics WHERE subject_id = ? LIMIT 1", subject_id):
        raise HTTPException(400, "У предмета пока нет тем. Сначала загрузите материал.")
    media = save_upload(file, "uploads", MEDIA_EXT)
    x("INSERT OR IGNORE INTO enrollments VALUES(?, ?)", student_id, subject_id)
    lid = x("INSERT INTO lessons(student_id, subject_id, title, date, media, created) VALUES(?,?,?,?,?,?)",
            student_id, subject_id, title.strip() or "Урок", date or dt.date.today().isoformat(), str(media),
            dt.datetime.now().isoformat())
    enqueue(lid)
    return {"id": lid}


@app.post("/api/lessons/{lesson_id}/retry")
def retry(lesson_id: int, user: dict = Depends(staff)):
    lesson_for(user, lesson_id)
    enqueue(lesson_id)
    return {"ok": True}


@app.post("/api/lessons/{lesson_id}/reanalyse")
def reanalyse(lesson_id: int, user: dict = Depends(staff)):
    """Repeats stage 4 only, with the current settings (for example after a language model was connected)."""
    lesson_for(user, lesson_id)
    enqueue(lesson_id, "analysis")
    return {"ok": True}


def tc(sec: float) -> str:
    return f"{int(sec) // 60:02d}:{int(sec) % 60:02d}"


@app.get("/api/lessons/{lesson_id}")
def lesson_report(lesson_id: int, user: dict = Depends(current_user)):
    l = lesson_for(user, lesson_id)
    card = lesson_card(l)
    if l["status"] != "done":
        return card
    res = json.loads(l["result"])
    topics = []
    for a in q("""SELECT a.*, t.title, t.slide FROM assessments a JOIN topics t ON t.id = a.topic_id
                  WHERE a.lesson_id = ? ORDER BY t.material_id, t.slide""", lesson_id):
        d = json.loads(a["detail"])
        color = color_of(a["idx"]) if a["touched"] else "gray"
        topics.append({
            "assessment_id": a["id"], "topic_id": a["topic_id"], "title": a["title"], "slide": a["slide"],
            "touched": bool(a["touched"]), "index": a["idx"], "auto_index": a["auto_idx"], "color": color,
            "teacher_label": TEACHER_LABEL[color], "student_label": STUDENT_LABEL[color],
            "confirmed": bool(a["confirmed"]), "changed": bool(a["changed"]), "comment": a["comment"] or "",
            "points": d["points"], "seconds": d["seconds"], "first_mention": d["first_mention"],
            "evidence": d.get("evidence", []), "analysis": d.get("comment", ""),
        })
    from datera.dialogue import dialogue

    engine = res.get("engine", "embeddings")
    rep_ = res.get("llm_reports") or {}
    touched = [t for t in topics if t["touched"]]
    good = [t["title"] for t in touched if t["color"] == "green"]
    weak = [t["title"] for t in touched if t["color"] in ("yellow", "red")]
    counts = {c: sum(1 for t in touched if t["color"] == c) for c in ("green", "yellow", "red")}
    # Without a language model the texts are assembled from the numbers by a template.
    summary = rep_.get("summary") or (
        f"На уроке затронуто тем: {len(touched)} из {len(topics)}. "
        + (f"Хорошо раскрыты: {', '.join(good)}. " if good else "")
        + (f"Раскрыты не полностью: {', '.join(weak)}. " if weak else ""))
    recs = rep_.get("next_lesson") or [f"Повторить «{t['title']}»: {p['text']}" for t in touched if t["color"] != "green"
                                       for p in t["points"] if not p["covered"]][:5]
    untouched = [t["title"] for t in topics if not t["touched"]]
    st = rep_.get("student") or {}
    student = {
        "summary": st.get("summary") or (
            (f"На уроке разобрали тем: {len(touched)}. " if touched else "На этом уроке темы материала не обсуждались. ")
            + (f"Хорошо получилось: {', '.join(good)}. " if good else "")
            + (f"Стоит ещё раз вернуться к темам: {', '.join(weak)}." if weak else "Повторять пока нечего, так держать!")),
        "good": st.get("good") or [p["text"] for t in touched for p in t["points"] if p["covered"]][:8],
        "repeat": st.get("repeat") or [{"topic_id": t["topic_id"],
                                        "what": "; ".join(p["text"] for p in t["points"] if not p["covered"])[:300],
                                        "tip": f"Посмотри слайд {t['slide']} в материале."}
                                       for t in touched if t["color"] != "green"],
    }
    parent = rep_.get("parent") or (
        f"На уроке «{l['title']}» обсудили тем: {len(touched)}. Уверенно получается: {counts['green']}, "
        f"нужно закрепить: {counts['yellow']}, пока не получается: {counts['red']}. "
        + ("Поддержите ребёнка: попросите рассказать своими словами темы, которые нужно повторить." if weak
           else "Всё идёт хорошо, дополнительная помощь сейчас не нужна."))
    turns, pairs = dialogue(res["segments"])
    marks = res.get("turn_marks") or {}
    for p in pairs:
        m = marks.get(str(p["answer"]["idx"])) if p["answer"] else None
        if m:
            p["answer"]["topics"], p["verdict"], p["note"] = m["topics"], m["verdict"], m.get("note", "")
    two = res.get("speakers", {}).get("speakers") == 2
    cfg = settings()
    return {**card, "turns": turns, "pairs": pairs, "two_speakers": two,
            "speakers": res.get("speakers", {"speakers": 1}),
            "topics": topics, "counts": counts, "untouched": untouched, "summary": summary,
            "strengths": rep_.get("strengths") or [], "difficulties": rep_.get("difficulties") or [],
            "recommendations": recs, "student": student, "parent_text": parent,
            "engine": engine, "llm": res.get("llm"), "llm_error": res.get("llm_error"),
            "pause_seconds": float(cfg["pause_seconds"]),
            "outside": res["outside"], "segments": res["segments"], "peaks": res["peaks"],
            "on_topic_share": res.get("on_topic_share"),
            "language": res["language"], "checked": sum(1 for t in touched if t["confirmed"]), "to_check": len(touched),
            "model": {"whisper": res["whisper"], "language_probs": res["language_probs"], "timings": res["timings"],
                      "embedding_model": res["embedding_model"], "threshold": res["threshold"]}}


@app.post("/api/lessons/{lesson_id}/swap-roles")
def swap_roles(lesson_id: int, user: dict = Depends(teacher_only)):
    l = lesson_for(user, lesson_id)
    if l["status"] != "done" or json.loads(l["result"]).get("speakers", {}).get("speakers") != 2:
        raise HTTPException(400, "В этой записи не выделено два говорящих")
    enqueue(lesson_id, "swap")
    return {"ok": True}


@app.get("/api/lessons/{lesson_id}/audio")
def lesson_audio(lesson_id: int, user: dict = Depends(current_user)):
    lesson_for(user, lesson_id)
    path = DATA / "lessons" / str(lesson_id) / "audio.m4a"
    if not path.exists():
        raise HTTPException(404, "Аудио не найдено")
    return FileResponse(path, media_type="audio/mp4")


@app.get("/api/lessons/{lesson_id}/mel.png")
def lesson_mel(lesson_id: int, user: dict = Depends(staff)):
    lesson_for(user, lesson_id)
    path = DATA / "lessons" / str(lesson_id) / "mel.png"
    if not path.exists():
        raise HTTPException(404, "Нет спектрограммы")
    return FileResponse(path, media_type="image/png")


@app.post("/api/assessments/{assessment_id}")
async def review(assessment_id: int, request: Request, user: dict = Depends(teacher_only)):
    """The teacher confirms the system's status or changes it; the final word is the teacher's (FR-8.7)."""
    a = one("SELECT * FROM assessments WHERE id = ?", assessment_id)
    if not a:
        raise HTTPException(404, "Оценка не найдена")
    lesson_for(user, a["lesson_id"])
    b = await request.json()
    if b.get("action") == "change":
        level = int(b.get("level", -1))
        if level not in (0, 50, 100):
            raise HTTPException(400, "Уровень должен быть 0, 50 или 100")
        x("UPDATE assessments SET idx = ?, touched = 1, confirmed = 1, changed = 1, comment = ? WHERE id = ?",
          level, str(b.get("comment", ""))[:500], assessment_id)
    else:
        x("UPDATE assessments SET confirmed = 1 WHERE id = ?", assessment_id)
    return {"ok": True}


# ------------------------------------------------------------------ student cabinet

@app.get("/api/my/home")
def my_home(child: int = 0, user: dict = Depends(current_user)):
    """Home data of the student. A parent sees the same for the chosen child (FR-13.1 - FR-13.3)."""
    children = []
    if user["role"] == "parent":
        children = children_of(user)
        if not children:
            return {"maps": [], "lessons": [], "children": [], "child": None}
        sid = child if child in [c["id"] for c in children] else children[0]["id"]
    elif user["role"] == "student":
        sid = user["id"]
    else:
        raise HTTPException(403, "Только для ученика или родителя")
    subjects = q("SELECT s.*, u.name AS teacher_name FROM enrollments e JOIN subjects s ON s.id = e.subject_id "
                 "JOIN users u ON u.id = s.teacher_id WHERE e.student_id = ?", sid)
    maps = [{"subject": s["name"], "teacher": s["teacher_name"], "topics": knowledge_map(sid, s["id"])} for s in subjects]
    lessons_ = [lesson_card(l) for l in q(LESSON_LIST + " WHERE l.student_id = ? ORDER BY l.date DESC, l.id DESC", sid)]
    name = one("SELECT name FROM users WHERE id = ?", sid)["name"]
    return {"maps": maps, "lessons": lessons_, "children": children, "child": {"id": sid, "name": name},
            "trend": trend(sid), "stuck": stuck_topics(sid)}


# ------------------------------------------------------------------ Whisper check: the original and the fine-tuned model side by side

WHISPER_PROJECT = ROOT.parent / "whisper-finetune"          # where the fine-tuning was done (data, results, weights)


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def wer(reference: str, hypothesis: str):
    """Word error rate: word edit distance divided by the number of reference words (None without a reference)."""
    r, h = _words(reference), _words(hypothesis)
    if not r:
        return None
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i]
        for j, hw in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw)))
        prev = cur
    return round(prev[-1] / len(r), 3)


def _test_examples() -> list[dict]:
    """Utterances of the FLEURS test subset: the fine-tuning never saw them, and they come with the correct text."""
    f = WHISPER_PROJECT / "data" / "processed" / "test.csv"
    if not f.exists():
        return []
    import csv
    with f.open(encoding="utf-8") as fh:
        return [{"id": Path(r["path"]).stem, "path": str(WHISPER_PROJECT / "data" / "raw" / "audio" / "test" / Path(r["path"]).name), "text": r["text"], "seconds": round(float(r["seconds"]), 1)}
                for r in csv.DictReader(fh)]       # the id is the file name: the FLEURS id repeats for different speakers; the folder may have been moved


@app.get("/api/whisper/examples")
def whisper_examples(user: dict = Depends(staff)):
    """Test utterances with the saved result of the evaluation: where fine-tuning helped most and where it hurt most."""
    import csv
    ex = _test_examples()
    from datera import asr
    out = {"better": [], "worse": [], "model_ready": FINETUNED_READY(), "models": asr.MODELS}
    zf, ff = (WHISPER_PROJECT / "results" / "predictions" / f"{m}__test.csv" for m in ("whisper_base_zero_shot", "whisper_base_finetuned"))
    if ex and zf.exists() and ff.exists():
        with zf.open(encoding="utf-8") as a, ff.open(encoding="utf-8") as b:
            rows = []
            for e, x, y in zip(ex, csv.DictReader(a), csv.DictReader(b)):         # both files list the test utterances in the same order
                if e["text"] == x["text"] == y["text"] and e["seconds"] <= 14:
                    n = max(float(x["ref_words"]), 1)
                    rows.append({"id": e["id"], "text": e["text"], "seconds": e["seconds"], "before": round(int(x["word_errors"]) / n, 3), "after": round(int(y["word_errors"]) / n, 3)})
        rows.sort(key=lambda r: r["before"] - r["after"], reverse=True)
        out["better"], out["worse"] = rows[:8], rows[::-1][:3]
    elif ex:
        out["better"] = [{"id": e["id"], "text": e["text"], "seconds": e["seconds"], "before": None, "after": None} for e in ex if e["seconds"] <= 9][:8]
    return out


def FINETUNED_READY() -> bool:
    from datera import asr
    return asr.FINETUNED_PATH.exists()


@app.post("/api/whisper/compare")
def whisper_compare(file: UploadFile | None = File(None), example_id: str = Form(""), reference: str = Form(""), user: dict = Depends(staff)):
    """Transcribes one recording with the original Whisper-base and with the one fine-tuned by the team, and scores both when the correct text is known."""
    import time

    from datera import asr, audio
    if not FINETUNED_READY():
        raise HTTPException(503, "Файл дообученной модели не найден: whisper-finetune/models/whisper-base-ru.pt (его создаёт шаг 08_export_openai.py).")
    temp = []
    if example_id:
        ex = next((e for e in _test_examples() if e["id"] == example_id), None)
        if not ex:
            raise HTTPException(404, "Такого примера нет")
        src, reference = Path(ex["path"]), ex["text"]
    elif file is not None:
        src = save_upload(file, "uploads", (".wav", ".mp3", ".m4a", ".mp4", ".mov", ".webm", ".flac", ".ogg", ".mkv"))
        temp.append(src)
    else:
        raise HTTPException(400, "Выберите пример или загрузите запись")
    wav = DATA / "work" / f"compare_{secrets.token_hex(6)}.wav"
    temp.append(wav)
    try:
        audio.prepare_audio(src, wav)
        seconds = audio.duration_seconds(wav)
        if seconds > 180:
            raise HTTPException(400, "Для проверки нужна запись не длиннее 3 минут")
        out = []
        with models_lock:
            for name, label in (("base", "Whisper-base, обычный"), (asr.FINETUNED, "Whisper-base, дообученный вами")):
                t0 = time.time()
                text = asr.transcribe(asr.load_model(name), str(wav), "ru")["text"].strip()
                out.append({"model": name, "label": label, "text": text, "seconds": round(time.time() - t0, 1), "wer": wer(reference, text)})
    finally:
        for t in temp:
            if t != src or file is not None:
                t.unlink(missing_ok=True)
    return {"duration": round(seconds, 1), "reference": reference.strip(), "results": out}


_PAIR_TYPES = (".wav", ".mp3", ".m4a", ".mp4", ".mov", ".webm", ".flac", ".ogg", ".mkv")


@app.post("/api/whisper/pair")
def whisper_pair(file_a: UploadFile | None = File(None), file_b: UploadFile | None = File(None), model_a: str = Form("base"), model_b: str = Form("base-ru-finetuned"),
                 reference_a: str = Form(""), reference_b: str = Form(""), same_audio: str = Form(""), language: str = Form("ru"), split_roles: str = Form(""), user: dict = Depends(staff)):
    """Two recordings, each with its own Whisper model, recognised one after the other so that the results can be compared on one page.
    With `same_audio` the second slot uses the recording of the first one: the same sound through two different models."""
    import time

    from datera import asr, audio
    for m in (model_a, model_b):
        if m not in asr.MODELS:
            raise HTTPException(400, "Неизвестная модель Whisper")
        if m == asr.FINETUNED and not FINETUNED_READY():
            raise HTTPException(503, "Файл дообученной модели не найден: whisper-finetune/models/whisper-base-ru.pt")
    if file_a is None:
        raise HTTPException(400, "Загрузите первую запись")
    if not same_audio and file_b is None:
        raise HTTPException(400, "Загрузите вторую запись или отметьте «та же запись»")
    lang = None if language == "auto" else language
    temp: list[Path] = []
    try:
        def prepare(file):
            src = save_upload(file, "uploads", _PAIR_TYPES)
            temp.append(src)
            wav = DATA / "work" / f"pair_{secrets.token_hex(6)}.wav"
            temp.append(wav)
            audio.prepare_audio(src, wav)
            seconds = audio.duration_seconds(wav)
            if seconds > 180:
                raise HTTPException(400, "Для проверки нужна запись не длиннее 3 минут")
            return wav, round(seconds, 1)
        wav_a, sec_a = prepare(file_a)
        wav_b, sec_b = (wav_a, sec_a) if same_audio else prepare(file_b)
        out = []
        with models_lock:
            for slot, wav, sec, model, ref in (("A", wav_a, sec_a, model_a, reference_a), ("B", wav_b, sec_b, model_b, reference_b or (reference_a if same_audio else ""))):
                t0 = time.time()
                loaded = asr.load_model(model)
                t1 = time.time()
                tr = asr.transcribe(loaded, str(wav), lang)
                text = tr["text"].strip()
                done = time.time()
                turns, speakers = None, 1
                if split_roles and tr["segments"]:            # who asks and who answers: voice prints (WavLM), the one who asks more is the teacher
                    from datera import diarize
                    from datera.dialogue import dialogue
                    speakers = diarize.assign_speakers(str(wav), tr["segments"])["speakers"]
                    if speakers == 2:
                        turns = [{"speaker": t["speaker"], "start": round(t["start"], 1), "text": t["text"]} for t in dialogue(asr.merge_sentences(tr["segments"]))[0]]
                out.append({"slot": slot, "model": model, "duration": sec, "text": text, "load_seconds": round(t1 - t0, 1), "seconds": round(done - t1, 1),
                            "reference": ref.strip(), "wer": wer(ref, text), "turns": turns, "speakers": speakers})
    finally:
        for t in temp:
            t.unlink(missing_ok=True)
    return {"same_audio": bool(same_audio), "results": out}


# ------------------------------------------------------------------ system admin (FR-15.2, FR-15.3)

def masked(key: str) -> str:
    return ("•" * 8 + key[-4:]) if len(key) > 8 else ("•" * len(key))


@app.get("/api/admin/settings")
def admin_settings(user: dict = Depends(admin_only)):
    from datera import asr, llm, llm_analysis

    cfg = settings()
    key = cfg.pop("llm_api_key")
    return {"settings": cfg, "key_set": bool(llm.api_key({"llm_api_key": key})), "key_hint": masked(key),
            "whisper_models": asr.MODELS, "presets": llm.PRESETS, "prompt_version": llm_analysis.PROMPT_VERSION}


@app.post("/api/admin/settings")
async def save_settings(request: Request, user: dict = Depends(admin_only)):
    from datera import asr

    b = await request.json()
    allowed = {k: str(v).strip() for k, v in b.items() if k in DEFAULTS and v is not None}
    if "llm_api_key" in allowed and not allowed["llm_api_key"]:
        allowed.pop("llm_api_key")                      # an empty field keeps the saved key
    if b.get("clear_key"):
        allowed["llm_api_key"] = ""
    if allowed.get("whisper_model", "small") not in asr.MODELS:
        raise HTTPException(400, "Неизвестная модель Whisper")
    if allowed.get("analysis_mode", "llm") not in ("embeddings", "llm"):
        raise HTTPException(400, "Неизвестный способ анализа")
    for name, lo, hi in (("threshold", 0.3, 0.95), ("pause_seconds", 1, 60), ("llm_temperature", 0, 1.5)):
        if name in allowed:
            try:
                if not lo <= float(allowed[name]) <= hi:
                    raise ValueError
            except ValueError:
                raise HTTPException(400, f"Значение {name} должно быть числом от {lo} до {hi}")
    for k, v in allowed.items():
        x("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", k, v)
    return {"ok": True}


def draft_cfg(body: dict) -> dict:
    """Settings as typed in the form, with the saved key when the key field was left empty."""
    cfg = settings()
    cfg.update({k: str(v).strip() for k, v in body.items() if k in DEFAULTS and v not in (None, "")})
    return cfg


@app.post("/api/admin/test-llm")
async def test_llm(request: Request, user: dict = Depends(admin_only)):
    import time

    from datera import llm

    cfg = draft_cfg(await request.json())
    t0 = time.time()
    try:
        answer = llm.chat(cfg, "Ты проверка связи. Отвечай одним словом.", "Ответь словом: готово", json_mode=False, timeout=60)
    except llm.LLMError as e:
        msg = str(e)
        if e.code == 404 and "model" in msg.lower():          # wrong model name: show what the account can actually use
            try:
                msg += " Доступные вам модели: " + ", ".join(llm.list_models(cfg)[:12]) + "."
            except llm.LLMError:
                pass
        raise HTTPException(400, msg)
    return {"ok": True, "answer": answer.strip()[:120], "seconds": round(time.time() - t0, 1), "model": cfg["llm_model"]}


@app.post("/api/admin/models")
async def admin_models(request: Request, user: dict = Depends(admin_only)):
    from datera import llm

    try:
        return {"models": llm.list_models(draft_cfg(await request.json()))[:300]}
    except llm.LLMError as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/queue")
def admin_queue(user: dict = Depends(admin_only)):
    out = []
    for l in q(LESSON_LIST + " ORDER BY l.id DESC"):
        res = json.loads(l["result"]) if l.get("result") else {}
        out.append({**lesson_card(l), "engine": res.get("engine", "embeddings") if res else None,
                    "llm_model": (res.get("llm") or {}).get("model"), "llm_error": res.get("llm_error"),
                    "whisper": (res.get("whisper") or {}).get("name"), "timings": res.get("timings"),
                    "speakers": (res.get("speakers") or {}).get("speakers")})
    return {"lessons": out, "waiting": jobs.qsize()}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
