# TutorAgent 상품 개발 단계별 지침서 (Handoff)

> 새 세션의 AI 어시스턴트(Opus 4.8)에게 전달하는 문서. 이 문서만으로 프로젝트 맥락을 파악하고
> Phase 1부터 이어서 개발할 수 있도록 작성됨. 작성일: 2026-07-06.

---

## 0. 이 문서 사용법

- 상품화 종합 검토(경쟁·원가·가격·Go/No-Go)의 원본은 `~/.claude/plans/snug-watching-quasar.md`에 있다. 없으면 이 문서 §2·§7이 요약본이다.
- 작업 규칙은 §5(컨벤션)를 반드시 따를 것. 특히 **함정 목록(§6)은 실제 발생했던 문제들**이므로 관련 코드를 만지기 전에 읽을 것.
- 현재 단계: **Phase 0(지인 베타 준비) 완료** → 다음 작업은 §8 Phase 1.

## 1. 제품 개요

**TutorAgent** — PDF 강의자료 기반 AI 학습 도우미 (LangGraph 멀티에이전트 + FastAPI + React/Vite, Railway 배포).

- **타겟**: 성인 학습자 B2C (방송대·사이버대·자격증 — 자기 교재로 공부하는 사람)
- **포지셔닝**: "교재를 귀로 정독하고, 잊기 전에 다시 물어봐 주는 학습 루프". 채팅·퀴즈는 무료 NotebookLM과 차별화 불가 — **원문 낭독 + 복습 루프가 유일한 웨지**이며, 이 둘의 품질·리텐션이 제품의 생명선이다.
- **가격 방향(미확정)**: 무료(체험) / ₩9,900(낭독 20만 자·자료 20개) / ₩19,900(낭독 100만 자). 원가 드라이버는 TTS(청취량 비례, 활성 1인 월 ₩2~3천).

### 기능 인벤토리 (모두 동작)
1:1 과외 채팅 · 자동 퀴즈(객관식7+OX3) · Q&A · 자료 검색(Gemini File Search) · 학습 인덱스 자동 생성 · **원문 낭독**(문장 하이라이트·PDF 페이지 동기화·배속·이어듣기·섹션 자동 연속 재생·모바일 지원) · 복습 스케줄링(다음날 Slack 퀴즈) · 오답 재시험 · 학습 노트

## 2. 현재 상태 (2026-07-06)

- 배포: https://tutor-agent-production-5cf2.up.railway.app/ (Railway, Volume `/app/data`)
- **Phase 0(지인 베타 준비) 구현 완료** — 상세는 바로 아래 표. Phase 1은 미착수(계획 문서만 존재).
- **미푸시 상태일 수 있음** — `git log origin/main..main`으로 확인. push는 사용자가 직접 하거나 암호 확인 후에만 (§5).

### Phase 0 완료 기록 (2026-07-05 구현, 전 항목 실측 검증)

목표: 외부 사용자(지인 10명)를 받기 전 최소 안전장치. 원 계획은 상품화 검토 문서 §4
(세션 계획 파일 — 저장소 밖)였으며, 아래가 실행 결과의 정본이다.

| 작업 | 커밋 | 내용 | 검증 방법 |
|---|---|---|---|
| 소유권 검증 | `412920b` | DELETE /api/notes에 본인 확인 추가 (유일했던 격리 구멍). 나머지 변경성 엔드포인트는 전수 감사로 이상 없음 확인 | 타인 note_id 삭제 404, 본인 200 (curl 실측) |
| 시크릿 fail-fast | `412920b` | Railway 환경에서 JWT_SECRET_KEY·CRON_SECRET 미설정 시 기동 거부 (api.py lifespan) | 미설정 기동 거부·설정 시 기동 실측 |
| CORS 환경변수화 | `412920b` | `ALLOWED_ORIGINS`(콤마 구분), 기본 localhost | — |
| SQLite WAL | `412920b` | `_get_db()`에 WAL + busy_timeout 5s | — |
| 초대 코드 | `334ab86` | `INVITE_CODE` 설정 시 가입에 요구 (403). 가입 폼에 입력 필드 | 무코드·오코드 403, 정상 201 (curl) |
| 인덱싱 상태 영속화 | `519eb34` | 인메모리 dict → `indexing_status` 테이블. 30분 방치된 'indexing'은 'error' 간주 | 재시작·만료 시나리오 실측 |
| 대화 영속화 | `ccb6f0f` | MemorySaver → SqliteSaver(`data/checkpoints.db`, WAL) — 재배포에도 스레드 유지 | 프로세스 재시작 후 히스토리 복원 확인 |
| 사용량 하드캡 | `2f9d6dd` | `usage.py` + `usage_counters` 테이블. 일 채팅 100 / 월 TTS 30만 자 / 월 업로드 20 (env 조정). 초과 시 429 + 한국어 안내. 캐시 재생은 무관, TTS는 생성 시 실제 문자 수 기록 | 한도 1로 낮춰 2회차 429 실측 |
| Sentry (선택) | `3ccf6d3` | `SENTRY_DSN` 설정 시에만 활성화 | — |

