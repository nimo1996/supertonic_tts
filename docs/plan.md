# TTS 시스템 재구성 계획서

작성일: 2026-05-26  
버전: v2 (CPU 우선, 상업용)

---

## 1. 현재 상태 분석

### 기존 구성 문제점

| 엔진 | 실제 라이센스 | 상업 사용 | 현황 |
|------|-------------|---------|------|
| Fish Speech 1.5 | Fish Audio Research License | ⚠️ 제한 있음 | fish-speech/ 디렉터리 누락 |
| Meta MMS-TTS | CC-BY-NC-4.0 | ❌ 불가 | 의존성 미설치 |

> Fish Speech는 README에 Apache 2.0으로 표기되어 있으나, 실제 레포지토리 라이센스는  
> "Fish Audio Research License"로 상업적 사용 전 별도 확인이 필요합니다.

---

## 2. 요구사항

| 항목 | 조건 |
|------|------|
| 라이센스 | Apache 2.0 / MIT (상업 사용 명확히 가능) |
| 실행 환경 | **CPU 우선** — 시간이 걸려도 음질이 핵심 |
| GPU | 선택적 가속 지원 (있으면 사용, 없어도 동작) |
| 한국어 품질 | 최우선 |
| 다국어 | 지원하면 좋음 |
| 배포 방식 | 로컬 실행, 자체 호스팅 |

---

## 3. 엔진 선택

### 상업용 CPU TTS 엔진 비교

| 엔진 | 라이센스 | 한국어 | CPU RTF | RAM | ONNX | 다국어 |
|------|---------|--------|---------|-----|------|--------|
| **Kokoro TTS** | Apache 2.0 | ★★★★★ | 3~11× 실시간 | <2GB | ✅ | 9개 언어 |
| **MeloTTS** | MIT | ★★★★☆ | 실시간 | 낮음 | ✅ | 6개 언어 |
| Bark | MIT | ★★★☆☆ | 느림 | 8GB | ✅ | 13개 언어 |
| Piper TTS | GPL | ★★★☆☆ | 매우 빠름 | 500MB | ✅ | 다국어 |
| CosyVoice 2 | Apache 2.0 | ★★★★☆ | 10~50× 느림 | 16GB | ✅ | 다국어 |
| Fish Speech 1.5 | ⚠️ 전용 | ★★★★★ | CPU 병목 | GPU 권장 | ❌ | 8개 언어 |

### 결론

**1순위: Kokoro TTS (Apache 2.0)**
- CPU에서 3~11배 실시간 속도 (현실적으로 가장 빠름)
- 82M 파라미터, ONNX 80MB로 경량
- 한국어 품질 최상급 (Apache 2.0 엔진 중)
- GPU 있으면 자동 가속

**2순위: MeloTTS (MIT)**
- 한국어 전용 모델 존재 (MeloTTS-Korean)
- CPU 실시간 추론 가능, 매우 가벼움
- Kokoro 미지원 언어 보완용 (베트남어, 인도네시아어 등)

**Bark (MIT) — 선택적 추가**
- 13개 언어 지원, 가장 자연스러운 감정 표현
- CPU에서 느림 → "고품질/느린 모드" 옵션으로만 제공

---

## 4. 목표 아키텍처

```
multilingual_tts/
├── tts.py                    # 통합 CLI (기존 스타일 유지)
├── engines/
│   ├── kokoro_engine.py      # Kokoro TTS 래퍼 (주 엔진)
│   ├── melo_engine.py        # MeloTTS 래퍼 (보조 엔진)
│   └── bark_engine.py        # Bark 래퍼 (선택적 고품질 모드)
├── core/
│   ├── router.py             # 언어 코드 → 엔진 자동 라우팅
│   ├── audio.py              # 오디오 후처리 (정규화, 포맷 변환)
│   └── lang_detect.py        # 텍스트/파일명 기반 언어 감지
├── models/                   # 모델 캐시 (gitignore)
│   ├── kokoro/
│   └── melo/
├── scripts/                  # 기존 언어별 샘플 텍스트 유지
├── output/                   # 생성 음성 파일 (gitignore)
├── reference/                # 레퍼런스 음성 (선택적)
├── docs/
│   └── plan.md
├── requirements.txt
├── setup.sh                  # 자동 설치 스크립트
└── README.md
```

### 언어 → 엔진 라우팅 전략

```
입력 텍스트/언어 코드
        ↓
  Kokoro 지원 여부?
   ↙ Yes        ↘ No
Kokoro TTS    MeloTTS 지원 여부?
(Apache 2.0)    ↙ Yes    ↘ No
              MeloTTS    Bark
               (MIT)     (MIT)
```

### Kokoro 지원 언어 (9개)
한국어, 영어(미/영), 일본어, 중국어, 프랑스어, 스페인어, 인도계 영어, 브라질 포르투갈어

### MeloTTS 추가 커버 (6개)
한국어, 영어, 중국어, 일본어, 스페인어, 프랑스어 (+ Kokoro 미지원 언어 폴백)

