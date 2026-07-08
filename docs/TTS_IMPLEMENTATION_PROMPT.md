# 구현 지시: 원문 낭독 (Read-Aloud) 기능

> Claude Code에 전달할 구현 프롬프트. `tts-demo/` 폴더의 검증된 데모 코드를 참조할 것.

---

TutorAgent에 **자료 원문 낭독 기능**을 구현하세요. 전자책 리더처럼 업로드된 PDF의 원문을 그대로 음성으로 들려주는 기능입니다 (요약·해설이 아닌 원문 낭독).

## 배경 (이미 검증된 사항)

- `tts-demo/tts_demo.py` — Gemini 2.5 Flash TTS 호출이 프로젝트의 `GOOGLE_API_KEY`로 동작 확인됨. PCM(24kHz s16le mono) 응답 → WAV 변환 코드 포함.
- `tts-demo/reader-demo.html` — 문장 클릭 재생, 하이라이트 따라가기, 배속, 이어듣기 UX 검증됨. 프론트 구현 시 이 UX를 그대로 재현할 것.
- 낭독용 텍스트 정제 규칙 검증됨 (아래 3단계 참조).
- 음성: `Kore`(여성), `Charon`(남성 저음), `Puck`(남성 밝음) 3종 모두 자연스러움 확인. 기본값은 `Charon`.
- 비용: 오디오 출력 $10/1M 토큰. 반드시 **생성 후 캐싱**하고, **사용자가 재생을 요청한 챕터만 온디맨드 생성**할 것.

## 아키텍처 요구사항

### 1. TTS 엔진 추상화 — `tutor_agent/tts.py`

- `TTSEngine` 프로토콜(또는 ABC)로 분리: `synthesize(text: str, voice: str) -> bytes` (PCM 반환).
- 구현체는 `GeminiTTSEngine` 하나만 만들되, 추후 Google Cloud TTS/Speechify로 교체 가능한 구조로.
- 모델: `gemini-2.5-flash-preview-tts`. 재시도 로직 포함 (빈 응답 시 1회 재시도 — `quiz_agent`의 기존 패턴 참조).

### 2. 낭독용 텍스트 정제 파이프라인 — `tutor_agent/narration.py`

PDF 텍스트에서 낭독용 문장 리스트를 만드는 순수 함수들. `tts-demo`에서 검증된 규칙:

1. 한자 병기 제거: `사술(邪術)` → `사술` (정규식 `([가-힣]+)\(([一-鿿]+)\)` → `\1`), 잔여 독립 한자 어절 제거
2. 깨진 글리프·제어문자 제거, `‧` 등 특수 구두점 정리, 공백 정규화
3. 문장 분리 후 숫자 비율 15% 초과 문장(목차·쪽번호) 제외, 표 내용은 건너뛰기
4. 문장 리스트를 **청크로 그룹핑** (청크당 2~4문장, ~500자 이내 — TTS 1회 호출 단위)

### 3. 오디오 생성·캐싱 — `tutor_agent/service.py` 확장

- 청크별로 TTS 호출 → PCM 길이로 **청크당 정확한 재생 시간(초) 계산** → 전체를 하나의 오디오 파일로 병합 + 매니페스트 JSON 생성:
  ```json
  {"voice": "Charon", "chunks": [{"text": "...", "start": 0.0, "end": 12.4, "sentences": ["...", "..."]}]}
  ```
  이 매니페스트가 프론트 하이라이트 동기화의 근거임 (Gemini TTS는 타임스탬프를 주지 않으므로 이 방식이 필수).
- 저장 위치: `data/audio/{user_id}/{material_id}/{section}_{voice}.mp3` + `.manifest.json` (Railway Volume `/app/data` 하위 — 기존 DB와 동일).
- MP3 인코딩: ffmpeg 사용 가능하면 MP3, 없으면 WAV로 폴백.
- 생성은 **백그라운드 태스크**로 (자료 인덱싱을 백그라운드로 전환한 기존 패턴 재사용 — 커밋 `55d1d72` 참조). 상태는 SQLite에 기록.

### 4. DB — `tutor_agent/auth.py`의 스키마에 테이블 추가

```sql
audio_assets(id, user_id, class_id, material_id, section, voice,
             status TEXT,  -- pending | generating | ready | failed
             duration REAL, file_path TEXT, created_at)
```

### 5. API — `tutor_agent/platforms/api.py`

모두 기존 JWT 인증 적용:

- `POST /api/classes/{class_id}/materials/{material_id}/audio` — body: `{section, voice}`. 캐시 있으면 즉시 ready 반환, 없으면 백그라운드 생성 시작
- `GET  .../audio/status?section=&voice=` — 생성 상태 폴링
- `GET  .../audio/file?section=&voice=` — 오디오 스트리밍 (**HTTP Range 지원 필수** — 모바일 탐색·이어듣기용)
- `GET  .../audio/manifest?section=&voice=` — 매니페스트 JSON

### 6. 프론트 — `web/src/components/audio/`

- `AudioReader.tsx`: 재생/일시정지, 배속(0.7~2.0, `playbackRate`), 음성 선택(여성/남성 저음/남성 밝음), 진행바
- 매니페스트 기반 **현재 청크 하이라이트 + 자동 스크롤**, 문장 클릭 시 해당 시점으로 시크 (`tts-demo/reader-demo.html`의 UX 재현)
- 재생 위치 `localStorage` 저장 → 이어듣기
- `MaterialIndexPanel` 옆 또는 내부에 "🎧 듣기" 진입점 추가. 생성 중일 때는 진행 상태 표시 (학습 완료 버튼 로딩 패턴 참조 — 커밋 `018b127`)
- Zustand 스토어: `audioStore.ts`

## 제약

- 기존 기능(과외/퀴즈/Q&A/Slack)을 깨뜨리지 말 것. 기존 코드 스타일·패턴을 따를 것.
- 새 의존성 최소화 (Gemini 호출은 기존 `google-genai` 또는 표준 라이브러리 REST 사용).
- 환경변수 추가 없음 — 기존 `GOOGLE_API_KEY` 재사용.
- 커밋은 기능 단위로 분리, 기존 한국어 커밋 메시지 스타일 유지.

## 검증 (완료 조건)

1. `narration.py` 단위 테스트: 한자 병기 제거, 목차 필터링, 청크 그룹핑 (pytest — 이 프로젝트 최초의 테스트이므로 `tests/` 디렉토리 신설)
2. 로컬에서: 자료 업로드 → 듣기 버튼 → 30초 내 첫 청크 재생 시작 → 하이라이트가 음성과 동기화되는지 확인
3. 같은 섹션 재요청 시 API 호출 없이 캐시에서 즉시 반환되는지 확인
4. Range 요청으로 중간 탐색이 동작하는지 curl로 확인