**Phase 0의 비코드 잔여 작업** (베타 시작 전 사용자·어시스턴트가 확인):
- [ ] 위 커밋 push + Railway 재배포
- [ ] Railway 변수: `INVITE_CODE` 설정 (필요 시 `SENTRY_DSN`, `LIMIT_*` 조정)
- [ ] 지인 베타 시작 → 4주간 §7 Go/No-Go 지표 관찰 (정밀 계측은 Phase 1 T9 — 그 전엔 usage_counters로 근사)
- README.md에 세션 이전부터 미커밋 수정이 있음(기능 소개 개편 + 새 환경변수 문서) — 커밋 여부는 사용자 결정 대기 중.
- 로컬 테스트 계정: `audio-test@local` / `test-pw-1234` (클래스 `testcls`, 자료 "명리학개론"·"명리학개론2") — 로컬 DB 전용, 프로덕션에는 없음.

## 3. 아키텍처 지도

```
tutor_agent/
├── auth.py          # SQLite(users.db) 전체 스키마 + CRUD. 테이블: users, classes,
│                    #  quiz_results, completions, study_notes, audio_assets,
│                    #  usage_counters, indexing_status. WAL 활성화됨.
├── service.py       # 서비스 레이어(유일한 그래프 진입점). stream_chat, 자료 업로드/인덱스,
│                    #  원문 낭독 파이프라인(생성·캐싱·매니페스트), 예약 퀴즈 크론.
│                    #  체크포인터: SqliteSaver(data/checkpoints.db)
├── narration.py     # 낭독 텍스트 정제 (순수 함수, pytest 대상). 슬라이드 PDF 보정 규칙 다수
├── tts.py           # TTSEngine 프로토콜. GoogleCloudTTSEngine(기본)·GeminiTTSEngine.
│                    #  TTS_ENGINE 환경변수로 선택
├── usage.py         # 사용자별 사용량 카운터·한도 (일 채팅/월 TTS 문자/월 업로드)
├── file_search.py   # Gemini File Search Store 관리 (업로드·검색·manifest·인덱스 생성)
├── agents/          # LangGraph: supervisor → tutor/quiz/qna/search
└── platforms/
    ├── api.py       # FastAPI 전체 엔드포인트 + 정적 서빙(web/dist). JWT 인증
    └── slack.py     # 단일 사용자 하드코딩 (SLACK_DEFAULT_USER_EMAIL) — Phase 1에서 교체 대상

web/src/
├── api/client.ts    # fetch 래퍼 + 오디오/PDF API
├── stores/          # zustand: auth, class, chat, audio
└── components/
    ├── audio/       # AudioReader(플레이어+하이라이트), PdfPageView(react-pdf, 지연 로딩)
    ├── material/MaterialIndexPanel.tsx   # 인덱스/낭독 패널 (🎧 듣기 토글)
    └── chat/ChatArea.tsx                 # 패널 배치: 데스크톱 사이드(드래그 폭)·모바일 오버레이

data/ (Railway Volume /app/data — git 미포함)
├── users.db         # 메인 SQLite
├── checkpoints.db   # LangGraph 대화 체크포인트
├── materials/{user}/{class}/  # PDF 원본 + manifest.json + 인덱스 .md
└── audio/{user}/{자료명}/{섹션}_{음성}.mp3 + .manifest.json
```

