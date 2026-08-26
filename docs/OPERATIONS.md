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

옵션이 없으면 `config.yaml`의 기본값을 쓴다.

### 4.1 텍스트 안에서 간격/효과음을 조절하는 3가지 방법

| 방법 | 적용 위치 | 값 지정 | 비고 |
|------|-----------|---------|------|
| 구두점 프리셋 (4.2절) | 문장 **안**, 구두점 자리 | 정해진 증분값만 (임의 초 불가) | 텍스트만 쓰면 됨, 별도 설정 불필요 |
| `[PAUSE]`/`[BELL]`/`[SFX]` 줄 마커 (4.3절) | **줄 전체**가 마커여야 함 | 초 단위 자유 지정(`PAUSE`), 파일 경로 지정(`BELL`/`SFX`) | 문장 중간엔 못 넣음 |
| `<별칭>` 인라인 태그 (4.4절) | 문장 **중간** 어디든 | `config.yaml`에 등록해둔 wav만 | 태그 앞뒤 텍스트는 각각 TTS로 나눠 합성 |

### 4.2 구두점으로 문장 내 간격 조절

문장 안에 특정 구두점을 넣으면 그 자리에서 정해진 만큼 간격이 늘어난다. 값은 고정 증분이며 임의의 초 단위로
지정할 수는 없다.

| 구두점 | 예시 | 추가 간격 |
|--------|------|-----------|
| 없음 | `이 세상에는 많은 사람이 있다.` | - |
| `,` | `이 세상에는, 많은 사람이 있다.` | +0.2초 |
| `...` | `이 세상에는... 많은 사람이 있다.` | +0.8초 |
| `……` | `이 세상에는…… 많은 사람이 있다.` | +1.2초 |

CLI/API 모두 `text`에 그대로 포함해서 보내면 되고, 별도 설정이나 파라미터가 필요 없다.

### 4.3 스크립트 마커 (묵음 / wav 파일을 줄 단위로 삽입)

**줄 전체**가 아래 형식이면 마커로 인식된다 (마커는 반드시 별도 줄에 작성).

| 마커 | 설명 |
|------|------|
| `[PAUSE: 초]` | 지정한 시간만큼 묵음 삽입 (예: `[PAUSE: 1.5]`) |
| `[BELL: 경로]` | 해당 경로의 wav 파일을 그 줄 위치에 삽입 |
| `[SFX: 경로]` | `[BELL]`과 완전히 동일 (별칭) |

```text
[BELL: sounds/bell.wav]
안녕하세요, 오늘의 안내를 시작합니다.
[PAUSE: 1.0]
첫 번째 안내입니다.
[SFX: sounds/chime.wav]
감사합니다.
```

```bash
./supertonic-tts --input scripts/announcement.txt --lang ko
```

경로가 상대경로면 설치 디렉터리(프로젝트 루트) 기준으로 찾는다. 마커가 포함된 스크립트는 `--split`
옵션과 함께 쓸 수 없다. API에서 이 마커를 쓰는 방법은 5.3절 참고.

### 4.4 `<별칭>` 인라인 태그 (문장 중간에 wav 삽입)

`[BELL]`/`[SFX]`는 줄 전체를 차지해야 하지만, `<별칭>` 태그는 **문장 중간에 자유롭게** 끼워 넣을 수 있다.
사용법은 5.3절에서 API 기준으로 자세히 설명한다 — CLI도 `--text`/`--input`의 텍스트에 동일하게
`<별칭>`을 포함시키면 똑같이 동작한다.

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

### 5.3 API로 저장해둔 wav 파일을 문장 중간에 삽입하기 (`<별칭>` 태그)

미리 준비해둔 효과음/종소리 등의 wav 파일에 별칭을 붙여두면, API 요청의 `text` 필드 안에서
`<별칭>` 형태로 문장 어디든 끼워 넣을 수 있다. 별칭 앞뒤 텍스트는 각각 TTS로 합성되고, 그 사이에 등록된
wav가 그대로 삽입된다 (문장이 끊기는 지점에서도 자연스러운 흐름을 위해 tail 간격만 짧게 들어간다).

**① wav 파일 준비**

삽입할 wav 파일을 설치 디렉터리 아래 아무 곳에나 둔다 (배포판 기준 예: `sounds/`).

```bash
cp my_bell.wav /opt/supertonic-tts/sounds/
```

**② `config.yaml`에 별칭 등록**

`sfx:` 섹션에 `별칭: 경로` 형태로 원하는 만큼 등록한다. 경로가 상대경로면 설치 디렉터리
(`config.yaml`이 있는 위치) 기준으로 찾는다.

```yaml
sfx:
  시작 종: sounds/bell.wav
  종료 종: sounds/chime.wav
  안내 벨: sounds/my_bell.wav
```

> 예: `함장 승함(2단 이상 계류 시)` 안내용 종소리는 원본 녹음(`raw_sources/`에 보관, 배포 패키지에는
> 포함되지 않음)에서 타종 1회/2회 구간만 잘라 `sounds/captain_bell_1x.wav`,
> `sounds/captain_bell_2x.wav`로 등록해두었다 (`함장승함 종1회`, `함장승함 종2회` 별칭).

