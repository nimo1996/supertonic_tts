#!/usr/bin/env python3
"""
multilingual-tts  —  상업용 다국어 TTS (CPU 우선)
엔진: Kokoro TTS (Apache 2.0)
"""
import argparse
import sys
import time
from pathlib import Path

ENGINES = {
    "kokoro": None,  # lazy load
}

LANG_ENGINE = {
    "ko": "kokoro",
    "en": "kokoro",
    "en-us": "kokoro",
    "en-gb": "kokoro",
    "ja": "kokoro",
    "zh": "kokoro",
    "fr": "kokoro",
    "es": "kokoro",
    "it": "kokoro",
    "pt": "kokoro",
    "pt-br": "kokoro",
    "hi": "kokoro",
}


def get_engine(name: str):
    if ENGINES[name] is None:
        if name == "kokoro":
            from engines.kokoro_engine import KokoroEngine
            ENGINES[name] = KokoroEngine()
    return ENGINES[name]


def detect_lang(path: Path) -> str | None:
    stem = path.stem.lower()
    mapping = {
        "korean": "ko",
        "english": "en",
        "chinese": "zh",
        "japanese": "ja",
        "vietnamese": "vi",
        "russian": "ru",
        "thai": "th",
        "indonesian": "id",
        "tagalog": "tl",
        "uzbek": "uz",
        "mongolian": "mn",
        "french": "fr",
        "spanish": "es",
        "italian": "it",
        "portuguese": "pt",
        "hindi": "hi",
    }
    return mapping.get(stem)


def run(args):
    # 입력 텍스트 확정
    if args.text:
        text = args.text
        input_name = "text"
    elif args.input:
        p = Path(args.input)
        if not p.exists():
            print(f"[오류] 파일 없음: {args.input}", file=sys.stderr)
            sys.exit(1)
        text = p.read_text(encoding="utf-8").strip()
        input_name = p.stem
    else:
        print("[오류] --text 또는 --input 을 지정하세요.", file=sys.stderr)
        sys.exit(1)

    # 언어 결정
    lang = args.lang
    if not lang and args.input:
        lang = detect_lang(Path(args.input))
    if not lang:
        lang = "ko"

    lang = lang.lower()

    # 출력 경로
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{input_name}_{lang}.wav"

    # 엔진 선택
    if lang not in LANG_ENGINE:
        print(f"[오류] 지원하지 않는 언어: {lang}", file=sys.stderr)
        print(f"  지원 언어: {', '.join(sorted(LANG_ENGINE))}", file=sys.stderr)
        sys.exit(1)

    engine_name = LANG_ENGINE[lang]
    print(f"[TTS] 언어={lang} | 엔진={engine_name} | 출력={out_path}")

    engine = get_engine(engine_name)
    engine.generate_to_file(
        text=text,
        output_path=str(out_path),
        lang=lang,
        voice=args.voice or None,
        speed=args.speed,
        verbose=True,
    )


def list_voices(args):
    engine = get_engine("kokoro")
    print("사용 가능한 목소리:")
    for v in engine.get_voices():
        print(f"  {v}")


def main():
    parser = argparse.ArgumentParser(
        description="multilingual-tts: 상업용 다국어 TTS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python tts.py --input scripts/korean.txt
  python tts.py --text "안녕하세요" --lang ko
  python tts.py --input scripts/english.txt --lang en --voice bf_emma
  python tts.py --voices
        """,
    )
    parser.add_argument("--input", "-i", help="입력 텍스트 파일 경로")
    parser.add_argument("--text", "-t", help="직접 입력 텍스트")
    parser.add_argument("--lang", "-l", help="언어 코드 (ko/en/ja/zh/fr/es/...)")
    parser.add_argument("--output", "-o", help="출력 WAV 파일 경로")
    parser.add_argument("--voice", "-v", help="목소리 이름 (예: af_heart, bf_emma)")
    parser.add_argument("--speed", "-s", type=float, default=1.0, help="발화 속도 (기본: 1.0)")
    parser.add_argument("--voices", action="store_true", help="사용 가능한 목소리 목록 출력")

    args = parser.parse_args()

    if args.voices:
        list_voices(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
