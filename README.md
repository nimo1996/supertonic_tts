# Multilingual TTS System

다국어 텍스트 음성 변환(TTS) 시스템.
Fish Speech 1.5(주요 언어) + Meta MMS-TTS(확장 언어) 이중 구조.

---

## 구성

| 파일 | 역할 |
|------|------|
| `tts.py` | Fish Speech 1.5 클라이언트 (8개 주요 언어) |
| `mms_tts.py` | Meta MMS-TTS 클라이언트 (1100개 언어) |
| `start_server.sh` | Fish Speech API 서버 시작 스크립트 |
| `scripts/` | 언어별 TTS 샘플 스크립트 |

---

## 지원 언어

### Fish Speech 1.5 (`tts.py`)

공식 지원 8개 언어. 자연스러운 억양과 감정 표현.

| 언어 | 코드 |
|------|------|
| 한국어 | ko |
| 영어 | en |
| 중국어 | zh |
| 일본어 | ja |
| 프랑스어 | fr |
| 독일어 | de |
| 아랍어 | ar |
| 스페인어 | es |

### Meta MMS-TTS (`mms_tts.py`)

Fish Speech 미지원 언어 대상. 1100개 이상 언어 지원 (CC-BY-NC-4.0).

| 언어 | 코드 | MMS 모델 코드 |
|------|------|-------------|
| 베트남어 | vi | vie |
| 태국어 | th | tha |
| 필리핀어(Tagalog) | tl / fil | tgl |
| 인도네시아어 | id | ind |
| 우즈벡어 (키릴) | uz | uzb-script_cyrillic |
| 몽골어 | mn | mon |
| 러시아어 | ru | rus |
| 힌디어 | hi | hin |
| 터키어 | tr | tur |
| 우크라이나어 | uk | ukr |

> ⚠️ 우즈벡어는 키릴 문자 모델만 존재. `scripts/Uzbek.txt`는 키릴 문자로 작성.

---

## 설치

```bash
# Fish Speech 의존성
python3 -m venv venv
source venv/bin/activate
pip install -r fish-speech/requirements.txt  # 또는 fish-speech 설치 가이드 참조

# MMS-TTS 의존성 (transformers, scipy는 대부분 이미 설치됨)
pip install transformers scipy torch
```

---

## 실행

### Fish Speech 서버 시작

```bash
./start_server.sh
# 기본 포트: 8080
```

### Fish Speech TTS (`tts.py`)

```bash
# 텍스트 직접 입력
python3 tts.py "안녕하세요" -o output.wav

# 파일에서 읽기 (출력 파일명 자동 설정)
python3 tts.py -f scripts/korean.txt

# 옵션
python3 tts.py "Hello" -o out.wav --top-p 0.7 --temperature 0.7
```

### MMS-TTS (`mms_tts.py`)

```bash
# 파일명으로 언어 자동 감지
python3 mms_tts.py -f scripts/Vietnamese.txt
python3 mms_tts.py -f scripts/Russian.txt
python3 mms_tts.py -f scripts/Mongolian.txt

# 언어 코드 직접 지정
python3 mms_tts.py "Xin chào" --lang vi -o output.wav
python3 mms_tts.py "Здравствуйте" --lang ru -o output.wav
```

---

## 언어 자동 감지 (mms_tts.py)

`--file` 옵션 사용 시 파일명으로 언어 자동 감지:

| 파일명 | 감지 언어 |
|--------|---------|
| Vietnamese.txt | vi |
| Russian.txt | ru |
| Thai.txt | th |
| Mongolian.txt | mn |
| Uzbek.txt | uz |
| Indonesian.txt | id |
| Tagalog.txt | tl |

파일명이 목록에 없으면 `--lang` 옵션 필수.

---

## 샘플 스크립트 (`scripts/`)

국민건강보험 고객센터 업무 시나리오 기반 다국어 스크립트.

| 파일 | 내용 |
|------|------|
| korean.txt | 보험료 납부 안내 |
| english.txt | 외국인 건강보험 자격 안내 |
| chinese.txt | 건강검진 대상 조회 |
| japanese.txt | 고액요양비 제도 안내 |
| Vietnamese.txt | 피부양자 등록 안내 |
| Russian.txt | 의료비 환급 안내 |
| Thai.txt | 건강검진 안내 |
| Indonesian.txt | 지역가입자 보험료 안내 |
| Tagalog.txt | 보험료 납부 안내 |
| Uzbek.txt | 주소 변경 안내 (키릴 문자) |
| Mongolian.txt | 주소 변경 안내 |

---

## 모델 정보

| 모델 | 라이선스 | VRAM | 특징 |
|------|---------|------|------|
| Fish Speech 1.5 | Apache 2.0 | ~4GB | 고품질, 음성 복제 지원 |
| Meta MMS-TTS | CC-BY-NC-4.0 | ~0.3GB/언어 | 1100개 언어, 언어별 개별 모델 |

---

## 향후 계획

- [ ] Fish Speech 참조 음성(`--ref-audio`) 활용한 화자 일관성 개선
- [ ] MMS-TTS 라틴 우즈벡어 지원 (현재 키릴만 가능)
- [ ] 언어 자동 감지 기반 Fish Speech / MMS-TTS 자동 라우팅
