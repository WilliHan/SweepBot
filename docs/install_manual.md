# SweepBot (OpenClaw) 설치 매뉴얼

> 작성일: 2026-05-30  
> 대상 서버: Oracle Cloud Ubuntu 22.04 (Free Tier)  
> 도메인: `mlt-service.n-e.kr`  
> 설치 경로: `/home/ubuntu/.nvm/versions/node/v24.16.0/lib/node_modules/openclaw`  
> 서비스 접속 URL: `https://mlt-service.n-e.kr/molt/`

---

## 1. 개요

SweepBot은 OpenClaw 게이트웨이 기반의 AI 에이전트 서비스다.  
Oracle Cloud 서버에 Node.js 앱으로 설치하고, 기존 Nginx HTTPS 구성에 `/molt` 경로로 연동한다.  
MSS(Money Sprout Sniffer) Streamlit 앱의 "AI 분석" 탭과도 연동된다.

### 구성 요소

| 구성 요소 | 역할 |
|-----------|------|
| OpenClaw Gateway | AI 에이전트 WebSocket 서버 (포트 3000, loopback) |
| Nginx | `/molt/` 경로 리버스 프록시, HTTPS 처리 |
| systemd (user) | `openclaw-gateway.service` 자동 시작 관리 |
| MSS tab_moltbot | Streamlit 내 iframe 임베드 탭 |

---

## 2. 사전 요구 사항

### 2.1 서버 환경

- Oracle Cloud Ubuntu 22.04 (또는 24.04)
- Nginx 설치 및 HTTPS 인증서 발급 완료 (`/etc/letsencrypt/live/<도메인>/`)
- 도메인 DNS A레코드 → 서버 IP 연결 완료
- Docker는 **불필요** (OpenClaw는 npm 패키지로 설치)

### 2.2 필요 API 키

`.env` 파일에 아래 키 중 하나 이상 준비:

| 키 이름 | 용도 | 비고 |
|---------|------|------|
| `GEMINI_API_KEY` | Google Gemini AI 모델 | AIzaSy... 형식, 39자 |
| `OPENAI_API_KEY` | OpenAI 모델 | 선택 |
| `OPENROUTER_API_KEY` | OpenRouter 멀티모델 | 선택 |
| `DEEPSEEK_API_KEY` | DeepSeek 모델 | 선택 |

> **주의**: Gemini API 키는 Google Cloud Console에서 "Generative Language API"가 활성화된 프로젝트의 키여야 한다. IP 제한이 설정된 경우 서버 IP를 허용 목록에 추가해야 한다.

---

## 3. 설치 절차

### 3.1 Docker 설치 (선택적 — 이번 설치에서는 미사용)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
```

> OpenClaw는 Docker를 사용하지 않는다. Docker는 다른 서비스 용도로 미리 설치만 해둔 상태.

### 3.2 Node.js 설치 (nvm 사용)

OpenClaw는 **Node.js 22.19 이상**을 요구한다. Ubuntu 기본 패키지 버전(20.x)은 미달이므로 nvm으로 24를 설치한다.

```bash
# nvm 설치
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash

# 새 셸 세션 또는 아래 로드
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Node.js 24 LTS 설치
nvm install 24
nvm use --delete-prefix v24.16.0   # npmrc prefix 충돌 해결
node --version   # v24.16.0 확인
npm --version    # 11.x 확인
```

### 3.3 OpenClaw 설치

```bash
# 설치 스크립트 다운로드 후 내용 확인 (보안 검토)
curl -fsSL https://openclaw.ai/install.sh -o /tmp/openclaw_install.sh
cat /tmp/openclaw_install.sh   # 내용 확인

# 설치 실행 (onboard 단계 건너뜀 — 나중에 수동 설정)
export NVM_DIR="$HOME/.nvm" && \. "$NVM_DIR/nvm.sh" && nvm use v24.16.0
bash /tmp/openclaw_install.sh --no-onboard

# 설치 확인
openclaw --version   # OpenClaw 2026.5.27 (27ae826)
```

> 설치 경로: `/home/ubuntu/.nvm/versions/node/v24.16.0/lib/node_modules/openclaw`

### 3.4 OpenClaw 게이트웨이 설정

설치 직후 `~/.openclaw/openclaw.json` 설정 파일을 생성한다.

```bash
export NVM_DIR="$HOME/.nvm" && \. "$NVM_DIR/nvm.sh" && nvm use v24.16.0