**낭독 파이프라인**: PDF → 폰트 크기 필터 추출(본문 95% 미만 = 각주·푸터 제외, service.py `_extract_body_pages`) → narration.py 정제(한자·가짜 마침표·제목 번호 복원 등) → 청크(2~4문장, 제목은 청크 시작) → 청크별 TTS(동시 3) → PCM 병합 → MP3(ffmpeg)/WAV → 매니페스트(청크별 start/end/페이지 — 하이라이트·페이지 동기화의 근거. Gemini/GCP TTS 모두 타임스탬프를 안 주므로 이 방식이 필수).

### 환경변수 (전체)
`GOOGLE_API_KEY`(Gemini 전반) · `GCP_TTS_API_KEY`(Cloud TTS 전용, 없으면 GOOGLE_API_KEY) · `TTS_ENGINE`(gcp|gemini) · `JWT_SECRET_KEY`·`CRON_SECRET`(**프로덕션 필수 — 없으면 기동 거부**) · `INVITE_CODE`(가입 제한) · `ALLOWED_ORIGINS` · `SENTRY_DSN` · `LIMIT_CHAT_DAILY`(100)·`LIMIT_TTS_CHARS_MONTHLY`(30만)·`LIMIT_UPLOADS_MONTHLY`(20) · Slack 3종(선택)

## 4. 실행·검증 방법

```bash
uv run python run_api.py        # 백엔드 :8000 (reload)
cd web && npm run dev           # 프론트 :5173 (proxy → 8000)
uv run pytest -q                # 테스트 39개 (narration 정제 규칙)
cd web && npm run build         # tsc + vite (커밋 전 필수)
```
- 브라우저 검증용 `.claude/launch.json`에 `tutor-api`(:8899) 구성이 있음 (dist 정적 서빙 — 프론트 변경 시 build 필요).
- GCP 프로젝트: **Saju Thread Bot** (사주 봇과 공용, Tier 1). File Search Store·Gemini 키가 이 프로젝트에 묶여 있어 **GOOGLE_API_KEY를 다른 프로젝트 키로 바꾸면 기존 자료 전부 재인덱싱 필요**.

## 5. 작업 컨벤션 (사용자 확립 규칙)

1. 한국어로 대화·커밋 메시지. 커밋은 기능 단위로 분리, 제목은 "무엇 — 왜" 형식 (git log 참고)
2. **git push 금지** — 사용자가 요청하고 암호(별도 확인)를 제시할 때만 직접 push
3. 지시한 업무만 수행. 관련 없는 코드 수정 금지. DRY
4. 리소스(파일·DB 레코드·외부 스토어) 삭제 전 목록을 보여주고 확인 받기. Gemini Store는 `tutor-` 프리픽스만 삭제 대상
5. 구현 후 실제 검증까지: pytest + 프론트 빌드 + 가능하면 브라우저/curl 실측. 검증 없이 "완료" 보고 금지
6. 퀴즈 선택지는 자료 원문 그대로 (의역·일반 상식 보완 금지) — 프롬프트 규칙에 반영되어 있음

## 6. ⚠️ 이 프로젝트의 함정들 (실제 겪은 문제)

