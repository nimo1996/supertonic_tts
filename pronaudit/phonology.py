"""한글 표기 → 표면 발음형.

왜 필요한가. STT는 *표기*를 뱉는다. TTS가 "조타"를 완벽하게 읽어도 STT는
[조타]를 듣고 훨씬 흔한 "좋다"라고 적는다. 표기끼리 자모 비교를 하면
이게 100% 오류로 잡히지만, 실제로는 TTS가 정확히 읽은 것이다.

그래서 원문과 STT 결과를 **둘 다** 표준 발음법대로 표면형으로 바꾼 뒤
비교한다. 좋다/조타, 납부/납뿌, 폭뢰/폭뇌, 왜국/외국, 패/폐가 모두 같은
소리로 접히고, 갑판/가판처럼 실제로 소리가 다른 것만 남는다.

일부러 적용하지 **않는** 규칙이 있다.
  · ㅎ 탈락 (영향→영양, 하함→하암) — 지금 찾고 있는 결함 그 자체다.
  · 조음위치 동화 (함미→한미, 신문→심문) — 표준이 아니고 수의적이다.
    strict에서는 빼고, loose에서만 적용해 "동음충돌"로 따로 표시한다.
양쪽에 똑같이 적용되므로 규칙이 조금 어긋나도 대부분 상쇄되지만,
위 두 가지는 한쪽으로만 작동해 진짜 결함을 지워버리므로 제외한다.
"""
from __future__ import annotations

import re
import unicodedata

from jamo import BASE, CHO, JUNG, JONG

# 격음화: ㅎ + 평음 → 격음
ASPIRATE = {"ㄱ": "ㅋ", "ㄷ": "ㅌ", "ㅈ": "ㅊ", "ㅅ": "ㅆ", "ㅂ": "ㅍ"}
# 경음화: 폐쇄음 뒤 평음 → 된소리
TENSE = {"ㄱ": "ㄲ", "ㄷ": "ㄸ", "ㅂ": "ㅃ", "ㅅ": "ㅆ", "ㅈ": "ㅉ"}
# 받침 중화 (평파열음화)
NEUTRAL = {"ㄲ": "ㄱ", "ㅋ": "ㄱ",
           "ㅅ": "ㄷ", "ㅆ": "ㄷ", "ㅈ": "ㄷ", "ㅊ": "ㄷ", "ㅌ": "ㄷ", "ㅎ": "ㄷ",
           "ㅍ": "ㅂ"}
# 겹받침 → (남는 받침, 뒤로 넘어가는 자음)
CLUSTER = {
    "ㄳ": ("ㄱ", "ㅅ"), "ㄵ": ("ㄴ", "ㅈ"), "ㄶ": ("ㄴ", "ㅎ"),
    "ㄺ": ("ㄹ", "ㄱ"), "ㄻ": ("ㄹ", "ㅁ"), "ㄼ": ("ㄹ", "ㅂ"),
    "ㄽ": ("ㄹ", "ㅅ"), "ㄾ": ("ㄹ", "ㅌ"), "ㄿ": ("ㄹ", "ㅍ"),
    "ㅀ": ("ㄹ", "ㅎ"), "ㅄ": ("ㅂ", "ㅅ"),
}
# 겹받침이 자음 앞에서 줄어드는 대표음
CLUSTER_CODA = {"ㄳ": "ㄱ", "ㄵ": "ㄴ", "ㄶ": "ㄴ", "ㄺ": "ㄱ", "ㄻ": "ㅁ",
                "ㄼ": "ㄹ", "ㄽ": "ㄹ", "ㄾ": "ㄹ", "ㄿ": "ㅂ", "ㅀ": "ㄹ",
                "ㅄ": "ㅂ"}
NASALIZE = {"ㄱ": "ㅇ", "ㄷ": "ㄴ", "ㅂ": "ㅁ"}

_HANGUL = re.compile(r"[가-힣]")


