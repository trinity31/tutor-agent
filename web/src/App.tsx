import { useEffect } from 'react';
import { useAuthStore } from './stores/authStore';
import AuthPage from './components/auth/AuthPage';
import AppShell from './components/layout/AppShell';
import ChatArea from './components/chat/ChatArea';

export default function App() {
  const { user, token, checkAuth } = useAuthStore();

  useEffect(() => {
    if (token && !user) {
      checkAuth();
    }
  }, [token, user, checkAuth]);

  if (!user) {
    return <AuthPage />;
  }

  return (
    <AppShell>
      <ChatArea />
    </AppShell>
  );
}
