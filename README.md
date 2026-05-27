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
| 출력 품질 | 44,100Hz 16-bit WAV |
| CPU 속도 | RTF 3~5x |
| 목소리 | F1~F5 (여성), M1~M5 (남성) |
| 지원 언어 | 31개 |

---

## 설치

```bash
git clone <repo>
cd multilingual-tts
bash setup.sh
```

모델(~305MB)은 첫 실행 시 Hugging Face에서 자동 다운로드.

---

## 사용법

```bash
# 파일 변환 (파일명으로 언어 자동 감지)
.venv/bin/python tts.py --input scripts/korean.txt

# 텍스트 직접 입력
.venv/bin/python tts.py --text "안녕하세요" --lang ko

# 출력 경로 지정
.venv/bin/python tts.py --text "Hello" --lang en --output hello.wav

# 목소리 변경
.venv/bin/python tts.py --text "안녕하세요" --voice F1

# 속도 / 품질 조절
.venv/bin/python tts.py --input scripts/korean.txt --speed 0.9 --steps 16
```

### 정보 확인

```bash
.venv/bin/python tts.py --voices   # 목소리 목록
.venv/bin/python tts.py --langs    # 지원 언어 목록
.venv/bin/python tts.py --config   # 현재 설정 출력
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

CLI 옵션이 config.yaml보다 우선 적용.

---

## 지원 언어 (31개)

`ko en ja fr de es it pt ru vi id hi ar tr uk pl nl sv da fi cs sk ro hu hr bg el et lv lt sl`

**미지원**: `zh` 중국어, `th` 태국어, `tl` 타갈로그어, `uz` 우즈베크어, `mn` 몽골어

---

## 라이센스

| 구성 요소 | 라이센스 | 상업 사용 |
|-----------|---------|---------|
| Supertonic 코드 | MIT | ✅ |
| Supertonic 모델 | OpenRAIL-M | ✅ (딥페이크·사칭·불법 용도 제외) |
