#!/usr/bin/env python3
"""수집한 시행을 발음 규칙으로 집계한다.

핵심은 "몇 번 틀렸나"가 아니라 "**어떤 조건에서 일관되게** 틀렸나"다.
같은 문항을 목소리·take·샘플레이트를 바꿔가며 여러 번 돌렸으므로, 그
분포로 원인을 갈라낼 수 있다:

  두 판정기 모두 거의 항상 틀림   → 표기가 모델을 잘못 이끄는 발음 규칙 결함
  moonshine만 틀림                 → 운용 STT가 못 받는 발음 (실전 지표)
  중간 대역에서 흔들림             → 샘플러 take 편차 (best-of-N 영역)
  8k만 틀림                        → 전화 대역 문제. 표기로는 못 고침
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
JUDGES = ("moonshine", "whisper")


def pct(x: float) -> str:
    return f"{x*100:4.0f}%"


def josa(word: str, pair: str = "으로/로") -> str:
    """받침 유무에 맞는 조사. 리포트를 사람이 읽는 문장으로 내기 위한 것."""
    a, b = pair.split("/")
    if not word:
        return b
    ch = word[-1]
    if not ("가" <= ch <= "힣"):
        return b
    jong = (ord(ch) - 0xAC00) % 28
    if pair == "으로/로":
        return b if jong in (0, 8) else a   # 받침 없음 · ㄹ 받침 → "로"
    return a if jong else b


def bar(x: float, w: int = 10) -> str:
    n = round(x * w)
    return "█" * n + "·" * (w - n)


def load(db: Path):
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def pair_direction(conn):
    """최소대립쌍이 어느 방향으로 무너지는지 센다.

    (cross[(원본, 짝, 판정기)], tried[(낱말, 판정기)], pairs[낱말] = 짝)
    """
    from jamo import normalize
    cross, tried, pairs = Counter(), Counter(), {}
    rows = conn.execute("""
        SELECT t.grp, t.target, h.judge, h.text, h.ok FROM trial t
        JOIN hyp h ON h.trial_id=t.id
        WHERE t.grp <> '' AND h.judgeable = 1
    """).fetchall()
    for r in rows:
        a_w, b_w = r["grp"].split("|")
        partner = b_w if r["target"] == a_w else a_w
        pairs[r["target"]] = partner
        tried[(r["target"], r["judge"])] += 1
        if not r["ok"] and normalize(partner) and normalize(partner) in normalize(r["text"]):
            cross[(r["target"], partner, r["judge"])] += 1
    return cross, tried, pairs


def per_word(conn, show_low: bool):
    """낱말 × 발음사전 × 판정기 × 위치별 오류율.

    문항 id가 아니라 **낱말** 단위로 묶는 게 중요하다. 파일럿에서 드러난 대로
    낱말 단독 발화는 STT의 사전확률 때문에 위양성 바닥이 높다 — 단독에서만
    틀리고 문장 안에서는 멀쩡하면 그건 TTS 결함이 아니다. 위치(단독/문말/문두)
    두 자리 이상에서 무너져야 발음 결함으로 본다.
    """
    rows = conn.execute("""
        SELECT t.item_id, t.text, t.axis, t.grp, t.mode, t.sensitivity, t.target,
               t.voice, t.sr, t.pron, t.wav, h.judge, h.ok, h.kind, h.text AS hyp
        FROM trial t JOIN hyp h ON h.trial_id = t.id
        WHERE h.judgeable = 1
    """).fetchall()

    def blank():
        return {"n": 0, "bad": 0, "homo": 0, "by_sr": defaultdict(lambda: [0, 0]),
                "by_mode": defaultdict(lambda: [0, 0]), "voices": set(),
                "hyps": Counter(), "wavs": []}

    agg = defaultdict(lambda: defaultdict(blank))
    meta = {}
    for r in rows:
        if r["sensitivity"] == "low" and not show_low:
            continue
        word = r["target"] or r["text"]
        k = (word, r["pron"])
        meta[k] = r
        a = agg[k][r["judge"]]
        a["n"] += 1
        a["voices"].add(r["voice"])
        a["by_sr"][r["sr"]][0] += 1
        a["by_mode"][r["mode"]][0] += 1
        if r["kind"] == "동음충돌":
            # 표준 발음으로는 다르지만 실제 발화에서 늘 일어나는 동화까지 맞다.
            # 소리가 사실상 같으므로 결함으로 세지 않고 따로 표시한다.
            a["homo"] += 1
        elif not r["ok"]:
            a["bad"] += 1
            a["by_sr"][r["sr"]][1] += 1
            a["by_mode"][r["mode"]][1] += 1
            a["hyps"][r["hyp"]] += 1
            if r["wav"]:
                a["wavs"].append(r["wav"])
    return agg, meta


def rate(pair) -> float:
    return pair[1] / pair[0] if pair[0] else 0.0


def lm_prior(m: dict, w: dict, pd: dict) -> str:
    """STT 언어모델이 더 흔한 낱말로 끌어당긴 것인가.

    최소대립쌍에서 한쪽으로만 쏠리고 반대 방향은 멀쩡하면, TTS가 그 소리를
    못 내는 게 아니라 STT가 빈도 높은 낱말을 골라 적은 것이다. "사외"가
    늘 "사회"로 적히는데 "사회"는 한 번도 "사외"가 되지 않는 상황이 그렇다.
    """
    for j in JUDGES:
        d = pd.get(j)
        if not d:
            continue
        fwd, n_self, rev, n_partner, partner = d
        if n_self < 4 or n_partner < 4:
            continue
        if fwd / n_self >= 0.5 and rev / n_partner <= 0.15:
            return partner
    return ""


def classify(m: dict, w: dict, pd: dict | None = None) -> tuple[str, str]:
    """(딱지, 근거). moonshine/whisper 오류율과 조건별 분포로 원인을 가른다."""
    mr = rate((m["n"], m["bad"]))
    wr = rate((w["n"], w["bad"]))

    hr = max(rate((m["n"], m["homo"])), rate((w["n"], w["homo"])))
    if hr >= 0.5 and max(mr, wr) < 0.4:
        return "동음충돌", "표준 발음은 달라도 실제 발화에선 같은 소리 — 판정 불가"

    # 위치 corroboration. 충분히 시행된(>=2) 자리만 판단에 쓴다 — 한 번 돌린
    # 자리를 "멀쩡했다"고 읽으면 위치 한정이라는 결론이 근거 없이 나온다.
    MIN = 2
    broke, held = set(), set()
    for j in (m, w):
        for mode, c in j["by_mode"].items():
            if c[0] < MIN:
                continue
            (broke if rate(c) >= 0.6 else held).add(mode)
    carrier_tested = {p for p in (broke | held) if p.startswith("carrier")}

    sr_gap = 0.0
    for j in (m, w):
        lo, hi = j["by_sr"].get(8000), j["by_sr"].get(16000)
        if lo and hi and lo[0] >= MIN and hi[0] >= MIN:
            sr_gap = max(sr_gap, rate(lo) - rate(hi))

    partner = lm_prior(m, w, pd or {})
    if partner and max(mr, wr) >= 0.5:
        return "STT어휘편향", f"한 방향으로만 '{partner}'{josa(partner)} 쏠림 — 반대는 멀쩡"

    if wr >= 0.6 and mr >= 0.6:
        if broke == {"bare"} and carrier_tested and not (carrier_tested & broke):
            return "단독발화한정", "문장 안에서는 멀쩡 — 짧은 발화 경로 의심"
        if len(broke) >= 2:
            return "발음규칙결함", f"{len(broke)}개 위치에서 일관되게 붕괴"
        return "결함의심", "무너졌지만 위치 한 자리뿐 — 반복 시행 필요"
    if sr_gap >= 0.4:
        return "전화대역", f"8k에서만 {sr_gap*100:.0f}%p 더 틀림"
    if mr >= 0.6 and wr < 0.3:
        return "운용STT취약", "whisper는 알아들음 — 운용 STT 쪽 한계"
    if 0.2 <= max(mr, wr) < 0.6:
        return "take편차", "조건에 따라 들쭉날쭉 — 샘플러 문제"
    if wr >= 0.6:
        return "발음규칙결함", "whisper까지 틀림"
    return "정상", ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(HERE / "data" / "audit.sqlite"))
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--min-trials", type=int, default=4,
                    help="이만큼 반복된 조합만 판정한다 (한두 번은 우연)")
    ap.add_argument("--json", default="", help="결함 후보를 JSON으로도 저장")
    ap.add_argument("--show-low", action="store_true",
                    help="감도 낮은 축(음운변동·실문장)도 표에 포함")
    args = ap.parse_args()

    conn = load(Path(args.db))
    total = conn.execute("SELECT COUNT(*) FROM trial").fetchone()[0]
    if not total:
        print("시행 기록이 없습니다. run.py 를 먼저 돌리세요.")
        return

    print("=" * 78)
    print(f"  시행 {total}건")
    for j in JUDGES:
        r = conn.execute("SELECT COUNT(*), SUM(1-ok) FROM hyp WHERE judge=? AND judgeable=1", (j,)).fetchone()
        if r[0]:
            print(f"  {j:10s} 오인식 {r[1] or 0}/{r[0]}  ({(r[1] or 0)/r[0]*100:.1f}%)")
    gen = conn.execute("SELECT AVG(gen_s), AVG(dur_s) FROM trial").fetchone()
    print(f"  평균 합성 {gen[0]:.2f}s / 음성 {gen[1]:.2f}s")
    print("=" * 78)

    agg, meta = per_word(conn, args.show_low)
    cross, tried, pairs = pair_direction(conn)

    def pd_for(word):
        out = {}
        for j in JUDGES:
            partner = pairs.get(word)
            if not partner:
                continue
            out[j] = (cross.get((word, partner, j), 0), tried.get((word, j), 0),
                      cross.get((partner, word, j), 0), tried.get((partner, j), 0),
                      partner)
        return out

    scored = []
    for (word, pron), by_judge in agg.items():
        m = by_judge.get("moonshine")
        w = by_judge.get("whisper")
        if not m or not w or min(m["n"], w["n"]) < args.min_trials:
            continue
        verdict, why = classify(m, w, pd_for(word))
        if verdict == "정상":
            continue
        r = meta[(word, pron)]
        scored.append({
            "word": word, "axis": r["axis"], "grp": r["grp"], "pron": bool(pron),
            "verdict": verdict, "why": why,
            "moonshine": round(rate((m["n"], m["bad"])), 3),
            "whisper": round(rate((w["n"], w["bad"])), 3),
            "n": m["n"], "voices": len(m["voices"]),
            "by_mode": {k: round(rate(v), 2)
                        for k, v in sorted(w["by_mode"].items()) if v[0]},
            "heard_moonshine": m["hyps"].most_common(3),
            "heard_whisper": w["hyps"].most_common(3),
            "wavs": (w["wavs"] + m["wavs"])[:3],
        })
    order = {"발음규칙결함": 0, "전화대역": 1, "단독발화한정": 2, "결함의심": 3,
             "take편차": 4, "운용STT취약": 5, "STT어휘편향": 6, "동음충돌": 7}
    scored.sort(key=lambda d: (order.get(d["verdict"], 9),
                               -(d["whisper"] + d["moonshine"])))

    print("\n■ 결함 후보 — 조건을 바꿔도 일관되게 틀리는 낱말\n")
    print(f"{'판정':13s} {'낱말':12s} {'축':10s} {'사전':4s} {'moon':>10s} {'whis':>10s}  들린 말")
    print("-" * 84)
    for d in scored[:args.top]:
        heard = ", ".join(f"{t!r}×{c}" for t, c in
                          (d["heard_whisper"] or d["heard_moonshine"])[:2])
        print(f"{d['verdict']:13s} {d['word']:12s} {d['axis']:10s} "
              f"{'ON ' if d['pron'] else 'off':4s} "
              f"{bar(d['moonshine'],5)}{pct(d['moonshine'])} "
              f"{bar(d['whisper'],5)}{pct(d['whisper'])}  {heard}")
        print(f"{'':13s} {'':12s} 위치별(whisper) {d['by_mode']}  — {d['why']}")
    if not scored:
        print("  (기준을 넘는 결함 후보 없음)")

    # ── 최소대립쌍 교차 ───────────────────────────────────────────────────────
    print("\n■ 최소대립쌍 방향성 — 어느 쪽으로 무너지는가")
    print("-" * 84)
    # 짝의 양방향을 한 줄에 놓아야 "대립이 무너졌다"와 "STT가 빈도 높은 쪽으로
    # 끌어당겼다"를 구분할 수 있다. 한 방향으로만 쏠리면 후자일 때가 많다.
    seen = set()
    lines = []
    for (src, dst, j), c in cross.items():
        key = tuple(sorted((src, dst))) + (j,)
        if key in seen:
            continue
        seen.add(key)
        x, y = key[0], key[1]
        fwd, rev = cross.get((x, y, j), 0), cross.get((y, x, j), 0)
        lines.append((fwd + rev, x, y, j, fwd, rev, tried.get((x, j), 0), tried.get((y, j), 0)))
    if lines:
        print(f"  {'대립쌍':20s} {'판정기':10s} {'→':>8s} {'←':>8s}   해석")
        for tot, x, y, j, fwd, rev, nx, ny in sorted(lines, reverse=True)[:20]:
            fr = f"{fwd}/{nx}" if nx else "-"
            rr = f"{rev}/{ny}" if ny else "-"
            if fwd and rev:
                note = "양방향 — 대립 자체가 무너짐"
            elif fwd:
                note = f"{x}{josa(x, '만/만')} {y}{josa(y)} 쏠림"
            else:
                note = f"{y}{josa(y, '만/만')} {x}{josa(x)} 쏠림"
            print(f"  {x+' / '+y:20s} {j:10s} {fr:>8s} {rr:>8s}   {note}")
    else:
        print("  (없음)")

    # ── 자모 혼동 규칙 ────────────────────────────────────────────────────────
    print("\n■ 자모 혼동 규칙 — 어떤 소리가 어떤 환경에서 무너지는가")
    print("-" * 78)
    # STT가 흔한 낱말로 끌어당긴 것(사외→사회)은 TTS가 낸 소리의 증거가
    # 아니다. 규칙 집계에 넣으면 "ㅇ이 ㅎ으로 바뀐다" 같은 없는 규칙이 만들어진다.
    skip = tuple(d["word"] for d in scored
                 if d["verdict"] in ("STT어휘편향", "동음충돌"))
    holes = ",".join("?" * len(skip)) or "''"
    for j in JUDGES:
        # 숫자·라틴문자·실문장 문항은 표기와 읽기가 애초에 다르다("3"→"삼").
        # 규칙 집계에 섞으면 혼동 행렬이 통째로 오염되므로 감도 높은 문항만 센다.
        rows = conn.execute(f"""
            SELECT e.rule, e.env, COUNT(*) c,
                   GROUP_CONCAT(DISTINCT COALESCE(NULLIF(t.target,''), t.text)) words
            FROM edit e JOIN trial t ON t.id = e.trial_id
            WHERE e.judge=? AND e.in_target=1 AND t.sensitivity='high'
              AND COALESCE(NULLIF(t.target,''), t.text) NOT IN ({holes})
            GROUP BY e.rule, e.env ORDER BY c DESC LIMIT 12
        """, (j, *skip)).fetchall()
        if not rows:
            continue
        print(f"\n  [{j}]")
        for r in rows:
            ex = ",".join((r["words"] or "").split(",")[:3])
            print(f"    {r['rule']:20s} {r['env']:20s} {r['c']:4d}회  {ex}")

    # ── 발음사전 효과 ─────────────────────────────────────────────────────────
    both = conn.execute("""
        SELECT t.item_id, t.pron, h.judge, COUNT(*) n, SUM(1-h.ok) bad
        FROM trial t JOIN hyp h ON h.trial_id=t.id
        WHERE h.judgeable = 1
        GROUP BY t.item_id, t.pron, h.judge
    """).fetchall()
    byitem = defaultdict(dict)
    for r in both:
        byitem[(r["item_id"], r["judge"])][r["pron"]] = (r["n"], r["bad"])
    lines = []
    for (item_id, j), d in byitem.items():
        if 0 in d and 1 in d and min(d[0][0], d[1][0]) >= args.min_trials:
            off = d[0][1] / d[0][0]
            on = d[1][1] / d[1][0]
            if abs(off - on) >= 0.25:
                lines.append((off - on, item_id, j, off, on))
    if lines:
        print("\n■ 발음 교정 사전 효과 (--pron both 로 돌린 경우)")
        print("-" * 78)
        for gain, item_id, j, off, on in sorted(lines, reverse=True):
            arrow = "개선" if gain > 0 else "악화"
            print(f"  {item_id:28s} {j:10s} off {pct(off)} → on {pct(on)}  {arrow}")

    # ── 들어볼 목록 ───────────────────────────────────────────────────────────
    listen = [d for d in scored if d["wavs"]][:12]
    if listen:
        print("\n■ 직접 들어볼 파일 (상위 후보)")
        print("-" * 78)
        for d in listen:
            print(f"  {d['word']:14s} {d['verdict']:13s} {d['wavs'][0]}")
        print(f"\n  afplay {listen[0]['wavs'][0]}")

    if args.json:
        Path(args.json).write_text(json.dumps(scored, ensure_ascii=False, indent=2))
        print(f"\nJSON 저장: {args.json}")


if __name__ == "__main__":
    main()
