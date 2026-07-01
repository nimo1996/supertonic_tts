# multilingual-tts HTTP API 규격서

| 항목 | 내용 |
|------|------|
| 문서 버전 | 1.0 |
| 작성일 | 2026-06-24 |
| 프로토콜 | HTTP/1.1 |
| 데이터 형식 | JSON (요청/응답), WAV (파일 저장) |
| 인증 | 없음 |
| 기본 Base URL | `http://{host}:9090` |

---

## 1. 개요

multilingual-tts API는 텍스트를 음성(WAV)으로 변환하고, 서버 로컬 디스크의 지정 디렉터리에 파일로 저장한다.

- 엔진: Supertonic v3
- 출력 포맷: 44,100Hz, 16-bit, mono WAV
- 동시 요청: 단일 프로세스 내 순차 처리 (모델 1회 로드 후 재사용)

### 1.1 서버 실행

```bash
cd /home/aicc/supertonic_tts
.venv/bin/python api.py
```

서버 설정은 `config.yaml`의 `api` 섹션에서 변경한다.

```yaml
api:
  host: 0.0.0.0
  port: 9090
  output_directory: /home/aicc/supertonic_tts/output
```

| 설정 키 | 기본값 | 설명 |
|---------|--------|------|
| `api.host` | `0.0.0.0` | 바인딩 주소 |
| `api.port` | `9090` | 리스닝 포트 |
| `api.output_directory` | `output` (상대 경로) | WAV 저장 디렉터리. 상대 경로는 프로젝트 루트 기준 |

### 1.2 공통 규칙

| 항목 | 규칙 |
|------|------|
| Content-Type (요청) | `application/json; charset=utf-8` |
| Content-Type (응답) | `application/json; charset=utf-8` |
| 문자 인코딩 | UTF-8 |
| HTTP 메서드 | 명세에 정의된 메서드만 사용 |

---

## 2. 엔드포인트 목록

| No | 메서드 | 경로 | 설명 |
|----|--------|------|------|
| 1 | GET | `/api/health` | 서버 상태 및 출력 디렉터리 확인 |
| 2 | POST | `/api/tts` | 텍스트 합성 후 WAV 파일 저장 |

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

### 3.2 텍스트 음성 합성 (TTS)

텍스트를 음성으로 변환하고, 서버의 출력 디렉터리에 WAV 파일로 저장한다.

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
  "lang": "ko"
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `text` | string | O | - | 합성할 텍스트. 1자 이상 |
| `filename` | string | O | - | 저장할 파일명 (경로 제외). `.wav` 확장자는 생략 가능 |
| `voice` | string | X | `config.yaml`의 `supertonic.voice` | 목소리 ID. 대소문자 무관 (`m2` -> `M2`) |
| `speed` | number (float) | X | `config.yaml`의 `supertonic.speed` | 발화 속도. 범위: 0.5 ~ 2.0 |
| `lang` | string | X | `"ko"` | 언어 코드 (소문자) |

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

#### 오류 응답

FastAPI 기본 오류 형식:

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

## 4. 처리 흐름

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

---

## 5. 제약 및 참고 사항

| 항목 | 내용 |
|------|------|
| 인증 | API 키, 토큰 등 인증 없음. 외부 노출 시 방화벽/리버스 프록시로 접근 제어 권장 |
| 파일 접근 | API는 WAV 바이너리를 HTTP 응답으로 반환하지 않음. 저장 경로만 반환 |
| 응답 시간 | 텍스트 길이에 비례. 짧은 문장 기준 수 초 이내 (CPU RTF 3~5x) |
| 타임아웃 | 클라이언트는 긴 문장 합성 시 60~120초 이상 타임아웃 설정 권장 |
| 멀티라인 | API는 단일 `text` 문자열을 한 번에 합성. 줄바꿈(`\n`) 포함 시 엔진의 멀티라인 처리 규칙 적용 |
| OpenAPI | 서버 실행 중 `http://{host}:{port}/docs` 에서 Swagger UI 제공 (FastAPI 자동 생성) |

---

## 6. 변경 이력

| 버전 | 일자 | 변경 내용 |
|------|------|-----------|
| 1.0 | 2026-06-24 | 최초 작성 (`/api/health`, `/api/tts`) |
