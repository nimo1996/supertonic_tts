# multilingual-tts

CPU 우선 상업용 다국어 TTS 시스템.  
한국어 품질 최우선, GPU 없이 실시간 이상의 속도로 자연스러운 음성 생성.

CLI, HTTP API, 셸 스크립트 세 가지 방식으로 사용할 수 있습니다.

---

## 빠른 시작

```bash
git clone <repo-url>
cd supertonic_tts
bash setup.sh

# CLI
.venv/bin/python tts.py --text "안녕하세요" --lang ko

# API 서버 (백그라운드)
./run_api.sh start

# API 요청
./scripts/call_tts_api.sh -t "안녕하세요" -f greeting -l ko -v M2
```

---

## 엔진: Supertonic v3

| 항목 | 내용 |
|------|------|
| 개발사 | Supertone Inc. (한국) |
| 코드 라이센스 | MIT |
| 모델 라이센스 | BigScience OpenRAIL-M (상업 사용 가능) |
| 모델 출처 | [Supertone/supertonic-3](https://huggingface.co/Supertone/supertonic-3) |
| 모델 크기 | ~305MB |
| 출력 품질 | 44,100Hz 16-bit WAV |
| CPU 속도 | RTF 3~5x (1초 음성을 0.2~0.3초에 생성) |
| 목소리 | F1~F5 (여성), M1~M5 (남성) - 총 10종 |
| 지원 언어 | 31개 |

---

## 요구 사항

- Python 3.10 이상 (Rocky Linux 8: `python3.11` 권장)
- `curl` (API 요청 스크립트 사용 시)
- 인터넷 연결 (최초 1회 모델 다운로드)
- 디스크 여유 공간 약 400MB (`~/.cache/supertonic3/` 에 저장)

---

## 설치

### 1. 저장소 클론

```bash
git clone <repo-url>
cd supertonic_tts
```

### 2. 설치 스크립트 실행

```bash
bash setup.sh
```

Python 가상환경(`.venv`)을 생성하고 의존 패키지를 설치합니다.  
모델 파일은 설치 단계에서 받지 않으며, **첫 실행 시 자동으로 다운로드**됩니다.

### 3. 모델 다운로드 (첫 실행)

첫 실행 시 Hugging Face에서 모델(~305MB)을 자동으로 받습니다.

```bash
.venv/bin/python tts.py --text "안녕하세요" --lang ko
# -> ~/.cache/supertonic3/ 에 모델 자동 다운로드 후 실행
```

인터넷이 없는 환경을 위해 미리 수동 다운로드도 가능합니다:

```bash
.venv/bin/pip install huggingface_hub
.venv/bin/huggingface-cli download Supertone/supertonic-3 --local-dir ~/.cache/supertonic3
```

캐시 위치를 직접 지정하려면:

```bash
export SUPERTONIC_CACHE_DIR=/path/to/model
.venv/bin/python tts.py --text "안녕하세요" --lang ko
```

---

## CLI 사용법

### 기본

```bash
# 파일 변환 (파일명으로 언어 자동 감지)
.venv/bin/python tts.py --input scripts/korean.txt

# 텍스트 직접 입력
.venv/bin/python tts.py --text "안녕하세요" --lang ko

# 출력 경로 지정
.venv/bin/python tts.py --text "Hello" --lang en --output hello.wav
```

### 목소리 / 속도 / 품질

```bash
.venv/bin/python tts.py --voices                          # 목소리 목록
.venv/bin/python tts.py --text "안녕하세요" --voice F1
.venv/bin/python tts.py --text "안녕하세요" --speed 0.8    # 느리게
.venv/bin/python tts.py --input scripts/korean.txt --steps 16   # 고품질
.venv/bin/python tts.py --input scripts/korean.txt --steps 4     # 빠른 미리보기
```

### 정보 확인

```bash
.venv/bin/python tts.py --voices    # 목소리 목록
.venv/bin/python tts.py --langs     # 지원 언어 목록
.venv/bin/python tts.py --config    # 현재 설정 출력
```

### 줄별 개별 파일 생성 (`--split`)

입력 파일의 각 줄을 별도 WAV 파일로 저장합니다.

```bash
.venv/bin/python tts.py --input scripts/sample.txt --split
.venv/bin/python tts.py --input scripts/sample.txt --split --output output/my_dir
```

### 멀티라인 파일 (한 파일로 합성)

줄 단위로 분할해 생성 후 이어붙입니다. `--gap`으로 줄 사이 묵음 길이를 조절할 수 있습니다 (기본 0.4초).

```bash
.venv/bin/python tts.py --input scripts/daily.txt
.venv/bin/python tts.py --input scripts/daily.txt --gap 0.8
```

### 스크립트 마커 (효과음 / 묵음 삽입)

스크립트 파일에 마커를 사용해 효과음과 묵음을 원하는 위치에 삽입할 수 있습니다.  
마커는 반드시 **별도 줄**에 작성합니다.

| 마커 | 설명 |
|------|------|
| `[BELL: 경로]` | WAV 파일을 해당 위치에 삽입 |
| `[SFX: 경로]` | `[BELL]`과 동일 (별칭) |
| `[PAUSE: 초]` | 지정한 시간만큼 묵음 삽입 |

**스크립트 예시 (`scripts/announcement.txt`):**

```text
[BELL: sounds/bell.wav]
안녕하세요, 오늘의 안내를 시작합니다.
[PAUSE: 1.0]
첫 번째 안내입니다.
[SFX: sounds/chime.wav]
감사합니다.
```

```bash
.venv/bin/python tts.py --input scripts/announcement.txt --lang ko
```

> **주의:** 마커가 포함된 스크립트는 `--split` 옵션과 함께 사용하지 않습니다.

### 문장 내 간격 조절 (구두점 활용)

| 구두점 | 예시 | 추가 간격 |
|--------|------|----------|
| 없음 | `이 세상에는 많은 사람이 있다.` | - |
| `,` | `이 세상에는, 많은 사람이 있다.` | +0.2초 |
| `...` | `이 세상에는... 많은 사람이 있다.` | +0.8초 |
| `……` | `이 세상에는…… 많은 사람이 있다.` | +1.2초 |

---

## HTTP API

텍스트를 받아 서버 로컬 디스크에 WAV 파일로 저장하는 REST API입니다.  
상세 규격은 [`docs/api-spec.md`](docs/api-spec.md) 를 참고하세요.

### 서버 실행

**포그라운드 (직접 실행):**

```bash
.venv/bin/python api.py
```

**백그라운드 (권장):**

```bash
./run_api.sh start      # 시작
./run_api.sh status     # 상태 확인
./run_api.sh stop       # 종료
./run_api.sh restart    # 재시작
```

- 로그: `logs/api.log`
- PID 파일: `.api.pid`
- Swagger UI: `http://127.0.0.1:9090/docs`

### API 요청 스크립트

```bash
# health 확인
./scripts/call_tts_api.sh --health

# TTS 요청
./scripts/call_tts_api.sh -t "안녕하세요" -f greeting
./scripts/call_tts_api.sh -t "Hello" -f hello_en -l en -v F3 -s 1.05
```

| 옵션 | 설명 |
|------|------|
| `-t, --text` | 합성 텍스트 (필수) |
| `-f, --filename` | 저장 파일명 (필수, 경로 없이) |
| `-v, --voice` | 목소리 (F1~F5 / M1~M5) |
| `-s, --speed` | 속도 (0.5~2.0) |
| `-l, --lang` | 언어 (기본: ko) |
| `--host` | API 호스트 (기본: 127.0.0.1) |
| `-p, --port` | 포트 (기본: config.yaml) |
| `--health` | 상태 확인만 |

### curl 예시

```bash
curl -s http://127.0.0.1:9090/api/health

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

응답 예:

```json
{
  "ok": true,
  "path": "/home/aicc/supertonic_tts/output/greeting.wav",
  "filename": "greeting.wav"
}
```

API는 WAV 바이너리를 HTTP 응답으로 반환하지 않고, 서버 디스크에 저장한 뒤 경로만 반환합니다.  
동일한 `filename`으로 재요청하면 기존 파일을 덮어씁니다.

---

## 설정 (config.yaml)

```yaml
supertonic:
  voice: M2          # F1~F5 (여성), M1~M5 (남성)
  speed: 1.0         # 발화 속도 (0.5 ~ 2.0)
  steps: 16          # 품질 단계 (4~16, 높을수록 느리고 품질 좋음)

output:
  directory: output  # CLI 기본 출력 폴더

api:
  host: 0.0.0.0
  port: 9090
  output_directory: output   # API WAV 저장 폴더 (절대/상대 경로 가능)
```

| 섹션 | 용도 |
|------|------|
| `supertonic` | CLI/API 공통 기본 목소리, 속도, 품질 |
| `output.directory` | CLI `--output` 미지정 시 저장 위치 |
| `api.host` / `api.port` | HTTP API 바인딩 주소 |
| `api.output_directory` | API 요청 시 WAV 저장 위치 |

CLI 옵션과 API 요청 본문의 값이 config.yaml보다 우선 적용됩니다.

---

## 지원 언어 (31개)

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

**미지원**: `zh` 중국어, `th` 태국어, `tl` 타갈로그어, `uz` 우즈베크어, `mn` 몽골어

---

## 프로젝트 구조

```
supertonic_tts/
├── tts.py                     # CLI
├── api.py                     # HTTP API 서버
├── run_api.sh                 # API 서버 start/stop/status
├── config.yaml                # 사용자 설정
├── requirements.txt           # 의존 패키지
├── setup.sh                   # 설치 스크립트
├── engines/
│   └── supertonic_engine.py   # Supertonic v3 래퍼
├── scripts/
│   ├── call_tts_api.sh        # API 요청 스크립트
│   └── *.txt                  # 입력 스크립트 (텍스트 + 마커)
├── docs/
│   └── api-spec.md            # HTTP API 규격서
├── sounds/                    # 효과음 WAV 파일
├── logs/                      # API 서버 로그 (git 제외)
└── output/                    # 생성 음성 파일 (git 제외)
```

모델 파일은 `~/.cache/supertonic3/` 에 저장됩니다 (프로젝트 폴더 외부).

---

## 라이센스

| 구성 요소 | 라이센스 | 상업 사용 |
|-----------|---------|---------|
| 이 프로젝트 코드 | MIT | OK |
| Supertonic 코드 | MIT | OK |
| Supertonic 모델 | OpenRAIL-M | OK (딥페이크/사칭/불법 용도 제외) |

OpenRAIL-M 주요 제한: 동의 없는 타인 목소리 사칭(딥페이크), 허위정보 생성, 아동 착취 등 오남용 목적 금지.  
고객센터, 콘텐츠 제작, 서비스 안내 등 정상적인 상업 목적은 제한 없이 사용 가능.
