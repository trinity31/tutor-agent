# TutorAgent PRD (Product Requirements Document)

> 작성일: 2026-03-25
> 상태: Phase 1 구현 중

---

## 1. 개요

### 1.1 제품명
**TutorAgent** — LangGraph 멀티에이전트 AI 학습 도우미

### 1.2 한 줄 요약
대학 강의 PDF를 기반으로 학습 세션 관리, 자동 퀴즈 생성, 맞춤 복습까지 에이전트가 자율적으로 수행하는 AI 학습 도우미.

### 1.3 배경
기존 Quiz Bot(Slack 기반 단일 함수 호출 구조)을 LangGraph 멀티에이전트로 전환합니다.
- **기존 문제**: 단순 선형 흐름, 플랫폼 종속(Slack), 확장 어려움
- **목표**: 플랫폼 독립적인 에이전트 코어 + 어댑터 패턴으로 카카오톡 등 확장 가능

### 1.4 타임라인
| 단계 | 기간 | 목표 |
|------|------|------|
| Phase 1 | 3-4일 | LangGraph 뼈대 + 퀴즈 생성 에이전트 |
| Phase 2 | 2-3일 | Supervisor 라우팅 + 자료 매칭 강화 |
| Phase 3 | 2일 | 학습 코치 에이전트 |
| Phase 4 | 3-5일 | 적응형 학습 (오답 분석, 난이도 조절) |
| 셀프 테스트 | 1학기 | 실사용 검증 및 개선 |
| 상품화 | 이후 | 카카오톡 마이그레이션 + B2B |

---

## 2. 핵심 기능

### 2.1 학습 세션 (과외 모드)

학습 세션은 **1:1 과외를 받는 경험**을 제공합니다. 에이전트가 능동적으로 이해도를 확인하고, 모르는 부분은 즉시 보충 설명합니다.

**사용자 플로우:**
```
/start 양택풍수론 4주차
  │
  ├─ TutorAgent: "양택풍수론 4주차 학습을 시작합니다.
  │               자료를 검토했습니다. 학습이 끝나면 알려주세요!"
  │
  │  (사용자가 강의 수강 중... /memo 수시 입력 가능)
  │
  ├─ /memo 금맥 마케팅 활용 사례        ← 수동 메모
  ├─ /ask 옥삼분이 뭐야?               ← 수시 질문도 가능
  │
  ├─ 사용자: "다 들었어"
  │
  │  ── 이해도 확인 시작 (3~5문제) ──
  │
  ├─ TutorAgent: "좋습니다! 이해도를 확인해볼게요.
  │               한옥 건축에서 '옥삼분'이란 무엇을 의미하나요?"
  │
  ├─ 사용자: "건물을 세 부분으로 나누는 거요"
  │
  ├─ TutorAgent: "맞습니다! 상분(지붕), 중분(몸체), 하분(기단)으로 나눕니다.  ✅
  │               그럼 지붕 형식 중 팔작지붕의 특징은요?"
  │
  ├─ 사용자: "잘 모르겠어요"
  │
  ├─ TutorAgent: "팔작지붕은 지붕면이 4면이고 측면에 합각부가 형성됩니다.     ❌ → 보충 설명
  │               우진각지붕과 달리 용마루 양쪽에 삼각형 벽면이 보여요.
  │               📝 취약점으로 기록합니다."
  │
  ├─ (... 이해도 확인 계속 ...)
  │
/done
  │
  ├─ TutorAgent: "세션 요약:
  │    ✅ 이해도 확인 3문제 중 2문제 정답 (67%)
  │    📝 취약점: 지붕 형식 구분
  │    📝 수동 메모: 금맥 마케팅 활용 사례
  │    → 내일 퀴즈에 취약점 + 메모 반영합니다!"
  │
  → 다음날 아침 9시: 취약점 + 메모 반영된 퀴즈 출제
```

**요구사항:**

