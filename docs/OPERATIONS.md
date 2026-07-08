# 운영 매뉴얼

설치가 끝난 multilingual-tts 배포판을 일상적으로 운영하기 위한 문서. 설치 자체는 [INSTALL.md](INSTALL.md) 참고.

---

## 1. 구성 요소

| 파일 | 역할 |
|------|------|
| `supertonic-tts` | CLI. 한 번 실행하고 끝나는 배치성 변환 (파일 → WAV, 텍스트 → WAV) |
| `supertonic-api` | HTTP API 서버 본체. 보통 직접 실행하지 않고 `run_api.sh`로 관리 |
| `run_api.sh` | API 서버 start/stop/status/restart 관리 스크립트 |
| `scripts/call_tts_api.sh` | 실행 중인 API에 curl로 요청을 보내는 래퍼 스크립트 |
| `config.yaml` | 목소리/속도/품질/포트 등 설정 |
| `output/` | 생성된 WAV 파일 저장 위치 |
| `logs/api.log` | API 서버 표준출력/에러 로그 |

---

## 2. API 서버 운영

### 2.1 시작 / 중지 / 상태 / 재시작

```bash
cd /opt/supertonic-tts
./run_api.sh start      # 백그라운드로 기동, PID를 .api.pid 에 기록
./run_api.sh status     # 프로세스 상태 + /api/health 호출 결과
./run_api.sh stop       # 정상 종료 (SIGTERM, 10초 대기 후 SIGKILL)
./run_api.sh restart    # stop 후 start
```

`status`는 아래 세 줄을 출력한다.

```
process: running (pid 12345, managed)
port:    9090
health:  HTTP 200
```

- `health: HTTP 200`이 아니면 서버가 떠 있어도 요청을 못 받는 상태일 수 있음 → `logs/api.log` 확인
- `process: running (..., orphan - not in .api.pid)`는 `run_api.sh`가 아닌 방법으로 뜬 프로세스가 그 포트를
  이미 점유 중이라는 뜻. `stop` 또는 `start`로 다시 실행하면 관리 대상으로 편입(adopt)된다.

### 2.2 부팅 시 자동 시작 (systemd)

상시 운영 서버라면 systemd 서비스로 등록해 서버 재부팅 시 자동 기동되게 한다.

`/etc/systemd/system/supertonic-tts.service` 예시:

```ini
[Unit]
Description=multilingual-tts API server
After=network.target

[Service]
Type=forking
User=aicc
WorkingDirectory=/opt/supertonic-tts
ExecStart=/opt/supertonic-tts/run_api.sh start
ExecStop=/opt/supertonic-tts/run_api.sh stop
ExecReload=/opt/supertonic-tts/run_api.sh restart
PIDFile=/opt/supertonic-tts/.api.pid
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now supertonic-tts
sudo systemctl status supertonic-tts
```

`User=`는 실제 설치/운영 계정으로 바꾼다. `run_api.sh`가 이미 PID 파일과 중복 기동 방지를 처리하므로
`Type=forking` + `PIDFile`로 충분하다.

---

## 3. 로그

- 위치: `logs/api.log` (API 서버만 해당, CLI는 표준출력으로 바로 출력)
- 내용: uvicorn 접속 로그(`INFO: ... "POST /api/tts HTTP/1.1" 200 OK` 등) + 서버 기동 메시지
- 별도 로테이션 설정이 없으므로 장기 운영 시 `logrotate` 등록을 권장한다:

```
# /etc/logrotate.d/supertonic-tts
/opt/supertonic-tts/logs/api.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
```

(`copytruncate`를 쓰는 이유: 실행 중인 프로세스가 로그 파일 디스크립터를 계속 들고 있으므로, 파일을
바꿔치기하지 않고 내용만 자른다.)

---

## 4. CLI 사용법

```bash
# 텍스트 직접 입력
./supertonic-tts --text "안녕하세요" --lang ko

# 파일 입력 (파일명에서 언어 자동 인식: korean.txt → ko)
./supertonic-tts --input scripts/korean.txt

# 목소리/속도/품질 지정
./supertonic-tts --text "Hello" --lang en --voice F3 --speed 1.1 --steps 16

# 줄 단위로 개별 WAV 생성
./supertonic-tts --input scripts/sample.txt --split --output output/my_dir

# 사용 가능한 목소리 / 지원 언어 / 현재 설정 확인
./supertonic-tts --voices
./supertonic-tts --langs
./supertonic-tts --config
```

옵션이 없으면 `config.yaml`의 기본값을 쓴다. 텍스트 안에 `[PAUSE: 1.5]`, `[BELL: sounds/bell.wav]`,
`[SFX: sounds/chime.wav]` 마커를 줄 단위로 넣으면 묵음/효과음을 끼워 넣을 수 있다 (자세한 건 README 참고).

---

## 5. API 사용법

### 5.1 스크립트로 호출

