import { create } from 'zustand';
import { apiPost, apiGet } from '../api/client';

interface User {
  email: string;
  name: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem('token'),
  loading: false,
  error: null,

  login: async (email, password) => {
    set({ loading: true, error: null });
    try {
      const res = await apiPost<{ token: string; user: User }>('/auth/login', {
        email,
        password,
      });
      localStorage.setItem('token', res.token);
      set({ user: res.user, token: res.token, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  register: async (email, password, name) => {
    set({ loading: true, error: null });
    try {
      const res = await apiPost<{ token: string; user: User }>('/auth/register', {
        email,
        password,
        name,
      });
      localStorage.setItem('token', res.token);
      set({ user: res.user, token: res.token, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  logout: () => {
    localStorage.removeItem('token');
    set({ user: null, token: null });
  },

  checkAuth: async () => {
    const token = localStorage.getItem('token');
    if (!token) return;
    try {
      const res = await apiGet<{ user: User }>('/auth/me');
      set({ user: res.user, token });
    } catch {
      localStorage.removeItem('token');
      set({ user: null, token: null });
    }
  },

  clearError: () => set({ error: null }),
}));