| 단계 | 동작 | 에이전트 |
|------|------|---------|
| `/start` | 세션 시작, 자료 사전 검색 | material_searcher |
| 학습 중 | `/memo`, `/ask` 자유 입력 | learning_coach |
| "다 들었어" | 이해도 확인 질문 3~5개 시작 | **tutor_session** (신규) |
| 이해도 확인 | 정답 → 다음 질문, 오답 → 보충 설명 + 취약점 기록 | tutor_session |
| `/done` | 세션 요약 + 학습완료 기록 | tutor_session |

**이해도 확인 규칙:**
- 자료에서 핵심 개념 3~5개를 선별하여 **개방형 질문** (선택지 없음)
- 사용자 답변을 LLM이 평가 (정답/부분 정답/오답)
- 정답 → 칭찬 + 보충 포인트
- 부분 정답 → 부족한 부분 보충 설명
- 오답 → 정확한 설명 + **자동으로 취약점 메모에 기록**
- 세션 종료 시 이해도 점수 + 취약점 목록 제공

**세션 데이터:**
```json
// GCS: sessions/{session_id}.json
{
  "session_id": "s-abc12345",
  "subject": "양택풍수론 4주차",
  "started_at": "2026-03-25T14:00:00+09:00",
  "ended_at": "2026-03-25T15:30:00+09:00",
  "comprehension_check": {
    "questions": [
      {"question": "옥삼분이란?", "user_answer": "건물을 세 부분으로 나누는 것", "correct": true},
      {"question": "팔작지붕의 특징은?", "user_answer": "잘 모르겠어요", "correct": false}
    ],
    "score": 2,
    "total": 3,
    "weak_topics": ["지붕 형식 구분"]
  },
  "status": "completed"
}
```

### 2.2 학습 메모

메모는 **사용자 수동 입력**과 **에이전트 자동 기록** 두 가지 경로로 수집됩니다.

| 유형 | 경로 | 예시 |
|------|------|------|
| 수동 메모 | `/memo` 명령 | "금맥 마케팅 활용 사례" |
| 자동 메모 | 이해도 확인 중 오답 | "취약점: 지붕 형식 구분 (팔작지붕 vs 우진각지붕)" |

**요구사항:**
- `/memo` 명령으로 수시 기록 (세션 중 무제한)
- 이해도 확인 시 오답/부분 정답은 자동으로 취약점 메모에 추가
- 메모는 과목/주차별로 GCS에 누적 저장
- 퀴즈 생성 시 해당 과목 메모를 자동 조회하여 반영
- 메모 내용에서 최소 3문제 출제 보장 (`from_review: true`)

**데이터 구조:**
```json
// GCS: memos/{subject_key}.json
{
  "subject": "양택풍수론 4주차",
  "memos": [
    {"content": "금맥 마케팅 활용 사례", "source": "user", "created_at": "2026-03-25T14:10:00+09:00"},
    {"content": "취약점: 지붕 형식 구분 (팔작지붕 vs 우진각지붕)", "source": "auto", "created_at": "2026-03-25T15:20:00+09:00"}
  ]
}
```

### 2.3 자료 기반 퀴즈 생성

**퀴즈 유형 (총 10문제):**

| 유형 | 문제 수 | JSON `type` | UI |
|------|---------|-------------|-----|
| 4지선다 | 4문제 | `multiple_choice` | 버튼 A/B/C/D |
| O/X 진위형 | 2문제 | `true_false` | 버튼 O/X |
| 빈칸 채우기 | 2문제 | `fill_blank` | 보기 4개 버튼 |
| 연결하기 | 2문제 | `matching` | 조합 보기 4개 버튼 |

