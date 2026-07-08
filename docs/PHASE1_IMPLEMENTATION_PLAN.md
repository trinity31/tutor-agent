# Phase 1 세부 구현 계획 (공개 베타 100명)

> `docs/PRODUCT_HANDOFF.md` §8의 실행 상세본. 각 작업을 파일·스키마·함수 수준으로 구체화했다.
> 작성일: 2026-07-06. 작업 전 반드시 PRODUCT_HANDOFF.md §5(컨벤션)·§6(함정)을 읽을 것.

## 실행 순서 (의존성 웨이브)

```
Wave 1 (기반):      T1 Postgres 전환 ──→ T2 체크포인터
Wave 2 (병행 가능):  T4 이메일 인프라 · T6 크론 병렬화 · T7 플랜 티어 · T9 PostHog · T11 PWA/MediaSession
Wave 3 (Wave1·2 후): T5 알림 재설계(T4 필요) · T8 File Search 대체(T1 필요)
Wave 4 (여유 시):    T3 GCS 전환 · T10 랜딩·온보딩
```
- **베타 피드백 대응은 항상 이 로드맵보다 우선.** 낭독 리텐션이 낮으면 T11·낭독 UX부터.
- 각 T는 독립 커밋(들). 완료 기준 미충족 시 다음 T로 넘어가지 말 것.

---

## T1. SQLite → PostgreSQL (16~24h)

**목표**: 동시 쓰기·수평 확장의 토대. 로컬 개발은 SQLite 유지(듀얼 백엔드).

**접근**: SQLAlchemy 2.0 **Core**(ORM 아님 — 현재 함수형 CRUD 구조 유지) + alembic.
`DATABASE_URL` 미설정 시 `sqlite:///data/users.db`로 폴백 → 로컬 개발 흐름 불변.

1. 의존성: `uv add "sqlalchemy>=2" "psycopg[binary]" alembic`
2. `tutor_agent/db.py` 신설:
   ```python
   DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/users.db")
   engine = create_engine(DATABASE_URL, pool_pre_ping=True,
                          connect_args={"check_same_thread": False} if sqlite else {})
   # SQLite일 때만 PRAGMA WAL/busy_timeout 이벤트 리스너
   ```
3. `auth.py` 전환 — 테이블 8개를 `MetaData` + `Table`로 선언 (users, classes, quiz_results,
   completions, study_notes, audio_assets, usage_counters, indexing_status):
   - `AUTOINCREMENT` → `Integer, Identity()` / `datetime('now')` → `func.now()` (컬럼은 `DateTime`)
   - JSON 문자열 컬럼(questions/answers/wrong_questions)은 `Text` 유지 — 코드 변경 최소화
   - `INSERT ... ON CONFLICT`(audio_assets 선점, usage_counters 누적, indexing_status upsert)는
     `sqlalchemy.dialects.postgresql.insert` / `sqlite.insert`의 `on_conflict_do_*`로 분기 헬퍼 작성
   - 각 CRUD 함수: `conn = _get_db()` → `with engine.begin() as conn:` + `text()` 쿼리
     (플레이스홀더 `?` → `:name` 전면 치환)
4. `usage.py`·`file_search.py`(indexing_status 위임)도 같은 방식.
5. alembic 초기화: `alembic init migrations`, 첫 리비전 = 현 스키마 스냅샷. 이후 스키마 변경은
   alembic 리비전으로만 (auth.py의 CREATE TABLE IF NOT EXISTS·ALTER 마이그레이션 제거).
6. 이관 스크립트 `scripts/migrate_sqlite_to_pg.py`: users.db 8테이블 → Postgres 벌크 insert.
   실행 순서: Railway Postgres 추가 → `DATABASE_URL` 설정 → 배포 → 스크립트 1회 실행(로컬에서
   프로덕션 DB URL로) → 검증 후 볼륨의 users.db는 백업으로 보존.