```bash
./scripts/call_tts_api.sh -t "안녕하세요" -f greeting            # output/greeting.wav 로 저장
./scripts/call_tts_api.sh -t "Hello" -l en -v F3 -f hello_en
./scripts/call_tts_api.sh -t "안녕하세요" --audio out.wav         # 저장 없이 오디오 응답을 바로 파일로
./scripts/call_tts_api.sh --health
```

### 5.2 curl로 직접 호출

```bash
curl -s http://127.0.0.1:9090/api/health

curl -s -X POST http://127.0.0.1:9090/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"안녕하세요","filename":"greeting","lang":"ko"}'
```

엔드포인트 전체 규격(요청/응답 스키마, 에러 코드)은 [api-spec.md](api-spec.md) 참고.

---

## 6. 설정 변경

`config.yaml` 수정 후에는 **API 서버를 재시작**해야 반영된다 (`./run_api.sh restart`). CLI는 실행할 때마다
파일을 새로 읽으므로 재시작 개념이 없다.

| 키 | 기본값 | 설명 |
|----|--------|------|
| `supertonic.voice` | `M2` | 기본 목소리 (F1~F5 여성, M1~M5 남성) |
| `supertonic.speed` | `1.0` | 발화 속도 (0.5~2.0) |
| `supertonic.steps` | `16` | 생성 품질 단계 (4~16). 높을수록 느리지만 품질 좋음 |
| `output.directory` | `output` | CLI 기본 출력 폴더. 상대경로는 설치 디렉터리 기준 |
| `api.host` | `0.0.0.0` | API 바인딩 주소 |
| `api.port` | `9090` | API 리스닝 포트 |
| `api.output_directory` | `output` | API가 저장하는 WAV 폴더. 상대경로는 설치 디렉터리 기준 |

CLI 옵션(`--voice`, `--speed`, `--steps` 등)은 `config.yaml`보다 우선한다.

---

## 7. 트러블슈팅

| 증상 | 확인/조치 |
|------|-----------|
| `run_api.sh start` 했는데 `status`에서 `health: HTTP 000` | `logs/api.log` 확인. 모델 다운로드 중이거나(첫 실행) 포트 충돌 가능성 |
| `[error] port 9090 is already in use by another process` | `ss -tlnp \| grep :9090`으로 점유 프로세스 확인 후 처리, 또는 `config.yaml`의 `api.port` 변경 |
| 첫 실행이 오래 걸리거나 멈춤 | 모델 다운로드 중(~305MB). 아웃바운드 인터넷 확인, 프록시 필요 시 `HTTPS_PROXY` 환경변수 설정 후 재시도 |
| `생성` 자체가 실패, 500 에러 | `logs/api.log`의 스택트레이스 확인. 디스크 공간 부족 여부(`df -h`)도 확인 |
| CLI/API 결과 음질·속도가 기대와 다름 | `config.yaml`의 `speed`/`steps` 조정, `steps`를 올리면 품질↑ 속도↓ |
| 서버는 떠 있는데 다른 서버/PC에서 접속 안 됨 | `api.host: 0.0.0.0`인지, 방화벽에서 포트가 열려있는지 확인 (`firewall-cmd --list-ports` 등) |
| 재부팅 후 서비스가 안 뜸 | systemd 미등록 상태. 2.2절 참고해 등록 |

---

## 8. 백업 대상

- `config.yaml` — 운영 설정
- `output/` — 필요 시 생성물 보관 정책에 따라 (기본적으로는 재생성 가능하므로 필수는 아님)
- `~/.cache/supertonic3/` — 모델 캐시. 재다운로드 가능하지만 폐쇄망이면 백업 권장

`supertonic-tts`/`supertonic-api` 실행파일 자체는 배포 아카이브(`supertonic-tts-YYYYMMDD.tar.gz`)로 대체
가능하므로 별도 백업 불필요.

---

## 9. 보안 운영 지침

- API에는 인증이 없다. `api.host: 0.0.0.0`으로 열어두면 네트워크 내 누구나 호출 가능하므로, 다음 중
  하나를 적용한다.
  - 방화벽으로 API 포트를 신뢰할 수 있는 소스 IP/대역으로 제한
  - `api.host: 127.0.0.1`로 바꾸고, 인증을 처리하는 리버스 프록시(nginx 등) 뒤에서만 서비스
- 배포판에는 `.py` 소스가 포함되어 있지 않다. 다만 PyInstaller 실행파일은 완전한 암호화가 아니라
  "코드를 실행파일 안에 컴파일해 넣는" 방식이므로, 전문 도구로 바이트코드를 추출하려는 시도까지
  막지는 못한다는 점은 인지한다 (일반적인 사내 배포/열람 방지 목적으로는 충분).
- `logs/api.log`에는 요청 경로와 상태 코드만 남고 요청 본문(텍스트 내용)은 기록되지 않는다.
