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


def _compress_dynamic_range(
    wav: np.ndarray,
    sr: int,
    threshold_db: float = -24.0,
    ratio: float = 6.0,
    attack_ms: float = 3.0,
    release_ms: float = 80.0,
    block_ms: float = 5.0,
) -> np.ndarray:
    """조용한/큰 구간의 음량 차이를 줄여 평균 음량(RMS)을 피크에 가깝게 끌어올린다.

    방송/광고에서 쓰는 "loudness maximizing" 기법과 동일하다: threshold_db를
    넘는 구간만 ratio 비율로 눌러서, 이후 피크 정규화(TARGET_PEAK)를 적용했을 때
    조용한 부분까지 같이 커지도록 만든다. 결과적으로 최대 진폭(피크)은 그대로
    두면서 "체감 음량"만 크게 키우는 효과가 있다.
    """
    n = len(wav)
    if n == 0:
        return wav

    block_size = max(1, int(sr * block_ms / 1000))
    pad = (-n) % block_size
    padded = np.concatenate([wav, np.zeros(pad, dtype=wav.dtype)]) if pad else wav
    blocks = padded.reshape(-1, block_size)

    rms = np.sqrt(np.mean(blocks.astype(np.float64) ** 2, axis=1))
    rms_db = 20 * np.log10(np.maximum(rms, 1e-8))

    over_db = np.maximum(rms_db - threshold_db, 0.0)
    reduction_db = over_db * (1.0 - 1.0 / ratio)

    blocks_per_attack = max(1e-6, attack_ms / block_ms)
    blocks_per_release = max(1e-6, release_ms / block_ms)
    attack_coeff = np.exp(-1.0 / blocks_per_attack)
    release_coeff = np.exp(-1.0 / blocks_per_release)

    smoothed = np.empty_like(reduction_db)
    prev = 0.0
    for i, target in enumerate(reduction_db):
        coeff = attack_coeff if target > prev else release_coeff
        prev = coeff * prev + (1 - coeff) * target
        smoothed[i] = prev

    gain_lin = 10 ** (-smoothed / 20.0)
    gain_per_sample = np.repeat(gain_lin, block_size)[:n].astype(np.float32)

    return (wav * gain_per_sample).astype(np.float32)


