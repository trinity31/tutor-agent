import posthog from 'posthog-js';

// PostHog 퍼널 계측 (T9). VITE_POSTHOG_KEY가 없으면 전체 무동작 —
// 로컬 개발·키 미설정 환경에서 빌드/실행에 영향을 주지 않는다.
// 이벤트는 §7 Go/No-Go 지표(활성화 퍼널·주간 낭독 리텐션·복습 응답)와 1:1로 매핑된다.

let enabled = false;

export function initAnalytics(): void {
  const key = import.meta.env.VITE_POSTHOG_KEY;
  if (!key) return;
  posthog.init(key, {
    api_host: import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
    // 익명 프로필을 만들지 않고, identify된 로그인 사용자만 인물로 집계
    person_profiles: 'identified_only',
    // 명시적 퍼널 이벤트만 수집 — 자동 캡처·페이지뷰 노이즈 제거
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
  });
  enabled = true;
}

export function identifyUser(email: string): void {
  if (!enabled) return;
  posthog.identify(email);
}

export function resetAnalytics(): void {
  if (!enabled) return;
  posthog.reset();
}

export type AnalyticsEvent =
  | 'signup'
  | 'material_upload'
  | 'chat_message'
  | 'quiz_complete'
  | 'listen_start'
  | 'listen_session'
  | 'listen_complete_section'
  | 'study_complete' // '학습 완료' 버튼 — 복습 루프 방아쇠
  | 'review_quiz_answered'; // T5(웹 복습)에서 연결

export function track(event: AnalyticsEvent, props?: Record<string, unknown>): void {
  if (!enabled) return;
  posthog.capture(event, props);
}