def _split(text: str) -> list[list[str]]:
    out = []
    for ch in _HANGUL.findall(unicodedata.normalize("NFC", text)):
        code = ord(ch) - BASE
        cho, rest = divmod(code, 588)
        jung, jong = divmod(rest, 28)
        out.append([CHO[cho], JUNG[jung], JONG[jong]])
    return out


def _join(syls: list[list[str]]) -> str:
    return "".join(
        chr(BASE + CHO.index(c) * 588 + JUNG.index(v) * 28 + JONG.index(t))
        for c, v, t in syls
    )


def _coda_head(t: str) -> str:
    """겹받침에서 앞에 남는 자음."""
    return CLUSTER[t][0] if t in CLUSTER else t


def _coda_tail(t: str) -> str | None:
    """겹받침에서 뒤 음절로 넘어가는 자음."""
    return CLUSTER[t][1] if t in CLUSTER else None


def surface(text: str, loose: bool = False) -> str:
    """표기 → 표면 발음형(한글 음절열)."""
    s = _split(text)
    n = len(s)

    # 1) ㅎ 축약·격음화. 중화보다 먼저 해야 좋다→조타가 나온다.
    for i in range(n - 1):
        t, nxt = s[i][2], s[i + 1]
        c = nxt[0]
        if t in ("ㅎ", "ㄶ", "ㅀ"):
            residual = {"ㅎ": " ", "ㄶ": "ㄴ", "ㅀ": "ㄹ"}[t]
            if c in ("ㄱ", "ㄷ", "ㅈ", "ㅅ"):
                nxt[0] = ASPIRATE[c]
                # 굳히다 → 구티다 → 구치다: 격음화로 생긴 ㅌ도 구개음화한다
                if nxt[0] == "ㅌ" and nxt[1] == "ㅣ":
                    nxt[0] = "ㅊ"
                s[i][2] = residual
            elif c == "ㄴ":
                s[i][2] = "ㄴ" if t in ("ㅎ", "ㄶ") else "ㄹ"
            elif c == "ㅇ":
                # ㅎ은 탈락, 남은 자음은 연음
                s[i][2] = " "
                if residual != " ":
                    nxt[0] = residual
            else:
                s[i][2] = residual
        elif c == "ㅎ":
            head = _coda_head(t)
            if head in ASPIRATE and head != "ㅅ":
                nxt[0] = ASPIRATE[head]
                s[i][2] = " " if t not in CLUSTER else CLUSTER[t][0]
                if t in CLUSTER:
                    # ㄺ+ㅎ → ㄹ+ㅋ
                    s[i][2] = CLUSTER[t][0]
                    nxt[0] = ASPIRATE[CLUSTER[t][1]] if CLUSTER[t][1] in ASPIRATE else nxt[0]

    # 2) 구개음화 — ㄷ/ㅌ 받침 + '이' → ㅈ/ㅊ
    for i in range(n - 1):
        t, nxt = s[i][2], s[i + 1]
        if nxt[0] == "ㅇ" and nxt[1] == "ㅣ":
            if t == "ㄷ":
                nxt[0], s[i][2] = "ㅈ", " "
            elif t == "ㅌ":
                nxt[0], s[i][2] = "ㅊ", " "
            elif t == "ㄾ":
                nxt[0], s[i][2] = "ㅊ", "ㄹ"

    # 3) 연음 — 받침 + 초성 ㅇ
    for i in range(n - 1):
        t, nxt = s[i][2], s[i + 1]
        if t in (" ", "ㅇ") or nxt[0] != "ㅇ":
            continue
        tail = _coda_tail(t)
        if tail is not None:
            s[i][2] = CLUSTER[t][0]
            nxt[0] = tail
        else:
            s[i][2] = " "
            nxt[0] = t

    # 4) 자음군 단순화 + 받침 중화
    for i in range(n):
        t = s[i][2]
        if t in CLUSTER_CODA:
            t = CLUSTER_CODA[t]
        s[i][2] = NEUTRAL.get(t, t)

    # 5) 경음화 · 비음화 · 유음화. 앞 음절 종성이 바뀌면 그 앞 경계에도
    #    영향을 주므로 변화가 없을 때까지 돌린다.
    for _ in range(3):
        changed = False
        for i in range(n - 1):
            t, nxt = s[i][2], s[i + 1]
            c = nxt[0]
            if t == " ":
                continue
            if t in ("ㄱ", "ㄷ", "ㅂ"):
                if c in TENSE:                       # 경음화
                    nxt[0] = TENSE[c]
                    changed = True
                elif c in ("ㄴ", "ㅁ"):               # 비음화
                    s[i][2] = NASALIZE[t]
                    changed = True
                elif c == "ㄹ":                       # 폭뢰 → 퐁뇌
                    s[i][2] = NASALIZE[t]
                    nxt[0] = "ㄴ"
                    changed = True
            elif t in ("ㅁ", "ㅇ") and c == "ㄹ":      # 종로 → 종노
                nxt[0] = "ㄴ"
                changed = True
            elif t == "ㄴ" and c == "ㄹ":              # 신라 → 실라
                s[i][2] = "ㄹ"
                changed = True
            elif t == "ㄹ" and c == "ㄴ":              # 설날 → 설랄
                nxt[0] = "ㄹ"
                changed = True
        if not changed:
            break

    # 6) 현대 서울말에서 이미 합류한 모음들
    for i in range(n):
        c, v, _t = s[i]
        if v == "ㅒ":
            v = "ㅖ"
        elif v == "ㅐ":
            v = "ㅔ"
        elif v in ("ㅙ", "ㅞ"):
            v = "ㅚ"
        if v == "ㅖ" and c not in ("ㅇ", "ㄹ"):        # 폐 → [페]
            v = "ㅔ"
        if v == "ㅢ" and c != "ㅇ":                    # 희 → [히]
            v = "ㅣ"
        s[i][1] = v

    if loose:
        # 조음위치 동화 — 표준은 아니지만 실제 발화에서 거의 항상 일어난다.
        for i in range(n - 1):
            t, c = s[i][2], s[i + 1][0]
            if t == "ㄴ" and c in ("ㅂ", "ㅃ", "ㅍ", "ㅁ"):
                s[i][2] = "ㅁ"
            elif t == "ㄴ" and c in ("ㄱ", "ㄲ", "ㅋ"):
                s[i][2] = "ㅇ"
            elif t == "ㅁ" and c in ("ㄱ", "ㄲ", "ㅋ"):
                s[i][2] = "ㅇ"
            elif t == "ㄷ" and c in ("ㄱ", "ㄲ", "ㅋ"):
                s[i][2] = "ㄱ"
            elif t == "ㄷ" and c in ("ㅂ", "ㅃ", "ㅍ"):
                s[i][2] = "ㅂ"

    return _join(s)


