#!/usr/bin/env python3
"""Config 파일 없이 동작하는 최소 TTS API 서버.

api.py와 달리 config.yaml을 읽지 않는다 — 목소리/속도/품질/샘플레이트/게인 등
모든 합성 설정은 아래 DEFAULTS에 고정값으로 박혀 있다(배포판 config.yaml의
현재 운영값과 동일). 요청 바디에서 받는 값은 text / filename / soundEffect
셋뿐이다. 실행파일 1개(supertonic-api-lite) + sounds/ + 호출 스크립트만으로
배포한다.
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from engines.supertonic_engine import SupertonicEngine
from paths import base_dir

PROJECT_ROOT = base_dir()
SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

# config.yaml 없이 고정으로 쓰는 값 — 배포판 config.yaml의 운영값과 동일하게 맞춰둔다.
DEFAULTS = dict(
    host="0.0.0.0",
    port=9090,
    output_directory="output",
    voice="M2",
    speed=1.0,
    steps=16,
    sample_rate=8000,
    gain=None,  # None = 매 요청마다 자동 최대 음량(피크 정규화)
    lang="ko",
    gap=0.4,
    bell_wav_1x="sounds/captain_bell_1x.wav",
    bell_wav_2x="sounds/captain_bell_2x.wav",
    sfx_aliases={
        "알림": "sounds/notify.wav",
        "경고음": "sounds/alert.wav",
        "성공음": "sounds/success.wav",
        "함장승함 종1회": "sounds/captain_bell_1x.wav",
        "함장승함 종2회": "sounds/captain_bell_2x.wav",
        "타종2회": "sounds/ship_bell.wav",
    },
)

_engine: SupertonicEngine | None = None


def get_engine() -> SupertonicEngine:
    global _engine
    if _engine is None:
        _engine = SupertonicEngine(
            voice=DEFAULTS["voice"],
            speed=DEFAULTS["speed"],
            steps=DEFAULTS["steps"],
            sfx_aliases=DEFAULTS["sfx_aliases"],
            sample_rate=DEFAULTS["sample_rate"],
            bell_wav_1x=DEFAULTS["bell_wav_1x"],
            bell_wav_2x=DEFAULTS["bell_wav_2x"],
            gain=DEFAULTS["gain"],
        )
    return _engine


def resolve_output_dir() -> Path:
    return PROJECT_ROOT / DEFAULTS["output_directory"]


def sanitize_filename(name: str) -> str:
    stem = Path(name).name
    if stem.lower().endswith(".wav"):
        stem = stem[:-4]
    if not stem or not SAFE_FILENAME_RE.match(stem):
        raise ValueError(
            "filename must contain only letters, digits, dot, underscore, or hyphen"
        )
    return f"{stem}.wav"


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize")
    filename: str = Field(..., min_length=1, description="Output WAV filename (without path)")
    sound_effect: int = Field(
        0,
        alias="soundEffect",
        ge=0,
        le=10,
        description=(
            "0: none, 1~5: captain_bell_1x.wav repeated N times, "
            "6~10: captain_bell_2x.wav repeated (N-5) times, prepended before the TTS audio"
        ),
    )

    model_config = {"populate_by_name": True}


class TTSResponse(BaseModel):
    ok: bool = True
    path: str
    filename: str


class HealthResponse(BaseModel):
    status: str = "ok"
    output_directory: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_engine()
    resolve_output_dir().mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="multilingual-tts API (lite)", lifespan=lifespan)


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(output_directory=str(resolve_output_dir()))


@app.post("/api/tts", response_model=TTSResponse)
def synthesize(req: TTSRequest):
    try:
        wav_name = sanitize_filename(req.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    out_path = resolve_output_dir() / wav_name

    try:
        get_engine().generate_to_file(
            text=req.text,
            output_path=str(out_path),
            lang=DEFAULTS["lang"],
            gap=DEFAULTS["gap"],
            verbose=False,
            sfx_base=PROJECT_ROOT,
            sound_effect=req.sound_effect,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"synthesis failed: {exc}") from exc

    return TTSResponse(path=str(out_path), filename=wav_name)


def main():
    host, port = DEFAULTS["host"], DEFAULTS["port"]
    print(f"API server (lite, no config.yaml): http://{host}:{port}")
    print(f"  output: {resolve_output_dir()}")

    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