**퀴즈 JSON 구조:**
```json
{
  "quiz_id": "q-abc12345",
  "user_message": "양택풍수론 4주차",
  "questions": [
    {
      "number": 1,
      "type": "multiple_choice",
      "question": "한옥 지붕 중 팔작지붕의 특징은?",
      "options": ["A. 지붕면 2면", "B. 지붕면 4면+합각", "C. 모임형", "D. 평지붕"],
      "correct": "B",
      "explanation": "팔작지붕은 4면 구성에 합각부가 형성된다.",
      "from_review": true
    },
    {
      "number": 2,
      "type": "true_false",
      "question": "기단의 삼분할은 천(天), 인(人), 지(地)로 구분한다.",
      "options": ["O", "X"],
      "correct": "O",
      "explanation": "상분(천), 중분(인), 하분(지)으로 구분한다.",
      "from_review": true
    },
    {
      "number": 3,
      "type": "fill_blank",
      "question": "풍수에서 건물을 지면으로부터 띄워 습기를 막는 요소는 ___이다.",
      "options": ["A. 기단", "B. 처마", "C. 용마루", "D. 주초"],
      "correct": "A",
      "explanation": "기단은 지면으로부터 건물을 이격시키는 역할을 한다.",
      "from_review": false
    }
  ],
  "current_question": 0,
  "answers": {},
  "score": 0,
  "status": "in_progress",
  "created_at": "2026-03-25T09:00:00+09:00"
}
```

**출제 규칙:**
- 자료 전반에서 골고루 출제 (앞/중간/뒷부분 균형)
- 한 주제에 문제 편중 금지
- 오답 선택지는 같은 범주에서 그럴듯하게 작성
- "없음", "해당 없음" 선택지 금지
- 정답이 A/B/C/D에 고르게 분포

**품질 검증:**
1. 문제 수 10개 확인
2. 문제 텍스트 중복 검사
3. 메모 반영 최소 3문제 확인 (`from_review: true`)
4. 실패 시 최대 3회 재생성 (3회차는 메모 제외 폴백)

### 2.4 학습 코치 (Q&A)

**요구사항:**
- `/ask` 명령으로 강의 자료 기반 질문 답변
- 세션 중이면 해당 과목 맥락 자동 적용
- 스레드 내 후속 질문 시 대화 맥락 유지
- 자료에 없는 내용은 "자료에서 확인할 수 없습니다" 응답
- 답변 순서: 핵심 개념 → 예시 → 요약

### 2.5 적응형 복습 관리 (Phase 4)

**요구사항:**
- 오답 패턴 분석 → 취약 영역 파악
- 학습자 프로필에 정답률, 취약 주제 누적
- 퀴즈 생성 시 취약 영역 비중 증가
- 복습 스케줄 자동 생성

**학습자 프로필:**
```json
// GCS: learner_profiles/{user_id}.json
{
  "user_id": "U0ACL0N2M6E",
  "subjects": {
    "양택풍수론": {
      "total_quizzes": 5,
      "avg_score": 7.2,
      "weak_topics": ["기단 구조", "지붕 형식"],
      "strong_topics": ["풍수 기본 원리"]
    }
  },
  "updated_at": "2026-03-25T10:00:00+09:00"
}
```

---

## 3. 아키텍처

### 3.1 시스템 구성

```
┌─────────────────────────────────────────────┐
│                플랫폼 어댑터                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Slack    │  │ 카카오톡  │  │ LangSmith │  │
│  │ Adapter  │  │ Adapter  │  │ (테스트)   │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
│       │              │              │        │
│       └──────────────┼──────────────┘        │
│                      │                       │
│              graph.ainvoke(state)             │
│                      │                       │
│  ┌───────────────────┼───────────────────┐   │
│  │          LangGraph Agent Core         │   │
│  │                                       │   │
│  │  ┌─────────────────────────────┐      │   │
│  │  │      Supervisor Agent       │      │   │
│  │  │   (자연어 분석 + 라우팅)      │      │   │
│  │  └──────────┬──────────────────┘      │   │
│  │             │ transfer_to_agent()     │   │
│  │    ┌────────┼────────┬─────────┬────────┐  │
│  │    ▼        ▼        ▼         ▼        ▼  │
│  │ Material  Quiz    Learning  Tutor    Analytics│
│  │ Searcher  Gen     Coach    Session  (Phase4) │
│  │    │        │        │                │   │
│  │    ▼        ▼        ▼                │   │
│  │  [도구]   [도구]   [도구]              │   │
│  │                                       │   │
│  └───────────────────────────────────────┘   │
│                      │                       │
│              ┌───────┼───────┐               │
│              ▼       ▼       ▼               │
│           Gemini   GCS    File Search        │
│           API     Storage   Store            │
└─────────────────────────────────────────────┘
```