**주의**: `audio_assets` UNIQUE 선점(create_audio_asset의 rowcount 기반 잠금)과 usage 누적의
동시성 시맨틱이 PG에서도 유지되는지 동시 요청 테스트로 확인할 것.
**완료 기준**: `DATABASE_URL` 설정/미설정 양쪽에서 pytest + 업로드→채팅→퀴즈→낭독→노트 E2E 통과,
동시 가입·동시 오디오 요청(중복 생성 0) 테스트.

## T2. 체크포인터 → PostgresSaver (4h)

1. `uv add langgraph-checkpoint-postgres`
2. `service.py`: `DATABASE_URL`이 PG면 `PostgresSaver`(동기 — 그래프 호출이 동기이므로 Async 불필요),
   아니면 기존 SqliteSaver 유지. 최초 1회 `checkpointer.setup()`.
3. 이후 uvicorn `--workers 2+` 허용. 단, BackgroundTasks(오디오 생성)는 워커 로컬이므로 문제없음.

**완료 기준**: 재배포 후 기존 스레드 대화 이어짐, 워커 2로 띄워 서로 다른 워커에서 같은 스레드 접근 정상.

## T3. 파일 저장 GCS 전환 (8~12h) — Wave 4, 규모 신호 전 보류 가능

**선행 판단**: 단일 인스턴스 + Railway 볼륨으로 100명까지는 동작한다. 멀티 인스턴스가 필요해질 때 실행.

1. GCS 버킷 `tutor-agent-media` (Saju Thread Bot 프로젝트 또는 분리 — 사용자 확인).
   인증: Railway에 서비스계정 JSON(`GOOGLE_APPLICATION_CREDENTIALS_JSON`) → 기동 시 임시파일로 풀기.
2. 경로 스킴은 현행 미러: `materials/{user}/{class}/{name}.pdf`, `audio/{user}/{material}/{sec}_{voice}.mp3`
3. **매니페스트는 GCS가 아니라 DB로**: `audio_assets`에 `manifest TEXT` 컬럼 추가(alembic) —
   `.manifest.json` 파일 개념 제거, `get_audio_manifest`는 DB 조회로 단순화.
4. 서빙: `GET .../audio/url`·`/pdf/url` 신설 → V4 signed URL(15분) 반환. 프론트
   `audioFileUrl`/`pdfFileUrl`을 async 함수로 교체. **기존 `?token=` 쿼리 인증과 수동 Range 코드 삭제**
   (signed URL은 GCS가 Range 처리).
5. 업로드·생성 경로: 로컬 임시 파일 → GCS 업로드 → 로컬 삭제. `get_material_path`는 GCS 다운로드
   캐시(오디오 생성·롱컨텍스트 주입용) 헬퍼로 변경.

**완료 기준**: 모바일 시크(Range) 정상, 토큰이 URL에 노출되지 않음, 재배포 후 파일 접근 정상.

## T4. 이메일 검증 + 비밀번호 재설정 (8~12h)

**스택**: Resend (도메인 인증 필요 — 사용자에게 발신 도메인 확인). `RESEND_API_KEY` env.

1. 스키마(alembic): `users.email_verified BOOLEAN DEFAULT false`,
   `auth_tokens(token PK, user_email, purpose TEXT('verify'|'reset'), expires_at, used BOOLEAN)`
2. `tutor_agent/mailer.py` 신설: `send_verify_email(email, token)`, `send_reset_email(...)` —
   링크는 `{APP_BASE_URL}/verify?token=...` 형식. `APP_BASE_URL` env 추가.
3. 엔드포인트: `POST /api/auth/request-verify`(재발송), `POST /api/auth/verify {token}`,
   `POST /api/auth/request-reset {email}`(존재 여부 노출 금지 — 항상 200),
   `POST /api/auth/reset {token, new_password}`
4. 가입 흐름: register 성공 → 인증 메일 발송. **미인증 사용자는 업로드·낭독 차단**(채팅 체험은 허용)
   — `get_current_user`에 verified 요구 의존성 변형 `get_verified_user` 추가해 해당 엔드포인트만 교체.
5. 프론트: `/verify`·`/reset` 라우트(react-router 도입 또는 쿼리 파싱), AuthPage에 "비밀번호를
   잊으셨나요?" + 미인증 배너.
