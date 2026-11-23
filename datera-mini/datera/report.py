"""Stage 5. Report (FR-9.3, simplified): summary, topics with index and status, time codes, transcript."""
from __future__ import annotations

import json
from html import escape

COLORS = {"green": "#1f9d55", "yellow": "#d69e2e", "red": "#e02424"}


def tc(seconds: float) -> str:
    seconds = int(seconds)
    h, m, s = seconds // 3600, seconds % 3600 // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def summary_text(r: dict) -> str:
    a = r["analysis"]
    topics = a["topics"]
    green = [t for t in topics if t["color"] == "green"]
    yellow = [t for t in topics if t["color"] == "yellow"]
    red = [t for t in topics if t["color"] == "red"]
    parts = [
        f"Запись длится {tc(r['duration'])}, язык речи: {r['language']}. "
        f"В материале найдено тем: {len(topics)}. Полностью раскрыто: {len(green)}, "
        f"частично: {len(yellow)}, не раскрыто: {len(red)}. "
        f"Общий индекс покрытия материала: {a['overall_index']} %."
    ]
    if red:
        parts.append("Не прозвучали или почти не прозвучали: " + "; ".join(t["title"] for t in red) + ".")
    if yellow:
        parts.append("Стоит дополнить: " + "; ".join(t["title"] for t in yellow) + ".")
    if a["outside_material"]:
        parts.append(f"Фрагментов речи вне материала: {len(a['outside_material'])}.")
    return " ".join(parts)


def to_json(r: dict) -> str:
    data = {k: v for k, v in r.items() if k != "mel"}
    data["summary"] = summary_text(r)
    return json.dumps(data, ensure_ascii=False, indent=2)


def to_html(r: dict) -> str:
    a, w = r["analysis"], r["whisper"]
    rows, details = [], []
    for t in a["topics"]:
        c = COLORS[t["color"]]
        first = tc(t["first_mention"]) if t["first_mention"] is not None else "нет"
        rows.append(
            f"<tr><td>{t['slide']}</td><td>{escape(t['title'])}</td>"
            f"<td><span class='pill' style='background:{c}'>{t['index']} %</span></td>"
            f"<td>{t['status']}</td><td>{t['covered_points']} из {t['total_points']}</td>"
            f"<td>{first}</td><td>{tc(t['seconds'])}</td></tr>"
        )
        items = []
        for p in t["points"]:
            mark = "✓" if p["covered"] else "✗"
            cls = "ok" if p["covered"] else "miss"
            quote = (f"<div class='quote'>[{tc(p['start'])}] {escape(p['quote'])}</div>" if p["covered"]
                     else "<div class='quote muted'>в речи не найдено</div>")
            items.append(f"<li class='{cls}'><b>{mark}</b> {escape(p['text'])} "
                         f"<span class='muted'>(сходство {p['similarity']:.2f})</span>{quote}</li>")
        details.append(f"<h3 style='border-left:6px solid {c};padding-left:10px'>"
                       f"Слайд {t['slide']}. {escape(t['title'])} - {t['index']} %</h3><ul>{''.join(items)}</ul>")

    outside = "".join(f"<li>[{tc(o['start'])} - {tc(o['end'])}] {escape(o['text'])}</li>"
                      for o in a["outside_material"]) or "<li class='muted'>нет</li>"
    transcript = "".join(
        f"<tr><td class='muted'>{tc(s['start'])}</td><td>{escape(s['text'])}</td>"
        f"<td class='muted'>{'слайд ' + str(s['topic_slide']) if s.get('topic_slide') else ''}</td>"
        f"<td class='muted'>{s['confidence']:.2f}</td></tr>" for s in r["segments"])
    skipped = ", ".join(str(s["slide"]) for s in a["skipped_slides"])
    skipped_note = f"<p class='muted'>Слайды без содержательного текста не оценивались: {skipped}.</p>" if skipped else ""
    oc = COLORS[a["overall_color"]]

    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>DATERA EDU mini - отчёт</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:980px;margin:32px auto;padding:0 16px;color:#1a202c;line-height:1.5}}
table{{border-collapse:collapse;width:100%;margin:12px 0}} th,td{{border-bottom:1px solid #e2e8f0;padding:8px;text-align:left;vertical-align:top}}
th{{background:#f7fafc}} .pill{{color:#fff;border-radius:12px;padding:2px 10px;font-weight:600;white-space:nowrap}}
.muted{{color:#718096;font-size:.9em}} .quote{{margin:4px 0 8px 22px;font-size:.92em;color:#4a5568}}
ul{{list-style:none;padding-left:8px}} li.ok b{{color:#1f9d55}} li.miss b{{color:#e02424}}
.big{{font-size:2.4em;font-weight:700;color:{oc}}} .card{{background:#f7fafc;border-radius:10px;padding:16px;margin:16px 0}}
</style></head><body>
<h1>Отчёт по записи</h1>
<p class="muted">Запись: {escape(r['media_name'])} · Материал: {escape(r['material_name'])}</p>
<div class="card"><div class="big">{a['overall_index']} %</div>
<div><b>{a['overall_status']}</b> - общий индекс покрытия материала</div><p>{escape(summary_text(r))}</p>
<p class="muted">Доля речи по темам материала: {a['on_topic_share']} %.</p></div>
<h2>Карта тем</h2>
<table><tr><th>Слайд</th><th>Тема</th><th>Индекс</th><th>Статус</th><th>Ключевые пункты</th><th>Первое упоминание</th><th>Время на тему</th></tr>
{''.join(rows)}</table>{skipped_note}
<p class="muted">Красный: ниже 50 %. Жёлтый: 50-79 %. Зелёный: 80 % и выше.</p>
<h2>Разбор по темам</h2>{''.join(details)}
<h2>Вне материала</h2><ul>{outside}</ul>
<h2>Транскрипт</h2>
<table><tr><th>Время</th><th>Текст</th><th>Тема</th><th>Уверенность</th></tr>{transcript}</table>
<h2>Модели</h2>
<p class="muted">Распознавание речи: OpenAI Whisper {escape(w['name'])}, {w['parameters'] / 1e6:.0f} млн параметров,
энкодер {w['encoder_layers']} слоёв, декодер {w['decoder_layers']} слоёв, устройство {escape(w['device'])}.<br>
Сопоставление с темами: {escape(a['embedding_model'])}, порог сходства {a['threshold']}.<br>
Время по этапам, с: {escape(json.dumps(r['timings'], ensure_ascii=False))}</p>
</body></html>"""