### 3.2 기술 스택

| 구성요소 | 기술 | 버전 |
|---------|------|------|
| 에이전트 프레임워크 | LangGraph | >= 0.4 |
| LLM | Google Gemini 2.5 Flash | via langchain-google-genai |
| 에이전트 생성 | `langchain.agents.create_agent()` | langchain >= 1.2 |
| 자료 검색 | Gemini File Search Store | Google GenAI API |
| 데이터 저장 | Google Cloud Storage | JSON 파일 |
| 배포 | Google Cloud Run | min-instances=1 |
| 현재 UI | Slack Bolt (async) | Python |
| 향후 UI | 카카오톡 채널 봇 | 추후 |
| 모니터링 | LangSmith | 개발/테스트 |

### 3.3 디렉토리 구조

```
tutor-agent/
├── .env                           # API 키 (GOOGLE_API_KEY)
├── pyproject.toml                 # 의존성 관리 (uv)
├── main.py                        # 진입점
├── file_manifest.json             # File Search Store 파일 목록 캐시
│
├── tutor_agent/
│   ├── __init__.py
│   ├── config.py                  # 환경변수, KST, 싱글턴
│   ├── storage.py                 # GCS CRUD (completions, quizzes, memos, profiles)
│   │
│   ├── agents/
│   │   ├── __init__.py            # 모델 상수 (SUPERVISOR_MODEL, SPECIALIST_MODEL)
│   │   ├── state.py               # TutorAgentState(MessagesState)
│   │   ├── graph.py               # StateGraph 빌드 + 컴파일
│   │   ├── prompts.py             # 공통 프롬프트 (TRANSFER_SUFFIX)
│   │   ├── supervisor_agent.py    # Supervisor (자연어 라우팅)
│   │   ├── material_searcher.py   # 자료 검색 + 검증
│   │   ├── quiz_generator.py      # 퀴즈 생성 + 품질 검증
│   │   ├── learning_coach.py      # 질문 답변
│   │   ├── tutor_session.py       # 과외 세션 (이해도 확인 + 보충 설명)
│   │   ├── analytics.py           # 오답 분석 (Phase 4)
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── shared_tools.py    # transfer_to_agent (Command 패턴)
│   │       └── tutor_tools.py     # search_material, get_study_memos, save_memo
│   │
│   └── platforms/
│       ├── __init__.py
│       ├── slack_app.py           # Slack 어댑터 (graph.ainvoke 호출)
│       └── kakao_app.py           # 카카오 어댑터 (추후)
│
├── notebooks/
│   └── step2_basic_graph.ipynb    # 개발/테스트용 노트북
│
└── tests/                         # 테스트 (추후)
```

### 3.4 State 스키마

