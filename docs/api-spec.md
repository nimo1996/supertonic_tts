# multilingual-tts HTTP API 규격서

| 항목 | 내용 |
|------|------|
| 문서 버전 | 1.5 |
| 작성일 | 2026-07-03 |
| 프로토콜 | HTTP/1.1 |
| 데이터 형식 | JSON (요청), JSON 또는 WAV (응답) |
| 인증 | 없음 |
| 기본 Base URL | `http://{host}:9090` |

---

## 1. 개요

multilingual-tts API는 텍스트를 음성(WAV)으로 변환한다. 응답 방식은 두 가지이다.

- **파일 저장 모드** (`POST /api/tts`): 서버 로컬 디스크에 WAV를 저장하고, 저장 경로를 JSON으로 반환
- **오디오 응답 모드** (`POST /api/tts/audio`): WAV 바이너리를 HTTP 응답 본문으로 직접 반환 (디스크 저장 없음)

- 엔진: Supertonic v3
- 출력 포맷: 44,100Hz, 16-bit, mono WAV
- 동시 요청: 단일 프로세스 내 순차 처리 (모델 1회 로드 후 재사용)

### 1.1 서버 실행

배포판(권장, 소스 미포함 실행파일):

```bash
./run_api.sh start     # 백그라운드 실행
./run_api.sh status
./run_api.sh stop
```

설치·운영 절차 전체는 [INSTALL.md](INSTALL.md), [OPERATIONS.md](OPERATIONS.md) 참고.

소스 개발 환경에서 직접 실행할 경우:

```bash
cd supertonic_tts
.venv/bin/python api.py
```

서버 설정은 `config.yaml`의 `api` 섹션에서 변경한다.

```yaml
api:
  host: 0.0.0.0
  port: 9090
  output_directory: output
```

| 설정 키 | 기본값 | 설명 |
|---------|--------|------|
| `api.host` | `0.0.0.0` | 바인딩 주소 |
| `api.port` | `9090` | 리스닝 포트 |
| `api.output_directory` | `output` (상대 경로) | WAV 저장 디렉터리. 상대 경로는 설치 디렉터리(실행파일 위치) 기준 |

### 1.2 공통 규칙

| 항목 | 규칙 |
|------|------|
| Content-Type (요청) | `application/json; charset=utf-8` |
| Content-Type (응답) | 엔드포인트별 상이 (아래 참고) |
| 문자 인코딩 | UTF-8 |
| HTTP 메서드 | 명세에 정의된 메서드만 사용 |

---

## 2. 엔드포인트 목록

| No | 메서드 | 경로 | 설명 | 응답 형식 |
|----|--------|------|------|-----------|
| 1 | GET | `/api/health` | 서버 상태 및 출력 디렉터리 확인 | JSON |
| 2 | POST | `/api/tts` | 텍스트 합성 후 WAV 파일 저장 | JSON |
| 3 | POST | `/api/tts/audio` | 텍스트 합성 후 WAV 바이너리 반환 | WAV |

---

## 3. API 상세

### 3.1 서버 상태 확인

서버가 정상 동작 중인지, WAV가 저장되는 디렉터리 경로를 확인한다.

#### 요청

```
GET /api/health
```

요청 본문 없음.

#### 성공 응답

| HTTP 상태 | 200 OK |
|-----------|--------|

