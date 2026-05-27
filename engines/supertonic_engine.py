import time
from pathlib import Path

import numpy as np

VOICES = ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]


class SupertonicEngine:
    # Supertonic v3 공식 지원 언어
    SUPPORTED_LANGS = {
        "ko", "en", "ja", "ar", "bg", "cs", "da", "de", "el", "es",
        "et", "fi", "fr", "hi", "hr", "hu", "id", "it", "lt", "lv",
        "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "tr", "uk", "vi",
    }
    def __init__(self, voice: str = "M2", speed: float = 1.05, steps: int = 8):
        from supertonic import TTS
        self._tts = TTS(auto_download=True)
        self.voice = voice
        self.speed = speed
        self.steps = steps

    def supports(self, lang: str) -> bool:
        return lang.lower() in self.SUPPORTED_LANGS

    def generate(
        self,
        text: str,
        lang: str = "ko",
        voice: str | None = None,
        speed: float | None = None,
        steps: int | None = None,
    ) -> tuple[np.ndarray, int]:
        v = (voice or self.voice).upper()
        if v not in VOICES:
            raise ValueError(f"잘못된 목소리: {v}. 선택 가능: {VOICES}")

        style = self._tts.get_voice_style(v)
        wav, _ = self._tts.synthesize(
            text=text,
            voice_style=style,
            lang=lang.lower(),
            speed=speed or self.speed,
            total_steps=steps or self.steps,
        )
        # shape: (1, samples) → (samples,)
        return wav.squeeze(0), self._tts.sample_rate

    def generate_to_file(
        self,
        text: str,
        output_path: str,
        lang: str = "ko",
        voice: str | None = None,
        speed: float | None = None,
        steps: int | None = None,
        verbose: bool = True,
    ) -> float:
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            lines = [text]

        t0 = time.time()
        sr = self._tts.sample_rate
        silence = np.zeros(int(sr * 0.4))  # 줄 사이 0.4초 묵음

        tail_silence = np.zeros(int(sr * 0.15))  # 각 줄 끝 클리핑 방지 패딩

        chunks = []
        for i, line in enumerate(lines):
            if verbose and len(lines) > 1:
                print(f"  [{i+1}/{len(lines)}] {line[:40]}{'...' if len(line) > 40 else ''}")
            # 문장 종결 부호 없으면 마침표 추가 (모델이 끝을 인식하도록)
            send = line if line[-1] in ".。!！?？,，" else line + "."
            wav, _ = self.generate(send, lang=lang, voice=voice, speed=speed, steps=steps)
            chunks.append(wav)
            chunks.append(tail_silence)
            if i < len(lines) - 1:
                chunks.append(silence)

        full_wav = np.concatenate(chunks)
        elapsed = time.time() - t0

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self._tts.save_audio(full_wav[np.newaxis, :], output_path)

        if verbose:
            audio_dur = len(full_wav) / sr
            print(f"  생성: {elapsed:.1f}s | 음성: {audio_dur:.1f}s | RTF: {audio_dur/elapsed:.2f}x | {output_path}")
        return elapsed

    def get_voices(self) -> list[str]:
        return VOICES