```python
from langgraph.graph import MessagesState

class TutorAgentState(MessagesState):
    """TutorAgent 그래프의 공유 상태."""

    # --- 에이전트 관리 ---
    current_agent: str = ""             # 현재 활성 에이전트 이름

    # --- 명령 정보 ---
    command_type: str = ""              # "start" | "done" | "quiz" | "ask" | "memo"
    user_message: str = ""              # 원본 사용자 입력 (예: "풍수학개론 3주차")

    # --- 학습 세션 ---
    session_active: bool = False        # 세션 활성 여부
    session_subject: str = ""           # 세션 과목/주차 (예: "양택풍수론 4주차")
    session_phase: str = ""             # "learning" | "comprehension_check" | "summary"
    memos: list[str] = []               # 현재 세션 누적 메모 (수동 + 자동)

    # --- 이해도 확인 ---
    comprehension_questions: list[dict] = []   # 이해도 확인 문제 목록
    comprehension_results: list[dict] = []     # 질문별 결과 (question, answer, correct)
    weak_topics: list[str] = []                # 세션에서 파악된 취약 주제

    # --- 자료 검색 ---
    material: str = ""                  # File Search 검색 결과 텍스트
    material_valid: bool = False        # 자료 검증 통과 여부

    # --- 퀴즈 ---
    quiz: dict = {}                     # 생성된 퀴즈 데이터
    quiz_valid: bool = False            # 품질 검증 통과 여부
    generation_attempts: int = 0        # 생성 시도 횟수 (최대 3)

    # --- Q&A ---
    answer: str = ""                    # 학습 코치 답변

    # --- 에러 ---
    error: str = ""                     # 에러 메시지 (플랫폼 어댑터에서 사용)
```

### 3.5 그래프 흐름

```
[Slash Command]                           [자연어 메시지]
/quiz 풍수학개론 3주차                      "퀴즈 내줘"
        │                                       │
  command_type="quiz"                    Supervisor가 분석
  user_message="풍수학개론 3주차"                 │
        │                                       │
        └───────────── graph.ainvoke(state) ─────┘
                              │
                     ┌────────┼────────┬──────────┐
                     ▼        ▼        ▼          ▼
              material_    quiz_    learning_   tutor_
              searcher    generator   coach    session
                 │           │          │         │
           search_material   │    search_material │
                 │           │          │         │
           검증 (≥1500자)    │     자료 답변   이해도 확인
                 │           │          │      3~5문제
              transfer →  생성+검증     │         │
                         (최대 3회)   END    정답→칭찬
                             │            오답→보충설명
                            END           취약점 기록
                                             │
                                          세션 요약
                                             │
                                            END
```

### 3.6 에이전트 전환 패턴 (catbot-backend 참조)

```python
# shared_tools.py
from langchain_core.tools import tool
from langgraph.types import Command

@tool
def transfer_to_agent(agent_name: str):
    """다른 전문 에이전트로 전환합니다.

    Args:
        agent_name: 전환할 에이전트 이름
            - "material_searcher": 자료 검색
            - "quiz_generator": 퀴즈 생성
            - "learning_coach": 학습 코치
    """
    return Command(
        goto=agent_name,
        graph=Command.PARENT,
        update={"current_agent": agent_name},
    )
```

---

## 4. 자료 검색 시스템

### 4.1 Gemini File Search Store

**구조:**
- 강의 PDF를 Gemini File Search Store에 업로드 (영구 보존)
- 각 파일은 `{과목명} - {파일명}` 형식의 display_name을 가짐
  - 예: `양택풍수론 - 제04주차_전통건축의 이해 한옥과 문화재 풍수`
- `file_manifest.json`에 display_name 목록 캐싱 (Files API 48시간 TTL 대응)

### 4.2 파일 매칭 로직

사용자 입력 → 정확한 파일 display_name 매칭:

```
입력: "양택풍수론 4주차"
  ↓ 파싱: 과목="양택풍수론", 주차="04"
  ↓ file_manifest.json에서 검색
  ↓ 매칭: "양택풍수론 - 제04주차_전통건축의 이해 한옥과 문화재 풍수"
  ↓ File Search 쿼리에 파일명 힌트 포함
결과: 정확한 4주차 자료만 검색됨
```

### 4.3 search_material 도구

```python
@tool
def search_material(subject: str) -> str:
    """강의 자료를 검색합니다.

    Args:
        subject: 과목명과 주차 (예: "양택풍수론 4주차")

    Returns:
        검색된 자료 내용 (핵심 개념, 주요 용어, 중요 내용)
    """
```

