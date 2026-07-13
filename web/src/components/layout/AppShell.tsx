import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import { useUIStore } from '../../stores/uiStore';
import { useReviewStore } from '../../stores/reviewStore';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { sidebarOpen, openSidebar, closeSidebar } = useUIStore();
  const navigate = useNavigate();
  const reviewCount = useReviewStore((s) => s.pending.length);
  const loadReviews = useReviewStore((s) => s.load);

  // 복습 대기 개수(배지) — 앱 진입 시 1회 로드
  useEffect(() => {
    loadReviews();
  }, [loadReviews]);

  return (
    <div className="flex h-dvh w-full">
      <Sidebar open={sidebarOpen} onClose={closeSidebar} />

      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header */}
        <header className="flex items-center border-b border-warm-100 bg-white px-4 py-3 md:hidden">
          <button
            onClick={openSidebar}
            className="rounded-lg p-2 text-warm-600 hover:bg-warm-100"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path
                d="M3 5h14M3 10h14M3 15h14"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <h1 className="ml-3 text-base font-bold text-warm-900">AI Tutor</h1>
          <button
            onClick={() => navigate('/review')}
            className="relative ml-auto flex items-center gap-1.5 rounded-full border border-warm-200 px-3 py-1.5 text-xs font-bold text-warm-700 active:scale-95 transition-transform"
            title="복습"
          >
            🔁 복습
            {reviewCount > 0 && (
              <span className="grid h-4 min-w-4 place-items-center rounded-full bg-primary-500 px-1 text-[10px] font-bold text-white">
                {reviewCount}
              </span>
            )}
          </button>
        </header>

        {children}
      </main>
    </div>
  );
}
