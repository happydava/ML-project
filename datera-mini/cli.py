"""Command line: python cli.py lesson.mp4 slides.pptx --model small"""
import argparse
from pathlib import Path

from datera import asr, pipeline, report


def main():
    ap = argparse.ArgumentParser(description="DATERA EDU mini: запись + презентация -> отчёт")
    ap.add_argument("media", help="аудио или видео (mp3, wav, m4a, mp4, mov, ...)")
    ap.add_argument("material", help="презентация или материал (.pptx, .pdf, .txt, .md)")
    ap.add_argument("--model", default="small", choices=asr.MODELS, help="размер модели Whisper")
    ap.add_argument("--language", default=None, help="язык речи (ru, en); по умолчанию определяется сам")
    ap.add_argument("--threshold", type=float, default=0.65, help="порог сходства для 'пункт раскрыт'")
    ap.add_argument("--out", default="out", help="папка для отчёта")
    args = ap.parse_args()

    result = pipeline.run(args.media, args.material, args.model, args.language, args.threshold, on_stage=print)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(args.media).stem
    (out / f"{stem}_report.html").write_text(report.to_html(result), encoding="utf-8")
    (out / f"{stem}_report.json").write_text(report.to_json(result), encoding="utf-8")

    print("\n" + report.summary_text(result) + "\n")
    for t in result["analysis"]["topics"]:
        print(f"  слайд {t['slide']:>2}  {t['index']:>3} %  {t['status']:<18} {t['title'][:60]}")
    print(f"\nВремя по этапам, с: {result['timings']}")
    print(f"Отчёт: {out / f'{stem}_report.html'}")


if __name__ == "__main__":
    main()
