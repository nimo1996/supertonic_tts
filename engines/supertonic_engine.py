import io
import re
import time
from functools import lru_cache
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


@lru_cache(maxsize=8)
def _sinc_lowpass(cutoff_hz: float, sr: int, numtaps: int = 255) -> np.ndarray:
    """Blackman 창을 씌운 windowed-sinc 저역통과 FIR 계수."""
    n = np.arange(numtaps) - (numtaps - 1) / 2.0
    fc = cutoff_hz / sr
    h = 2 * fc * np.sinc(2 * fc * n) * np.blackman(numtaps)
    return (h / h.sum()).astype(np.float32)


def _resample(data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """샘플레이트 변환. 다운샘플링 시에는 반드시 안티에일리어싱을 먼저 건다.

    44.1kHz → 8kHz처럼 크게 낮출 때 저역통과 필터 없이 바로 솎아내면
    4kHz 위의 성분이 가청대역 안으로 접혀 들어온다(aliasing). 이 접힌 성분은
    ㅎ/ㅅ/ㅊ 같은 마찰음이 몰려 있는 3~4kHz 대역에 정확히 겹쳐서 자음 분간을
    흐린다. 나이퀴스트의 90%(0.45 * target_sr) 지점에서 잘라낸 뒤 보간한다.
    """
    if orig_sr == target_sr:
        return data
    if target_sr < orig_sr:
        taps = 255
        if len(data) > taps:
            h = _sinc_lowpass(0.45 * target_sr, orig_sr, taps)
            data = np.convolve(data, h, mode="same").astype(np.float32)
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


# ─── 후보 품질 평가 (best-of-N) ───────────────────────────────────────────────
#
# Supertonic은 flow-matching 샘플러라 매 호출마다 서로 다른 난수 latent에서
# 출발한다. 즉 같은 문장이라도 take마다 결과가 다르고, 특히 짧은 문장에서는
# 음절이 서로 뭉개지거나(예: "하함" → "함") 마지막 음절이 급하게 삼켜지는
# 실패 take가 섞여 나온다. 아래 함수들은 생성된 wav의 에너지 포락선에서
# 음절 핵(모음 정점) 개수와 실제 발화 길이를 재서, 여러 take 중 가장 또렷한
# 것을 고르기 위한 점수를 만든다.

_HANGUL_SYLLABLE_RE = re.compile(r"[가-힣]")
_LATIN_VOWEL_GROUP_RE = re.compile(r"[aeiouyAEIOUY]+")
_DIGIT_RE = re.compile(r"\d")


def _expected_units(text: str) -> int:
    """텍스트에서 기대되는 음절(모음 정점) 개수의 근사값.

    한글은 음절 블록 수가 곧 음절 수다. 라틴 문자는 모음 덩어리 수로 센다.
    어느 쪽으로도 셀 수 없으면(기호만 있는 등) 0을 돌려주고, 호출부는 이때
    후보 선별을 건너뛴다.
    """
    n = len(_HANGUL_SYLLABLE_RE.findall(text))
    n += len(_LATIN_VOWEL_GROUP_RE.findall(text))
    n += len(_DIGIT_RE.findall(text))
    return n


def _rms_envelope(wav: np.ndarray, sr: int, hop_ms: float = 10.0, win_ms: float = 30.0) -> np.ndarray:
    """hop_ms 간격, win_ms 길이 창의 RMS 포락선 (누적합으로 한 번에 계산)."""
    hop = max(1, int(sr * hop_ms / 1000))
    win = max(hop, int(sr * win_ms / 1000))
    if len(wav) < win:
        return np.zeros(0, dtype=np.float32)
    csum = np.concatenate([[0.0], np.cumsum(wav.astype(np.float64) ** 2)])
    starts = np.arange(0, len(wav) - win + 1, hop)
    return np.sqrt((csum[starts + win] - csum[starts]) / win).astype(np.float32)


def _syllable_nuclei(
    wav: np.ndarray,
    sr: int,
    hop_ms: float = 10.0,
    min_dist_ms: float = 70.0,
    min_prominence: float = 0.10,
    min_level: float = 0.15,
) -> tuple[list[int], np.ndarray]:
    """에너지 포락선의 뚜렷한 정점 위치(프레임 인덱스)와 정규화된 포락선.

    정점 개수 = 또렷하게 발음된 음절 수의 근사값이다.

    공명음 받침(ㄴ/ㅁ/ㅇ/ㄹ)이 이어지면 인접 음절이 하나로 뭉쳐 보여서 실제
    음절 수보다 적게 세는 경향이 있다. 그래서 이 값은 "정답 개수 맞히기"가
    아니라 **같은 문장의 take끼리 비교**하는 용도로만 쓴다 — 뭉개진 take는
    정점이 눈에 띄게 적게 나온다.
    """
    env = _rms_envelope(wav, sr, hop_ms)
    if env.size < 3:
        return [], env
    env = np.convolve(env, np.ones(5) / 5, mode="same")
    env = env / (env.max() + 1e-9)

    peaks: list[tuple[int, float]] = []
    for i in range(1, len(env) - 1):
        if not (env[i] >= env[i - 1] and env[i] > env[i + 1] and env[i] >= min_level):
            continue
        # prominence: 좌/우로 내려가다 다시 올라가기 직전까지의 최소값 대비 높이
        l = i
        while l > 0 and env[l - 1] <= env[l]:
            l -= 1
        r = i
        while r < len(env) - 1 and env[r + 1] <= env[r]:
            r += 1
        if env[i] - max(env[l], env[r]) >= min_prominence or env[i] >= 0.85:
            peaks.append((i, float(env[i])))

    min_dist = max(1, int(min_dist_ms / hop_ms))
    peaks.sort(key=lambda x: -x[1])
    kept: list[int] = []
    for idx, _ in peaks:
        if all(abs(idx - k) >= min_dist for k in kept):
            kept.append(idx)
    return sorted(kept), env


def _final_syllable_tail(wav: np.ndarray, sr: int, hop_ms: float = 10.0) -> float:
    """마지막 음절 정점부터 발화가 끝날 때까지의 길이(초).

    마지막 음절을 삼킨 take는 이 값이 눈에 띄게 짧다. 다만 절대값은 끝소리가
    무엇이냐에 크게 좌우된다 — 파열음 받침으로 끝나는 "집합"[지팝]은 원래
    폐쇄로 끝나서 60ms대가 정상이고, "하함"은 120ms대가 정상이다. 그래서 이
    값은 **같은 문장의 take끼리 비교할 때만** 의미가 있다. best-of-N은 정확히
    그 조건(문장 고정, take만 다름)이라 끝소리 차이가 상수로 상쇄된다.
    """
    peaks, env = _syllable_nuclei(wav, sr, hop_ms)
    if not peaks or env.size == 0:
        return 0.0
    active = np.flatnonzero(env > 0.10)
    if active.size == 0:
        return 0.0
    return max(0, int(active[-1]) - peaks[-1]) * hop_ms / 1000.0


def _speech_span(wav: np.ndarray, sr: int, rel_threshold: float = 0.04) -> float:
    """앞뒤 묵음을 뺀 실제 발화 길이(초)."""
    if len(wav) == 0:
        return 0.0
    amp = np.abs(wav)
    peak = amp.max()
    if peak <= 1e-6:
        return 0.0
    active = np.flatnonzero(amp > rel_threshold * peak)
    if active.size == 0:
        return 0.0
    return float(active[-1] - active[0]) / sr


def _voiced_tail(wav: np.ndarray, sr: int, hop_ms: float = 10.0) -> float:
    """마지막 음절 정점부터 **유성음이 끝나는 지점**까지의 길이(초).

    _final_syllable_tail과 달리 무성 구간을 tail로 세지 않는다. 이게 중요한
    이유: 일부 take는 발화 뒤에 170~310ms짜리 숨소리를 붙이는데, 유성/무성을
    구분하지 않으면 그런 take가 "끝음이 잘 살아있는 take"로 오인된다(실측:
    숨 구간의 1kHz 이하 에너지 비중 35% vs 정상 발음 92%).

    1kHz 저역통과 사본과 원본의 프레임별 에너지비로 유성 여부를 판정한다.
    """
    peaks, env = _syllable_nuclei(wav, sr, hop_ms=hop_ms)
    if not peaks or env.size == 0:
        return 0.0
    low = np.convolve(wav, _sinc_lowpass(1000.0, sr), mode="same").astype(np.float32)
    env_low = _rms_envelope(low, sr, hop_ms)
    n = min(env.size, env_low.size)
    if n == 0:
        return 0.0
    env, env_low = env[:n], env_low[:n]
    peak = env.max()
    if peak <= 1e-9:
        return 0.0
    voiced = (env > 0.10 * peak) & (
        (env_low ** 2) > 0.5 * np.maximum(env ** 2, 1e-18)
    )
    if not voiced.any():
        return 0.0
    return max(0, int(np.flatnonzero(voiced)[-1]) - peaks[-1]) * hop_ms / 1000.0


def _release_decay_ms(
    wav: np.ndarray, sr: int, hop_ms: float = 2.0, win_ms: float = 10.0
) -> float:
    """마지막 음절이 -10dB에서 -30dB까지 떨어지는 데 걸리는 시간(ms).

    사람이 말을 맺을 때는 진폭이 서서히 잦아든다. 이 모델은 같은 텍스트라도
    take에 따라 그 감쇠가 12ms만에 끝나버리는 경우를 25~30% 확률로 낸다.
    청취 검증에서 "발음은 다 들리는데 페이드아웃 느낌이 없고 음량이 뚝
    떨어진다"고 지목된 take들이 정확히 이 값이 짧았다(결함 45ms / 정상 77ms,
    AUC 0.81 — 측정한 지표 중 지각과 가장 잘 맞는다).

    끝음 '길이'와는 다른 값이다. 길이로 고른 take는 결함률이 그대로였다.
    """
    hop = max(1, int(sr * hop_ms / 1000))
    win = max(hop, int(sr * win_ms / 1000))
    if len(wav) < win:
        return 0.0
    csum = np.concatenate([[0.0], np.cumsum(wav.astype(np.float64) ** 2)])
    starts = np.arange(0, len(wav) - win + 1, hop)
    db = 20 * np.log10(np.maximum(np.sqrt((csum[starts + win] - csum[starts]) / win), 1e-9))
    db -= db.max()

    active = np.flatnonzero(db > -35)
    if active.size == 0:
        return 0.0
    end = int(active[-1])
    back = int(150 / hop_ms)
    lo = max(0, end - back)
    peak = lo + int(np.argmax(db[lo:end + 1]))

    def cross(threshold: float) -> int:
        for i in range(peak, end + 1):
            if db[i] - db[peak] <= threshold:
                return i
        return end

    return (cross(-30.0) - cross(-10.0)) * hop_ms


# 이 음절 수 이하는 "짧은 발화"로 보고 끝음 길이를 1순위로 평가한다.
# 근거: 짧은 단어에서는 정점 개수가 모든 take에서 동일하게 나와(예: "확인."은
# 8 take 전부 2) 1순위 키가 변별력을 완전히 잃는다. 반면 청취 검증에서 "끝이
# 잘린 것 같다"고 지목된 take는 예외 없이 같은 그룹 내 끝음 최단이었다.
_SHORT_UNITS = 4



def _take_score(
    wav: np.ndarray, sr: int, expected: int
) -> tuple[int, tuple[float, float, float]]:
    """(정점 개수, 정렬용 점수). 점수가 클수록 좋은 take.

    긴 발화에서는 기대 음절 수 일치가 1순위다 — 음절이 뭉개진 take를 걸러내는
    것이 가장 중요하다.

    2순위만 발화 길이에 따라 다르다. 짧은 발화(_SHORT_UNITS 이하)는 끝음 감쇠
    시간을, 그보다 길면 끝음 길이를 쓴다. 짧은 단어는 정점 개수가 take마다
    똑같이 나오는 일이 많아("확인."은 8 take 전부 2) 1순위만으로는 사실상
    무작위 선택이 되는데, 그 동점을 감쇠로 깬다.

    감쇠를 1순위로 올려본 적이 있으나 되돌렸다. "함장 하함"처럼 여러 단어로 된
    짧은 문구에서 음절이 뭉개진 take가 감쇠만 길면 선택돼 버린다. 정점 개수를
    1순위로 두어도 감쇠 이득은 거의 그대로다(같은 풀에서 후보 5개 선별 시뮬레이션:
    "좌현" 99.1ms→98.8ms, "함장 하함" 90.2ms→88.9ms, 무선별은 각각 77.8/71.1ms).
    대신 정점 개수가 기대치와 일치하는 비율이 97.6%→100%, 90.7%→100%로 오른다.

    끝음 '길이'를 기준으로 삼았던 적도 있는데 효과가 없었다. 길이는 결함과 상관만
    있고(AUC 0.74) 원인이 아니어서, 끝음이 짧은 take를 걸러내도 결함률이
    5/15 → 4/15로 그대로였다. 감쇠 시간은 청취에서 지목된 현상 자체의 물리량이다.

    긴 발화의 2순위 끝음 길이는 무성 구간을 제외한 _voiced_tail을 쓴다. 무성까지
    세면 발화 뒤에 숨소리가 붙은 take가 "끝음이 긴 take"로 오인된다.
    """
    peaks, _ = _syllable_nuclei(wav, sr)
    nuclei = len(peaks)
    matched = min(nuclei, expected)
    over = max(0, nuclei - expected)

    clarity = matched - 0.5 * over
    span = _speech_span(wav, sr)

    if 0 < expected <= _SHORT_UNITS:
        return nuclei, (clarity, _release_decay_ms(wav, sr), span)
    return nuclei, (clarity, _voiced_tail(wav, sr), span)


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
        candidates: int = 3,
        short_candidates: int | None = None,
        candidates_max_units: int = 25,
        pronunciation: dict[str, str] | None = None,
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
        # 한 문장을 몇 번 생성해서 가장 좋은 것을 고를지. 1이면 예전처럼 1회만.
        self.candidates = max(1, int(candidates))
        # 짧은 발화(_SHORT_UNITS 이하)에만 쓰는 후보 수. 짧은 발화는 조기 종료
        # 없이 매번 다 뽑으므로 비용이 후보 수에 정비례하고, 반대로 긴 문장은
        # 정점 검출이 기대 음절 수를 못 채워 조기 종료가 거의 발동하지 않는다
        # (16음절 문장에서 정점 9~11개). 그래서 하나의 값을 공유하면 검증된
        # 이득이 없는 긴 문장까지 같이 느려진다(25음절 6.3s → 10.4s).
        self.short_candidates = (
            self.candidates if short_candidates is None else max(1, int(short_candidates))
        )
        # 이 음절 수를 넘는 긴 문장은 후보 선별을 건너뛴다(느려지기만 하고,
        # 긴 문장은 애초에 뭉개짐 문제가 거의 없다).
        self.candidates_max_units = max(1, int(candidates_max_units))
        # 발음 교정 사전: 합성 직전에 원문을 치환한다. 긴 표기부터 적용.
        self.pronunciation = dict(pronunciation or {})
        self._pron_rules = sorted(
            self.pronunciation.items(), key=lambda kv: -len(kv[0])
        )

    def apply_pronunciation(self, text: str) -> str:
        """config의 발음 교정 사전을 적용한다.

        Supertonic v3는 G2P 없이 문자를 그대로 먹는 모델이라, 한국어의 모음
        사이 ㅎ 약화 같은 구어 음운 현상을 그대로 학습해 버렸다("하함"이
        [하암]처럼 흘러 "함" 하나로 들리는 원인). 발음이 뭉개지는 낱말을
        모델이 또렷하게 읽는 표기로 바꿔치기하는 것이 가장 확실한 해결책이고,
        코드 수정 없이 config.yaml에서 계속 늘려갈 수 있다.
        """
        for src, dst in self._pron_rules:
            text = text.replace(src, dst)
        return text

    def supports(self, lang: str) -> bool:
        return lang.lower() in self.SUPPORTED_LANGS

    def generate(
        self,
        text: str,
        lang: str = "ko",
        voice: str | None = None,
        speed: float | None = None,
        steps: int | None = None,
        candidates: int | None = None,
    ) -> tuple[np.ndarray, int]:
        """한 문장을 합성한다. candidates>1이면 best-of-N으로 가장 또렷한 take를 고른다.

        모델 샘플러가 확률적이라 짧은 문장일수록 실패 take(음절 뭉개짐, 마지막
        음절 삼킴)가 섞여 나온다. 최소 2 take를 뽑아 비교한 뒤, 기대 음절 수를
        정확히 맞춘 take가 있으면 거기서 멈춘다.
        """
        v = (voice or self.voice).upper()
        if v not in VOICES:
            raise ValueError(f"잘못된 목소리: {v}. 선택 가능: {VOICES}")

        style = self._tts.get_voice_style(v)
        sr = self._tts.sample_rate

        def synth() -> np.ndarray:
            wav, _ = self._tts.synthesize(
                text=text,
                voice_style=style,
                lang=lang.lower(),
                speed=speed or self.speed,
                total_steps=steps or self.steps,
            )
            # shape: (1, samples) → (samples,)
            return wav.squeeze(0)

        expected = _expected_units(text)
        short = 0 < expected <= _SHORT_UNITS
        if candidates is not None:
            n = max(1, int(candidates))
        else:
            n = self.short_candidates if short else self.candidates
        if n == 1 or expected == 0 or expected > self.candidates_max_units:
            return synth(), sr

        # 후보 평가는 **실제 출력 sample rate**에서 한다. 8kHz로 내보내면
        # 3.6kHz 위가 잘려나가므로, 모델 sr(44.1kHz)에서 잰 값이 최종 결과와
        # 어긋날 수 있다 — "비상소집."에서 모델 기준 감쇠 142ms인 take가
        # 8kHz에서는 16ms였다(모델↔출력 상관 +0.24). 끝소리에 고역이 걸리는
        # 단어에서만 드러나서, 저역으로 끝나는 단어로 시험하면 놓친다.
        score_sr = self.sample_rate or sr

        if short:
            # 짧은 발화는 조기 종료하지 않는다. 정점 개수가 기대치를 채워도
            # 2순위인 감쇠는 아직 비교가 안 끝났고, "감쇠가 충분히 길다"는 절대
            # 기준은 세울 수 없다 — 정상값이 마지막 음운에 좌우되기 때문이다
            # (파열받침 42ms, 비음받침 148ms). 끝까지 뽑아야 최선을 고를 수 있다.
            # 짧은 단어는 생성도 빨라 비용이 작다.
            takes = []
            for _ in range(n):
                wav = synth()
                probe = wav if score_sr == sr else _resample(wav, sr, score_sr)
                takes.append((wav, _take_score(probe, score_sr, expected)[1]))
            return max(takes, key=lambda t: t[1])[0], sr

        # 긴 발화는 음절 수를 채운 take가 나오면 조기 종료한다. 더 뽑아도 얻을
        # 게 없고, 긴 문장은 애초에 take 편차가 작다(끝음 CV 0.10~0.17).
        best_wav: np.ndarray | None = None
        best_score = (-1e9, -1e9, -1e9)
        for i in range(n):
            wav = synth()
            probe = wav if score_sr == sr else _resample(wav, sr, score_sr)
            _, score = _take_score(probe, score_sr, expected)
            if score > best_score:
                best_wav, best_score = wav, score
            if i >= 1 and best_score[0] >= expected:
                break
        assert best_wav is not None
        return best_wav, sr

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
        candidates: int | None = None,
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
            send = self.apply_pronunciation(segment)
            send = send if send[-1] in ".。!！?？,，" else send + "."
            wav, _ = self.generate(
                send, lang=lang, voice=voice, speed=speed, steps=steps,
                candidates=candidates,
            )
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
        candidates: int | None = None,
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
            candidates=candidates,
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
        candidates: int | None = None,
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
            candidates=candidates,
        )

        buf = io.BytesIO()
        sf.write(buf, full_wav, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue(), elapsed

    def get_voices(self) -> list[str]:
        return VOICES
