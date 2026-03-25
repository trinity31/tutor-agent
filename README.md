# TutorAgent

LangGraph 멀티에이전트 기반 AI 학습 도우미. 대학 강의 PDF를 기반으로 학습 세션 관리, 자동 퀴즈 생성, 맞춤 복습까지 에이전트가 자율적으로 수행합니다.

## 주요 기능

- **학습 세션 (과외 모드)** — 1:1 과외 경험 제공. 이해도 확인 질문 + 오답 보충 설명 + 취약점 자동 기록
- **자료 기반 퀴즈 생성** — 4지선다, O/X, 빈칸 채우기, 연결하기 총 10문제 자동 생성 + 품질 검증
- **학습 메모** — 수동 메모(`/memo`) + 이해도 확인 시 자동 취약점 기록. 퀴즈에 자동 반영
- **학습 코치 (Q&A)** — 강의 자료 기반 질문 답변 (`/ask`)
- **적응형 복습** — 오답 패턴 분석, 취약 영역 비중 증가, 복습 스케줄 자동 생성 (Phase 4)

## 아키텍처

```
Slack / 카카오톡 / LangSmith (테스트)
              │
      graph.ainvoke(state)
              │
     ┌────────┴────────┐
     │  Supervisor Agent │  ← 자연어 분석 + 라우팅
     └────────┬────────┘
              │ transfer_to_agent()
    ┌─────────┼─────────┬──────────┐
    ▼         ▼         ▼          ▼
Material   Quiz      Learning   Tutor
Searcher   Generator  Coach     Session
```

## 기술 스택

| 구성요소 | 기술 |
|---------|------|
| 에이전트 프레임워크 | LangGraph >= 0.4 |
| LLM | Google Gemini 2.5 Flash 이상 |
| 자료 검색 | Gemini File Search API |
| 데이터 저장 | Google Cloud Storage (JSON) |
| 배포 | Google Cloud Run |
| UI | Slack Bolt (현재) / 카카오톡 (추후) |

## 설치

```bash
# Python 3.13 필요
uv sync
```

## 환경 변수

`.env` 파일에 다음 값을 설정합니다:

```
GOOGLE_API_KEY=           # Gemini API 키
SLACK_BOT_TOKEN=          # Slack Bot 토큰
SLACK_SIGNING_SECRET=     # Slack 요청 검증
SLACK_CHANNEL_ID=         # 퀴즈 전송 채널
GCS_BUCKET_NAME=          # GCS 버킷 이름
FILE_SEARCH_STORE_NAME=   # File Search Store 경로
```

## 실행

```bash
uv run python main.py
```

## 프로젝트 구조

```
tutor_agent/
├── agents/
│   ├── graph.py               # StateGraph 빌드 + 컴파일
│   ├── state.py               # TutorAgentState
│   ├── prompts.py             # 공통 프롬프트
│   ├── supervisor_agent.py    # Supervisor (자연어 라우팅)
│   ├── material_searcher.py   # 자료 검색 + 검증
│   ├── quiz_generator.py      # 퀴즈 생성 + 품질 검증
│   ├── learning_coach.py      # 질문 답변
│   └── tools/
│       ├── shared_tools.py    # transfer_to_agent (Command 패턴)
│       └── tutor_tools.py     # search_material, get_study_memos, save_memo
└── platforms/
    └── slack_app.py           # Slack 어댑터
```

## 사용법

| 명령어 | 설명 |
|-------|------|
| `/start 양택풍수론 4주차` | 학습 세션 시작 |
| `/memo 팔작지붕 중요` | 학습 메모 기록 |
| `/ask 옥삼분이 뭐야?` | 자료 기반 질문 |
| `/done` | 세션 종료 + 학습완료 기록 |
| `/quiz 양택풍수론 4주차` | 퀴즈 생성 |

## 개발 현황

| 단계 | 상태 | 목표 |
|------|------|------|
| Phase 1 | 🔨 구현 중 | LangGraph 뼈대 + 퀴즈 생성 에이전트 |
| Phase 2 | 대기 | Supervisor 라우팅 + 자료 매칭 강화 |
| Phase 3 | 대기 | 학습 코치 에이전트 |
| Phase 4 | 대기 | 적응형 학습 (오답 분석, 난이도 조절) |
