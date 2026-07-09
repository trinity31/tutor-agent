import { useState } from 'react';

// iOS는 홈 화면에 추가해야(16.4+) 웹푸시·standalone이 가능하다.
// Safari에는 자동 설치 프롬프트가 없으므로 공유→홈 화면 추가를 1회 안내한다.
const DISMISS_KEY = 'tutor-ios-a2hs-dismissed';

function shouldShow(): boolean {
  if (localStorage.getItem(DISMISS_KEY)) return false;
  const ua = navigator.userAgent;
  const isIOS =
    /iphone|ipad|ipod/i.test(ua) ||
    // iPadOS 13+는 Mac으로 위장 — 터치 지원으로 구분
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isStandalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as { standalone?: boolean }).standalone === true;
  return isIOS && !isStandalone;
}

export default function IosInstallBanner() {
  // 브라우저 API만 읽으므로 렌더 시 1회 판정 (CSR 전용, effect 불필요)
  const [show, setShow] = useState<boolean>(() => shouldShow());

  if (!show) return null;

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, '1');
    setShow(false);
  };

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-warm-200 bg-white px-4 py-3 shadow-[0_-4px_16px_rgba(0,0,0,0.06)]">
      <div className="mx-auto flex max-w-xl items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-500 text-lg font-bold text-white">
          T
        </div>
        <p className="flex-1 text-sm leading-snug text-warm-700">
          홈 화면에 추가하면 앱처럼 쓰고 복습 알림을 받을 수 있어요. 공유
          <span className="mx-0.5 font-semibold">⎋</span>
          &rarr; &ldquo;홈 화면에 추가&rdquo;
        </p>
        <button
          onClick={dismiss}
          className="shrink-0 rounded-lg px-2 py-1 text-sm font-medium text-warm-400 hover:text-warm-600"
          aria-label="닫기"
        >
          닫기
        </button>
      </div>
    </div>
  );
}
