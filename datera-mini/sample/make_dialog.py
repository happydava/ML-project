"""Builds sample/dialog.m4a: a teacher-student dialogue on the topics of sample/slides.pptx.
macOS has one Russian voice, so the student's lines are the same voice shifted down in pitch."""
import subprocess
import tempfile
from pathlib import Path

here = Path(__file__).parent
lines = [  # (speaker, pause before the line in seconds, text)
    ("T", 0.3, "Здравствуй. Сегодня повторяем нейронные сети. Расскажи, из чего состоит нейронная сеть?"),
    ("S", 0.8, "Нейронная сеть состоит из слоёв, а в каждом слое находятся искусственные нейроны."),
    ("T", 0.6, "Хорошо. А что делает один нейрон?"),
    ("S", 0.9, "Каждый нейрон считает взвешенную сумму своих входов и применяет функцию активации."),
    ("T", 0.6, "Верно. Чем сеть отличается от обычной программы?"),
    ("S", 1.0, "Сеть учится на примерах, а правила вручную ей никто не задаёт."),
    ("T", 0.6, "Отлично. Теперь про обучение. Зачем нужна функция потерь?"),
    ("S", 1.2, "Функция потерь показывает, насколько сильно модель ошибается."),
    ("T", 0.6, "А как сеть уменьшает эту ошибку? Что такое градиентный спуск?"),
    ("S", 6.5, "Я не помню. Кажется, это как-то связано со скоростью компьютера."),
    ("T", 0.6, "Не совсем. Мы вернёмся к этому на следующем уроке. Что такое переобучение?"),
    ("S", 1.0, "Это когда модель запоминает обучающие данные и плохо работает на новых данных."),
    ("T", 0.6, "Правильно. Какие способы борьбы с переобучением ты знаешь?"),
    ("S", 1.5, "Можно использовать дропаут, он случайно отключает часть нейронов во время обучения."),
    ("T", 0.6, "Молодец. На сегодня всё, до встречи."),
]
tmp = Path(tempfile.mkdtemp())
parts = []
for i, (who, pause, text) in enumerate(lines):
    raw, out = tmp / f"{i}.aiff", tmp / f"{i}.wav"
    subprocess.run(["say", "-v", "Milena", "-o", str(raw), text], check=True)
    voice = "asetrate=22050*0.78,aresample=16000,atempo=1.22" if who == "S" else "aresample=16000"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
                    f"{voice},adelay={int(pause * 1000)}:all=1", "-ac", "1", str(out)], check=True)
    parts.append(out)
(tmp / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                str(here / "dialog.m4a")], check=True)
print("ok")