> **중요**: `config.yaml`을 수정한 뒤에는 반드시 API 서버를 재시작해야 반영된다
> (`./run_api.sh restart`, 6절 참고). API 서버는 기동 시 한 번만 `sfx` 목록을 읽어 메모리에 올려둔다.

**③ API 요청 시 `text`에 태그 포함**

```bash
curl -s -X POST http://127.0.0.1:9090/api/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "<시작 종> 안내말씀드리겠습니다. <종료 종>",
    "filename": "announce_001",
    "lang": "ko"
  }'
```

`scripts/call_tts_api.sh`로도 동일하게 가능하다 (셸에서 `<`, `>`는 특수문자가 아니므로 따옴표 안에서
그대로 쓰면 된다).

```bash
./scripts/call_tts_api.sh -t "<시작 종> 안내말씀드리겠습니다. <종료 종>" -f announce_001
```

`/api/tts/audio`(오디오 바로 응답)에서도 `text`는 완전히 동일하게 동작한다.

**참고 / 주의사항**

| 상황 | 동작 |
|------|------|
| `config.yaml`의 `sfx`에 없는 태그(`<모름>` 등) | 경고 로그만 남기고 건너뜀 (요청은 실패하지 않고 200 응답) |
| 등록은 됐지만 실제 파일이 없는 경우 | 마찬가지로 경고 후 건너뜀 |
| 태그 안 별칭에 앞뒤 공백 | 자동으로 trim 되므로 `< 시작 종 >`도 `시작 종`과 동일하게 인식 |
| 줄 단위 `[BELL]`/`[SFX]` 마커(4.3절)와의 차이 | 마커는 줄 전체를 차지, `<별칭>`은 문장 중간에 삽입 가능. 또한 마커는 매번 경로를 직접 쓰지만 `<별칭>`은 `config.yaml`에 미리 등록해둔 이름만 사용 |

### 5.4 구두점으로 문장 내 간격 조절 (API)

4.2절의 구두점 프리셋은 API에서도 별도 설정 없이 `text` 필드에 그대로 쓰면 동일하게 적용된다.

| 구두점 | 예시 | 추가 간격 |
|--------|------|-----------|
| 없음 | `이 세상에는 많은 사람이 있다.` | - |
| `,` | `이 세상에는, 많은 사람이 있다.` | +0.2초 |
| `...` | `이 세상에는... 많은 사람이 있다.` | +0.8초 |
| `……` | `이 세상에는…… 많은 사람이 있다.` | +1.2초 |

```bash
curl -s -X POST http://127.0.0.1:9090/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"이 세상에는...... 많은 사람이 있다.","filename":"pause_test","lang":"ko"}'
```

문장 사이(줄 단위)의 간격을 조절하려면 구두점이 아니라 `gap` 필드를 쓴다 (`api-spec.md` 3.2/3.3절 참고).

### 5.5 tts 맨 앞에 종소리 삽입 (`soundEffect`)

API 요청에 `soundEffect` 필드(정수, `0`~`4`)를 추가하면 `config.yaml`의 `sound_effect.wav_1x`/`wav_2x`에
등록해둔 종소리 wav를 tts 음성 **맨 앞**에 붙인다. `1`이면 `wav_1x`(일과타종 1타)를 2회, `2`~`4`면
`wav_2x`(예식타종 2타)를 그 횟수만큼 반복해서 붙인다. `0` 또는 생략 시 아무것도 붙지 않는다.

**① `config.yaml`에 종소리 wav 등록**

```yaml
sound_effect:
  wav_1x: sounds/captain_bell_1x.wav
  wav_2x: sounds/captain_bell_2x.wav
```

> **중요**: `config.yaml`을 수정한 뒤에는 API 서버를 재시작해야 반영된다 (`./run_api.sh restart`).

**② API 요청 시 `soundEffect` 지정**

```bash
curl -s -X POST http://127.0.0.1:9090/api/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "안녕하세요, 오늘의 안내를 시작합니다.",
    "filename": "announce_003",
    "lang": "ko",
    "soundEffect": 3
  }'
```

타종끼리는 항상 간격 없이 붙여서 재생된다 (`gap` 값과 무관하게 고정). 종소리 전체가 끝난 뒤 tts
본문이 시작되기 전 간격만 `gap` 필드 값을 쓴다 (생략 시 기본 0.4초). 해당 구간의 `wav_1x`/`wav_2x`가
설정되어 있지 않거나 파일이 없으면 경고 로그만 남기고 건너뛴다 (요청은 실패하지 않음). `/api/tts/audio`도
동일하게 지원한다.

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
| `sfx` | (없음) | `<별칭>` 인라인 태그용 wav 파일 매핑 (`별칭: 경로` 형태, 5.3절 참고). 여러 개 등록 가능 |
| `sound_effect.wav_1x` / `wav_2x` | (없음) | API `soundEffect` 필드(1: 일과타종 1타 2회 / 2~4: 예식타종 2타 N회)로 tts 맨 앞에 반복 삽입할 종소리 wav 경로 (5.5절 참고) |

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