```json
{
  "status": "ok",
  "output_directory": "/home/aicc/supertonic_tts/output"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | string | 서버 상태. 정상 시 `"ok"` |
| `output_directory` | string | WAV 파일이 저장되는 절대 경로 |

#### cURL 예시

```bash
curl -s http://127.0.0.1:9090/api/health
```

---

### 3.2 텍스트 음성 합성 - 파일 저장 (`/api/tts`)

텍스트를 음성으로 변환하고, 서버의 출력 디렉터리에 WAV 파일로 저장한다. 저장 경로를 JSON으로 반환한다.

#### 요청

```
POST /api/tts
Content-Type: application/json
```

#### 요청 본문 (JSON)

```json
{
  "text": "안녕하세요, 오늘의 안내를 시작합니다.",
  "filename": "announce_001",
  "voice": "M2",
  "speed": 1.0,
  "lang": "ko",
  "gap": 0.4,
  "soundEffect": 0
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `text` | string | O | - | 합성할 텍스트. 1자 이상 |
| `filename` | string | O | - | 저장할 파일명 (경로 제외). `.wav` 확장자는 생략 가능 |
| `voice` | string | X | `config.yaml`의 `supertonic.voice` | 목소리 ID. 대소문자 무관 (`m2` -> `M2`) |
| `speed` | number (float) | X | `config.yaml`의 `supertonic.speed` | 발화 속도. 범위: 0.5 ~ 2.0 |
| `lang` | string | X | `"ko"` | 언어 코드 (소문자) |
| `gap` | number (float) | X | `0.4` | 줄/태그 조각 사이에 넣는 묵음(초). 범위: 0.0 ~ 5.0. 문장 내부 구두점 간격이나 인라인 `<별칭>` 태그 사이 간격(0.15초 고정)과는 별개 |
| `soundEffect` | integer | X | `0` | `0`이면 무시. `1`이면 `config.yaml`의 `sound_effect.wav_1x`(일과타종 1타)를 2회, `2~4`면 `wav_2x`(예식타종 2타)를 그 횟수만큼 반복해서 tts 음성 맨 앞에 붙임. 반복끼리는 항상 간격 없이 붙여서 재생되며(`gap` 값과 무관), 종소리 전체와 tts 본문 사이 간격만 `gap` 값을 사용 |

#### `filename` 규칙

| 규칙 | 설명 |
|------|------|
| 경로 제거 | `subdir/file.wav`처럼 경로가 포함되면 파일명(`file.wav`)만 사용 |
| 확장자 | `.wav`가 없으면 자동 추가. `announce_001` -> `announce_001.wav` |
| 허용 문자 | 영문, 숫자, `.`(dot), `_`(underscore), `-`(hyphen) |
| 금지 | 빈 문자열, `/`, `\`, `..`, 공백, 한글 등 |

유효 예: `greeting`, `announce_001`, `test-v2.wav`

무효 예: `../secret`, `my file`, `안내.wav`

#### 사용 가능한 목소리 (`voice`)

| ID | 설명 |
|----|------|
| `F1` ~ `F5` | 여성 목소리 5종 |
| `M1` ~ `M5` | 남성 목소리 5종 |

`voice`를 생략하면 `config.yaml`의 `supertonic.voice` 값이 사용된다.

#### 지원 언어 (`lang`)

| 코드 | 언어 | 코드 | 언어 | 코드 | 언어 |
|------|------|------|------|------|------|
| `ko` | 한국어 | `en` | 영어 | `ja` | 일본어 |
| `fr` | 프랑스어 | `de` | 독일어 | `es` | 스페인어 |
| `it` | 이탈리아어 | `pt` | 포르투갈어 | `ru` | 러시아어 |
| `vi` | 베트남어 | `id` | 인도네시아어 | `hi` | 힌디어 |
| `ar` | 아랍어 | `tr` | 터키어 | `uk` | 우크라이나어 |
| `pl` | 폴란드어 | `nl` | 네덜란드어 | `sv` | 스웨덴어 |
| `da` | 덴마크어 | `fi` | 핀란드어 | `cs` | 체코어 |
| `sk` | 슬로바키아어 | `ro` | 루마니아어 | `hu` | 헝가리어 |
| `hr` | 크로아티아어 | `bg` | 불가리아어 | `el` | 그리스어 |
| `et` | 에스토니아어 | `lv` | 라트비아어 | `lt` | 리투아니아어 |
| `sl` | 슬로베니아어 | | | | |

#### 성공 응답

| HTTP 상태 | 200 OK |
|-----------|--------|
| Content-Type | `application/json` |

```json
{
  "ok": true,
  "path": "/home/aicc/supertonic_tts/output/announce_001.wav",
  "filename": "announce_001.wav"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `ok` | boolean | 처리 성공 여부. 성공 시 `true` |
| `path` | string | 저장된 WAV 파일의 절대 경로 |
| `filename` | string | 저장된 파일명 (확장자 포함) |

동일한 `filename`으로 재요청하면 기존 파일을 덮어쓴다.

#### cURL 예시

```bash
curl -X POST http://127.0.0.1:9090/api/tts \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "안녕하세요",
    "filename": "greeting",
    "voice": "M2",
    "speed": 1.0,
    "lang": "ko"
  }'
```

#### Python 예시

```python
import requests

resp = requests.post(
    "http://127.0.0.1:9090/api/tts",
    json={
        "text": "Hello world",
        "filename": "hello_en",
        "voice": "F3",
        "speed": 1.05,
        "lang": "en",
    },
    timeout=120,
)
resp.raise_for_status()
result = resp.json()
print(result["path"])
```

---

### 3.3 텍스트 음성 합성 - 오디오 응답 (`/api/tts/audio`)

텍스트를 음성으로 변환하고, WAV 바이너리를 HTTP 응답 본문으로 직접 반환한다. 서버 디스크에는 저장하지 않는다.

#### 요청

```
POST /api/tts/audio
Content-Type: application/json
```

#### 요청 본문 (JSON)

```json
{
  "text": "안녕하세요, 오늘의 안내를 시작합니다.",
  "voice": "M2",
  "speed": 1.0,
  "lang": "ko",
  "gap": 0.4,
  "soundEffect": 0,
  "filename": "greeting"
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `text` | string | O | - | 합성할 텍스트. 1자 이상 |
| `voice` | string | X | `config.yaml`의 `supertonic.voice` | 목소리 ID. 대소문자 무관 (`m2` -> `M2`) |
| `speed` | number (float) | X | `config.yaml`의 `supertonic.speed` | 발화 속도. 범위: 0.5 ~ 2.0 |
| `lang` | string | X | `"ko"` | 언어 코드 (소문자) |
| `gap` | number (float) | X | `0.4` | 줄/태그 조각 사이에 넣는 묵음(초). 범위: 0.0 ~ 5.0 |
| `soundEffect` | integer | X | `0` | `0`이면 무시. `1`이면 `config.yaml`의 `sound_effect.wav_1x`(일과타종 1타)를 2회, `2~4`면 `wav_2x`(예식타종 2타)를 그 횟수만큼 반복해서 tts 음성 맨 앞에 붙임. 반복끼리는 항상 간격 없이 붙여서 재생되며(`gap` 값과 무관), 종소리 전체와 tts 본문 사이 간격만 `gap` 값을 사용 |
| `filename` | string | X | `"tts.wav"` | `Content-Disposition` 헤더에 사용할 파일명. 3.2절 `filename` 규칙 동일 적용 |

`voice`, `lang` 값은 3.2절과 동일하다.

#### `filename` vs 클라이언트 저장 경로

| 항목 | 위치 | 역할 |
|------|------|------|
| JSON `filename` | 서버 | 응답 헤더 `Content-Disposition: attachment; filename="..."` 에 사용. 브라우저 등이 다운로드 시 제안하는 파일명 |
| curl `-o` / 클라이언트 저장 경로 | 클라이언트 | 실제로 파일을 저장할 로컬 경로. curl 사용 시 `-o`가 저장 위치를 결정하며, JSON `filename`과 독립적 |

예: `-d '{"filename":"greeting"}' -o my_voice.wav` 이면 헤더는 `greeting.wav`, 실제 저장 파일은 `my_voice.wav`이다.

#### 성공 응답

| HTTP 상태 | 200 OK |
|-----------|--------|
| Content-Type | `audio/wav` |
| 응답 본문 | WAV 바이너리 (44,100Hz, 16-bit, mono) |

응답 헤더 예:

```
Content-Type: audio/wav
Content-Disposition: attachment; filename="greeting.wav"
```

#### cURL 예시

```bash
curl -X POST http://127.0.0.1:9090/api/tts/audio \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "안녕하세요",
    "voice": "M2",
    "speed": 1.0,
    "lang": "ko",
    "filename": "greeting"
  }' \
  -o greeting.wav
```

`filename`을 생략하면 `Content-Disposition` 기본값은 `tts.wav`이다.

```bash
curl -X POST http://127.0.0.1:9090/api/tts/audio \
  -H 'Content-Type: application/json' \
  -d '{"text": "안녕하세요", "lang": "ko"}' \
  -o output.wav
```

#### Python 예시

```python
import requests

resp = requests.post(
    "http://127.0.0.1:9090/api/tts/audio",
    json={
        "text": "Hello world",
        "voice": "F3",
        "speed": 1.05,
        "lang": "en",
        "filename": "hello_en",
    },
    timeout=120,
)
resp.raise_for_status()
with open("hello_en.wav", "wb") as f:
    f.write(resp.content)
```

#### 스크립트 예시

```bash
./scripts/call_tts_api.sh -t "안녕하세요" --audio greeting.wav -v M2
```

---

### 3.4 공통 오류 응답

TTS 엔드포인트(`/api/tts`, `/api/tts/audio`)에서 발생하는 오류는 FastAPI 기본 형식을 따른다.

```json
{
  "detail": "오류 메시지"
}
```

| HTTP 상태 | 발생 조건 | `detail` 예시 |
|-----------|-----------|---------------|
| 400 | `filename` 형식 오류 | `"filename must contain only letters, digits, dot, underscore, or hyphen"` |
| 400 | 지원하지 않는 언어 | `"unsupported lang: zh"` |
| 400 | 잘못된 목소리 | `"unknown voice: X9"` |
| 400 | 기타 입력 검증 실패 | `"잘못된 목소리: X9. 선택 가능: [...]"` |
| 422 | JSON 스키마 오류 (필수 필드 누락 등) | Pydantic 검증 메시지 |
| 500 | 합성 중 서버 내부 오류 | `"synthesis failed: ..."` |

오류 시 응답 Content-Type은 `application/json`이다.

---

## 4. 처리 흐름

### 4.1 파일 저장 모드 (`/api/tts`)

```
Client                    API Server                     Disk
  |                          |                            |
  |  POST /api/tts           |                            |
  |  {text, filename, ...}   |                            |
  |------------------------->|                            |
  |                          |  입력 검증 (filename, lang, voice)
  |                          |  TTS 합성 (Supertonic v3)
  |                          |  WAV 저장                  |
  |                          |--------------------------->|
  |                          |                            |
  |  200 {ok, path, filename}|                            |
  |<-------------------------|                            |
```

1. 서버 기동 시 TTS 모델을 메모리에 로드한다 (최초 기동 시 모델 다운로드 가능).
2. 요청 수신 후 `filename`, `lang`, `voice`를 검증한다.
3. 텍스트를 합성하여 `api.output_directory` 아래에 WAV로 저장한다.
4. 저장 경로와 파일명을 JSON으로 반환한다.

### 4.2 오디오 응답 모드 (`/api/tts/audio`)

```
Client                    API Server
  |                          |
  |  POST /api/tts/audio     |
  |  {text, voice, ...}      |
  |------------------------->|
  |                          |  입력 검증 (lang, voice, filename)
  |                          |  TTS 합성 (Supertonic v3)
  |                          |  WAV 바이너리 생성 (메모리)
  |                          |
  |  200 audio/wav (binary)  |
  |<-------------------------|
  |                          |
  |  클라이언트가 로컬 저장   |
```

1. 요청 수신 후 `lang`, `voice`, `filename`(선택)을 검증한다.
2. 텍스트를 합성하여 메모리상 WAV 바이너리를 생성한다.
3. `Content-Type: audio/wav` 와 `Content-Disposition` 헤더와 함께 응답 본문으로 반환한다.
4. 서버 디스크에는 파일을 저장하지 않는다.

---

## 5. 제약 및 참고 사항

| 항목 | 내용 |
|------|------|
| 인증 | API 키, 토큰 등 인증 없음. 외부 노출 시 방화벽/리버스 프록시로 접근 제어 권장 |
| 응답 방식 | `/api/tts`는 JSON(저장 경로), `/api/tts/audio`는 WAV 바이너리. 용도에 맞게 선택 |
| 응답 시간 | 텍스트 길이에 비례. 짧은 문장 기준 수 초 이내 (CPU RTF 3~5x) |
| 타임아웃 | 클라이언트는 긴 문장 합성 시 60~120초 이상 타임아웃 설정 권장 |
| 멀티라인 | API는 단일 `text` 문자열을 한 번에 합성. 줄바꿈(`\n`) 포함 시 엔진의 멀티라인 처리 규칙 적용 |
| 스크립트 마커 | `text`에 `[BELL: 경로]` / `[SFX: 경로]` / `[PAUSE: 초]`를 **별도 줄**로 넣으면 CLI와 동일하게 처리됨 (5.1절 참고) |
| 별칭 태그 | `text` 문장 **중간에** `<별칭>` 태그를 넣으면 `config.yaml`의 `sfx` 섹션에 등록된 wav가 그 위치에 삽입됨 (5.2절 참고) |
| OpenAPI | 서버 실행 중 `http://{host}:{port}/docs` 에서 Swagger UI 제공 (FastAPI 자동 생성) |

### 5.1 스크립트 마커 (효과음 / 묵음)

`text` 필드 안에 아래 마커를 줄 단위로 넣으면 해당 위치에 wav 삽입 또는 묵음을 넣을 수 있다. 자세한 문법은 [README.md](../README.md#스크립트-마커-효과음--묵음-삽입) 참고.

| 마커 | 설명 |
|------|------|
| `[BELL: 경로]` / `[SFX: 경로]` | 해당 wav 파일을 그 위치에 삽입 |
| `[PAUSE: 초]` | 지정한 시간만큼 묵음 삽입 |

```json
{
  "text": "[BELL: sounds/bell.wav]\n안녕하세요, 오늘의 안내를 시작합니다.\n[PAUSE: 1.0]\n감사합니다.",
  "lang": "ko"
}
```

상대 경로는 `/api/tts`, `/api/tts/audio` 모두 설치 디렉터리(프로젝트 루트) 기준으로 resolve된다.

### 5.2 별칭 태그 (`<별칭>`)

`config.yaml`의 `sfx` 섹션에 미리 등록해 둔 wav 파일은, `text` 문장 **중간에도** `<별칭>` 형태로 끼워 넣을 수 있다. 태그 앞뒤 텍스트는 각각 TTS로 합성되고 그 사이에 wav가 삽입된다.

```yaml
# config.yaml
sfx:
  시작 종: sounds/bell.wav
  종료 종: sounds/chime.wav
```

```json
{
  "text": "<시작 종> 안내말씀드리겠습니다. <종료 종>",
  "lang": "ko"
}
```

등록되지 않은 태그는 서버 로그에 경고를 남기고 건너뛴다 (요청은 실패하지 않음).

### 5.3 시작 종소리 (`soundEffect`)

`soundEffect` 필드(정수, 0~4)를 지정하면 `config.yaml`의 `sound_effect.wav_1x`/`wav_2x`에 등록된 종소리 wav를 tts 음성 맨 앞에 붙인다. `1`이면 `wav_1x`(일과타종 1타)를 2회, `2~4`면 `wav_2x`(예식타종 2타)를 그 횟수만큼 반복한다. `0` 또는 생략 시 아무것도 붙이지 않는다.

```yaml
# config.yaml
sound_effect:
  wav_1x: sounds/captain_bell_1x.wav
  wav_2x: sounds/captain_bell_2x.wav
```

```json
{
  "text": "안녕하세요, 오늘의 안내를 시작합니다.",
  "lang": "ko",
  "soundEffect": 3
}
```

타종끼리는 항상 간격 없이 붙여서 재생된다 (`gap` 값과 무관하게 고정). 종소리 전체가 끝난 뒤 tts 본문이 시작되기 전 간격만 `gap` 필드 값을 사용한다 (생략 시 기본 0.4초). `config.yaml`에 해당 구간의 `wav_1x`/`wav_2x`가 설정되어 있지 않거나 파일이 없으면 서버 로그에 경고를 남기고 건너뛴다 (요청은 실패하지 않음).

---

## 6. 변경 이력

| 버전 | 일자 | 변경 내용 |
|------|------|-----------|
| 1.5 | 2026-07-31 | `soundEffect` 타종 반복 사이 간격을 `gap` 값과 무관하게 항상 0으로 고정 (붙여서 재생) |
| 1.4 | 2026-07-31 | `/api/tts`, `/api/tts/audio`에 `soundEffect` 필드 추가 (0~5, tts 맨 앞에 종소리 반복 삽입) |
| 1.3 | 2026-07-31 | `/api/tts`, `/api/tts/audio`에 `gap` 필드 추가 (줄/태그 조각 사이 묵음 조절) |
| 1.2 | 2026-07-31 | 스크립트 마커(`[BELL]`/`[SFX]`/`[PAUSE]`) 및 문장 내 별칭 태그(`<별칭>`) API 지원 명시, `/api/tts` 상대경로 기준을 `/api/tts/audio`와 통일 |
| 1.1 | 2026-07-03 | `/api/tts/audio` 추가 (WAV 바이너리 직접 응답) |
| 1.0 | 2026-06-24 | 최초 작성 (`/api/health`, `/api/tts`) |