6. 베타 호환: `INVITE_CODE` 병행 유지. 기존 사용자는 이관 시 `email_verified=true`로 세팅.

**완료 기준**: 가입→메일 수신→인증→업로드 가능 / 미인증 차단 / 재설정 왕복 / 만료·재사용 토큰 거부.

## T5. 알림 재설계 — 이메일·웹푸시 (12~20h, T4 후)

**목표**: 복습 루프(제품 웨지 절반)를 Slack 없이 모든 사용자에게. Slack은 `SLACK_ENABLED=1`일 때만
로드되는 개인용 레거시로 격리 (삭제 여부는 사용자 결정 대기).

1. **웹 복습 퀴즈 화면(선행)**: 현재 예약 퀴즈는 Slack 버튼으로만 풀 수 있다.
   - `GET /api/quiz-results?status=in_progress` 필터 추가
   - 프론트: 사이드바에 "오늘의 복습" 배지 + 진입 → 기존 `QuizCard`/`QuizResult` 재사용,
     완료 시 `update_quiz_result(status='completed', answers, score)` 호출하는
     `PATCH /api/quiz-results/{id}/complete` 신설 (소유권 검증 포함)
2. `tutor_agent/notifications.py` 신설:
   `notify_review_quiz(user_email, quiz)` → ① 이메일(mailer 재사용, 퀴즈 링크) ② 웹푸시.
   채널 설정: `users.notify_email BOOLEAN DEFAULT true`, `notify_push BOOLEAN DEFAULT true`.
3. **웹푸시**: `uv add pywebpush`, VAPID 키 생성(env `VAPID_PRIVATE_KEY`/`VAPID_PUBLIC_KEY`).
   스키마: `push_subscriptions(id, user_email, endpoint UNIQUE, keys_json, created_at)`.
   엔드포인트: `POST /api/push/subscribe`, `DELETE /api/push/subscribe`.
   프론트: T11의 서비스워커에 push 핸들러 — 알림 클릭 시 `/review`로.
4. `service.run_scheduled_quiz_generation`: `post_quiz_to_slack` 호출을
   `notifications.notify_review_quiz`로 교체 (Slack은 SLACK_ENABLED 시 추가 채널).
5. slack.py: import 시점 부작용 제거 — `SLACK_ENABLED` 아니면 핸들러 미등록 (`api.py`의
   `if slack_handler:` 분기는 이미 존재).

**완료 기준**: 학습 완료 → 다음날 크론 → 이메일+푸시 수신 → 링크로 웹에서 퀴즈 완료 → 오답 재시험
예약까지 Slack 없이 전체 루프 동작. iOS(홈 화면 추가)·Android 실기기 푸시 확인.

## T6. 크론 병렬화 + 백그라운드 재시도 (8~16h)

1. `run_scheduled_quiz_generation`: for 루프 → `asyncio.gather` + `asyncio.Semaphore(5)`,
   동기 `_graph.invoke`는 `asyncio.to_thread`로. 사용자당 실패 격리(현행 try/except 유지).
2. 크론 엔드포인트에 처리 시간·성공/실패 카운트 로깅 (Sentry breadcrumb).
3. 백그라운드 재시도: `finish_indexing`·`generate_audio_asset`을 공통 래퍼
   `run_background_job(job_name, fn, *args)`로 감싸 실패 시 1회 재시도(지수 백오프 30s) 후
   상태 기록. 별도 잡 큐는 도입하지 않는다(Phase 2 이후 규모 신호 시 재검토).

**완료 기준**: 가짜 completion 20건 시딩 → 크론 1회 실행이 순차 대비 3배+ 단축, 부분 실패에도 나머지 성공.

## T7. 플랜 티어 시스템 (6~8h)

1. 스키마: `users.plan TEXT DEFAULT 'free'` (free|plus|pro — 값은 Phase 2 결제와 공유).
2. `usage.py`: `LIMITS` → `PLAN_LIMITS = {"free": {...}, "plus": {...}, "pro": {...}}`
   (수치는 PRODUCT_HANDOFF §7 가격안 기준: free 자료3/월·낭독은 자료당 첫 섹션만,
   plus 자료20/월·낭독 20만자/월). `check_limit(email, metric)`이 plan을 조회해 적용.
   env 오버라이드(`LIMIT_*`)는 free 기본값 재정의로 유지.
