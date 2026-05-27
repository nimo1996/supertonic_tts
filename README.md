# multilingual-tts

CPU 우선 상업용 다국어 TTS 시스템.  
한국어 품질 최우선, GPU 없이 실시간 이상의 속도로 자연스러운 음성 생성.

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
| 목소리 | F1~F5 (여성), M1~M5 (남성) — 총 10종 |
| 지원 언어 | 31개 |

---

## 요구 사항

- Python 3.10 이상
- 인터넷 연결 (최초 1회 모델 다운로드)
- 디스크 여유 공간 약 400MB (`~/.cache/supertonic3/` 에 저장)

---

## 설치

### 1. 저장소 클론

```bash
git clone <repo-url>
cd multilingual-tts
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
# → ~/.cache/supertonic3/ 에 모델 자동 다운로드 후 실행
```

인터넷이 없는 환경을 위해 미리 수동 다운로드도 가능합니다:

```bash
# huggingface_hub CLI로 수동 다운로드
.venv/bin/pip install huggingface_hub
.venv/bin/huggingface-cli download Supertone/supertonic-3 --local-dir ~/.cache/supertonic3
```

또는 캐시 위치를 직접 지정하려면:

```bash
export SUPERTONIC_CACHE_DIR=/path/to/model
.venv/bin/python tts.py --text "안녕하세요" --lang ko
```

---

## 사용법

### 기본

```bash
# 파일 변환 (파일명으로 언어 자동 감지)
.venv/bin/python tts.py --input scripts/korean.txt

# 텍스트 직접 입력
.venv/bin/python tts.py --text "안녕하세요" --lang ko

# 출력 경로 지정
.venv/bin/python tts.py --text "Hello" --lang en --output hello.wav
```

### 목소리 변경

```bash
# 목소리 목록 확인
.venv/bin/python tts.py --voices

# 특정 목소리 사용
.venv/bin/python tts.py --text "안녕하세요" --voice F1
```

### 속도 / 품질 조절

```bash
# 느리게
.venv/bin/python tts.py --text "안녕하세요" --speed 0.8

# 고품질 (느림, 기본값 16)
.venv/bin/python tts.py --input scripts/korean.txt --steps 16

# 빠른 미리보기 (저품질)
.venv/bin/python tts.py --input scripts/korean.txt --steps 4
```

### 정보 확인

```bash
.venv/bin/python tts.py --voices    # 목소리 목록
.venv/bin/python tts.py --langs     # 지원 언어 목록
.venv/bin/python tts.py --config    # 현재 설정 출력
```

### 멀티라인 파일

줄 단위로 분할해 생성 후 이어붙입니다. 줄 사이에 0.4초 묵음이 삽입됩니다.

```bash
.venv/bin/python tts.py --input scripts/daily.txt
# [1/44] 총기상 15분전
# [2/44] 총기상 5분전
# ...
```

---

## 설정 (config.yaml)

```yaml
supertonic:
  voice: M2      # F1~F5 (여성), M1~M5 (남성)
  speed: 1.0     # 발화 속도 (0.5 ~ 2.0)
  steps: 16      # 품질 단계 (4~16, 높을수록 품질 좋고 느림)

output:
  directory: output
```

CLI 옵션이 config.yaml보다 우선 적용됩니다.

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
multilingual-tts/
├── tts.py                     # 메인 CLI
├── config.yaml                # 사용자 설정
├── requirements.txt           # 의존 패키지
├── setup.sh                   # 설치 스크립트
├── engines/
│   ├── supertonic_engine.py   # Supertonic v3 래퍼
│   └── __init__.py
├── scripts/                   # 언어별 샘플 텍스트
├── docs/                      # 상세 문서
├── models/                    # (사용 안 함, git 제외)
└── output/                    # 생성 음성 파일 (git 제외)
```

모델 파일은 `~/.cache/supertonic3/` 에 저장됩니다 (프로젝트 폴더 외부).

---

## 라이센스

| 구성 요소 | 라이센스 | 상업 사용 |
|-----------|---------|---------|
| 이 프로젝트 코드 | MIT | ✅ |
| Supertonic 코드 | MIT | ✅ |
| Supertonic 모델 | OpenRAIL-M | ✅ (딥페이크·사칭·불법 용도 제외) |

OpenRAIL-M 주요 제한: 동의 없는 타인 목소리 사칭(딥페이크), 허위정보 생성, 아동 착취 등 오남용 목적 금지.  
고객센터, 콘텐츠 제작, 서비스 안내 등 정상적인 상업 목적은 제한 없이 사용 가능.