class SupertonicEngine:
    # Supertonic v3 공식 지원 언어
    SUPPORTED_LANGS = {
        "ko", "en", "ja", "ar", "bg", "cs", "da", "de", "el", "es",
        "et", "fi", "fr", "hi", "hr", "hu", "id", "it", "lt", "lv",
        "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "tr", "uk", "vi",
    }

    # 자동 gain(피크 정규화) 모드에서 TTS 음성 구간이 도달할 목표 최대 진폭.
    # 1.0(풀스케일) 바로 아래로 여유를 둬 리샘플링 등에서 생기는 미세한
    # 오버슈트로도 clip되지 않게 함.
    TARGET_PEAK = 0.97
    # 원본이 거의 무음(peak≈0)인 이상 케이스에서 노이즈까지 과증폭되는 것을 막는 상한
    MAX_AUTO_GAIN = 8.0

    def __init__(
        self,
        voice: str = "M2",
        speed: float = 1.05,
        steps: int = 8,
        sfx_aliases: dict[str, str] | None = None,
        sample_rate: int | None = None,
        bell_wav_1x: str | None = None,
        bell_wav_2x: str | None = None,
        gain: float | None = None,
    ):
        from supertonic import TTS
        self._tts = TTS(auto_download=True)
        self.voice = voice
        self.speed = speed
        self.steps = steps
        self.sfx_aliases = sfx_aliases or {}
        # None이면 모델 기본 sample rate(self._tts.sample_rate) 그대로 사용
        self.sample_rate = sample_rate
        # soundEffect(0~10) 필드로 tts 맨 앞에 반복 삽입할 종소리 wav
        # 1~5: bell_wav_1x를 N회, 6~10: bell_wav_2x를 (N-5)회 반복
        self.bell_wav_1x = bell_wav_1x
        self.bell_wav_2x = bell_wav_2x
        # TTS 음성 구간에만 적용되는 배율. None이면 매 요청마다 TARGET_PEAK까지
        # 자동으로 최대화(피크 정규화)하고, 숫자를 주면 그 배율을 고정으로 곱한다
        # (레거시 방식, 클리핑 방지를 위해 [-1, 1]로 clip됨)
        self.gain = gain

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
        sound_effect: int = 0,
        gain: float | None = None,
    ) -> tuple[np.ndarray, int, float]:
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            lines = [text]

        t0 = time.time()
        sr = self._tts.sample_rate
        gap_silence = np.zeros(int(sr * gap))
        tail_silence = np.zeros(int(sr * 0.15))

        # gain은 TTS로 합성된 음성 구간에만 적용한다 (종소리/효과음 wav는 원본
        # 유지 — 이미 진폭이 커서(예: captain_bell 0.82) 같이 증폭하면 쉽게 clip됨).
        # chunks와 별도로 tts_flags를 같은 길이로 유지해 어느 chunk가 TTS 음성인지 기록.
        chunks: list[np.ndarray] = []
        tts_flags: list[bool] = []

        def add(arr: np.ndarray, is_tts: bool = False):
            chunks.append(arr)
            tts_flags.append(is_tts)

        if sound_effect and sound_effect > 0:
            if 1 <= sound_effect <= 5:
                bell_wav, repeat = self.bell_wav_1x, sound_effect
            else:  # 6~10
                bell_wav, repeat = self.bell_wav_2x, sound_effect - 5
            if not bell_wav:
                print("  [경고] sound_effect 지정됐지만 config.yaml의 sound_effect wav_1x/wav_2x 미설정 — 건너뜀", flush=True)
            else:
                bell_path = _resolve_path(bell_wav, sfx_base, output_path)
                if not bell_path.exists():
                    print(f"  [경고] 종소리 파일 없음: {bell_path} — 건너뜀", flush=True)
                else:
                    bell_audio = _load_sfx(str(bell_path), sr)
                    if verbose:
                        print(f"  [SOUND_EFFECT {bell_path.name} x{repeat}]")
                    # 타종과 타종 사이 간격은 `gap` 요청값과 무관하게 항상 0으로 고정 (붙여서 재생)
                    for i in range(repeat):
                        add(bell_audio)
                    add(gap_silence)

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
            wav = _compress_dynamic_range(wav, sr)
            add(wav, is_tts=True)
            add(tail_silence)

        def emit_sfx(label: str, value: str):
            path = _resolve_path(value, sfx_base, output_path)
            if not path.exists():
                print(f"  [경고] 파일 없음: {path} — 건너뜀", flush=True)
                return
            if verbose:
                print(f"  [{label} {path.name}]")
            add(_load_sfx(str(path), sr))
            add(tail_silence)

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
                    add(np.zeros(int(sr * secs), dtype=np.float32))
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
                add(gap_silence)

        # chunk 경계(원본 sr 기준 샘플 인덱스)를 TTS 여부와 함께 기록해 둔다.
        chunk_lens = [len(c) for c in chunks]
        offsets = np.cumsum([0] + chunk_lens)
        tts_spans_native = [
            (offsets[i], offsets[i + 1]) for i in range(len(chunks)) if tts_flags[i]
        ]

        full_wav = np.concatenate(chunks)
        out_sr = self.sample_rate or sr
        if out_sr != sr:
            full_wav = _resample(full_wav, sr, out_sr)

        ratio = out_sr / sr
        tts_spans = [
            (int(round(s * ratio)), int(round(e * ratio))) for s, e in tts_spans_native
        ]
        full_wav = self._apply_tts_gain(full_wav, tts_spans, gain)

        elapsed = time.time() - t0
        return full_wav, out_sr, elapsed

    def _apply_tts_gain(
        self, full_wav: np.ndarray, tts_spans: list[tuple[int, int]], gain: float | None
    ) -> np.ndarray:
        """TTS 음성 구간(tts_spans)에만 gain을 적용한다.

        gain(요청 값) 또는 self.gain(설정 기본값)이 숫자로 주어지면 그 배율을
        그대로 곱한다(레거시 고정 배율 모드). 둘 다 None이면, 클리핑 직전까지
        자동으로 음량을 최대화하는 피크 정규화 모드로 동작한다 — 매 요청마다
        TTS 구간의 실제 최대 진폭을 측정해 목표치(TARGET_PEAK)에 맞춰 배율을
        계산하므로, 조용한 목소리/문장도 항상 안전한 한도 내에서 최대로 크게
        나온다.
        """
        if not tts_spans:
            return full_wav

        g = gain if gain is not None else self.gain

        if g is None:
            tts_peak = max(
                (np.max(np.abs(full_wav[s:e])) for s, e in tts_spans if e > s),
                default=0.0,
            )
            if tts_peak <= 1e-6:
                return full_wav
            g = min(self.MAX_AUTO_GAIN, self.TARGET_PEAK / tts_peak)

        if g == 1.0:
            return full_wav

        for s, e in tts_spans:
            full_wav[s:e] = np.clip(full_wav[s:e] * g, -1.0, 1.0)
        return full_wav

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
        sound_effect: int = 0,
        gain: float | None = None,
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
            sound_effect=sound_effect,
            gain=gain,
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
        sound_effect: int = 0,
        gain: float | None = None,
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
            sound_effect=sound_effect,
            gain=gain,
        )

        buf = io.BytesIO()
        sf.write(buf, full_wav, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue(), elapsed

    def get_voices(self) -> list[str]:
        return VOICES
