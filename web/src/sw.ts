/// <reference lib="webworker" />
import { precacheAndRoute } from 'workbox-precaching';

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<{ url: string; revision: string | null }>;
};

// 앱 셸 프리캐시 (빌드 시 파일 목록 주입). 오디오·PDF는 캐싱하지 않는다.
precacheAndRoute(self.__WB_MANIFEST);

// 새 SW를 즉시 활성화 (registerType: autoUpdate와 함께 최신 반영)
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// --- T5(웹푸시 복습 알림): 여기에 push / notificationclick 핸들러가 들어간다 ---

export {};
