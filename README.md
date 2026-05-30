# SweepBot

Oracle Cloud Ubuntu 서버에서 운영하는 AI 에이전트 서비스.  
OpenClaw 게이트웨이 기반으로 `https://mlt-service.n-e.kr/molt/` 에서 접근 가능하다.

## 빠른 접속

| 경로 | 설명 |
|------|------|
| `https://mlt-service.n-e.kr/molt/` | OpenClaw 웹 UI 직접 접속 |
| `https://mlt-service.n-e.kr/mss/` → AI 분석 탭 | MSS 내 통합 뷰 |

## 구성

- **AI 엔진**: OpenClaw 2026.5.27 (Node.js 24)
- **기본 모델**: Google Gemini 2.5 Pro
- **인프라**: Oracle Cloud Ubuntu 22.04 + Nginx HTTPS
- **서비스 관리**: systemd user service (`openclaw-gateway`)

## 문서

- [설치 매뉴얼](docs/install_manual.md) — 전체 설치 및 설정 절차
- [Nginx 위치 블록](nginx/molt_location.conf) — `/molt/` 경로 설정 스니펫
- [환경변수 예시](config/.env.example) — API 키 및 설정 항목 목록
- [OpenClaw 설정 예시](config/openclaw.json.example) — 게이트웨이 설정 템플릿

## 운영 명령

```bash
# 상태 확인
systemctl --user status openclaw-gateway

# 재시작
systemctl --user restart openclaw-gateway

# 실시간 로그
journalctl --user -u openclaw-gateway -f
```

## 관련 프로젝트

- [MSS (Money Sprout Sniffer)](../MSS/) — 주식 분석 플랫폼, AI 분석 탭으로 SweepBot 연동
