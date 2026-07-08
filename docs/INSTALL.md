# 설치 매뉴얼

multilingual-tts 배포판 설치 절차. 이 배포판은 **컴파일된 실행파일**(`supertonic-tts`, `supertonic-api`)만 포함하며,
`.py` 소스 코드는 들어있지 않다. 소스에서 배포판을 만드는 방법은 맨 아래 "빌드 담당자용" 절을 참고.

---

## 1. 요구 사항

| 항목 | 내용 |
|------|------|
| OS | Rocky Linux 8 x86_64 (빌드 시 사용한 배포판과 동일 계열 권장) |
| 아키텍처 | x86_64 |
| 디스크 | 최소 1GB 여유 공간 (실행파일 ~65MB × 2 + 모델 ~305MB + 생성 음성 파일) |
| 네트워크 | 최초 1회 모델 다운로드 시 HuggingFace(`huggingface.co`)로 아웃바운드 접속 필요. 폐쇄망은 4절 참고 |
| 방화벽 | API를 외부에 노출할 경우 `config.yaml`의 `api.port`(기본 9090) 인바운드 허용 |
| 권한 | 실행파일에 실행 권한(`chmod +x`)만 있으면 됨. root 불필요, 일반 사용자 계정으로 설치·운영 가능 |

PyInstaller로 만든 실행파일은 **빌드에 사용한 OS의 glibc 이상 버전**에서만 동작한다. 빌드는 Rocky Linux 8에서
했으므로, Rocky Linux 8/9 또는 그보다 최신인 RHEL 계열에서는 문제없이 동작한다. Ubuntu 등 다른 배포판에
설치해야 하면 그 배포판에서 다시 빌드해야 한다.

---

## 2. 설치 절차

### 2.1 배포 아카이브 전달받기

빌드 담당자로부터 `supertonic-tts-YYYYMMDD.tar.gz` 파일을 전달받는다 (사내 파일 공유, scp 등).

### 2.2 압축 해제

```bash
mkdir -p /opt/supertonic-tts   # 설치 위치는 임의로 선택 가능. 예시로 /opt 사용
tar -C /opt/supertonic-tts --strip-components=1 -xzf supertonic-tts-YYYYMMDD.tar.gz
cd /opt/supertonic-tts
```

설치 후 디렉터리 구조:

```
/opt/supertonic-tts/
├── supertonic-tts       # CLI 실행파일
├── supertonic-api       # API 서버 실행파일
├── run_api.sh           # API 서버 시작/중지/상태 스크립트
├── config.yaml           # 설정 파일 (voice, speed, host, port, ...)
├── scripts/
│   ├── call_tts_api.sh   # API 호출용 curl 래퍼
│   └── *.txt             # 언어별 샘플 텍스트
├── sounds/               # [BELL]/[SFX] 마커용 효과음 샘플
├── output/                # 생성된 WAV 저장 위치 (초기엔 비어있음)
├── logs/                  # API 서버 로그
├── INSTALL.md             # 이 문서
└── OPERATIONS.md          # 운영 매뉴얼
```

### 2.3 실행 권한 확인

압축 해제 시 보통 권한이 유지되지만, 확인 차 한 번 더 부여한다.

```bash
chmod +x supertonic-tts supertonic-api run_api.sh scripts/call_tts_api.sh
```

### 2.4 설정 확인

`config.yaml`을 열어 운영 환경에 맞게 조정한다.

```yaml
supertonic:
  voice: M2          # 기본 목소리 (F1~F5 / M1~M5)
  speed: 1.0          # 발화 속도 (0.5~2.0)
  steps: 16            # 품질 단계 (4~16, 높을수록 느리고 품질 좋음)

output:
  directory: output   # CLI 기본 출력 폴더

api:
  host: 0.0.0.0        # 0.0.0.0 = 모든 인터페이스에서 접속 허용
  port: 9090
  output_directory: output   # 상대경로는 이 config.yaml 이 있는 설치 디렉터리 기준
```

설정 항목별 상세 설명은 [OPERATIONS.md](OPERATIONS.md)의 "설정 변경" 절 참고.

> **보안 주의**: API는 인증 기능이 없다(`docs/api-spec.md` 참고). `api.host: 0.0.0.0`으로 두면 네트워크 상의
> 누구나 API를 호출할 수 있으므로, 사내망 전용으로 방화벽을 잠그거나 `api.host: 127.0.0.1`로 두고 별도
> 리버스 프록시/게이트웨이 뒤에서만 서비스하는 것을 권장한다.