3. "자료당 첫 섹션만" 게이팅: `material_audio_request`에서 free 플랜 + section != 첫 섹션 → 402/안내.
4. `GET /api/me/usage`: 플랜·잔여량 반환 → 프론트 사이드바 하단에 사용량 미터(낭독 자수·업로드).

**완료 기준**: 플랜별 한도 차등 동작, 프론트 미터 표시, 한도 초과 안내에 업그레이드 문구.

## T8. File Search Store 대체 (12~16h, T1 후)

### (a) 자료 지정 경로 → 추출 텍스트 직접 주입 (주류 경로, 효과 최대)
1. 업로드 시 본문 텍스트를 미리 추출·저장: `service.upload_material`에서
   `_extract_body_pages`(폰트 필터 — narration과 동일 품질) 결과를
   `materials/{user}/{class}/{name}.txt`로 저장. 기존 자료는 lazy(첫 요청 시 추출·캐시).
2. `tutor_tools.search_material` 수정: `material_name`이 있으면 **file_search 호출 없이**
   추출 텍스트를 그대로 반환 (`{"subject", "content": 전문, "char_count"}`) — 에이전트 LLM이
   전문을 직접 소비. 3만 자 초과 시 앞 3만 자 + 인덱스(`get_material_index`) 병기.
   효과: 검색 LLM 호출 1~2회 제거(지연·비용↓), "다른 주차 내용 섞임" 원천 차단.
3. `service.generate_example_messages`도 동일 전환.

### (b) 클래스 전체 검색 → pgvector
1. T1에서 `CREATE EXTENSION IF NOT EXISTS vector` (Railway PG 지원 확인).
2. 스키마: `material_chunks(id, user_email, class_id, material_name, chunk_idx,
   content TEXT, embedding vector(768))` + ivfflat 인덱스. SQLite 폴백 시 이 기능은 비활성
   (로컬 개발은 자료 지정 경로로 충분).
3. 업로드 백그라운드에서 청킹(문단 기준 ~1,000자) → `gemini-embedding-001`
   (`client.models.embed_content`, `output_dimensionality=768`) 배치 임베딩 → insert.
4. `search_material`의 `material_name` 없는 분기: 질의 임베딩 → 코사인 top-8 청크 반환.
5. 클래스/자료 삭제 시 청크 삭제.

### (c) File Search 제거·정리
1. `upload_pdf_start`의 Store 인입 제거, `_store_name_for`·`wait_for_indexing` 의존 제거
   (indexing_status는 텍스트 추출·임베딩 완료 추적으로 의미 전환).
2. `file_search.py`는 `search()`/store 관련 함수 제거 후 인덱스 생성·manifest 유틸만 남기고
   파일명 유지 (혹은 `materials.py`로 개명 — 커밋 분리).
3. 잔존 스토어 정리 스크립트: `tutor-` 프리픽스 목록 출력 → **사용자 확인 후** 일괄 삭제.

**완료 기준**: 자료 지정 Q&A·퀴즈 품질 스팟체크(기존 대비 동등 이상), 클래스 전체 질문이 pgvector로
응답, 신규 업로드가 Store를 만들지 않음, 잔존 스토어 0 (사용자 승인 후).

## T9. PostHog 퍼널 (4~6h) — 베타 시작 전 필수

1. `npm i posthog-js` — `web/src/main.tsx`에서 `VITE_POSTHOG_KEY` 있을 때만 init
   (`person_profiles: 'identified_only'`). 로그인 시 `posthog.identify(email)`.
2. 이벤트 계측 지점:
   - `signup` (AuthPage) · `material_upload` (classStore.uploadMaterial)
   - `listen_start`/`listen_session`(청취 초 — AudioReader pause/ended에서 구간 합산)
   - `listen_complete_section` (ended) · `quiz_complete` (QuizResult 표시 시)
   - `review_quiz_answered` (T5 웹 복습 완료) · `chat_message` (chatStore.sendMessage)
