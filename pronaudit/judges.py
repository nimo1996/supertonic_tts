"""판정용 STT 두 종류. 결과는 **합치지 않고 각각 따로** 기록한다.

- moonshine: 실제 운용에 쓰는 그 모델(cpu_stt). 여기서 틀리는 발음은
  "TTS 출력이 우리 STT로 다시 들어갈 때 깨지는 발음"이라 그 자체가 실전 지표다.
  다만 모델이 작아 자기 오류가 많다.
- whisper(large-v3-turbo): 훨씬 강한 모델. 이쪽까지 틀리면 TTS가 실제로
  뭉갠 것일 가능성이 높다.

둘의 불일치가 정보다. moonshine만 틀리면 "작은 모델이 못 알아듣는 발음",
둘 다 틀리면 "TTS 발음 결함". 그래서 다수결로 뭉개지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

TARGET_SR = 16000

# ── 리샘플 ────────────────────────────────────────────────────────────────────
# TTS 쪽(engines/supertonic_engine.py)과 같은 이유로 안티에일리어싱을 건다.
# 8k 출력을 16k로 올릴 때 필터 없이 늘리면 이미징 성분이 얹혀 STT가 그걸
# 마찰음으로 오인한다 — 그러면 TTS 결함이 아닌 것을 결함으로 세게 된다.

def _sinc_lowpass(cutoff_hz: float, sr: int, numtaps: int = 255) -> np.ndarray:
    n = np.arange(numtaps) - (numtaps - 1) / 2
    fc = cutoff_hz / (sr / 2)
    h = np.sinc(fc * n) * fc
    return (h * np.hamming(numtaps)) / np.sum(h * np.hamming(numtaps))


def resample(data: np.ndarray, orig_sr: int, target_sr: int = TARGET_SR) -> np.ndarray:
    if orig_sr == target_sr:
        return data.astype(np.float32)
    from math import gcd
    g = gcd(orig_sr, target_sr)
    up, down = target_sr // g, orig_sr // g
    if up > 1:
        x = np.zeros(len(data) * up, dtype=np.float64)
        x[::up] = data
        x *= up
    else:
        x = data.astype(np.float64)
    inter_sr = orig_sr * up
    nyq = min(orig_sr, target_sr) / 2
    x = np.convolve(x, _sinc_lowpass(nyq * 0.95, inter_sr), mode="same")
    return x[::down].astype(np.float32)


def load_16k(path: str | Path) -> np.ndarray:
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return resample(data, sr, TARGET_SR)


# ── 판정 결과 ─────────────────────────────────────────────────────────────────

@dataclass
class Hypothesis:
    judge: str
    text: str
    secs: float


class Judge:
    name = "base"

    def transcribe(self, audio: np.ndarray) -> str:  # pragma: no cover
        raise NotImplementedError


class MoonshineJudge(Judge):
    """cpu_stt가 쓰는 sherpa-onnx moonshine-tiny-ko (양자화)."""
    name = "moonshine"

    def __init__(self, model_dir: str | Path, num_threads: int = 4):
        import sherpa_onnx
        d = Path(model_dir)
        self._rec = sherpa_onnx.OfflineRecognizer.from_moonshine_v2(
            encoder=str(d / "encoder_model.ort"),
            decoder=str(d / "decoder_model_merged.ort"),
            tokens=str(d / "tokens.txt"),
            num_threads=num_threads,
        )

    def transcribe(self, audio: np.ndarray) -> str:
        s = self._rec.create_stream()
        s.accept_waveform(TARGET_SR, audio)
        self._rec.decode_stream(s)
        return s.result.text.strip()


class WhisperJudge(Judge):
    """mlx-whisper. Apple Silicon에서 실시간보다 훨씬 빠르게 돈다."""
    name = "whisper"

    def __init__(self, repo: str = "mlx-community/whisper-large-v3-turbo"):
        import mlx_whisper
        self._mw = mlx_whisper
        self._repo = repo

    def transcribe(self, audio: np.ndarray) -> str:
        # temperature=0 고정 + 이전 문맥 차단. 문맥을 주면 whisper가 앞
        # 문항의 낱말을 뒤 문항에 흘려 넣어(최소대립쌍이라 특히 위험) 정답을
        # 만들어내 버린다.
        r = self._mw.transcribe(
            audio,
            path_or_hf_repo=self._repo,
            language="ko",
            temperature=0.0,
            condition_on_previous_text=False,
            fp16=True,
            verbose=None,
        )
        return (r.get("text") or "").strip()


# whisper가 없는 소리를 지어내는(hallucination) 전형적 문구. 무음/초단발화에서
# 튀어나오는 것들이라, 그대로 두면 결함으로 잘못 센다.
_HALLUCINATION = re.compile(
    r"(시청해\s*주셔서|구독과?\s*좋아요|감사합니다\s*$|MBC\s*뉴스|한글자막|"
    r"이 영상은|다음 영상에서|Thanks for watching)"
)


def looks_hallucinated(text: str, ref: str) -> bool:
    from jamo import normalize
    if not _HALLUCINATION.search(text):
        return False
    return normalize(ref) not in normalize(text)