1. **자료명 유니코드 NFC/NFD**: macOS 업로드 파일명은 NFD, 브라우저 경유는 NFC가 섞임. 오디오 캐시 키는 NFC로 통일했고(`service._nfc`), `get_material_path`는 양쪽 폴백. **자료명을 키로 쓰는 새 기능을 만들면 반드시 같은 처리를 할 것.** Linux(Railway) 파일시스템은 바이트 단위 매칭이라 로컬(macOS)에서 재현 안 되는 버그가 남.
2. **Gemini TTS 쿼터**: gemini-2.5-flash-tts는 Tier 1에서도 일 100회뿐. 그래서 기본 엔진을 Cloud TTS(Neural2)로 전환함. Gemini TTS로 되돌릴 일이 있으면 쿼터부터 확인.
3. **genai 클라이언트 + 스레드**: 병렬 TTS 호출 중 공유 genai.Client를 리셋/GC하면 다른 스레드 요청이 "client has been closed"로 죽는다. tts.py는 **호출마다 독립 클라이언트**를 만든다 — 이 패턴을 유지할 것.
4. **슬라이드형 PDF 추출**: pypdf가 따옴표·마침표·번호·한자를 본문과 분리된 위치로 추출한다. narration.py의 규칙들(가짜 마침표=종결 어미 휴리스틱, 제목 번호 복원, 고아 구두점)은 전부 이 문제의 보정이다. 규칙 수정 시 실제 PDF(`data/materials/`)로 전후 비교 + pytest 필수.
5. **SQLite 이스케이프**: 한글·특수문자 코드를 Edit 도구로 다룰 때 유니코드 정규화로 매칭이 깨질 수 있음 — 정규식 리터럴에 한자·특수문자 대신 `\uXXXX` 이스케이프 사용.
6. **BackgroundTasks**: 실패 시 재시도 없음. 오디오 생성은 DB 상태(pending/generating/ready/failed + error 사유)로 추적하고 실패 시 사용자가 재시도. 새 백그라운드 작업도 같은 패턴으로.
7. **Railway 볼륨**: data/ 전체가 볼륨. 로컬과 프로덕션의 DB·오디오·자료는 서로 별개다.
8. **프론트 오디오 요소**: 패널을 데스크톱/모바일 두 벌로 렌더링하면 `<audio>`가 중복 생성됨 — ChatArea는 뷰포트에 따라 한쪽만 렌더링한다.

## 7. 사업 검토 요약 & Go/No-Go

- **베타 핵심 가설**: "원문 낭독+복습 루프는 NotebookLM이 못 채우는 습관을 만든다"
- Go 기준 (지인 베타 10명, 4주): 활성화(업로드→첫 낭독/퀴즈) ≥60% · **주 2회+ 낭독 청취자 ≥40% (최우선)** · W2/W4 재방문 ≥40%/25% · 복습 퀴즈 24h 응답 ≥30% · 인터뷰에서 낭독·복습 자발적 언급
- **No-Go 신호**: 낭독 완청률 <10%, 복습 푸시 옵트아웃 과반, 채팅만 사용. No-Go 시 피벗: B2B(학원·기업교육) 또는 낭독 단독 경량 제품
- NotebookLM이 원문 낭독을 추가하면 웨지가 무너진다 — **속도가 전략**이다.

### 구현 형태 전략 (결정됨 2026-07-06)

이 제품은 실질적으로 "팟캐스트 앱처럼 쓰이는" 제품(통근 청취 + 복습 푸시)이다. 형태는 단계적으로:

1. **지금~베타: 웹앱 + PWA 강화** (Phase 1의 8-5·8-11에서 구현)
   - Media Session API로 잠금화면 재생 컨트롤 — 모바일 브라우저 `<audio>`는 화면을 꺼도 재생이
     유지되므로 이것만으로 이동 중 청취 UX의 80%가 확보된다
   - PWA manifest + 서비스워커. 웹푸시: Android는 브라우저 즉시 가능, iOS는 홈 화면 추가 시(16.4+)
   - 근거: 검증 전 플랫폼 확장 금물. 베타는 "링크 하나로 시작"이 마찰 최소
2. **Go 판정 후: Capacitor 래핑** (2~4주) — 기존 React를 그대로 앱스토어/플레이스토어 배포.
   네이티브 푸시(FCM/APNs)·백그라운드 오디오 플러그인·오프라인 다운로드 확보. 스토어 발견성
   ("PDF 낭독" 검색 유입) 확보. **결제는 웹(토스) 유지** — 앱 내 구독은 스토어 수수료 15~30%를
   떼이므로 앱에서는 결제 페이지로 웹 링크만 연결
3. **비권장: React Native/Flutter 재작성** — 수개월간 웨지 검증이 멈춘다. 유료 사용자 증가로
   WebView UX가 실제 병목이 된 뒤에나 재검토

## 8. Phase 1 — 공개 베타 100명 (4~6주, 95~140h)

> 각 항목은 독립 커밋(들)로. 순서는 의존성 순. 완료 기준을 만족해야 다음으로.
> **파일·스키마·함수 수준의 세부 실행 계획은 `docs/PHASE1_IMPLEMENTATION_PLAN.md`** (T1~T11이
> 아래 8-1~8-11에 대응). 실행 시 그 문서를 기준으로 할 것.