### 2.5 첫 실행 (모델 다운로드 확인)

TTS 모델(~305MB)은 실행파일에 포함되어 있지 않고, **첫 실행 시 자동으로** `~/.cache/supertonic3/`에
다운로드된다. 인터넷이 되는 환경에서 최초 1회 아래처럼 실행해 정상 다운로드되는지 확인한다.

```bash
./supertonic-tts --text "설치 테스트입니다" --lang ko -o /tmp/install_test.wav
```

몇 초~수십 초 내에 `[TTS] ...` 로그와 함께 `생성: N.Ns | ...` 줄이 출력되면 성공이다. 두 번째 실행부터는
캐시를 재사용하므로 다운로드 없이 바로 실행된다.

### 2.6 API 서버 기동 확인

```bash
./run_api.sh start
./run_api.sh status     # health: HTTP 200 이 나오면 정상
./scripts/call_tts_api.sh -t "안녕하세요" -f smoke_test
./run_api.sh stop
```

여기까지 정상이면 설치가 끝난 것이다. 상시 운영(부팅 시 자동 시작, systemd 등록 등)은
[OPERATIONS.md](OPERATIONS.md)를 참고한다.

---

## 3. 여러 대에 배포하기

동일 아카이브(`supertonic-tts-YYYYMMDD.tar.gz`)를 각 서버에 복사해 2절 절차를 반복하면 된다.
서버마다 `~/.cache/supertonic3/`에 모델을 각자 새로 받아야 하므로(자동), 서버 수가 많고 인터넷이
느리다면 4절의 오프라인 방법으로 모델 캐시를 미리 준비해 함께 배포하는 것이 빠르다.

---

## 4. 폐쇄망(오프라인) 설치

인터넷이 안 되는 서버에 설치해야 하면, 인터넷이 되는 다른 장비에서 모델을 미리 받아 캐시 디렉터리를
통째로 복사해 온다.

```bash
# 인터넷 되는 장비에서
./supertonic-tts --text "warmup" -o /tmp/warmup.wav
tar -C ~/.cache -czf supertonic3-model-cache.tar.gz supertonic3

# 오프라인 서버로 옮긴 뒤
mkdir -p ~/.cache
tar -C ~/.cache -xzf supertonic3-model-cache.tar.gz
```

이후 오프라인 서버에서 `./supertonic-tts ...`를 실행하면 다운로드 없이 캐시를 바로 사용한다.

---

## 5. 업데이트

새 배포 아카이브를 받으면:

```bash
cd /opt/supertonic-tts
./run_api.sh stop
tar -C /tmp/supertonic-update --strip-components=1 -xzf supertonic-tts-새버전.tar.gz
cp supertonic-tts supertonic-api run_api.sh /opt/supertonic-tts/   # 실행파일과 스크립트만 교체
# config.yaml, output/, logs/ 는 그대로 유지 (덮어쓰지 않는다)
./run_api.sh start
```

`config.yaml`은 새 버전에 새 항목이 추가됐을 수 있으니, 업데이트 노트를 확인하고 필요한 항목만 수동으로 반영한다.

---

## 6. 제거

```bash
./run_api.sh stop
rm -rf /opt/supertonic-tts
# 모델 캐시까지 지우려면 (다른 용도로 재사용하지 않는 경우에만)
rm -rf ~/.cache/supertonic3
```

---

## 7. 빌드 담당자용: 배포 아카이브 만들기

소스 저장소에서 배포판을 새로 빌드하려면(소스 코드 접근 권한이 있는 개발 환경에서):

```bash
bash setup.sh     # 최초 1회: 빌드용 venv + 의존성 설치
bash build.sh     # PyInstaller로 컴파일 + dist/supertonic-tts-YYYYMMDD.tar.gz 생성
```

`build.sh`는 `tts.py`/`api.py`를 각각 단일 실행파일로 컴파일하고, 실행에 필요한 `config.yaml`,
`run_api.sh`, `scripts/`, `sounds/`를 묶어 `dist/supertonic-tts-pkg/`에 배치한 뒤 tar.gz로 압축한다.
결과 아카이브에는 `.py` 파일이 전혀 포함되지 않는다(`find dist/supertonic-tts-pkg -name "*.py"`로 확인 가능).

> 실행파일은 빌드에 사용한 OS/glibc에 종속된다. 배포 대상 서버와 동일하거나 더 낮은 버전의
> Rocky Linux/RHEL 계열에서 빌드해야 한다.
