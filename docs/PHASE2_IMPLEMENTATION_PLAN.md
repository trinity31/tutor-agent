# Phase 2 세부 구현 계획 (유료화)

> `docs/PRODUCT_HANDOFF.md` §9의 실행 상세본. 작성일: 2026-07-06.
> 착수 조건: **Phase 1 완료 + 지불 의사 신호 확인** (가격표 fake-door 전환 3~5% 이상, §7 Go 지표 충족).
> 작업 전 PRODUCT_HANDOFF.md §5(컨벤션)·§6(함정)과 PHASE1_IMPLEMENTATION_PLAN.md 완료 상태를 확인할 것.

## 실행 순서

```
T0 비코드 선행(사용자) ─── 리드타임 2~4주, 가장 먼저 시작 ───┐
Wave 1: T1 정기결제 — 토스(국내)+Stripe(해외) (T0 완료 필요)  │
Wave 2: T2 플랜 게이팅 UI (T1 후) · T3 TTS 원가 최적화(독립) │
Wave 3: T4 운영·법무 마감 (출시 게이트)                      │
별도 트랙: T5 Capacitor 앱 래핑 (Go 판정 후 언제든 병행 가능) ┘
```

## T0. 비코드 선행 작업 (사용자 실행 — 코드보다 먼저 시작할 것)

결제를 받으려면 법적 준비가 필요하고, 심사 리드타임이 개발보다 길다:

- [ ] **사업자등록** (개인사업자로 충분) — 국세청 홈택스, 1~3일
- [ ] **통신판매업 신고** — 유료 구독 판매의 법적 요건. 사업자등록 후 구청/정부24, ~1주
- [ ] **토스페이먼츠 가입·계약 심사** — 사업자등록증 필요, 정기결제(빌링) 심사 1~2주.
      테스트 키는 심사 전에도 발급되므로 개발은 병행 가능
- [ ] **Stripe 계정 개설** (해외 유저 결제용) — 사업자등록증 + 해외 결제 수령 계좌.
      달러 가격 결정 필요 (예: $7.99/$14.99 — 경쟁가 앵커). 해외 판매 세금 처리는 Stripe Tax
      활성화로 위임 권장
- [ ] **커스텀 도메인** — `*.up.railway.app`으로는 PG 심사·신뢰도에 불리. 도메인 구입 후 Railway 연결,
      `APP_BASE_URL`·`ALLOWED_ORIGINS` 갱신 (이메일 발신 도메인은 Phase 1 T4에서 완료됐을 것)
- [ ] 환불 정책 결정 (전자상거래법: 디지털 콘텐츠 청약철회 기준 — T4 약관에 반영)

## T1. 정기결제 — 토스(국내) + Stripe(해외) 이원화 (28~40h)

**구조 (결정됨 2026-07-06)**: 국내 사용자는 토스페이먼츠 빌링키, 해외 사용자는 Stripe.
**두 PG는 갱신 모델이 다르다** — 토스는 *우리 크론이* 빌링키로 매월 결제하고, Stripe는 *Stripe가*
자동 갱신하고 웹훅으로 통지한다. 이 차이를 추상화 없이 억지로 통일하지 말고, 공통 스키마 위에
provider별 경로를 분리 구현한다.

### 공통 스키마 (alembic)
```sql
subscriptions(
  id, user_email UNIQUE, plan TEXT,              -- plus | pro
  provider TEXT,                                  -- 'toss' | 'stripe'
  billing_key TEXT,                               -- toss 전용 (카드 재결제용)
  stripe_customer_id TEXT, stripe_subscription_id TEXT,  -- stripe 전용
  card_summary TEXT,                              -- '신한 **** 1234' 표시용
  status TEXT,                                    -- active | past_due | canceled
  current_period_end TIMESTAMP,
  fail_count INTEGER DEFAULT 0,                   -- toss 경로에서만 사용
  created_at, updated_at)
payment_history(id, user_email, provider, order_id UNIQUE, amount, currency, plan,
                status, raw_response TEXT, created_at)
```

### 라우팅 (누가 어느 PG로 가나)
- `/plans` 페이지에서 통화 토글(₩/KRW ↔ $/USD). 기본값: 브라우저 locale이 ko면 토스, 아니면 Stripe.
- 가격: ₩9,900/₩19,900 (토스) · $7.99/$14.99 (Stripe — T0에서 확정). 금액·플랜 매핑은 서버 상수.

### 토스 경로 — `tutor_agent/billing.py`
1. env: `TOSS_SECRET_KEY`, `TOSS_CLIENT_KEY`(프론트).
2. **카드 등록(빌링키)**: 프론트 토스 SDK `requestBillingAuth()` → `authKey` →
   `POST /api/billing/toss/register {auth_key, plan}` → 빌링키 발급 API → subscriptions upsert →
   **즉시 첫 결제** → 성공 시 `users.plan` 갱신.
