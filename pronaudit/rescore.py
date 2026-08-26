"""저장된 STT 결과를 표면 발음형 기준으로 다시 채점한다.

합성은 다시 하지 않는다. trial/hyp 테이블에 원문과 STT 텍스트가 그대로
남아 있으므로, 채점 규칙만 바꿔 12시간치 시행을 통째로 재해석할 수 있다.

바뀌는 것 세 가지.
  1. 표기 대신 표면 발음형으로 비교 (조타/좋다, 왜국/외국, 패/폐가 정답)
  2. STT가 숫자·라틴문자를 그대로 되뱉으면 무판정 (07시→"07시"는 TTS가
     뭐라고 읽었는지 알 수 없다. 오답도 정답도 아니다)
  3. 표준이 아닌 조음위치 동화까지 맞으면 "동음충돌"로 따로 표시 (함미/한미)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

import jamo
import phonology

DEFAULT_DB = Path(__file__).parent / "data" / "audit.sqlite"

_DIGIT = re.compile(r"\d")
_LATIN = re.compile(r"[A-Za-z]{2,}")
_KEEP = re.compile(r"[0-9A-Za-z가-힣]+")


def squash(s: str) -> str:
    return "".join(_KEEP.findall(unicodedata.normalize("NFC", s))).lower()


def unjudgeable(text: str, hyp: str) -> bool:
    """STT가 표기를 그대로 되돌려준 경우 — 무엇이 소리났는지 알 수 없다."""
    if _DIGIT.search(hyp) and _DIGIT.search(text):
        return True
    src = squash(text)
    for run in _LATIN.findall(hyp):
        if run.lower() in src:
            return True
    return False


def score(text: str, expects: list[str], target: str, hyp_text: str):
    """(judgeable, ok, kind, cer, tcer, diff, edits)"""
    if unjudgeable(text, hyp_text):
        return False, False, "무판정", 0.0, 0.0, "", []

    sh = phonology.surface(hyp_text)
    sh_loose = phonology.surface(hyp_text, loose=True)

    best = None
    ok = False
    loose_ok = False
    for exp in expects:
        se = phonology.surface(exp)
        if se == sh:
            ok = True
        if phonology.surface(exp, loose=True) == sh_loose:
            loose_ok = True
        cer, edits = jamo.jamo_cer(se, sh)
        # 채점 대상 구간은 표기 기준으로 잡고 표면형에 그대로 쓴다.
        # surface()는 음절 수를 바꾸지 않으므로 인덱스가 유지된다.
        if target:
            full, tgt = jamo.normalize(exp), jamo.normalize(target)
            i = full.find(tgt)
            span = (i, i + len(tgt)) if i >= 0 else (0, len(full))
        else:
            span = (0, len(jamo.normalize(exp)))
        in_span = [e for e in edits if e.ref is not None and span[0] <= e.ref.syl < span[1]]
        n_t = max(1, len(in_span))
        t_bad = sum(1 for e in in_span if e.op != "eq")
        cand = (cer, t_bad / n_t, edits, se, span)
        if best is None or cand[0] < best[0]:
            best = cand

    cer, tcer, edits, se, span = best
    if ok:
        kind, cer, tcer = "정답", 0.0, 0.0
    elif loose_ok:
        kind = "동음충돌"
    else:
        kind = "오답"
    diff = "" if ok else jamo.syllable_diff(se, sh)
    return True, ok, kind, cer, tcer, diff, (edits if kind == "오답" else [])


def main() -> None:
    ap = argparse.ArgumentParser(description="표면 발음형 기준 재채점")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(hyp)")}
    if "judgeable" not in cols:
        conn.execute("ALTER TABLE hyp ADD COLUMN judgeable INTEGER DEFAULT 1")
    if "kind" not in cols:
        conn.execute("ALTER TABLE hyp ADD COLUMN kind TEXT")
    if "ok_orth" not in cols:
        conn.execute("ALTER TABLE hyp ADD COLUMN ok_orth INTEGER")
        conn.execute("UPDATE hyp SET ok_orth = ok")
    conn.commit()

    rows = conn.execute("""
        SELECT h.trial_id, h.judge, h.text, t.text, t.expect, t.target
        FROM hyp h JOIN trial t ON t.id = h.trial_id
    """).fetchall()

    conn.execute("DELETE FROM edit")
    n = 0
    stats = {}
    for trial_id, judge, hyp_text, text, expect_json, target in rows:
        expects = json.loads(expect_json)
        judgeable, ok, kind, cer, tcer, diff, edits = score(
            text, expects, target or "", hyp_text)
        conn.execute(
            "UPDATE hyp SET ok=?, cer=?, target_cer=?, diff=?, judgeable=?, kind=? "
            "WHERE trial_id=? AND judge=?",
            (int(ok), cer, tcer, diff, int(judgeable), kind, trial_id, judge))
        if edits:
            if target:
                full, tgt = jamo.normalize(expects[0]), jamo.normalize(target)
                i = full.find(tgt)
                span = (i, i + len(tgt)) if i >= 0 else (0, len(full))
            else:
                span = (0, 10**6)
            conn.executemany(
                "INSERT INTO edit (trial_id,judge,op,rule,env,in_target) VALUES (?,?,?,?,?,?)",
                [(trial_id, judge, e.op, e.rule_key(), e.env_key(),
                  int(e.ref is not None and span[0] <= e.ref.syl < span[1]))
                 for e in edits if e.op != "eq"])
        stats[kind] = stats.get(kind, 0) + 1
        n += 1
        if n % 5000 == 0:
            conn.commit()
            print(f"  {n}/{len(rows)}")
    conn.commit()

    print(f"\n재채점 {n}건")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k:8s} {v:6d}  ({v / n:.1%})")
    before, after = conn.execute(
        "SELECT SUM(ok_orth=0), SUM(ok=0 AND judgeable=1) FROM hyp").fetchone()
    print(f"\n표기 기준 오답 {before} → 발음 기준 오답 {after}")
    conn.close()


if __name__ == "__main__":
    main()
