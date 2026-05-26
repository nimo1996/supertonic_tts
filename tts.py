#!/usr/bin/env python3
"""
multilingual-tts  —  상업용 다국어 TTS (CPU 우선)
엔진: Supertonic v3 (MIT) · MeloTTS (MIT) · Kokoro (Apache 2.0)
"""
import argparse
import sys
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

_engines: dict = {}


# ─── config ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def cfg_get(config: dict, *keys, default=None):
    node = config
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
        if node is default:
            return default
    return node


# ─── engine loader ───────────────────────────────────────────────────────────

def get_engine(name: str, config: dict):
    if name not in _engines:
        if name == "supertonic":
            from engines.supertonic_engine import SupertonicEngine
            _engines[name] = SupertonicEngine(
                voice=cfg_get(config, "supertonic", "voice", default="M2"),
                speed=cfg_get(config, "supertonic", "speed", default=1.05),
                steps=cfg_get(config, "supertonic", "steps", default=8),
            )
        elif name == "melo":
            from engines.melo_engine import MeloEngine
            _engines[name] = MeloEngine()
        elif name == "kokoro":
            from engines.kokoro_engine import KokoroEngine
            _engines[name] = KokoroEngine()
        else:
            print(f"[오류] 알 수 없는 엔진: {name}", file=sys.stderr)
            sys.exit(1)
    return _engines[name]


def pick_engine(lang: str, preferred: str, config: dict):
    """선호 엔진이 해당 언어를 지원하면 사용, 아니면 지원 가능한 엔진 탐색."""
    order = [preferred] + [e for e in ("supertonic", "melo", "kokoro") if e != preferred]
    for name in order:
        engine = get_engine(name, config)
        if engine.supports(lang):
            return name, engine
    return None, None


# ─── lang detection ──────────────────────────────────────────────────────────

FILENAME_LANG = {
    "korean": "ko", "english": "en", "chinese": "zh", "japanese": "ja",
    "vietnamese": "vi", "russian": "ru", "thai": "th", "indonesian": "id",
    "tagalog": "tl", "uzbek": "uz", "mongolian": "mn",
    "french": "fr", "spanish": "es", "italian": "it",
    "portuguese": "pt", "hindi": "hi", "arabic": "ar", "german": "de",
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
        out_dir = Path(cfg_get(config, "output", "directory", default="output"))
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{input_name}_{lang}.wav"

    # 엔진 선택
    preferred = args.engine or cfg_get(config, "engine", default="supertonic")
    engine_name, engine = pick_engine(lang, preferred, config)
    if engine is None:
        print(f"[오류] 언어 '{lang}'를 지원하는 엔진이 없습니다.", file=sys.stderr)
        sys.exit(1)

    print(f"[TTS] 언어={lang} | 엔진={engine_name} | 출력={out_path}")

    # 엔진별 추가 옵션
    kwargs = {}
    if engine_name == "supertonic":
        if args.voice:
            kwargs["voice"] = args.voice
        if args.speed:
            kwargs["speed"] = args.speed
        if args.steps:
            kwargs["steps"] = args.steps
    elif engine_name in ("melo", "kokoro"):
        if args.voice:
            kwargs["voice"] = args.voice
        if args.speed:
            kwargs["speed"] = args.speed

    engine.generate_to_file(text=text, output_path=str(out_path), lang=lang, **kwargs)


def cmd_voices(args, config: dict):
    engine_name = args.engine or cfg_get(config, "engine", default="supertonic")
    engine = get_engine(engine_name, config)
    print(f"[{engine_name}] 사용 가능한 목소리:")
    for v in engine.get_voices():
        marker = " ← 현재 기본값" if v == cfg_get(config, engine_name, "voice") else ""
        print(f"  {v}{marker}")


def cmd_config(args, config: dict):
    print(f"설정 파일: {CONFIG_PATH}")
    print()
    import yaml
    print(yaml.dump(config, allow_unicode=True, default_flow_style=False))


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    config = load_config()

    parser = argparse.ArgumentParser(
        description="multilingual-tts: 상업용 다국어 TTS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python tts.py --input scripts/korean.txt
  python tts.py --text "안녕하세요" --lang ko
  python tts.py --text "Hello" --lang en --voice F3
  python tts.py --voices
  python tts.py --config
        """,
    )

    parser.add_argument("--input",  "-i", help="입력 텍스트 파일")
    parser.add_argument("--text",   "-t", help="직접 입력 텍스트")
    parser.add_argument("--lang",   "-l", help="언어 코드 (ko/en/ja/zh/...)")
    parser.add_argument("--output", "-o", help="출력 WAV 파일 경로")
    parser.add_argument("--engine", "-e", help="엔진 지정 (supertonic/melo/kokoro)")
    parser.add_argument("--voice",  "-v", help="목소리 (예: M2, F1, af_heart)")
    parser.add_argument("--speed",  "-s", type=float, help="발화 속도 (기본: config 값)")
    parser.add_argument("--steps",        type=int,   help="[supertonic] 생성 품질 단계 (기본: 8)")
    parser.add_argument("--voices",       action="store_true", help="목소리 목록 출력")
    parser.add_argument("--config",       action="store_true", help="현재 설정 출력")

    args = parser.parse_args()

    if args.voices:
        cmd_voices(args, config)
    elif args.config:
        cmd_config(args, config)
    else:
        cmd_run(args, config)


if __name__ == "__main__":
    main()
