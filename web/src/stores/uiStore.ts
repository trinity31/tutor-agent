import { create } from 'zustand';

// 사이드바(모바일 드로어) 열림 상태 — 햄버거와 빈 상태 CTA가 공유한다
interface UIState {
  sidebarOpen: boolean;
  openSidebar: () => void;
  closeSidebar: () => void;
  // 자료 완료 상태 갱신 신호 — 홈에서 학습완료 시 사이드바 배지를 다시 로드시킨다
  statusVersion: number;
  bumpStatus: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: false,
  openSidebar: () => set({ sidebarOpen: true }),
  closeSidebar: () => set({ sidebarOpen: false }),
  statusVersion: 0,
  bumpStatus: () => set((s) => ({ statusVersion: s.statusVersion + 1 })),
}));