**검색 전략:**
1. `file_manifest.json`에서 파일명 매칭
2. 매칭된 파일명을 쿼리 힌트로 포함
3. File Search Store에서 의미론적 검색
4. 결과 부족 시 (< 1500자) 쿼리 변형 후 재시도

---

## 5. 데이터 모델

### 5.1 GCS 저장소 구조

```
gs://quiz-bot-data-494801/
├── completions.json               # 학습완료 기록
├── thread_states.json             # 스레드 대화 상태
├── quizzes/
│   └── {quiz_id}.json             # 퀴즈 진행 상태
├── memos/
│   └── {subject_key}.json         # 과목별 메모
└── learner_profiles/
    └── {user_id}.json             # 학습자 프로필 (Phase 4)
```

### 5.2 학습완료 기록 (completions.json)

```json
{
  "records": [
    {
      "id": "a1b2c3d4",
      "user_message": "양택풍수론 4주차",
      "completed_at": "2026-03-25T14:00:00+09:00",
      "quiz_generated": false,
      "quiz_id": null,
      "review_notes": "팔작지붕과 우진각 차이, 기단 삼분할",
      "type": "normal"
    },
    {
      "user_message": "양택풍수론 4주차 (오답 복습)",
      "completed_at": "2026-03-26T10:00:00+09:00",
      "quiz_generated": false,
      "quiz_id": null,
      "type": "retry",
      "source_quiz_id": "q-abc12345",
      "wrong_questions": [...]
    }
  ]
}
```

### 5.3 퀴즈 결과 처리

퀴즈 완료 시 사용자에게 제공하는 옵션:

| 옵션 | 동작 |
|------|------|
| 내일 오답만 재출제 | `type: "retry"`, 오답 문제만 저장, 다음날 자동 출제 |
| 날짜 지정 오답 재출제 | `type: "scheduled"`, `scheduled_date` 설정 |
| 날짜 지정 전체 재출제 | `type: "scheduled"`, 전체 자료로 새 퀴즈 생성 |

---

## 6. 플랫폼 어댑터

### 6.1 어댑터 인터페이스

모든 플랫폼 어댑터는 동일한 패턴으로 에이전트를 호출합니다:

```python
# 플랫폼 어댑터의 역할:
# 1. 사용자 입력 파싱 → TutorAgentState 구성
# 2. graph.ainvoke(state) 호출
# 3. 결과를 플랫폼 UI로 포맷팅/전송

async def handle_command(command_type, text, user_id):
    state = {
        "messages": [("user", text)],
        "command_type": command_type,
        "user_message": text,
    }
    result = await graph.ainvoke(state)
    # 플랫폼별 UI 렌더링
    return format_response(result)
```

### 6.2 Slack 어댑터 (현재)

| Slack Command | → command_type | → 에이전트 |
|---------------|---------------|-----------|
| `/start 양택풍수론 4주차` | `start` | 세션 시작 (저장만) |
| `/memo 팔작지붕 중요` | `memo` | 메모 저장 |
| `/done` | `done` | 세션 종료 + 학습완료 기록 |
| `/quiz 양택풍수론 4주차` | `quiz` | material_searcher → quiz_generator |
| `/ask 음양오행이란?` | `ask` | material_searcher → learning_coach |

**퀴즈 UI**: Slack Block Kit (Header + Section + Buttons)
**답변 처리**: `block_actions` 이벤트 핸들러

### 6.3 카카오톡 어댑터 (추후)

카카오 챗봇 API 연동. 핵심 로직(graph.ainvoke)은 동일하고 UI 렌더링만 카카오 형식으로 변환.

---

## 7. 자동 퀴즈 스케줄링

### 7.1 매일 아침 자동 출제

- **트리거**: Cloud Scheduler → `/generate-quiz` 엔드포인트 (매일 09:00 KST)
- **대상**: `completions.json`에서 `quiz_generated: false`인 기록
  - `type: "normal"` → 전날 기록만 처리
  - `type: "scheduled"` → `scheduled_date`가 오늘인 기록
  - `type: "retry"` → 전날 기록, `wrong_questions`를 그대로 재전송