if __name__ == "__main__":
    CASES = [
        ("좋다", "조타"), ("조타", "조타"),
        ("납부기한", "납뿌기한"), ("납부", "납뿌"),
        ("폭뢰", "퐁뇌"), ("폭뇌", "퐁뇌"),
        ("왜국", "외국"), ("외국", "외국"),
        ("패", "페"), ("폐", "페"),
        ("갑판", "갑판"), ("가판", "가판"),
        ("신라", "실라"), ("종로", "종노"), ("해돋이", "헤도지"),
        ("학교", "학꾜"), ("백로", "벵노"), ("굳히다", "구치다"),
        ("맏이", "마지"), ("읽다", "익따"), ("값", "갑"),
        ("영향", "영향"), ("영양", "영양"),   # ㅎ 탈락은 접지 않는다
        ("하함", "하함"), ("하암", "하암"),
        ("사외", "사외"), ("사회", "사회"),
        ("함미", "함미"), ("한미", "한미"),
    ]
    bad = 0
    for src, want in CASES:
        got = surface(src)
        flag = "ok " if got == want else "XX "
        if got != want:
            bad += 1
        print(f"  {flag}{src} → {got}  (기대 {want})")
    print(f"\nloose: 함미={surface('함미', loose=True)} 한미={surface('한미', loose=True)}")
    print(f"실패 {bad}/{len(CASES)}")
