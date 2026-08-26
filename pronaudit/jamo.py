"""한글 자모 분해 · 정렬 · 혼동 집계.

발음 결함을 "규칙"으로 뽑아내려면 "문장이 틀렸다"가 아니라 "어떤 소리가 어떤
소리로 바뀌었나"를 봐야 한다. 그래서 STT 결과와 원문을 완성형 음절이 아니라
자모 단위로 정렬하고, 치환이 일어난 자리의 앞뒤 자모까지 같이 기록한다.
"ㅎ이 사라진다"와 "모음 사이에서만 ㅎ이 사라진다"는 전혀 다른 결론이라,
환경 없이 모은 혼동 행렬은 규칙을 못 만든다.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

BASE = 0xAC00
LAST = 0xD7A3

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"

# 종성 위치의 겹받침은 실제 발음에서 하나로 줄어든다. STT는 표기를 뱉으므로
# 겹받침 자체가 나올 수 있지만, 혼동 행렬에서 ㄳ/ㄵ를 별개 기호로 두면
# 같은 현상이 잘게 쪼개진다. 대표음으로 접어서 센다.
JONG_REPRESENTATIVE = {
    "ㄳ": "ㄱ", "ㄵ": "ㄴ", "ㄶ": "ㄴ", "ㄺ": "ㄱ", "ㄻ": "ㅁ",
    "ㄼ": "ㄹ", "ㄽ": "ㄹ", "ㄾ": "ㄹ", "ㄿ": "ㅂ", "ㅀ": "ㄹ",
}

_SYLLABLE_RE = re.compile(r"[가-힣]")


@dataclass(frozen=True)
class Tok:
    """자모 하나. kind는 C(초성) / V(중성) / T(종성)."""
    kind: str
    jamo: str
    syl: int  # 원문에서 몇 번째 음절이었나

    def key(self) -> str:
        return f"{self.kind}:{self.jamo}"


def normalize(text: str) -> str:
    """비교용 정규화 — 한글 완성형 음절만 남긴다.

    공백·문장부호·숫자·라틴문자는 물론, 발음 교정용으로 끼워 넣은 조합용
    자모(ᄒ U+1112, 아래아 U+119E 등)도 전부 버린다. 그런 문자는 TTS에 넣는
    *입력*이지 사람이 듣고 받아적을 *소리*가 아니므로, 정답 문자열에서는
    빠져 있어야 한다.
    """
    text = unicodedata.normalize("NFC", text)
    return "".join(_SYLLABLE_RE.findall(text))


def to_tokens(text: str, fold_clusters: bool = True) -> list[Tok]:
    """한글 문자열 → 자모 토큰 열. 종성이 없으면 토큰을 만들지 않는다.

    (종성 없음을 빈 토큰으로 두지 않는 이유: 그러면 받침 탈락/첨가가 치환으로
    잡혀 "ㅇ→∅" 같은 가짜 기호가 생긴다. 아예 토큰이 없어야 정렬 단계에서
    삽입/삭제로 정직하게 드러난다.)
    """
    out: list[Tok] = []
    for i, ch in enumerate(normalize(text)):
        code = ord(ch) - BASE
        cho, rest = divmod(code, 588)
        jung, jong = divmod(rest, 28)
        out.append(Tok("C", CHO[cho], i))
        out.append(Tok("V", JUNG[jung], i))
        if jong:
            j = JONG[jong]
            if fold_clusters:
                j = JONG_REPRESENTATIVE.get(j, j)
            out.append(Tok("T", j, i))
    return out


def compose(cho: str, jung: str, jong: str = " ") -> str:
    return chr(BASE + CHO.index(cho) * 588 + JUNG.index(jung) * 28 + JONG.index(jong))


# ── 정렬 ──────────────────────────────────────────────────────────────────────

@dataclass
class Edit:
    op: str            # "sub" | "del" | "ins" | "eq"
    ref: Tok | None
    hyp: Tok | None
    left: str          # 원문 기준 바로 앞 자모 키 ("^" = 문두)
    right: str         # 원문 기준 바로 뒤 자모 키 ("$" = 문말)

    def rule_key(self) -> str:
        """혼동 행렬의 행 이름. 환경(앞/뒤)까지 포함한다."""
        r = self.ref.key() if self.ref else "∅"
        h = self.hyp.key() if self.hyp else "∅"
        return f"{r}→{h}"

    def env_key(self) -> str:
        return f"{self.left} _ {self.right}"


def align(ref: list[Tok], hyp: list[Tok]) -> list[Edit]:
    """레벤슈타인 정렬. 치환 비용 1, 삽입/삭제 비용 1.

    같은 kind끼리의 치환을 살짝 싸게(0.9) 쳐서, 초성이 중성으로 붙는
    엉뚱한 정렬 대신 자리별로 맞물리게 한다.
    """
    n, m = len(ref), len(hyp)
    INF = float("inf")
    d = [[INF] * (m + 1) for _ in range(n + 1)]
    bt = [[None] * (m + 1) for _ in range(n + 1)]
    d[0][0] = 0.0
    for i in range(1, n + 1):
        d[i][0] = i
        bt[i][0] = "del"
    for j in range(1, m + 1):
        d[0][j] = j
        bt[0][j] = "ins"

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            r, h = ref[i - 1], hyp[j - 1]
            if r.kind == h.kind and r.jamo == h.jamo:
                cost, op = 0.0, "eq"
            elif r.kind == h.kind:
                cost, op = 0.9, "sub"
            else:
                cost, op = 1.0, "sub"
            best, bop = d[i - 1][j - 1] + cost, op
            if d[i - 1][j] + 1 < best:
                best, bop = d[i - 1][j] + 1, "del"
            if d[i][j - 1] + 1 < best:
                best, bop = d[i][j - 1] + 1, "ins"
            d[i][j], bt[i][j] = best, bop

    edits: list[Edit] = []
    i, j = n, m
    while i > 0 or j > 0:
        op = bt[i][j] if (i > 0 or j > 0) else None
        if op in ("eq", "sub"):
            edits.append(Edit(op, ref[i - 1], hyp[j - 1], "", ""))
            i, j = i - 1, j - 1
        elif op == "del":
            edits.append(Edit("del", ref[i - 1], None, "", ""))
            i -= 1
        else:
            edits.append(Edit("ins", None, hyp[j - 1], "", ""))
            j -= 1
    edits.reverse()

    # 환경 채우기: 원문 기준 앞/뒤 자모.
    ref_pos = 0
    for e in edits:
        if e.ref is not None:
            e.left = ref[ref_pos - 1].key() if ref_pos > 0 else "^"
            e.right = ref[ref_pos + 1].key() if ref_pos + 1 < n else "$"
            ref_pos += 1
        else:  # 삽입 — 원문에는 자리가 없으므로 삽입 지점의 앞뒤로 잡는다
            e.left = ref[ref_pos - 1].key() if ref_pos > 0 else "^"
            e.right = ref[ref_pos].key() if ref_pos < n else "$"
    return edits


def jamo_cer(ref_text: str, hyp_text: str) -> tuple[float, list[Edit]]:
    """자모 단위 오류율과 편집 목록.

    음절 단위 CER 대신 자모를 쓰는 이유: "확인"이 "황인"으로 들리면 음절
    CER은 0.5지만 실제로 틀린 건 자모 하나다. 정도를 과장하지 않아야
    take마다 흔들리는 잡음과 진짜 결함을 구분할 수 있다.
    """
    ref = to_tokens(ref_text)
    hyp = to_tokens(hyp_text)
    edits = align(ref, hyp)
    bad = sum(1 for e in edits if e.op != "eq")
    return (bad / len(ref) if ref else (1.0 if hyp else 0.0)), edits


def syllable_diff(ref_text: str, hyp_text: str) -> str:
    """사람이 읽을 한 줄 요약: 틀린 음절만 `확인→황인` 꼴로."""
    ref, hyp = normalize(ref_text), normalize(hyp_text)
    edits = align(to_tokens(ref), to_tokens(hyp))
    bad_syls = sorted({e.ref.syl for e in edits if e.op != "eq" and e.ref is not None})
    if not bad_syls:
        return ""
    spans = []
    for s in bad_syls:
        # 해당 음절이 어떻게 들렸는지는 정렬된 hyp 토큰에서 되짚는다
        hyp_syls = sorted({e.hyp.syl for e in edits
                           if e.hyp is not None and e.ref is not None and e.ref.syl == s})
        got = "".join(hyp[k] for k in hyp_syls if k < len(hyp)) or "∅"
        spans.append(f"{ref[s]}→{got}")
    return " ".join(spans)