---

## 5. 구현 단계

### Phase 1: Kokoro TTS 구축 (한국어 핵심)

```bash
pip install kokoro-onnx soundfile
```

**엔진 래퍼 (`engines/kokoro_engine.py`)**
- ONNX 런타임으로 CPU 최적화 추론
- GPU 감지 시 자동 전환 (`onnxruntime-gpu`)
- 한국어 기본, 언어코드 파라미터로 전환 가능

**기본 사용법**
```bash
python tts.py --input scripts/korean.txt --lang ko
python tts.py --input scripts/english.txt --lang en
python tts.py --text "안녕하세요" --lang ko --output output/test.wav
```

### Phase 2: MeloTTS 통합 (다국어 보완)

```bash
pip install melo-tts
python -m melo.init_downloads --language KR
```

- 베트남어, 태국어, 인도네시아어 등 Kokoro 미지원 언어 자동 라우팅
- 기존 `scripts/` 폴더의 11개 언어 전체 커버

### Phase 3: 고품질 모드 (선택적)

- Bark 통합: `--quality high` 플래그로 활성화
- 생성 시간 ~3~5분/문단이지만 가장 자연스러운 억양
- 감정/스타일 프롬프트 지원 (`[laughs]`, `[sighs]` 등)

---

## 6. CPU 최적화 전략

| 기법 | 적용 엔진 | 효과 |
|------|---------|------|
| ONNX Runtime | Kokoro, MeloTTS | CPU 추론 최적화 |
| INT8 양자화 | Kokoro ONNX | 모델 크기 절반, 속도 1.5× |
| 멀티스레딩 | 모든 엔진 | `OMP_NUM_THREADS` 자동 설정 |
| 문장 단위 배치 | tts.py | 긴 텍스트를 청크로 분할 처리 |
| 모델 캐싱 | 모든 엔진 | 첫 로딩 후 메모리 유지 |

---

## 7. 언어 지원 계획

| 언어 | 코드 | 엔진 | 기존 샘플 |
|------|------|------|---------|
| 한국어 | ko | Kokoro | ✅ korean.txt |
| 영어 | en | Kokoro | ✅ english.txt |
| 중국어 | zh | Kokoro | ✅ chinese.txt |
| 일본어 | ja | Kokoro | ✅ japanese.txt |
| 베트남어 | vi | MeloTTS | ✅ Vietnamese.txt |
| 러시아어 | ru | MeloTTS | ✅ Russian.txt |
| 태국어 | th | MeloTTS | ✅ Thai.txt |
| 인도네시아어 | id | MeloTTS | ✅ Indonesian.txt |
| 타갈로그어 | tl | MeloTTS/Bark | ✅ Tagalog.txt |
| 우즈베크어 | uz | Bark | ✅ Uzbek.txt |
| 몽골어 | mn | Bark | ✅ Mongolian.txt |

---

## 8. 라이센스 정리

| 엔진 | 라이센스 | 상업 사용 | 출처 표기 |
|------|---------|---------|---------|
| Kokoro TTS | Apache 2.0 | ✅ 명확히 가능 | 필요 |
| MeloTTS | MIT | ✅ 명확히 가능 | 필요 |
| Bark | MIT | ✅ 명확히 가능 | 필요 |
| ~~Fish Speech~~ | Fish Audio 전용 | ⚠️ 별도 확인 | - |
| ~~MMS-TTS~~ | CC-BY-NC-4.0 | ❌ 불가 | - |

---

## 9. 시스템 요구사항

| 항목 | 최소 (CPU 전용) | 권장 (CPU+GPU) |
|------|--------------|--------------|
| CPU | 4코어 이상 | 8코어+ |
| RAM | 4GB | 8GB+ |
| GPU VRAM | 없어도 됨 | 4GB+ (선택) |
| 저장공간 | 3GB | 5GB+ |
| OS | Linux / macOS / Windows | Linux 권장 |
| Python | 3.10+ | 3.11 |

---

## 10. 우선순위 및 일정

| 단계 | 작업 | 우선순위 |
|------|------|---------|
| Phase 1-A | Kokoro 설치 + 한국어 테스트 | 🔴 필수 |
| Phase 1-B | `tts.py` 통합 CLI 작성 | 🔴 필수 |
| Phase 1-C | `requirements.txt` + `setup.sh` | 🔴 필수 |
| Phase 2 | MeloTTS 통합 + 다국어 라우팅 | 🟡 권장 |
| Phase 3 | Bark 고품질 모드 | 🟢 선택 |
| Phase 3 | GPU 자동 감지 및 전환 | 🟢 선택 |

---

## 다음 액션

1. **Kokoro TTS** 설치 및 한국어 샘플 테스트 (Phase 1-A)
2. CPU 성능 실측 (현재 장비 기준 RTF 확인)
3. MeloTTS 병렬 설치 검토
4. 기존 `tts.py` 리팩터링 방향 결정
