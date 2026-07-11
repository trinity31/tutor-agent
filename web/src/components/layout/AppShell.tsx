import Sidebar from './Sidebar';
import { useUIStore } from '../../stores/uiStore';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { sidebarOpen, openSidebar, closeSidebar } = useUIStore();

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
          <h1 className="ml-3 text-base font-bold text-warm-900">AI Tutor 24/7</h1>
        </header>

        {children}
      </main>
    </div>
  );
}
