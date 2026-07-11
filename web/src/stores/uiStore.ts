import { create } from 'zustand';

// 사이드바(모바일 드로어) 열림 상태 — 햄버거와 빈 상태 CTA가 공유한다
interface UIState {
  sidebarOpen: boolean;
  openSidebar: () => void;
  closeSidebar: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: false,
  openSidebar: () => set({ sidebarOpen: true }),
  closeSidebar: () => set({ sidebarOpen: false }),
}));
