"""낱말이 아니라 **글자 조합**의 실패율을 낸다.

숫자·라틴문자 문항("07시" → "영칠시")은 뺀다. 거기서 나는 오류는 소리를
못 낸 게 아니라 읽기 방식을 틀린 것이라, 자모 조합 통계에 섞으면 없는
규칙이 만들어진다.

"어뢰가 어래로 들린다"는 낱말 발견이지 규칙이 아니다. 규칙이 되려면
그 조합이 나온 **모든** 자리를 세서 "ㄹ 초성 앞 ㅚ는 몇 %가 무너지나"를
말할 수 있어야 한다. 분자(틀린 횟수)만 세면 자주 나오는 조합이 무조건
1등이 되므로, 분모(그 조합이 등장한 총 횟수)를 반드시 같이 센다.

또 하나 — 서로 다른 낱말 몇 개에서 나왔는지를 센다. 낱말 하나에서만
나온 100%는 규칙이 아니라 그 낱말 이야기다.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import jamo
import phonology
import rescore

HERE = Path(__file__).resolve().parent
JUDGES = ("moonshine", "whisper")


class Cell:
    __slots__ = ("n", "bad", "words", "bad_words", "voices", "examples")

    def __init__(self):
        self.n = 0
        self.bad = 0
        self.words = set()
        self.bad_words = set()
        self.voices = set()
        self.examples = Counter()

    def add(self, bad: bool, word: str, voice: str, ex: str = ""):
        self.n += 1
        self.words.add(word)
        self.voices.add(voice)
        if bad:
            self.bad += 1
            self.bad_words.add(word)
            if ex:
                self.examples[ex] += 1

    @property
    def rate(self) -> float:
        return self.bad / self.n if self.n else 0.0


def collect(conn, judge: str, max_cer: float = 0.6):
    """토큰 자리마다 (조합, 무너졌나)를 센다."""
    rows = conn.execute("""
        SELECT t.text, t.expect, t.target, t.voice, t.mode, h.text AS hyp
        FROM trial t JOIN hyp h ON h.trial_id = t.id
        WHERE h.judge = ? AND h.judgeable = 1 AND t.sensitivity = 'high'
          AND t.text NOT GLOB '*[0-9A-Za-z%]*'
    """, (judge,)).fetchall()

    tables = {k: defaultdict(Cell) for k in
              ("boundary", "onset_nucleus", "nucleus_coda", "jamo", "onset_pos")}
    total = [0, 0]

    for text, expect_json, target, voice, mode, hyp in rows:
        expects = json.loads(expect_json)
        sh = phonology.surface(hyp)
        best = None
        for exp in expects:
            se = phonology.surface(exp)
            cer, edits = jamo.jamo_cer(se, sh)
            if best is None or cer < best[0]:
                best = (cer, edits, se)
        _, edits, se = best
        if best[0] > max_cer:
            continue   # 통째로 못 알아들은 것 — 자리별 귀속이 불가능하다

        # 쉼표로 끊어 읽는 자리는 조합이 아니다. 조각 경계를 넘는 관찰은 뺀다.
        parts = phonology.surface_parts(json.loads(expect_json)[0])
        chunk_of, chunk_text, at = {}, {}, 0
        for ci, part in enumerate(parts):
            for k in range(len(part)):
                chunk_of[at + k] = ci
            chunk_text[ci] = part
            at += len(part)

        ref = jamo.to_tokens(se)
        if not ref:
            continue
        # 각 원문 토큰이 무너졌는지 — 치환/삭제면 무너진 것.
        broke = {}
        got = {}
        for e in edits:
            if e.ref is None:
                continue
            i = (e.ref.syl, e.ref.kind)
            broke[i] = e.op != "eq"
            got[i] = (e.hyp.jamo if e.hyp is not None else "∅")

        base_word = target or text
        for idx, tok in enumerate(ref):
            key = (tok.syl, tok.kind)
            if key not in broke:
                continue
            bad = broke[key]

            total[0] += 1
            total[1] += bad
            out = f"{tok.jamo}→{got[key]}"

            here = chunk_of.get(tok.syl, 0)
            # 격자는 발화 하나에 토큰 여러 개를 담으므로, 지지 근거를 셀 때는
            # 발화가 아니라 토큰을 센다. 안 그러면 "낱말 1개"로 보인다.
            word = chunk_text[here] if mode == "grid" else base_word
            prev = ref[idx - 1] if idx else None
            nxt = ref[idx + 1] if idx + 1 < len(ref) else None
            if prev is not None and chunk_of.get(prev.syl, 0) != here:
                prev = None      # 앞 조각 끝 — 끊어 읽으므로 이어지지 않는다
            if nxt is not None and chunk_of.get(nxt.syl, 0) != here:
                nxt = None

            # 낱말 안 자모 자체의 기본 난이도
            tables["jamo"][tok.key()].add(bad, word, voice, out)

            # 앞 음절 종성 × 이 음절 초성 — 사람이 말하는 "글자 조합"
            if tok.kind == "C":
                left = prev.jamo if (prev and prev.kind == "T") else "∅"
                tables["boundary"][f"{left} + {tok.jamo}"].add(bad, word, voice, out)
                pos = ("어두" if prev is None else
                       ("종성뒤" if left != "∅" else "모음뒤"))
                tables["onset_pos"][f"{tok.jamo} ({pos})"].add(bad, word, voice, out)
                if nxt and nxt.kind == "V":
                    tables["onset_nucleus"][f"{tok.jamo}{nxt.jamo}"].add(bad, word, voice, out)
            elif tok.kind == "V":
                c = prev.jamo if (prev and prev.kind == "C") else "∅"
                tables["onset_nucleus"][f"{c}{tok.jamo}"].add(bad, word, voice, out)
                t = nxt.jamo if (nxt and nxt.kind == "T") else "∅"
                tables["nucleus_coda"][f"{tok.jamo} + {t}"].add(bad, word, voice, out)
            else:  # 종성
                nc = nxt.jamo if (nxt and nxt.kind == "C") else "$"
                tables["boundary"][f"{tok.jamo} + {nc}"].add(bad, word, voice, out)

    return tables, total


def show(title: str, cells: dict, base: float, min_words: int, min_n: int, top: int):
    rows = [(k, c) for k, c in cells.items()
            if c.n >= min_n and len(c.words) >= min_words and c.rate > base]
    rows.sort(key=lambda kc: -(kc[1].rate - base) * (kc[1].n ** 0.5))
    if not rows:
        print(f"\n  {title}: 기준을 넘는 조합 없음 "
              f"(낱말 {min_words}개 이상 · {min_n}회 이상)")
        return []
    print(f"\n  {title}   (기준선 {base*100:.1f}%)")
    print(f"    {'조합':12s} {'실패율':>7s} {'시행':>6s} {'낱말':>4s} {'배수':>5s}  "
          f"주로 이렇게 → / 낱말")
    for k, c in rows[:top]:
        ex = ", ".join(f"{e}" for e, _ in
                       sorted(c.examples.items(), key=lambda x: -x[1])[:2])
        ws = ",".join(sorted(c.bad_words)[:3])
        print(f"    {k:12s} {c.rate*100:6.1f}% {c.n:6d} {len(c.words):4d} "
              f"{c.rate/base if base else 0:5.1f}x  {ex:14s} {ws}")
    return rows


def agree(per_judge: dict, tables_key: str, title: str,
          min_words: int, min_n: int, lift: float, top: int):
    """두 판정기가 **함께** 무너진 조합만 남긴다.

    무의미 음절은 STT가 가까운 실재 낱말로 바꿔 적는 편향이 있고, 그게
    이 격자의 바닥(18% 안팎)을 만든다. 그런데 그 편향은 모델의 언어모델에서
    오는 것이라 구조가 다른 두 모델에서 같은 자리에 나타날 이유가 없다.
    둘 다 같은 조합에서 무너지면 소리 쪽 원인일 가능성이 훨씬 높다.
    """
    rows = []
    for k in set(per_judge["moonshine"][0][tables_key]) & set(per_judge["whisper"][0][tables_key]):
        cells = {j: per_judge[j][0][tables_key][k] for j in JUDGES}
        bases = {j: per_judge[j][1] for j in JUDGES}
        if any(cells[j].n < min_n or len(cells[j].words) < min_words for j in JUDGES):
            continue
        lifts = {j: (cells[j].rate / bases[j] if bases[j] else 0) for j in JUDGES}
        if min(lifts.values()) < lift:
            continue
        rows.append((min(lifts.values()), k, cells, lifts))
    rows.sort(reverse=True)
    print(f"\n  {title}  — 두 판정기 모두 기준선 {lift:.0f}배 이상")
    if not rows:
        print("    (해당 없음)")
        return
    print(f"    {'조합':10s} {'moon':>14s} {'whis':>14s} {'토큰':>4s}  주로 이렇게")
    for _, k, cells, lifts in rows[:top]:
        m, w = cells["moonshine"], cells["whisper"]
        ex = ", ".join(e for e, _ in
                       sorted((m.examples + w.examples).items(), key=lambda x: -x[1])[:3])
        print(f"    {k:10s} {m.rate*100:6.1f}%({lifts['moonshine']:4.1f}x) "
              f"{w.rate*100:6.1f}%({lifts['whisper']:4.1f}x) {len(m.words):4d}  {ex}")


def main() -> None:
    ap = argparse.ArgumentParser(description="글자 조합별 실패율")
    ap.add_argument("--db", default=str(HERE / "data" / "audit.sqlite"))
    ap.add_argument("--min-words", type=int, default=3,
                    help="서로 다른 낱말 이만큼에서 나와야 규칙 후보로 본다")
    ap.add_argument("--min-n", type=int, default=30)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--lift", type=float, default=2.0,
                    help="합의 표에서 요구하는 기준선 대비 배수")
    ap.add_argument("--max-cer", type=float, default=0.6,
                    help="이보다 심하게 틀린 시행은 자리별 귀속이 불가능해 뺀다")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    per_judge = {}
    for judge in JUDGES:
        tables, total = collect(conn, judge, args.max_cer)
        per_judge[judge] = (tables, total[1] / total[0] if total[0] else 0.0)

    print("=" * 86)
    print("  두 판정기 합의 — 규칙 후보")
    print("=" * 86)
    for key, title in (("boundary", "① 앞 종성 + 뒤 초성"),
                       ("onset_nucleus", "② 초성 + 중성"),
                       ("nucleus_coda", "③ 중성 + 종성"),
                       ("onset_pos", "④ 초성 위치별")):
        agree(per_judge, key, title, args.min_words, args.min_n, args.lift, args.top)
    print()

    for judge in JUDGES:
        tables, base = per_judge[judge]
        total = [0, 0]
        print("=" * 86)
        print(f"  [{judge}]  기준선 {base*100:.1f}%")
        print("=" * 86)
        show("① 앞 종성 + 뒤 초성 (경계 조합)", tables["boundary"],
             base, args.min_words, args.min_n, args.top)
        show("② 초성 + 중성 (음절 조합)", tables["onset_nucleus"],
             base, args.min_words, args.min_n, args.top)
        show("③ 중성 + 종성", tables["nucleus_coda"],
             base, args.min_words, args.min_n, args.top)
        show("④ 초성 위치별", tables["onset_pos"],
             base, args.min_words, args.min_n, args.top)
        show("⑤ 자모 자체", tables["jamo"],
             base, args.min_words, args.min_n, args.top)
        print()


if __name__ == "__main__":
    main()
