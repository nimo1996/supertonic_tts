#!/usr/bin/env python3
"""합성 워커 — 프로젝트 .venv(TTS 쪽)에서 돌아가는 상주 프로세스.

판정용 STT는 sherpa-onnx / mlx 의존성이 필요하고, 그걸 TTS의 .venv에 섞으면
build.sh의 PyInstaller 패키징에 불필요한 위험이 생긴다. 그래서 검사 도구는
자기 venv에서 돌고, 합성만 이 워커에 stdin/stdout으로 시킨다. 문장마다
프로세스를 새로 띄우면 305MB 모델을 매번 다시 읽어야 해서 상주로 둔다.

프로토콜: stdin 한 줄 = 요청 JSON, stdout 한 줄 = 응답 JSON.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 응답 전용 fd를 따로 확보한 뒤 fd 1을 stderr로 덮는다. supertonic/onnxruntime이
# 무엇을 찍든(파이썬 레벨이든 C 레벨이든) 응답 스트림을 오염시킬 수 없게 한다.
_RESP_FD = os.dup(1)
os.dup2(2, 1)
sys.stdout = sys.stderr


def _send(obj: dict) -> None:
    os.write(_RESP_FD, (json.dumps(obj, ensure_ascii=False) + "\n").encode())


def main() -> None:
    from tts import load_config, get_engine

    config = load_config()
    engine = get_engine(config)
    base_pron = dict(engine.pronunciation)
    base_rules = list(engine._pron_rules)
    default_sr = engine.sample_rate

    _send({"ready": True, "voices": engine.get_voices(),
           "default_sample_rate": default_sr,
           "pronunciation": base_pron})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            _send({"ok": False, "error": f"bad json: {e}"})
            continue
        if req.get("quit"):
            break
        try:
            # 발음 교정 사전 on/off. 끄고 돌려야 새 결함이 보이고, 켜고 돌리면
            # 이미 넣은 교정이 실제로 듣는지 확인된다(양성 대조군).
            if req.get("pron", True):
                engine.pronunciation, engine._pron_rules = dict(base_pron), list(base_rules)
            else:
                engine.pronunciation, engine._pron_rules = {}, []

            sr = req.get("sample_rate", "keep")
            engine.sample_rate = default_sr if sr == "keep" else (None if sr is None else int(sr))

            out = req["out"]
            gen_s = engine.generate_to_file(
                text=req["text"],
                output_path=out,
                lang=req.get("lang", "ko"),
                voice=req.get("voice"),
                speed=req.get("speed"),
                steps=req.get("steps"),
                gap=req.get("gap", 0.4),
                verbose=False,
                candidates=req.get("candidates"),
            )
            import soundfile as sf
            info = sf.info(out)
            _send({"ok": True, "path": out, "gen_s": round(gen_s, 3),
                   "dur_s": round(info.frames / info.samplerate, 3),
                   "sr": info.samplerate})
        except Exception as e:  # 한 문항이 죽어도 장시간 루프는 계속 가야 한다
            _send({"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
