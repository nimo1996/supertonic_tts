#!/usr/bin/env python3
"""
multilingual-tts  —  상업용 다국어 TTS
엔진: Supertonic v3 (MIT / OpenRAIL-M)
"""
import argparse
import sys
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

_engine = None


# ─── config ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def cfg(config: dict, *keys, default=None):
    node = config
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
        if node is default:
            return default
    return node


# ─── engine ──────────────────────────────────────────────────────────────────

def get_engine(config: dict):
    global _engine
    if _engine is None:
        from engines.supertonic_engine import SupertonicEngine
        _engine = SupertonicEngine(
            voice=cfg(config, "supertonic", "voice", default="M2"),
            speed=cfg(config, "supertonic", "speed", default=1.05),
            steps=cfg(config, "supertonic", "steps", default=8),
        )
    return _engine


# ─── lang detection ──────────────────────────────────────────────────────────

FILENAME_LANG = {
    "korean": "ko",     "english": "en",    "chinese": "zh",
    "japanese": "ja",   "vietnamese": "vi", "russian": "ru",
    "thai": "th",       "indonesian": "id", "tagalog": "tl",
    "uzbek": "uz",      "mongolian": "mn",  "french": "fr",
    "spanish": "es",    "italian": "it",    "portuguese": "pt",
    "hindi": "hi",      "arabic": "ar",     "german": "de",
}


def detect_lang(path: Path) -> str | None:
    return FILENAME_LANG.get(path.stem.lower())


# ─── commands ────────────────────────────────────────────────────────────────

def cmd_run(args, config: dict):
    # 입력 텍스트
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

    # 언어
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
        out_dir = Path(cfg(config, "output", "directory", default="output"))
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{input_name}_{lang}.wav"

    engine = get_engine(config)

    if not engine.supports(lang):
        print(f"[오류] 지원하지 않는 언어: {lang}", file=sys.stderr)
        print(f"  지원 언어: {', '.join(sorted(engine.SUPPORTED_LANGS))}", file=sys.stderr)
        sys.exit(1)

    print(f"[TTS] 언어={lang} | 목소리={args.voice or cfg(config, 'supertonic', 'voice', default='M2')} | 출력={out_path}")

    engine.generate_to_file(
        text=text,
        output_path=str(out_path),
        lang=lang,
        voice=args.voice or None,
        speed=args.speed or None,
        steps=args.steps or None,
    )


def cmd_voices(args, config: dict):
    engine = get_engine(config)
    default_voice = cfg(config, "supertonic", "voice", default="M2")
    print("사용 가능한 목소리 (F=여성, M=남성):")
    for v in engine.get_voices():
        marker = " ← 기본값" if v == default_voice else ""
        print(f"  {v}{marker}")


def cmd_langs(args, config: dict):
    engine = get_engine(config)
    print("지원 언어:")
    for lang in sorted(engine.SUPPORTED_LANGS):
        print(f"  {lang}")


def cmd_config(args, config: dict):
    print(f"설정 파일: {CONFIG_PATH}\n")
    print(yaml.dump(config, allow_unicode=True, default_flow_style=False))


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    config = load_config()

    parser = argparse.ArgumentParser(
        description="multilingual-tts: 상업용 다국어 TTS (Supertonic v3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python tts.py --input scripts/korean.txt
  python tts.py --text "안녕하세요" --lang ko
  python tts.py --text "Hello world" --lang en --voice F3
  python tts.py --voices
  python tts.py --langs
  python tts.py --config
        """,
    )
    parser.add_argument("--input",  "-i", help="입력 텍스트 파일")
    parser.add_argument("--text",   "-t", help="직접 입력 텍스트")
    parser.add_argument("--lang",   "-l", help="언어 코드 (ko/en/ja/...)")
    parser.add_argument("--output", "-o", help="출력 WAV 파일 경로")
    parser.add_argument("--voice",  "-v", help="목소리 (F1~F5 / M1~M5)")
    parser.add_argument("--speed",  "-s", type=float, help="발화 속도 (기본: 1.05)")
    parser.add_argument("--steps",        type=int,   help="품질 단계 (기본: 8, 높을수록 느리고 좋음)")
    parser.add_argument("--voices",       action="store_true", help="목소리 목록")
    parser.add_argument("--langs",        action="store_true", help="지원 언어 목록")
    parser.add_argument("--config",       action="store_true", help="현재 설정 출력")

    args = parser.parse_args()

    if args.voices:
        cmd_voices(args, config)
    elif args.langs:
        cmd_langs(args, config)
    elif args.config:
        cmd_config(args, config)
    else:
        cmd_run(args, config)


if __name__ == "__main__":
    main()
