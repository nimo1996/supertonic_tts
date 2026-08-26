"""글자 조합 격자 — 낱말 목록 없이 규칙을 찾기 위한 코퍼스.

523개 손으로 고른 낱말로는 "규칙"을 말할 수 없다. "ㄹ+ㅎ이 무너진다"의
근거가 출항·입출항·1함대 세 낱말뿐이면, 그건 규칙이 아니라 그 낱말 이야기다.
조합마다 서로 다른 자리에서 수십 번씩 관찰해야 규칙이 된다.

한국어 낱말 사전이 없으므로 조합을 직접 만들어 쓴다. 실재하지 않는 음절
조합은 STT가 가까운 실재 낱말로 바꿔 적는 편향이 있는데, 이걸 이렇게 막는다.

  · **교차 배치** — 같은 음절이 여러 조합에 나오고, 같은 조합이 여러 음절
    틀에 나온다. 음절 자체의 편향은 조합들 사이에서 상쇄되고, 조합 효과만
    남는다. (낱말 하나에 갇힌 지금 코퍼스로는 불가능한 일이다.)
  · **자모 단위 채점** — 낱말이 통째로 맞았나가 아니라 자리마다 그 자모가
    살아남았나를 센다. "쿠역"이 "구역"으로 적혀도 무너진 건 자모 하나다.
  · **두 판정기 합의** — 구조가 다른 두 모델이 같은 조합에서 같이 무너져야
    조합 탓이다. 어휘 편향은 모델마다 다르게 나타난다.

측정 대상은 표면 발음형 기준이다. 종성은 표기 27종이 아니라 실제로 소리
나는 7종(+무종성)만 쓴다 — ㅋ/ㄲ은 어차피 [ㄱ]이라 따로 세면 같은 현상이
잘게 쪼개지기만 한다.
"""
from __future__ import annotations

import random

from corpus import Item
from jamo import compose

ONSETS = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")          # 19
NUCLEI = list("ㅏㅐㅑㅓㅔㅕㅗㅘㅚㅛㅜㅝㅟㅠㅡㅢㅣ")             # 17 (합류한 것 제외)
CODAS = ["", "ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅇ"]           # 표면 종성 7 + 무종성

# 한 발화에 몇 개를 담을까. 쉼표로 끊어 읽으므로 토큰 사이에는 음운변동이
# 넘어가지 않는다(phonology.surface 가 구두점에서 규칙을 끊는다).
PACK = 3


def _tok(c1, v1, t, c2, v2) -> str:
    return compose(c1, v1, t or " ") + compose(c2, v2, " ")


def boundary_items(seed: int = 7) -> list[Item]:
    """① 앞 음절 종성 × 뒤 음절 초성 — 8 × 19 = 152 조합.

    조합마다 서로 다른 모음 틀 3개에 넣는다. 같은 틀이 152개 조합 전부에
    쓰이므로, 틀에서 오는 편향은 조합 비교에서 상쇄된다.
    """
    frames = [("ㄱ", "ㅏ", "ㅏ"), ("ㅁ", "ㅣ", "ㅜ"), ("ㅂ", "ㅜ", "ㅓ")]
    toks = []
    for coda in CODAS:
        for onset in ONSETS:
            for fi, (c1, v1, v2) in enumerate(frames):
                toks.append((f"{coda or '∅'}+{onset}", fi,
                             _tok(c1, v1, coda, onset, v2)))
    return _pack(toks, "bd", "경계조합", seed)


def onset_nucleus_items(seed: int = 11) -> list[Item]:
    """② 초성 × 중성 — 19 × 17 = 323 조합. 앞에 무종성 음절을 붙여
    '모음 뒤 초성' 자리로 고정한다(종성 뒤는 ①이 맡는다)."""
    toks = []
    for onset in ONSETS:
        for v in NUCLEI:
            for fi, (c1, v1) in enumerate([("ㅇ", "ㅏ"), ("ㄷ", "ㅗ")]):
                toks.append((f"{onset}{v}", fi, _tok(c1, v1, "", onset, v)))
    return _pack(toks, "on", "초성중성", seed)


def nucleus_coda_items(seed: int = 13) -> list[Item]:
    """③ 중성 × 종성 — 17 × 7 = 119 조합. 종성이 뒤 음절 초성과 만나지
    않도록 뒤에 무종성 '아'를 두어 연음 자리로만 관찰한다."""
    toks = []
    for v in NUCLEI:
        for coda in CODAS[1:]:
            for fi, c1 in enumerate(["ㄱ", "ㅅ"]):
                toks.append((f"{v}+{coda}", fi,
                             compose(c1, v, coda) + compose("ㅇ", "ㅏ", " ")))
    return _pack(toks, "nc", "중성종성", seed)


def _pack(toks, prefix: str, axis: str, seed: int) -> list[Item]:
    """토큰을 쉼표로 묶어 발화로 만든다.

    묶는 순서는 섞는다. 같은 조합끼리 늘 붙어 있으면 앞뒤 토큰이 만드는
    운율까지 조합 효과에 섞여 들어간다.
    """
    rng = random.Random(seed)
    order = list(toks)
    rng.shuffle(order)
    items: list[Item] = []
    for k in range(0, len(order), PACK):
        chunk = order[k:k + PACK]
        text = ", ".join(t for _, _, t in chunk) + "."
        items.append(Item(
            id=f"grid:{prefix}:{k // PACK:04d}",
            text=text, expect=[text], axis=axis,
            group="", mode="grid", note=",".join(c for c, _, _ in chunk),
            target="", nonword=False, sensitivity="high"))
    return items


def build(which: str = "all") -> list[Item]:
    out: list[Item] = []
    if which in ("all", "boundary"):
        out += boundary_items()
    if which in ("all", "onset"):
        out += onset_nucleus_items()
    if which in ("all", "coda"):
        out += nucleus_coda_items()
    return out


if __name__ == "__main__":
    for which in ("boundary", "onset", "coda"):
        its = build(which)
        n_tok = sum(len(i.text.rstrip(".").split(", ")) for i in its)
        print(f"{which:9s} 발화 {len(its):4d} · 토큰 {n_tok:5d}")
        for i in its[:2]:
            print(f"    {i.id}  {i.text}   [{i.note}]")
    total = build("all")
    print(f"\n합계 발화 {len(total)}  → 목소리 10 × rate 2 = {len(total)*20} 시행")
