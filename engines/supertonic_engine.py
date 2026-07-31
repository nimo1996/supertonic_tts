import io
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf

VOICES = ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]

# [PAUSE: 1.5]  /  [BELL: sounds/bell.wav]  /  [SFX: sounds/chime.wav]
_MARKER_RE = re.compile(r'^\[(PAUSE|BELL|SFX)\s*:\s*(.+?)\s*\]$', re.IGNORECASE)

# 문장 중간에 끼워 넣는 별칭 태그: <시작 종>, <종료 종> ...
_INLINE_TAG_RE = re.compile(r'<\s*([^<>]+?)\s*>')


def _resolve_path(value: str, sfx_base: Path | None, output_path: str | None) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    if sfx_base is not None:
        base = sfx_base
    elif output_path is not None:
        base = Path(output_path).parent.parent
    else:
        base = Path.cwd()
    return base / value


def _resample(data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return data
    new_len = int(len(data) / orig_sr * target_sr)
    return np.interp(
        np.linspace(0, len(data) - 1, new_len),
        np.arange(len(data)),
        data,
    ).astype(np.float32)


def _load_sfx(path: str, target_sr: int) -> np.ndarray:
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    return _resample(data, sr, target_sr)


class SupertonicEngine:
    # Supertonic v3 공식 지원 언어
    SUPPORTED_LANGS = {
        "ko", "en", "ja", "ar", "bg", "cs", "da", "de", "el", "es",
        "et", "fi", "fr", "hi", "hr", "hu", "id", "it", "lt", "lv",
        "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "tr", "uk", "vi",
    }
    def __init__(
        self,
        voice: str = "M2",
        speed: float = 1.05,
        steps: int = 8,
        sfx_aliases: dict[str, str] | None = None,
        sample_rate: int | None = None,
    ):
        from supertonic import TTS
        self._tts = TTS(auto_download=True)
        self.voice = voice
        self.speed = speed
        self.steps = steps
        self.sfx_aliases = sfx_aliases or {}
        # None이면 모델 기본 sample rate(self._tts.sample_rate) 그대로 사용
        self.sample_rate = sample_rate

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

    def _synthesize_full_wav(
        self,
        text: str,
        lang: str = "ko",
        voice: str | None = None,
        speed: float | None = None,
        steps: int | None = None,
        gap: float = 0.4,
        verbose: bool = True,
        sfx_base: Path | None = None,
        output_path: str | None = None,
    ) -> tuple[np.ndarray, int, float]:
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            lines = [text]

        t0 = time.time()
        sr = self._tts.sample_rate
        gap_silence = np.zeros(int(sr * gap))
        tail_silence = np.zeros(int(sr * 0.15))

        def count_segments(l: str) -> int:
            if _MARKER_RE.match(l):
                return 0
            parts = _INLINE_TAG_RE.split(l)
            return sum(1 for j, s in enumerate(parts) if j % 2 == 0 and s.strip())

        tts_count = sum(count_segments(l) for l in lines)
        tts_idx = 0

        def emit_tts(segment: str):
            nonlocal tts_idx
            tts_idx += 1
            if verbose:
                print(f"  [TTS {tts_idx}/{tts_count}] {segment[:40]}{'...' if len(segment) > 40 else ''}")
            send = segment if segment[-1] in ".。!！?？,，" else segment + "."
            wav, _ = self.generate(send, lang=lang, voice=voice, speed=speed, steps=steps)
            chunks.append(wav)
            chunks.append(tail_silence)

        def emit_sfx(label: str, value: str):
            path = _resolve_path(value, sfx_base, output_path)
            if not path.exists():
                print(f"  [경고] 파일 없음: {path} — 건너뜀", flush=True)
                return
            if verbose:
                print(f"  [{label} {path.name}]")
            chunks.append(_load_sfx(str(path), sr))
            chunks.append(tail_silence)

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
                    emit_sfx(kind, value)
            else:
                tag_matches = _INLINE_TAG_RE.search(line)
                if not tag_matches:
                    emit_tts(line)
                else:
                    parts = _INLINE_TAG_RE.split(line)
                    for j, part in enumerate(parts):
                        if j % 2 == 1:
                            alias = part.strip()
                            if alias not in self.sfx_aliases:
                                print(f"  [경고] 등록되지 않은 태그: <{alias}> — 건너뜀", flush=True)
                                continue
                            emit_sfx(f"TAG <{alias}>", self.sfx_aliases[alias])
                        else:
                            text_part = part.strip()
                            if text_part:
                                emit_tts(text_part)

            if i < len(lines) - 1 and not _MARKER_RE.match(lines[i + 1]) and not m:
                chunks.append(gap_silence)

        full_wav = np.concatenate(chunks)
        out_sr = self.sample_rate or sr
        if out_sr != sr:
            full_wav = _resample(full_wav, sr, out_sr)
        elapsed = time.time() - t0
        return full_wav, out_sr, elapsed

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
        sfx_base: Path | None = None,
    ) -> float:
        full_wav, sr, elapsed = self._synthesize_full_wav(
            text=text,
            lang=lang,
            voice=voice,
            speed=speed,
            steps=steps,
            gap=gap,
            verbose=verbose,
            sfx_base=sfx_base,
            output_path=output_path,
        )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # TTS.save_audio()는 self._tts.sample_rate를 무시하고 항상 모델 기본
        # sample rate로 저장하므로, sample_rate 설정을 반영하려면 직접 써야 함.
        sf.write(output_path, full_wav, sr, subtype="PCM_16")

        if verbose:
            audio_dur = len(full_wav) / sr
            print(f"  생성: {elapsed:.1f}s | 음성: {audio_dur:.1f}s | RTF: {audio_dur/elapsed:.2f}x | {output_path}")
        return elapsed

    def generate_to_bytes(
        self,
        text: str,
        lang: str = "ko",
        voice: str | None = None,
        speed: float | None = None,
        steps: int | None = None,
        gap: float = 0.4,
        verbose: bool = False,
        sfx_base: Path | None = None,
    ) -> tuple[bytes, float]:
        full_wav, sr, elapsed = self._synthesize_full_wav(
            text=text,
            lang=lang,
            voice=voice,
            speed=speed,
            steps=steps,
            gap=gap,
            verbose=verbose,
            sfx_base=sfx_base,
        )

        buf = io.BytesIO()
        sf.write(buf, full_wav, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue(), elapsed

    def get_voices(self) -> list[str]:
        return VOICES
