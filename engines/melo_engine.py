import time
from pathlib import Path

import numpy as np
import soundfile as sf

# MeloTTS lang code → (melo language, speaker id)
LANG_MAP = {
    "ko": ("KR", "KR"),
    "en": ("EN", "EN-Default"),
    "en-us": ("EN", "EN-US"),
    "en-gb": ("EN", "EN-BR"),
    "zh": ("ZH", "ZH"),
    "ja": ("JP", "JP"),
    "es": ("ES", "ES"),
    "fr": ("FR", "FR"),
}

SUPPORTED_LANGS = set(LANG_MAP.keys())


class MeloEngine:
    def __init__(self, device: str = "auto"):
        import torch
        if device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = device

        # 모델은 언어별로 lazy load
        self._models: dict = {}

    def _load_model(self, melo_lang: str):
        if melo_lang not in self._models:
            from melo.api import TTS
            print(f"  [{melo_lang}] MeloTTS 모델 로딩 중...")
            model = TTS(language=melo_lang, device=self._device)
            self._models[melo_lang] = model
        return self._models[melo_lang]

    def supports(self, lang: str) -> bool:
        return lang.lower() in LANG_MAP

    def generate(
        self,
        text: str,
        lang: str = "ko",
        speed: float = 1.0,
    ) -> tuple[np.ndarray, int]:
        lang = lang.lower()
        if lang not in LANG_MAP:
            raise ValueError(f"MeloTTS 미지원 언어: {lang}. 지원: {sorted(LANG_MAP)}")

        melo_lang, speaker_id = LANG_MAP[lang]
        model = self._load_model(melo_lang)
        speaker_ids = model.hps.data.spk2id
        sid = speaker_ids[speaker_id]

        audio = model.tts_to_file(text, sid, None, speed=speed, quiet=True)
        sr = model.hps.data.sampling_rate
        return np.array(audio), sr

    def generate_to_file(
        self,
        text: str,
        output_path: str,
        lang: str = "ko",
        speed: float = 1.0,
        verbose: bool = True,
    ) -> float:
        t0 = time.time()
        samples, sr = self.generate(text, lang=lang, speed=speed)
        elapsed = time.time() - t0

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, samples, sr)

        if verbose:
            audio_dur = len(samples) / sr
            rtf = audio_dur / elapsed
            print(
                f"  생성: {elapsed:.1f}s | 음성: {audio_dur:.1f}s | RTF: {rtf:.2f}x | {output_path}"
            )
        return elapsed