3. **월 결제 크론**: `POST /api/billing/charge-due?secret=CRON_SECRET` (Cloud Scheduler 매일) —
   `provider='toss' AND current_period_end <= now`인 active 구독을 빌링키로 결제.
   성공 → period +1개월·fail_count 0. 실패 → fail_count++·`past_due`;
   **3회 실패 또는 7일 경과 시 free 강등** + 안내 메일(mailer 재사용).
4. **웹훅** `POST /api/billing/webhook/toss`: 결제 취소·카드 정지 등. 시크릿 검증 + 멱등(order_id UNIQUE).

### Stripe 경로 — 같은 `billing.py`, 구현량은 토스보다 작음 (관리를 Stripe에 위임)
1. `uv add stripe`. env: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, Price ID 2개(plus/pro — Stripe
   대시보드에서 recurring Price 생성).
2. **구독 시작**: `POST /api/billing/stripe/checkout {plan}` → Checkout Session(mode=subscription,
   customer_email, success/cancel URL) 생성 → 프론트는 URL로 리다이렉트만.
3. **관리 위임**: 카드 변경·해지는 **Customer Portal** (`POST /api/billing/stripe/portal` → portal URL)
   — 자체 UI 불필요.
4. **웹훅** `POST /api/billing/webhook/stripe` (`stripe.Webhook.construct_event`로 서명 검증):
   - `checkout.session.completed` → subscriptions upsert(provider='stripe') + plan 부여
   - `invoice.paid` → current_period_end 갱신
   - `invoice.payment_failed` → past_due (재시도는 Stripe Smart Retries에 위임)
   - `customer.subscription.deleted` → free 강등
   멱등: event id를 payment_history.order_id로 기록.
5. 크론의 charge-due는 stripe 구독을 건드리지 않는다 — 단, `past_due` 7일 초과 시 강등하는
   안전망 스윕만 provider 공통으로 수행.

### 공통 규칙
- 금액·플랜 검증은 항상 서버 기준(프론트 전달값 신뢰 금지). 모든 PG 응답은 payment_history.raw_response 보존.
- `users.plan` 갱신은 subscriptions 상태 변화의 단일 함수(`apply_subscription_state`)를 통해서만 —
  두 경로가 같은 강등/부여 로직을 공유.

### 프론트
- `/plans`: 플랜 비교표 + 통화 토글, 현재 플랜 표시
- 토스: 카드 등록 위젯 + `/billing/success`·`/billing/fail` 콜백 / Stripe: 리다이렉트만
- 설정: 현재 플랜·다음 결제일·카드·해지(토스는 자체 버튼, Stripe는 Portal 링크), 결제 내역

### 검증 (완료 기준)
- 토스 테스트 키: 카드 등록→첫 결제→plan 반영, 크론 갱신(period_end 과거 조작), 실패 카드로
  past_due→강등, 해지 후 만료 강등
- Stripe 테스트 모드: Checkout→plan 부여, `stripe trigger invoice.paid/payment_failed/
  customer.subscription.deleted`(Stripe CLI)로 웹훅 전 이벤트 처리, Portal에서 해지→강등
- 두 웹훅 모두 서명 위조 거부·중복 이벤트 멱등, 같은 유저가 이중 구독 불가(provider 전환 시 기존 해지 요구)
- 실 키 전환 후 소액 실결제·환불 각 1회 (사용자와 함께)

## T2. 플랜 게이팅 UI 고도화 (8~12h, T1 후)

1. **업그레이드 모달**: 429/402 응답(한도 초과·free 섹션 제한)을 공통 인터셉트(`client.ts`) →
   "무엇이 막혔고, 어느 플랜이면 되는지" 모달 + `/plans` 링크. 현재는 원문 메시지만 노출됨.
2. **낭독 분량 미터**: Phase 1 T7의 `GET /api/me/usage`를 AudioReader 헤더/설정에 표시
   ("이번 달 낭독 12.3만/20만 자"). 80% 도달 시 배지 경고.
3. 사이드바에 플랜 배지(Free/Plus/Pro) + 무료 사용자에게 비침습적 업그레이드 진입점.
4. free 플랜의 "자료당 첫 섹션만 낭독" 게이팅(Phase 1 T7)에 미리듣기 종료 시 업그레이드 안내 연결.

**완료 기준**: 무료 계정으로 각 한도(채팅·업로드·낭독 섹션)에 부딪혔을 때 전부 모달 → 플랜 페이지 동선 연결.

## T3. TTS 원가 최적화 (4~8h, 독립)

1. `tts.py` `GoogleCloudTTSEngine`에 플랜별 음성 카탈로그:
   - free: `ko-KR-Standard-C/D/A` ($4/1M자 — 원가 1/4)
   - plus/pro: 기존 Neural2/Wavenet 유지
   `VOICES`를 함수화(`voices_for_plan(plan)`)하고 `api.py` sections 엔드포인트·`_check_voice`가
   사용자 plan을 반영. 캐시 키에 음성명이 포함되므로 플랜 전환 시 충돌 없음.