3. 서버 이벤트(선택): 크론 발송 수 — posthog python 없이 로그로 충분.
4. 대시보드: 활성화 퍼널(가입→업로드→첫 청취/퀴즈), 주간 낭독 리텐션, W2/W4 — Go/No-Go 지표(§7)와 1:1.

**완료 기준**: 본인 계정으로 전 퍼널 이벤트가 PostHog에 보임. 지표 대시보드 링크를 README 또는 메모에 기록.

## T10. 랜딩·온보딩 (8~16h)

1. 비로그인 루트를 랜딩으로: 가치 제안 한 줄("교재를 귀로 정독하세요"), 낭독 데모(샘플 오디오 재생),
   가격 예고 없이 베타 가입 CTA. 기존 AuthPage는 `/login`.
2. 샘플 자료: 가입 직후 "샘플 클래스" 자동 생성(저작권 무관한 공개 PDF 1개 + 사전 생성 오디오 시딩
   스크립트) — 업로드 전에 낭독을 체험시켜 활성화율(Go 지표 ①)을 끌어올린다.
3. 관리자 뷰는 만들지 않는다 — Railway Postgres에 Metabase/TablePlus 연결로 대체.

**완료 기준**: 신규 가입 3클릭 내 첫 낭독 체험 가능.

## T11. PWA + Media Session (4~8h) — 베타 시작 전 강력 권장

1. `npm i -D vite-plugin-pwa` — manifest(이름·아이콘 192/512·standalone·theme_color),
   서비스워커는 generateSW로 최소 구성(오프라인 캐시는 셸만; 오디오 캐싱은 미도입).
   T5의 push 핸들러가 들어갈 자리이므로 `injectManifest` 방식 선택 권장.
2. `AudioReader.tsx`에 Media Session 연동 (재생 시작 시):
   ```ts
   navigator.mediaSession.metadata = new MediaMetadata({
     title: `${materialName} ${sectionTitle}`, artist: 'TutorAgent' });
   setActionHandler('play'/'pause'/'seekbackward'/'seekforward'(±15s)/'seekto')
   ```
   `playbackState`·`setPositionState`(duration/position/playbackRate) 동기화.
3. iOS 사용자 안내: 공유→홈 화면에 추가 배너(1회 노출, localStorage).

**완료 기준**: iOS Safari·Android Chrome 실기기에서 ① 화면 꺼도 재생 유지 ② 잠금화면에 제목·컨트롤
표시 및 동작 ③ 홈 화면 설치 후 standalone 실행.

---

## Phase 2 미리보기 (유료화 — 상세 계획은 Phase 1 완료 후 별도 작성)

- **토스페이먼츠 정기결제(빌링키)**: `subscriptions(id, user_email, plan, billing_key, status,
  current_period_end)` + `POST /api/billing/webhook`(서명 검증) + 결제 실패 3회 grace →
  free 강등. 프론트 플랜 선택·카드 등록 화면. 앱 래핑(Capacitor) 후에도 결제는 웹 링크 유지.
- 플랜 게이팅 UI 고도화(업그레이드 모달), TTS 무료 티어 Standard 보이스 옵션(`tts.py` VOICES 분기),
- 운영: PG 자동 백업 확인, uptime 모니터(Betterstack 등), 이용약관·개인정보처리방침(자료 보관·AI 처리·
  제3자 제공(Google) 고지 — 법률 검토 권장).

## 공통 검증 표준 (모든 T 공통)

1. `uv run pytest -q` + `cd web && npm run build` 통과
2. 회귀 E2E: 로그인→업로드→인덱스→채팅→퀴즈→낭독(하이라이트·페이지 동기화)→노트 (브라우저 프리뷰)
3. 보안 회귀: 타 사용자 리소스 접근 시도(노트·퀴즈·오디오) 403/404
4. 신규 env는 README 환경변수 섹션에 즉시 문서화
5. push는 사용자 요청+암호 확인 시에만. Railway 변수 변경은 사용자에게 목록으로 안내
