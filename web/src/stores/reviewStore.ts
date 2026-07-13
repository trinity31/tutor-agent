import { create } from 'zustand';
import { getQuizResults, type QuizResultRow } from '../api/client';

// 복습 대기(예약 생성됐지만 아직 안 푼) 퀴즈 — status='in_progress'
interface ReviewState {
  pending: QuizResultRow[];
  loaded: boolean;
  load: () => Promise<void>;
  removeCompleted: (id: string) => void;
}

export const useReviewStore = create<ReviewState>((set) => ({
  pending: [],
  loaded: false,
  load: async () => {
    try {
      const res = await getQuizResults();
      set({
        pending: res.results.filter((r) => r.status === 'in_progress'),
        loaded: true,
      });
    } catch {
      set({ loaded: true });
    }
  },
  removeCompleted: (id) =>
    set((s) => ({ pending: s.pending.filter((r) => r.id !== id) })),
}));
