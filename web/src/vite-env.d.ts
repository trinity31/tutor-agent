/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  /** PostHog 프로젝트 API 키. 없으면 계측 전체 비활성(로컬/미설정 환경에서 무동작). */
  readonly VITE_POSTHOG_KEY?: string;
  /** PostHog 호스트. 미설정 시 US 클라우드 기본값. */
  readonly VITE_POSTHOG_HOST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
