#!/usr/bin/env python3
"""HTTP API for multilingual-tts."""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from paths import base_dir
from tts import CONFIG_PATH, cfg, get_engine, load_config

PROJECT_ROOT = base_dir()
SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

config = load_config()
_engine = None


def resolve_output_dir(config: dict) -> Path:
    raw = cfg(config, "api", "output_directory", default="output")
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


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
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(..., min_length=1, description="Text to synthesize")
    filename: str = Field(..., min_length=1, description="Output WAV filename (without path)")
    voice: str | None = Field(None, description="Voice id (F1~F5 / M1~M5)")
    speed: float | None = Field(None, ge=0.5, le=2.0, description="Speech speed")
    lang: str = Field("ko", description="Language code")
    gap: float | None = Field(
        None, ge=0.0, le=5.0, description="Silence between lines/segments in seconds (default 0.4)"
    )
    sound_effect: int | None = Field(
        None,
        alias="soundEffect",
        ge=0,
        le=5,
        description="0: none, 1~5: number of bell wav repeats prepended before the TTS audio",
    )
    gain: float | None = Field(
        None, ge=0.1, le=5.0, description="Output volume multiplier (1.0 = original, e.g. 1.5 = +50%)"
    )


class TTSAudioRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(..., min_length=1, description="Text to synthesize")
    voice: str | None = Field(None, description="Voice id (F1~F5 / M1~M5)")
    speed: float | None = Field(None, ge=0.5, le=2.0, description="Speech speed")
    lang: str = Field("ko", description="Language code")
    gap: float | None = Field(
        None, ge=0.0, le=5.0, description="Silence between lines/segments in seconds (default 0.4)"
    )
    sound_effect: int | None = Field(
        None,
        alias="soundEffect",
        ge=0,
        le=5,
        description="0: none, 1~5: number of bell wav repeats prepended before the TTS audio",
    )
    filename: str | None = Field(
        None,
        description="Optional filename for Content-Disposition header",
    )
    gain: float | None = Field(
        None, ge=0.1, le=5.0, description="Output volume multiplier (1.0 = original, e.g. 1.5 = +50%)"
    )


class TTSResponse(BaseModel):
    ok: bool = True
    path: str
    filename: str


class HealthResponse(BaseModel):
    status: str = "ok"
    output_directory: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    _engine = get_engine(config)
    out_dir = resolve_output_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="multilingual-tts API", lifespan=lifespan)


def _resolve_tts_params(req: TTSRequest | TTSAudioRequest):
    engine = _engine or get_engine(config)
    lang = req.lang.lower()

    if not engine.supports(lang):
        raise HTTPException(
            status_code=400,
            detail=f"unsupported lang: {lang}",
        )

    voice = req.voice.upper() if req.voice else None
    if voice and voice not in engine.get_voices():
        raise HTTPException(
            status_code=400,
            detail=f"unknown voice: {voice}",
        )

    return engine, lang, voice


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(output_directory=str(resolve_output_dir(config)))


@app.post("/api/tts", response_model=TTSResponse)
def synthesize(req: TTSRequest):
    try:
        wav_name = sanitize_filename(req.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    engine, lang, voice = _resolve_tts_params(req)

    out_dir = resolve_output_dir(config)
    out_path = out_dir / wav_name

    try:
        engine.generate_to_file(
            text=req.text,
            output_path=str(out_path),
            lang=lang,
            voice=voice,
            speed=req.speed,
            gap=req.gap if req.gap is not None else 0.4,
            verbose=False,
            sfx_base=PROJECT_ROOT,
            sound_effect=req.sound_effect or 0,
            gain=req.gain,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"synthesis failed: {exc}") from exc

    return TTSResponse(path=str(out_path), filename=wav_name)


@app.post("/api/tts/audio")
def synthesize_audio(req: TTSAudioRequest):
    engine, lang, voice = _resolve_tts_params(req)

    disp_name = "tts.wav"
    if req.filename:
        try:
            disp_name = sanitize_filename(req.filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        wav_bytes, _ = engine.generate_to_bytes(
            text=req.text,
            lang=lang,
            voice=voice,
            speed=req.speed,
            gap=req.gap if req.gap is not None else 0.4,
            verbose=False,
            sfx_base=PROJECT_ROOT,
            sound_effect=req.sound_effect or 0,
            gain=req.gain,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"synthesis failed: {exc}") from exc

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": f'attachment; filename="{disp_name}"'},
    )


def main():
    host = cfg(config, "api", "host", default="0.0.0.0")
    port = cfg(config, "api", "port", default=9090)

    print(f"API server: http://{host}:{port}")
    print(f"  output: {resolve_output_dir(config)}")
    print(f"  config: {CONFIG_PATH}")

    uvicorn.run(
        app,
        host=host,
        port=int(port),
        reload=False,
    )


if __name__ == "__main__":
    main()
