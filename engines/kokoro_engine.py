import os
import time
from pathlib import Path

import numpy as np
import soundfile as sf

DEFAULT_MODEL = Path(__file__).parent.parent / "models/kokoro/kokoro-v1.0.int8.onnx"
DEFAULT_VOICES = Path(__file__).parent.parent / "models/kokoro/voices-v1.0.bin"

# lang code → (kokoro lang tag, default voice)
LANG_MAP = {
    "ko": ("ko", "af_heart"),
    "en": ("en-us", "af_heart"),
    "en-us": ("en-us", "af_heart"),
    "en-gb": ("en-gb", "bf_emma"),
    "ja": ("ja", "jf_alpha"),
    "zh": ("cmn", "zf_xiaoxiao"),
    "fr": ("fr-fr", "ff_siwis"),
    "es": ("es", "ef_dora"),
    "it": ("it", "if_sara"),
    "pt": ("pt-br", "pf_dora"),
    "pt-br": ("pt-br", "pf_dora"),
    "hi": ("hi", "hf_alpha"),
}

SUPPORTED_LANGS = set(LANG_MAP.keys())


class KokoroEngine:
    def __init__(self, model_path=None, voices_path=None):
        from kokoro_onnx import Kokoro

        model_path = model_path or DEFAULT_MODEL
        voices_path = voices_path or DEFAULT_VOICES

        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"Kokoro 모델 파일 없음: {model_path}\n"
                "setup.sh 를 실행하거나 models/kokoro/ 에 모델을 다운로드하세요."
            )
        if not Path(voices_path).exists():
            raise FileNotFoundError(
                f"Kokoro 보이스 파일 없음: {voices_path}\n"
                "setup.sh 를 실행하거나 models/kokoro/ 에 파일을 다운로드하세요."
            )

        self._kokoro = Kokoro(str(model_path), str(voices_path))

    def supports(self, lang: str) -> bool:
        return lang.lower() in LANG_MAP

    def generate(
        self,
        text: str,
        lang: str = "ko",
        voice: str | None = None,
        speed: float = 1.0,
    ) -> tuple[np.ndarray, int]:
        lang = lang.lower()
        if lang not in LANG_MAP:
            raise ValueError(f"Kokoro 미지원 언어: {lang}. 지원: {sorted(LANG_MAP)}")

        kokoro_lang, default_voice = LANG_MAP[lang]
        voice = voice or default_voice

        samples, sr = self._kokoro.create(
            text, voice=voice, lang=kokoro_lang, speed=speed
        )
        return samples, sr

    def generate_to_file(
        self,
        text: str,
        output_path: str,
        lang: str = "ko",
        voice: str | None = None,
        speed: float = 1.0,
        verbose: bool = True,
    ) -> float:
        t0 = time.time()
        samples, sr = self.generate(text, lang=lang, voice=voice, speed=speed)
        elapsed = time.time() - t0

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, samples, sr)

        audio_dur = len(samples) / sr
        if verbose:
            rtf = audio_dur / elapsed
            print(
                f"  생성: {elapsed:.1f}s | 음성: {audio_dur:.1f}s | RTF: {rtf:.2f}x | {output_path}"
            )
        return elapsed

    def get_voices(self) -> list[str]:
        return self._kokoro.get_voices()