### 8-1. SQLite → PostgreSQL (16~24h) — 최우선, 다른 작업의 토대
- Railway Postgres 추가. `auth.py`의 raw sqlite3를 SQLAlchemy(core 또는 ORM) + alembic 마이그레이션으로 전환. 테이블 7개(§3) 스키마 그대로 이식. **pgvector 확장도 이때 함께 활성화** (8-8-(b)의 토대).
- `usage.py`, `indexing_status`도 함께 이동. `ON CONFLICT` 문법 차이 주의.
- 기존 SQLite 데이터 이관 스크립트 1회성 작성 (users.db → Postgres).
- 완료 기준: 전체 기능 회귀(업로드→채팅→퀴즈→낭독→노트) + 동시 요청 테스트.

### 8-2. 체크포인터 → AsyncPostgresSaver (4h)
- `service.py:45` SqliteSaver → `langgraph-checkpoint-postgres`. 이후 uvicorn 워커 2+ 가능.

### 8-3. 파일 저장 GCS 전환 (8~12h)
- materials/audio를 GCS 버킷으로. 오디오/PDF 서빙은 signed URL로 교체 — `api.py`의 수동 Range 구현과 `?token=` 쿼리 인증(브라우저 히스토리에 토큰 노출되는 알려진 트레이드오프)이 함께 제거된다.
- 프론트 `audioFileUrl`/`pdfFileUrl`은 signed URL을 받아오는 API 호출로 변경.

### 8-4. 이메일 검증 + 비밀번호 재설정 (8~12h)
- Resend(간단) 또는 SES. users에 `email_verified`, 토큰 테이블. 가입 → 인증 메일 → 미인증 시 기능 제한. 초대 코드(`INVITE_CODE`)는 병행 유지.

### 8-5. 알림 채널 재설계 — Slack 제거 (12~20h)
- B2C에서 사용자별 Slack은 비현실적. `notifications.py` 신설: **이메일 + 웹푸시(PWA)** 로 복습 퀴즈 발송. `slack.py`의 SLACK_DEFAULT_USER_EMAIL 의존 제거(개인용 기능으로 격리하거나 삭제 — 사용자와 상의).
- 복습 퀴즈를 웹에서 풀 수 있는 화면 필요 (현재 Slack 버튼 UI뿐임): `quiz_results.status='in_progress'`를 웹 퀴즈 화면에 연결.

### 8-6. 크론 병렬화 + 작업 재시도 (8~16h)
- `service.run_scheduled_quiz_generation`: 순차 → `asyncio.gather` + Semaphore(5). 인덱싱/오디오 백그라운드 작업에 재시도 1회 + 실패 시 상태 기록.

### 8-7. 플랜 티어 시스템 (6~8h)
- users에 `plan` 컬럼(free/plus/pro). `usage.py` LIMITS를 플랜별 딕셔너리로. 프론트에 사용량 표시(설정 또는 사이드바).

### 8-8. File Search Store 대체 — 롱컨텍스트 + pgvector (12~16h)
> 결정됨(2026-07-06): File Search Store를 단계적으로 제거한다. 이유: GCP 프로젝트 종속(키 교체 시
> 전체 재인덱싱), 스토어 수명 관리 부담, 그리고 주류 사용 패턴에는 RAG 자체가 과설계.

- **(a) 자료 지정 상호작용(주류 경로) → 롱컨텍스트 직접 주입**: 프론트가 항상 `material_name`을
  넘기므로, `file_search.search()` 대신 로컬 PDF(`get_material_path`)를 Gemini 컨텍스트에 직접
  전달한다 (`generate_material_index`가 이미 쓰는 방식 — `types.Part.from_bytes`). 자료 1개 ≈ 3만
  토큰 ≪ 1M 컨텍스트, 질문당 ~$0.009, implicit caching으로 연속 대화 시 더 저렴. "다른 주차 내용
  섞임" 문제(프롬프트로 막고 있는 것)가 근본 해결됨. 대상: `agents/tools/` 검색 도구,
  `service.generate_example_messages`.
- **(b) 클래스 전체 검색(자료 미지정) → pgvector**: 8-1 Postgres 전환에 pgvector 확장을 얹고
  `gemini-embedding-001`로 업로드 시 청킹·임베딩(자료당 1회 ~$0.004). 텍스트 추출은 낭독
  파이프라인의 `_extract_body_pages`(폰트 필터) 재활용.