### 7.2 퀴즈 완료 후 재출제 흐름

```
퀴즈 완료 (7/10)
    │
    ├─ [내일 오답만] → retry 레코드 저장 → 다음날 자동 출제
    ├─ [날짜 지정 오답] → scheduled 레코드 (wrong_questions 포함)
    └─ [날짜 지정 전체] → scheduled 레코드 (새 퀴즈 생성)
```

---

## 8. 환경 설정

### 8.1 필수 환경변수

| 변수 | 용도 | 예시 |
|------|------|------|
| `GOOGLE_API_KEY` | Gemini API 인증 | `AIzaSy...` |
| `SLACK_BOT_TOKEN` | Slack Bot 토큰 | `xoxb-...` |
| `SLACK_SIGNING_SECRET` | Slack 요청 검증 | `2b97...` |
| `SLACK_CHANNEL_ID` | 퀴즈 전송 채널 | `C0AM...` |
| `GCS_BUCKET_NAME` | GCS 버킷 이름 | `quiz-bot-data-494801` |
| `FILE_SEARCH_STORE_NAME` | File Search Store 경로 | `fileSearchStores/quizbotknowledge-...` |

### 8.2 모델 설정

```python
# agents/__init__.py
SUPERVISOR_MODEL = "google_genai:gemini-2.5-flash"    # 라우팅용
SPECIALIST_MODEL = "google_genai:gemini-2.5-flash"    # 분석/생성용
```

### 8.3 배포

```yaml
# Cloud Run
서비스: quiz-bot
리전: asia-northeast3
min-instances: 1          # Cold Start 방지
메모리: 512MB
CPU: 1 vCPU
```

---

## 9. 레퍼런스 구현: catbot-backend

TutorAgent는 catbot-backend의 아키텍처 패턴을 따릅니다:

| 패턴 | catbot-backend | TutorAgent |
|------|---------------|------------|
| 에이전트 생성 | `create_agent(model, tools, system_prompt)` | 동일 |
| 에이전트 전환 | `transfer_to_agent()` → `Command(goto=...)` | 동일 |
| 병렬 실행 | `dispatch_agents()` → `Send()` 리스트 | Phase 4에서 검토 |
| 상태 관리 | `MessagesState` 상속 | 동일 |
| Supervisor | 도구 호출만, 직접 답변 금지 | 동일 |

**참조 파일:**
- `catbot-backend/agents/graph.py` — StateGraph 빌드, 조건부 엣지
- `catbot-backend/agents/state.py` — MessagesState 상속
- `catbot-backend/agents/tools/shared_tools.py` — Command 패턴
- `catbot-backend/agents/supervisor_agent.py` — Supervisor 프롬프트

---

## 10. 비기능 요구사항

### 10.1 성능
- 퀴즈 생성: 30초 이내
- 질문 답변: 15초 이내
- Slack `ack()` 응답: 3초 이내 (Cold Start 방지 필수)

### 10.2 비용
- Gemini 2.5 Flash: ~$0.003/퀴즈
- Cloud Run (min-instances=1): ~$3-5/월
- GCS: ~$0 (소량 JSON)
- **총 운영비: 약 $3-6/월 (1인 사용 기준)**

### 10.3 확장성
- 에이전트 코어는 플랫폼 독립 → 카카오톡, 웹 등 추가 가능
- 멀티테넌트: user_id 기반 데이터 분리로 확장 가능
- File Search Store: 과목 추가 시 PDF 업로드 + manifest 갱신만 필요

### 10.4 안전 전략
- `config.USE_LANGGRAPH` 플래그로 기존 로직 폴백 가능
- 기존 `quiz_manager.py` 병행 유지 (Phase 2 완료 전까지)
- GCS 데이터 형식 하위 호환 유지
