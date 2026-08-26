#!/usr/bin/env python3
"""장시간 자동 발음 검사 루프.

  문항 × 목소리 × take × 샘플레이트 → TTS 합성 → 두 STT가 각각 받아적기
  → 자모 단위 비교 → SQLite 적재

같은 문항을 여러 목소리·여러 take로 돌리는 게 핵심이다. 한 번 틀린 것만으로는
TTS 발음 결함인지, 샘플러가 이번 take만 말아먹은 건지, STT가 못 알아들은
건지 구분할 수 없다. 조건을 바꿔가며 반복했을 때 **일관되게** 틀리는 것만
발음 규칙 결함이다. 판정은 report.py가 그 분포를 보고 한다.

중단해도 안전하다(Ctrl+C / 시간 초과). 다시 돌리면 안 한 조합부터 이어간다.
그래서 문항 순서를 고정 시드로 섞는다 — 앞에서 끊겨도 모든 축이 고르게
커버되도록.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import random
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402
import jamo  # noqa: E402
import judges  # noqa: E402

DEFAULT_DB = HERE / "data" / "audit.sqlite"
DEFAULT_WAV = HERE / "data" / "wav"
MOONSHINE_DIR = Path("/Users/nimo/Desktop/project/cpu_stt/models/moonshine-tiny-ko")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trial (
  id INTEGER PRIMARY KEY,
  key TEXT UNIQUE,
  item_id TEXT, text TEXT, expect TEXT, axis TEXT, grp TEXT, mode TEXT,
  sensitivity TEXT, target TEXT,
  voice TEXT, sr INTEGER, pron INTEGER, take INTEGER,
  gen_s REAL, dur_s REAL, wav TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS hyp (
  trial_id INTEGER, judge TEXT, text TEXT, secs REAL,
  ok INTEGER, cer REAL, target_cer REAL, diff TEXT, flagged INTEGER,
  PRIMARY KEY (trial_id, judge)
);
CREATE TABLE IF NOT EXISTS edit (
  trial_id INTEGER, judge TEXT, op TEXT, rule TEXT, env TEXT, in_target INTEGER
);
CREATE INDEX IF NOT EXISTS idx_hyp_judge ON hyp(judge, ok);
CREATE INDEX IF NOT EXISTS idx_edit_rule ON edit(judge, rule);
CREATE INDEX IF NOT EXISTS idx_trial_item ON trial(item_id);
"""

_stop = False


def _on_signal(signum, frame):
    global _stop
    _stop = True
    print(f"\n[중단 요청 — 현재 문항 마치고 종료합니다]", file=sys.stderr, flush=True)