2. (선택) 무료 미리듣기 섹션은 항상 Standard로 강제 — 체험 원가 최소화.
3. 원가 모니터링: `usage_counters`의 tts_chars_monthly를 월별 집계하는 쿼리를 운영 문서에 기록
   (Metabase 카드로 — 월 100만 자 무료 한도 소진 예측).

**완료 기준**: free 계정 음성 목록이 Standard만 노출·생성, 유료 전환 시 Neural2 목록 복귀.
기존 Neural2 캐시는 유지 재생.

## T4. 운영·법무 마감 (8~16h) — 유료 출시 게이트

1. **백업**: Railway PG 자동 백업 활성 확인 + 주 1회 `pg_dump` → GCS 업로드 크론(스크립트).
   복구 리허설 1회 (스테이징 DB로 복원).
2. **업타임·헬스**: `GET /api/health` (DB ping + 버전) 신설 → BetterStack/UptimeRobot 5분 간격,
   다운 시 사용자에게 알림.
3. **약관·개인정보처리방침**: `/terms`·`/privacy` 정적 페이지. 필수 포함 —
   업로드 자료의 보관·처리(Google Gemini/Cloud TTS 제3자 제공 고지), 결제·자동갱신·해지·환불 정책(T0
   결정 반영), 탈퇴 시 데이터 삭제. **표준 템플릿 기반 초안 작성 후 법률 검토는 사용자 판단**.
   가입 시 동의 체크박스 + users에 동의 시각 기록.
4. **회원 탈퇴** (약관의 데이터 삭제 약속 이행): `DELETE /api/auth/me` — 구독 해지 + 전 테이블·GCS/볼륨
   파일·(잔존 시) 스토어 삭제. **삭제 전 목록 확인 규칙은 사용자 요청 삭제이므로 확인 불필요, 단 로그 보존**.
5. 결제 장애 대응 런북 한 페이지 (webhook 재처리 방법, 토스 대시보드 위치).

**완료 기준**: 헬스 모니터 알림 수신 테스트, 백업 복원 성공, 약관 링크가 가입·결제 화면에 노출,
탈퇴 E2E(재가입 시 빈 계정).

## T5. Capacitor 앱 래핑 (2~4주) — 별도 트랙 (형태 전략 2단계, PRODUCT_HANDOFF §7)

Go 판정 후 T1~T4와 병행 가능. 결제 완성 전에도 무료 앱으로 출시 가능.

1. `npm i @capacitor/core @capacitor/ios @capacitor/android` + `cap init` — 기존 web/dist를 그대로 래핑.
   API_BASE를 절대 URL로 전환(`VITE_API_BASE` env) — 현재 상대경로(`/api`)는 WebView에서 안 됨.
2. **네이티브 푸시**: `@capacitor/push-notifications` (FCM/APNs). Phase 1 T5의 push_subscriptions를
   `kind TEXT('webpush'|'fcm'|'apns')`로 확장, notifications.py에 FCM 발송 경로 추가.
3. **백그라운드 오디오**: Android는 WebView `<audio>`+Media Session으로 대체로 동작. iOS는
   `AVAudioSession` 카테고리 설정 플러그인(capacitor-community 또는 자체 브릿지) 필요 — 실기기에서
   화면 잠금·앱 백그라운드 재생을 최우선 검증.
4. **결제 정책 리스크(중요)**: 디지털 구독은 Apple IAP 요구 대상. 앱에서는 결제 버튼·가격 노출을 빼고
   웹에서만 결제(로그인 공유) — 그래도 심사 리젝 가능성이 있으므로 1차 심사에서 지적 시
   한국 제3자 결제(2022 허용) 경로 또는 IAP 병행을 재검토. **심사 리스크를 사용자에게 사전 고지할 것.**
5. 스토어 자산: 아이콘·스플래시(기존 T 로고), 스크린샷(낭독·퀴즈·복습), 심사용 테스트 계정.

**완료 기준**: TestFlight/내부 테스트 트랙에서 ① 로그인·낭독·퀴즈 전 기능 ② 잠금화면 재생 ③ 푸시 수신.
스토어 공개는 사용자 결정.

---

## 공통 검증 표준

Phase 1 계획서의 공통 표준(테스트·빌드·E2E·보안 회귀·env 문서화·push 규칙)에 추가로:
- 결제 관련 변경은 **항상 테스트 키로 전 흐름 재검증** 후 실 키 반영, 금액·플랜은 서버 검증 재확인
- 개인정보 관련 변경(탈퇴·약관)은 실제 데이터 삭제 여부를 DB·스토리지에서 직접 확인