- **(c) 마이그레이션·정리**: 업로드 경로에서 Store 인입 제거 → 기존 자료는 로컬 PDF로 (a)(b) 재인덱싱
  → 남은 `tutor-` 프리픽스 스토어 일괄 삭제 (**삭제 전 목록 확인 규칙 준수**). 이후 GOOGLE_API_KEY의
  프로젝트 종속 제약(§6-함정)과 `FILE_SEARCH_STORE_NAME`·인덱싱 대기 로직이 사라진다.
- 완료 기준: 자료 지정 Q&A/퀴즈가 File Search 없이 동일 품질(스팟체크), 클래스 전체 질문이 pgvector
  경로로 응답, Store 잔존 0개.

### 8-9. PostHog 퍼널 (4~6h) — Go/No-Go 데이터의 근거, 필수
- 이벤트: signup, material_upload, first_listen, listen_session(초), quiz_complete, review_quiz_answered, W주차 리텐션. `web/src`에 계측 + 서버 이벤트는 API에서.

### 8-10. 랜딩·온보딩 (8~16h)
- 랜딩 페이지(가치 제안: "교재를 귀로"), 온보딩에 샘플 자료 제공(업로드 전에 낭독 체험), 관리자 뷰는 Metabase/SQL로 대체 가능.

### 8-11. PWA + Media Session (4~8h) — §7 형태 전략 1단계
- `AudioReader.tsx`에 Media Session API 연동: 잠금화면에 자료명·섹션 표시, 재생/일시정지/±15초 탐색
  핸들러. 8-5의 웹푸시용 서비스워커·manifest와 함께 구현하면 중복이 없다.
- 완료 기준: 모바일에서 화면을 끄고도 재생 지속 + 잠금화면 컨트롤 동작 (iOS Safari·Android Chrome 실기기 확인).

## 9. Phase 2 — 유료화 (4~6주, 60~100h + Capacitor 별도 2~4주)

> **세부 실행 계획은 `docs/PHASE2_IMPLEMENTATION_PLAN.md`** (T0~T5). 착수 조건: Phase 1 완료 + 지불 의사 신호.

1. **T0 비코드 선행(사용자)**: 사업자등록·통신판매업 신고·토스페이먼츠 심사·Stripe 계정·커스텀 도메인 — 리드타임 2~4주라 가장 먼저 시작
2. **T1 정기결제 — 토스(국내)+Stripe(해외) 이원화 (결정됨)**: 공통 subscriptions 스키마 + provider별 경로. 토스=빌링키+자체 크론 갱신, Stripe=Checkout+Customer Portal+웹훅 위임. 통화 토글(₩/$) 라우팅 (28~40h)
3. **T2 플랜 게이팅 UI**: 한도 초과 시 업그레이드 모달, 낭독 분량 미터, 플랜 페이지 (8~12h)
4. **T3 TTS 원가 최적화**: free는 Standard 보이스($4/1M자), 유료는 Neural2 — 플랜별 음성 카탈로그 (4~8h)
5. **T4 운영·법무 마감(출시 게이트)**: 백업+복구 리허설, 헬스체크·업타임 모니터, 약관·개인정보처리방침, 회원 탈퇴(데이터 삭제) (8~16h)
6. **T5 Capacitor 앱 래핑(별도 트랙)**: 네이티브 푸시·백그라운드 오디오·스토어 배포. 결제는 웹 유지 — **Apple 심사 리스크 사전 고지** (2~4주)

## 10. 시작하기 전 체크리스트 (새 세션에서)

- [ ] `git log --oneline -15`로 현재 커밋 상태 확인, `git status`로 미커밋 변경(README 등) 파악
- [ ] `uv run pytest -q` 39개 통과 확인
- [ ] 사용자에게 확인할 것: ① Phase 0 push/배포 완료 여부와 INVITE_CODE 설정 ② 지인 베타 시작 여부 (Phase 1은 베타 신호를 보며 우선순위 조정 — 예: 낭독 리텐션이 낮으면 8-3보다 낭독 UX 개선이 먼저) ③ README 커밋 여부 ④ Slack 개인용 기능 유지/제거
- [ ] Phase 1 착수 시 8-1(Postgres)부터. 단, 베타 피드백 대응이 항상 로드맵보다 우선
