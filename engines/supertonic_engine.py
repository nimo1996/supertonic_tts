import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf

VOICES = ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]

# [PAUSE: 1.5]  /  [BELL: sounds/bell.wav]  /  [SFX: sounds/chime.wav]
_MARKER_RE = re.compile(r'^\[(PAUSE|BELL|SFX)\s*:\s*(.+?)\s*\]$', re.IGNORECASE)


def _load_sfx(path: str, target_sr: int) -> np.ndarray:
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != target_sr:
        new_len = int(len(data) / sr * target_sr)
        data = np.interp(
            np.linspace(0, len(data) - 1, new_len),
            np.arange(len(data)),
            data,
        ).astype(np.float32)
    return data


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
        gap: float = 0.4,
        verbose: bool = True,
    ) -> float:
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            lines = [text]

        t0 = time.time()
        sr = self._tts.sample_rate
        gap_silence = np.zeros(int(sr * gap))
        tail_silence = np.zeros(int(sr * 0.15))

        tts_count = sum(1 for l in lines if not _MARKER_RE.match(l))
        tts_idx = 0

        chunks = []
        for i, line in enumerate(lines):
            m = _MARKER_RE.match(line)
            if m:
                kind, value = m.group(1).upper(), m.group(2)
                if kind == "PAUSE":
                    try:
                        secs = float(value)
                    except ValueError:
                        print(f"  [경고] PAUSE 값 오류: {value!r} — 건너뜀", flush=True)
                        continue
                    if verbose:
                        print(f"  [PAUSE {secs}s]")
                    chunks.append(np.zeros(int(sr * secs), dtype=np.float32))
                else:  # BELL / SFX
                    sfx_path = Path(value)
                    if not sfx_path.is_absolute():
                        sfx_path = Path(output_path).parent.parent / value
                    if not sfx_path.exists():
                        print(f"  [경고] 파일 없음: {sfx_path} — 건너뜀", flush=True)
                        continue
                    if verbose:
                        print(f"  [{kind} {sfx_path.name}]")
                    chunks.append(_load_sfx(str(sfx_path), sr))
            else:
                tts_idx += 1
                if verbose:
                    print(f"  [TTS {tts_idx}/{tts_count}] {line[:40]}{'...' if len(line) > 40 else ''}")
                send = line if line[-1] in ".。!！?？,，" else line + "."
                wav, _ = self.generate(send, lang=lang, voice=voice, speed=speed, steps=steps)
                chunks.append(wav)
                chunks.append(tail_silence)

            if i < len(lines) - 1 and not _MARKER_RE.match(lines[i + 1]) and not m:
                chunks.append(gap_silence)

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