openclaw config patch --stdin << 'EOF'
{
  "gateway": {
    "port": 3000,
    "bind": "loopback",
    "mode": "local",
    "auth": {
      "mode": "trusted-proxy",
      "trustedProxy": {
        "userHeader": "X-Forwarded-User",
        "allowLoopback": true
      }
    },
    "trustedProxies": ["127.0.0.1"],
    "controlUi": {
      "enabled": true,
      "basePath": "/molt"
    }
  }
}
EOF
```

#### 설정 항목 설명

| 항목 | 값 | 이유 |
|------|----|------|
| `gateway.port` | `3000` | 기본 포트 |
| `gateway.bind` | `loopback` | 127.0.0.1만 바인딩, 외부 직접 접근 차단 |
| `gateway.auth.mode` | `trusted-proxy` | Nginx가 인증 대리 |
| `gateway.trustedProxies` | `["127.0.0.1"]` | trusted-proxy 모드 필수 설정 |
| `gateway.controlUi.basePath` | `"/molt"` | Nginx 경로와 일치, 경로 stripping 불필요 |

### 3.5 기본 AI 모델 설정 (Gemini 2.5 Pro)

```bash
openclaw config patch --stdin << 'EOF'
{
  "agents": {
    "defaults": {
      "models": {
        "google/gemini-2.5-pro": {
          "alias": "default"
        }
      }
    }
  }
}
EOF
```

### 3.6 systemd 서비스 등록

`openclaw gateway install` 명령으로 자동 설치한다.

```bash
export NVM_DIR="$HOME/.nvm" && \. "$NVM_DIR/nvm.sh" && nvm use v24.16.0
openclaw gateway install --port 3000
```

생성 위치: `~/.config/systemd/user/openclaw-gateway.service`

서비스 활성화 및 시작:

```bash
systemctl --user daemon-reload
systemctl --user enable openclaw-gateway
systemctl --user start openclaw-gateway
```

### 3.7 API 키 환경변수 주입

systemd 서비스는 쉘 환경변수를 상속하지 않으므로 별도 env 파일을 사용한다.

```bash
# 1) env 파일 생성 (권한 600 — 소유자만 읽기)
cat > ~/.openclaw/gateway.env << 'EOF'
GEMINI_API_KEY=여기에_실제_키_입력
EOF
chmod 600 ~/.openclaw/gateway.env

# 2) systemd 드롭인 생성
mkdir -p ~/.config/systemd/user/openclaw-gateway.service.d
cat > ~/.config/systemd/user/openclaw-gateway.service.d/env.conf << 'EOF'
[Service]
EnvironmentFile=%h/.openclaw/gateway.env
EOF

# 3) 서비스 재시작 적용
systemctl --user daemon-reload
systemctl --user restart openclaw-gateway
```

> **보안 주의**: `Environment=KEY=VALUE` 직접 지정 방식은 systemd 로그에 값이 노출되므로 반드시 `EnvironmentFile=` 방식을 사용한다.

---

## 4. Nginx 연동

기존 `mlt-service.n-e.kr` HTTPS 설정(`/etc/nginx/sites-available/mss.conf`)에 `/molt/` location 블록을 추가한다.

`nginx/molt_location.conf` 참고 또는 아래 내용을 직접 삽입:

```nginx
location = /molt {
    return 301 /molt/;
}

location /molt/ {
    proxy_pass         http://127.0.0.1:3000;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host $host;
    proxy_set_header   X-Forwarded-Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_set_header   X-Forwarded-User "openclaw-user";
    proxy_read_timeout 300;
    proxy_connect_timeout 30;
    proxy_send_timeout 120;
}
```

적용:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

> **proxy_pass 설계 근거**: `controlUi.basePath="/molt"` 설정 덕분에 OpenClaw가 `/molt/` 경로에서 직접 UI를 서빙한다. 따라서 `proxy_pass http://127.0.0.1:3000` (슬래시 없음)으로 경로를 그대로 전달하면 된다. 별도 `rewrite` 규칙 불필요.

### 4.1 SSL 인증서

기존 `mlt-service.n-e.kr` Let's Encrypt 인증서를 그대로 사용한다. 추가 certbot 실행 불필요.

---

## 5. MSS 연동 (AI 분석 탭)

MSS Streamlit 앱에 `webapp/tabs/tab_moltbot.py`를 추가하고 `mss_app.py`에 뷰를 등록한다.

### 추가된 파일 (MSS 프로젝트 내)

| 파일 | 설명 |
|------|------|
| `webapp/tabs/tab_moltbot.py` | OpenClaw UI를 iframe으로 임베드하는 탭 |
| `webapp/mss_app.py` | `"moltbot"` 뷰 및 메뉴 항목 추가 |
| `nginx/mss_https.conf` | `/molt/` location 블록 추가 |

### 접속 경로

- OpenClaw 단독: `https://mlt-service.n-e.kr/molt/`
- MSS 통합: `https://mlt-service.n-e.kr/mss/` → 사이드바 "AI 분석" 탭

---

## 6. 운영 및 관리

### 6.1 상태 확인

```bash
# 서비스 상태
systemctl --user status openclaw-gateway

# 로그 실시간 확인
journalctl --user -u openclaw-gateway -f

# HTTP 응답 확인
curl -I http://127.0.0.1:3000/molt/
curl -I https://mlt-service.n-e.kr/molt/

# AI 모델 및 인증 상태
export NVM_DIR="$HOME/.nvm" && \. "$NVM_DIR/nvm.sh"
openclaw capability model auth status
```

