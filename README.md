# TutorAgent

LangGraph 멀티에이전트 기반 AI 학습 도우미. 대학 강의 PDF를 기반으로 1:1 과외, 자동 퀴즈 생성, Slack 복습 스케줄링까지 에이전트가 자율적으로 수행합니다.

## 주요 기능

- **1:1 과외 (Tutor)** — 사고 유도형 학습. 질문 → 힌트 → 답변 확인
- **자료 기반 퀴즈** — 7 객관식 + 3 OX, 총 10문제 자동 생성
- **Q&A** — 강의 자료 기반 개념/용어 질문 답변
- **자료 검색** — Gemini File Search로 PDF 내용 검색
- **복습 스케줄링** — 학습 완료 → 다음날 Slack 자동 퀴즈 → 틀린 문제 재시험 예약
- **Slack 퀴즈** — 버튼으로 퀴즈 응답 + 채점 + 재시험 예약

## 기술 스택

| 구성요소 | 기술 |
|---------|------|
| 에이전트 프레임워크 | LangGraph >= 0.4 |
| LLM | Google Gemini 2.5 Flash |
| 자료 검색 | Gemini File Search API |
| 백엔드 | FastAPI + SQLite |
| 프론트엔드 | React 19 + Zustand + Tailwind CSS |
| Slack 연동 | Slack Bolt (퀴즈 전송/응답) |
| 배포 | Railway (Volume: /app/data) |
| 크론 | Google Cloud Scheduler |

## 로컬 개발 환경 설정

### 사전 요구사항

- Python 3.13+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python 패키지 매니저)

### 1. 의존성 설치

```bash
# 백엔드
uv sync

# 프론트엔드
cd web && npm install && cd ..
```

### 2. 환경변수 설정

`.env` 파일을 프로젝트 루트에 생성합니다:

```
GOOGLE_API_KEY=              # Gemini API 키
JWT_SECRET_KEY=              # JWT 서명 키 (임의 문자열)
FILE_SEARCH_STORE_NAME=      # Gemini File Search Store (선택)
DEFAULT_USER_ID=             # 기본 사용자 ID (선택)

# Slack 연동 (선택 — 없으면 Slack 기능 비활성)
SLACK_ENABLED=               # 1이면 일일 복습 퀴즈를 Slack에도 전송(기본 off — 인앱 '복습'만)
SLACK_BOT_TOKEN=             # Slack Bot OAuth 토큰
SLACK_SIGNING_SECRET=        # Slack 요청 서명 시크릿
SLACK_CHANNEL_ID=            # 퀴즈 전송 채널 ID

# 크론 (선택)
CRON_SECRET=                 # 예약 퀴즈 생성 엔드포인트 인증키

# 원문 낭독 TTS (선택)
GCP_TTS_API_KEY=             # Cloud Text-to-Speech 전용 키 (없으면 GOOGLE_API_KEY 사용)
TTS_ENGINE=                  # gcp(기본) | gemini

# 베타 운영 (선택)
INVITE_CODE=                 # 설정 시 가입에 초대 코드 요구
ALLOWED_ORIGINS=             # CORS 허용 origin (콤마 구분, 기본 localhost)
SENTRY_DSN=                  # 설정 시 Sentry 에러 추적 활성화
LIMIT_CHAT_DAILY=            # 사용자별 일 채팅 한도 (기본 100, 0=무제한)
LIMIT_TTS_CHARS_MONTHLY=     # 사용자별 월 낭독 문자 한도 (기본 300000)
LIMIT_UPLOADS_MONTHLY=       # 사용자별 월 업로드 한도 (기본 20)
```

> 프로덕션(Railway)에서는 `JWT_SECRET_KEY`와 `CRON_SECRET`이 없으면 서버가 기동을 거부합니다.

#### 프론트엔드 계측 (선택 — PostHog)

PostHog 퍼널 계측은 **빌드 타임** 변수라 백엔드 `.env`가 아니라 `web/.env`(또는 빌드 시 환경)에 넣어야
`npm run build` 산출물에 주입됩니다. **Railway 런타임 변수로는 적용되지 않습니다.** 키가 없으면 계측은
전체 비활성(빌드·실행에 영향 없음).

```
# web/.env
VITE_POSTHOG_KEY=            # PostHog 프로젝트 API 키 (없으면 계측 비활성)
VITE_POSTHOG_HOST=           # PostHog 호스트 (기본 https://us.i.posthog.com)
```

### 3. 실행

```bash
# 백엔드 (http://localhost:8000)
uv run python run_api.py

# 프론트엔드 (http://localhost:5173) — 별도 터미널
cd web && npm run dev
```

### 4. 접속

- 브라우저에서 http://localhost:5173 접속
- 회원가입 후 클래스 생성 → PDF 업로드 → 대화 시작

## 프로젝트 구조

```
tutor_agent/
├── agents/
│   ├── graph.py               # LangGraph StateGraph
│   ├── state.py               # TutorAgentState
│   ├── supervisor_agent.py    # Supervisor (의도 분석 → 라우팅)
│   ├── search_agent.py        # 자료 검색
│   ├── quiz_agent.py          # 퀴즈 생성
│   ├── qna_agent.py           # Q&A 답변
│   ├── tutor_agent.py         # 1:1 과외
│   └── tools/
│       ├── shared_tools.py    # transfer_to_agent (Command 패턴)
│       └── tutor_tools.py     # search_material, get_study_memos
├── platforms/
│   ├── api.py                 # FastAPI REST API + SSE
│   └── slack.py               # Slack Bolt (퀴즈 전송/응답)
├── auth.py                    # JWT 인증 + SQLite (users, classes, quiz_results, completions)
├── service.py                 # 서비스 레이어 (그래프 실행, 크론, 날짜 파싱)
└── file_search.py             # Gemini File Search Store 관리

web/src/
├── api/client.ts              # HTTP + SSE 클라이언트
├── stores/                    # Zustand 상태 관리
└── components/                # React 컴포넌트
```

## 배포

### Railway

```bash
# Railway CLI로 배포
railway up

# Volume 마운트 (DB 영구 저장)
railway volume add --mount-path /app/data
```

Railway Variables에 `.env`의 환경변수를 모두 설정해야 합니다.

### Cloud Scheduler (일일 퀴즈 생성)

```bash
gcloud scheduler jobs create http tutor-quiz-daily \
  --location=asia-northeast3 \
  --schedule="0 9 * * *" \
  --time-zone="Asia/Seoul" \
  --http-method=POST \
  --uri="https://<RAILWAY_URL>/api/generate-scheduled-quizzes?secret=<CRON_SECRET>" \
  --attempt-deadline=300s
```
