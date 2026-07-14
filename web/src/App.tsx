import { useEffect } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import AuthPage from './components/auth/AuthPage';
import AppShell from './components/layout/AppShell';
import ChatArea from './components/chat/ChatArea';
import IosInstallBanner from './components/pwa/IosInstallBanner';
import LandingPage from './components/landing/LandingPage';
import ReviewPage from './components/review/ReviewPage';
import ResetPasswordPage from './components/auth/ResetPasswordPage';

function AppHome() {
  return (
    <>
      <AppShell>
        <ChatArea />
      </AppShell>
      <IosInstallBanner />
    </>
  );
}

export default function App() {
  const { user, token, checkAuth } = useAuthStore();

  useEffect(() => {
    if (token && !user) {
      checkAuth();
    }
  }, [token, user, checkAuth]);

  // 인증 확인 중(토큰 있음·user 아직 없음)에는 랜딩 깜빡임을 막기 위해 빈 화면
  if (token && !user) return null;

  return (
    <Routes>
      <Route path="/" element={user ? <AppHome /> : <LandingPage />} />
      <Route
        path="/login"
        element={user ? <Navigate to="/" replace /> : <AuthPage />}
      />
      <Route path="/reset" element={<ResetPasswordPage />} />
      <Route
        path="/review"
        element={user ? <ReviewPage /> : <Navigate to="/" replace />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