class Worker:
    """TTS .venv에서 도는 상주 합성 프로세스."""

    def __init__(self, python: Path, script: Path):
        self.p = subprocess.Popen(
            [str(python), str(script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1, cwd=str(ROOT),
        )
        hello = json.loads(self.p.stdout.readline())
        self.voices: list[str] = hello["voices"]
        self.default_sr = hello["default_sample_rate"]
        self.pronunciation: dict = hello["pronunciation"]

    def synth(self, **req) -> dict:
        self.p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError("합성 워커가 죽었습니다")
        return json.loads(line)

    def close(self):
        try:
            self.p.stdin.write('{"quit":true}\n')
            self.p.stdin.flush()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def score(item: corpus.Item, hyp_text: str) -> tuple[bool, float, float, str, list]:
    """정답 후보 중 가장 잘 맞는 것으로 채점한다."""
    span = item.target_span()
    best = None
    for exp in item.expect:
        cer, edits = jamo.jamo_cer(exp, hyp_text)
        in_span = [e for e in edits if e.ref is not None and span[0] <= e.ref.syl < span[1]]
        n_t = max(1, len(in_span))
        t_bad = sum(1 for e in in_span if e.op != "eq")
        cand = (cer, t_bad / n_t, edits, exp)
        if best is None or cand[0] < best[0]:
            best = cand
    cer, tcer, edits, exp = best
    ok = jamo.normalize(exp) == jamo.normalize(hyp_text)
    return ok, cer, tcer, jamo.syllable_diff(exp, hyp_text), edits


def main() -> None:
    ap = argparse.ArgumentParser(description="TTS 발음 결함 자동 탐색")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--wav-dir", default=str(DEFAULT_WAV))
    ap.add_argument("--voices", default="M2,F1,M1,F3",
                    help="쉼표 구분. all 이면 10종 전부")
    ap.add_argument("--takes", type=int, default=3, help="같은 조건 반복 횟수")
    ap.add_argument("--rates", default="8000,16000",
                    help="출력 sample rate. keep 이면 config 설정 그대로")
    ap.add_argument("--pron", default="off", choices=["off", "on", "both"],
                    help="config 발음 교정 사전 적용 여부")
    ap.add_argument("--candidates", type=int, default=None,
                    help="best-of-N 후보 수. 미지정이면 config 설정(운용과 동일)")
    ap.add_argument("--no-carrier", action="store_true")
    ap.add_argument("--include-nonword", action="store_true",
                    help="비단어 짝도 합성한다 (기본은 제외 — 항상 오답이라 낭비)")
    ap.add_argument("--extra", default="", help="추가 텍스트 파일 (쉼표 구분)")
    ap.add_argument("--only", default="",
                    help="문항 id/축에 이 문자열이 든 것만 (쉼표로 여러 개)")
    ap.add_argument("--hours", type=float, default=0.0, help="이 시간이 지나면 종료")
    ap.add_argument("--limit", type=int, default=0, help="최대 시행 수")
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--keep-all-wav", action="store_true",
                    help="정답인 wav도 남긴다 (디스크 많이 씀)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    db_path = Path(args.db)
    wav_dir = Path(args.wav_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    wav_dir.mkdir(parents=True, exist_ok=True)

    extra = [Path(p) for p in args.extra.split(",") if p.strip()]
    items = corpus.build(include_carrier=not args.no_carrier, extra_files=extra,
                         include_nonword=args.include_nonword)
    if args.only:
        pats = [p.strip() for p in args.only.split(",") if p.strip()]
        items = [i for i in items if any(p in i.id or p in i.axis for p in pats)]

    worker = None if args.dry_run else Worker(ROOT / ".venv" / "bin" / "python",
                                              HERE / "tts_worker.py")
    all_voices = worker.voices if worker else ["F1","F2","F3","F4","F5","M1","M2","M3","M4","M5"]
    voices = all_voices if args.voices == "all" else [v.strip() for v in args.voices.split(",")]
    rates: list = []
    for r in args.rates.split(","):
        r = r.strip()
        rates.append("keep" if r == "keep" else (None if r in ("none", "model") else int(r)))
    prons = {"off": [False], "on": [True], "both": [False, True]}[args.pron]

    plan = [(it, v, sr, pr, t)
            for it in items for v in voices for sr in rates
            for pr in prons for t in range(args.takes)]
    random.Random(args.seed).shuffle(plan)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    done = {r[0] for r in conn.execute("SELECT key FROM trial")}

    def key_of(it, v, sr, pr, t):
        return f"{it.id}|{v}|{sr}|{int(pr)}|{t}|{args.candidates}"

    todo = [p for p in plan if key_of(*p) not in done]
    print(f"문항 {len(items)} · 목소리 {len(voices)} · rate {rates} · pron {prons} "
          f"· take {args.takes}", file=sys.stderr)
    print(f"전체 조합 {len(plan)} / 이미 완료 {len(plan)-len(todo)} / 이번에 할 것 {len(todo)}",
          file=sys.stderr)
    if args.dry_run:
        return

    moon = judges.MoonshineJudge(MOONSHINE_DIR)
    whis = judges.WhisperJudge()
    judge_list = [moon, whis]

    t_start = time.time()
    n = 0
    n_flag = 0
    for it, voice, sr, pron, take in todo:
        if _stop:
            break
        if args.hours and (time.time() - t_start) > args.hours * 3600:
            print("[지정한 시간 도달 — 종료]", file=sys.stderr)
            break
        if args.limit and n >= args.limit:
            break

        k = key_of(it, voice, sr, pron, take)
        # 파일명은 조합 키의 안정적 해시로 — 프로세스마다 달라지는 hash()를 쓰면
        # 재개했을 때 같은 조합이 다른 파일을 가리킨다.
        wav = wav_dir / (hashlib.sha1(k.encode()).hexdigest()[:16] + ".wav")
        r = worker.synth(text=it.text, out=str(wav), voice=voice,
                         sample_rate=sr, pron=pron, candidates=args.candidates)
        if not r.get("ok"):
            print(f"[합성 실패] {it.id} {voice}: {r.get('error')}", file=sys.stderr)
            continue

        audio = judges.load_16k(wav)
        cur = conn.execute(
            "INSERT OR IGNORE INTO trial (key,item_id,text,expect,axis,grp,mode,"
            "sensitivity,target,voice,sr,pron,take,gen_s,dur_s,wav,ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (k, it.id, it.text, json.dumps(it.expect, ensure_ascii=False), it.axis,
             it.group, it.mode, "low" if it.nonword else it.sensitivity, it.target, voice,
             r["sr"], int(pron), take, r["gen_s"], r["dur_s"], str(wav), time.time()))
        trial_id = cur.lastrowid if cur.rowcount else conn.execute(
            "SELECT id FROM trial WHERE key=?", (k,)).fetchone()[0]

        any_bad = False
        for J in judge_list:
            t0 = time.time()
            hyp = J.transcribe(audio)
            secs = time.time() - t0
            halluc = judges.looks_hallucinated(hyp, it.expect[0])
            ok, cer, tcer, diff, edits = score(it, hyp)
            flagged = int((not ok) and not halluc)
            any_bad = any_bad or bool(flagged)
            conn.execute(
                "INSERT OR REPLACE INTO hyp VALUES (?,?,?,?,?,?,?,?,?)",
                (trial_id, J.name, hyp, secs, int(ok), cer, tcer, diff, flagged))
            if flagged:
                span = it.target_span()
                conn.executemany(
                    "INSERT INTO edit VALUES (?,?,?,?,?,?)",
                    [(trial_id, J.name, e.op, e.rule_key(), e.env_key(),
                      int(e.ref is not None and span[0] <= e.ref.syl < span[1]))
                     for e in edits if e.op != "eq"])

        # 결함 후보의 wav만 남긴다. 이 루프의 최종 산출물은 "들어볼 파일 목록"이라,
        # 정답인 wav까지 쌓아두면 디스크만 먹고 쓸 일이 없다.
        if not any_bad and not args.keep_all_wav:
            wav.unlink(missing_ok=True)
            conn.execute("UPDATE trial SET wav='' WHERE id=?", (trial_id,))
        else:
            n_flag += 1

        n += 1
        if n % 10 == 0:
            conn.commit()
            el = time.time() - t_start
            rate = n / el * 3600
            print(f"  {n}/{len(todo)}  결함후보 {n_flag}  "
                  f"{rate:.0f}건/시간  경과 {el/60:.1f}분", file=sys.stderr, flush=True)

    conn.commit()
    conn.close()
    worker.close()
    el = time.time() - t_start
    print(f"\n완료: {n}건 / {el/60:.1f}분 / 결함후보 {n_flag}건", file=sys.stderr)
    print(f"리포트: .venv/bin/python report.py --db {db_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