### 6.2 모니터링 (5분 간격 자동)

```bash
chmod +x /home/ubuntu/projects/SweepBot/scripts/monitor.sh

# crontab 등록
crontab -e
# 추가:
# */5 * * * * /home/ubuntu/projects/SweepBot/scripts/monitor.sh >> /home/ubuntu/logs/sweepbot_monitor.log 2>&1
```

### 6.3 백업 (매일 03시 자동)

```bash
chmod +x /home/ubuntu/projects/SweepBot/scripts/backup.sh

# crontab 추가:
# 0 3 * * * /home/ubuntu/projects/SweepBot/scripts/backup.sh >> /home/ubuntu/logs/sweepbot_backup.log 2>&1
```

백업 대상: `~/.openclaw/` (설정, 에이전트 상태, 세션)  
백업 위치: `/home/ubuntu/backups/sweepbot/`  
보관 기간: 7일

### 6.4 업데이트

```bash
export NVM_DIR="$HOME/.nvm" && \. "$NVM_DIR/nvm.sh" && nvm use v24.16.0
curl -fsSL https://openclaw.ai/install.sh | bash   # 최신 버전으로 업그레이드
systemctl --user restart openclaw-gateway
```

### 6.5 재시작

```bash
systemctl --user restart openclaw-gateway
```

---

## 7. 트러블슈팅

### 7.1 게이트웨이가 시작되지 않을 때

```bash
journalctl --user -u openclaw-gateway -n 30 --no-pager
```

| 오류 메시지 | 원인 | 해결 |
|------------|------|------|
| `trusted-proxy requires gateway.trustedProxies` | trustedProxies 미설정 | `openclaw config patch` 로 `"trustedProxies": ["127.0.0.1"]` 추가 |
| `device identity required` | onboard 미완료 | `openclaw configure` 실행 |
| `Invalid environment assignment` | systemd env.conf 형식 오류 | `Environment=` 대신 `EnvironmentFile=` 방식 사용 |

### 7.2 Gemini API 키 오류

```
Error: API key not valid. Please pass a valid API key.
```

Google Cloud Console 확인 항목:
1. APIs & Services → Credentials → 키 활성 상태 확인
2. APIs & Services → Library → "Generative Language API" 활성화 여부
3. 키 상세 → Application restrictions / API restrictions → 서버 IP 허용 여부

### 7.3 /molt/ 접속 불가

```bash
# 게이트웨이 포트 확인
ss -ltnp | grep 3000

# nginx 설정 검증
sudo nginx -t

# 내부 연결 테스트
curl -v http://127.0.0.1:3000/molt/
```

### 7.4 MSS "AI 분석" 탭에서 iframe 표시 안 됨

브라우저 개발자 도구 → Console에서 CORS/CSP 에러 확인.  
`X-Frame-Options` 또는 `Content-Security-Policy` 헤더 이슈인 경우 Nginx에 아래 추가:

```nginx
# /molt/ location 블록 안에 추가
add_header X-Frame-Options "SAMEORIGIN";
```

---

## 8. 디렉토리 구조

```
/home/ubuntu/
├── .nvm/versions/node/v24.16.0/
│   └── lib/node_modules/openclaw/          # OpenClaw 설치 위치
├── .openclaw/
│   ├── openclaw.json                        # 게이트웨이 설정
│   ├── gateway.env                          # API 키 (권한 600, git 제외)
│   ├── agents/main/agent/
│   │   ├── models.json                      # 모델 카탈로그
│   │   └── auth-profiles.json               # 인증 프로파일
│   └── logs/                                # 게이트웨이 로그
├── .config/systemd/user/
│   ├── openclaw-gateway.service             # systemd 서비스 (자동 생성)
│   └── openclaw-gateway.service.d/
│       └── env.conf                         # EnvironmentFile 드롭인
├── projects/
│   ├── MSS/                                 # MSS 프로젝트 (기존)
│   │   ├── nginx/mss_https.conf             # /molt/ 블록 포함
│   │   └── webapp/tabs/tab_moltbot.py       # MSS AI 분석 탭
│   └── SweepBot/                            # 이 저장소
│       ├── config/
│       │   ├── .env.example
│       │   └── openclaw.json.example
│       ├── docs/
│       │   └── install_manual.md            # 이 문서
│       ├── nginx/
│       │   └── molt_location.conf           # Nginx 위치 블록 스니펫
│       └── scripts/
│           ├── monitor.sh
│           └── backup.sh
├── logs/
│   ├── sweepbot_monitor.log
│   └── sweepbot_backup.log
└── backups/sweepbot/                        # 백업 보관 위치
```

---

## 9. 참고

- OpenClaw 공식 문서: https://docs.openclaw.ai
- 설치 스크립트: `curl -fsSL https://openclaw.ai/install.sh`
- OpenClaw 버전: `2026.5.27 (27ae826)`
- Node.js 버전: `v24.16.0`
- 기본 AI 모델: `google/gemini-2.5-pro` (컨텍스트 1M, reasoning 지원)
