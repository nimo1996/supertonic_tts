# multilingual-tts 현재 상태

작성일: 2026-05-26

---

## 개요

CPU 우선으로 동작하는 상업용 다국어 TTS 시스템.  
한국어 품질을 최우선으로 하며, GPU 없이도 실시간 이상의 속도로 자연스러운 음성을 생성한다.

---

## 엔진: Supertonic v3

| 항목 | 내용 |
|------|------|
| 개발사 | Supertone Inc. (한국) |
| 코드 라이센스 | MIT |
| 모델 라이센스 | BigScience OpenRAIL-M (상업 사용 가능, 오남용 금지) |
| 아키텍처 | Flow-matching 기반, ONNX 런타임 |
| 모델 크기 | ~305MB |
| 출력 품질 | 44,100Hz 16-bit WAV |
| CPU 속도 | RTF 3~5x (1초 음성을 0.2~0.3초에 생성) |
| GPU | 선택적 (있으면 자동 가속) |

### 엔진 선택 이유

| 검토 엔진 | 결과 | 이유 |
|-----------|------|------|
| **Supertonic v3** | ✅ 채택 | 한국 회사 제작, 한국어 품질 최상, CPU RTF 3~5x |
| Kokoro TTS | ❌ 제외 | 영어 기반 — 한국어가 영어 억양으로 발음됨 |
| MeloTTS-Korean | ❌ 제외 | 한국어 발음은 정확하나 목소리 자체가 부자연스러움 |
| Meta MMS-TTS | ❌ 제외 | CC-BY-NC 라이센스 (상업 사용 불가) |
| Fish Speech 1.5 | ❌ 제외 | Fish Audio 전용 라이센스 (상업 사용 제한) |

---

## 지원 언어 (31개)

| 코드 | 언어 | 코드 | 언어 | 코드 | 언어 |
|------|------|------|------|------|------|
| ko | 한국어 | en | 영어 | ja | 일본어 |
| fr | 프랑스어 | de | 독일어 | es | 스페인어 |
| it | 이탈리아어 | pt | 포르투갈어 | ru | 러시아어 |
| vi | 베트남어 | id | 인도네시아어 | hi | 힌디어 |
| ar | 아랍어 | tr | 터키어 | uk | 우크라이나어 |
| pl | 폴란드어 | nl | 네덜란드어 | sv | 스웨덴어 |
| da | 덴마크어 | fi | 핀란드어 | cs | 체코어 |
| sk | 슬로바키아어 | ro | 루마니아어 | hu | 헝가리어 |
| hr | 크로아티아어 | bg | 불가리아어 | el | 그리스어 |
| et | 에스토니아어 | lv | 라트비아어 | lt | 리투아니아어 |
| sl | 슬로베니아어 | | | | |

**미지원 언어** (scripts/ 폴더에 샘플 있으나 현재 엔진 미지원):  
`zh` 중국어, `th` 태국어, `tl` 타갈로그어, `uz` 우즈베크어, `mn` 몽골어

---

## 프로젝트 구조

```
multilingual-tts/
├── tts.py                  # 메인 CLI
├── config.yaml             # 사용자 설정
├── requirements.txt        # 의존성
├── setup.sh                # 설치 스크립트
├── engines/
│   ├── supertonic_engine.py   # Supertonic v3 래퍼
│   └── __init__.py
├── scripts/                # 언어별 샘플 텍스트
│   ├── korean.txt
│   ├── english.txt
│   └── ...
├── models/                 # 모델 파일 (첫 실행 시 자동 다운로드, git 제외)
└── output/                 # 생성 음성 파일 (git 제외)
```

---

## 설치

```bash
git clone <repo>
cd multilingual-tts
bash setup.sh
```

모델(~305MB)은 첫 실행 시 Hugging Face에서 자동 다운로드된다.

---

## 사용법

### 기본

```bash
# 파일 변환 (파일명으로 언어 자동 감지)
.venv/bin/python tts.py --input scripts/korean.txt

# 직접 텍스트 입력
.venv/bin/python tts.py --text "안녕하세요" --lang ko

# 출력 경로 지정
.venv/bin/python tts.py --text "Hello" --lang en --output hello.wav
```

### 목소리 변경

```bash
# 목소리 목록 확인
.venv/bin/python tts.py --voices

# 특정 목소리 사용 (일회성)
.venv/bin/python tts.py --text "안녕하세요" --voice F1
```

### 기타 옵션

```bash
.venv/bin/python tts.py --langs          # 지원 언어 목록
.venv/bin/python tts.py --config         # 현재 설정 출력
.venv/bin/python tts.py --speed 0.9      # 느리게
.venv/bin/python tts.py --steps 16       # 고품질 (느림)
```

---

## 설정 (config.yaml)

```yaml
supertonic:
  voice: M2      # 기본 목소리: F1~F5 (여성), M1~M5 (남성)
  speed: 1.05    # 발화 속도 (0.5 ~ 2.0)
  steps: 8       # 품질 단계 (4~16, 높을수록 품질 좋고 느림)

output:
  directory: output
```

CLI 옵션이 config.yaml보다 우선 적용된다.

---

## 라이센스 요약

| 구성 요소 | 라이센스 | 상업 사용 |
|-----------|---------|---------|
| Supertonic 코드 | MIT | ✅ |
| Supertonic 모델 | OpenRAIL-M | ✅ (딥페이크·사칭·불법 용도 제외) |

OpenRAIL-M 주요 제한: 동의 없는 타인 목소리 사칭(딥페이크), 허위정보 생성, 아동 착취 등 오남용 목적 금지.  
고객센터, 콘텐츠 제작, 서비스 안내 등 정상적인 상업 목적은 제한 없이 사용 가능.
