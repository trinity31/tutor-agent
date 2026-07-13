import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';

export default function AuthPage() {
  const [searchParams] = useSearchParams();
  const [isLogin, setIsLogin] = useState(searchParams.get('mode') !== 'register');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const { login, register, loading, error, clearError } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isLogin && password !== confirmPw) return;
    if (isLogin) {
      await login(email, password);
    } else {
      await register(email, password);
    }
  };

  return (
    <div className="flex min-h-dvh items-center justify-center bg-warm-50 p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-xl bg-primary-500 text-3xl text-white">
            T
          </div>
          <h1 className="text-2xl font-bold text-warm-900">AI Tutor</h1>
          <p className="mt-1 text-warm-500">나만의 AI 과외 선생님</p>
        </div>

        {/* Form Card */}
        <div className="rounded-2xl bg-white p-8 shadow-sm">
          <div className="mb-6 flex rounded-xl bg-warm-100 p-1">
            <button
              className={`flex-1 rounded-lg py-2.5 text-sm font-semibold transition-all ${
                isLogin
                  ? 'bg-white text-warm-900 shadow-sm'
                  : 'text-warm-500 hover:text-warm-700'
              }`}
              onClick={() => {
                setIsLogin(true);
                clearError();
              }}
            >
              로그인
            </button>
            <button
              className={`flex-1 rounded-lg py-2.5 text-sm font-semibold transition-all ${
                !isLogin
                  ? 'bg-white text-warm-900 shadow-sm'
                  : 'text-warm-500 hover:text-warm-700'
              }`}
              onClick={() => {
                setIsLogin(false);
                clearError();
              }}
            >
              회원가입
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-warm-700">
                이메일
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="email@example.com"
                required
                className="w-full rounded-xl border border-warm-200 bg-warm-50 px-4 py-3 text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-100 transition-all"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-warm-700">
                비밀번호
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="4자 이상"
                required
                minLength={4}
                className="w-full rounded-xl border border-warm-200 bg-warm-50 px-4 py-3 text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-100 transition-all"
              />
            </div>

            {!isLogin && (
              <div>
                <label className="mb-1.5 block text-sm font-medium text-warm-700">
                  비밀번호 확인
                </label>
                <input
                  type="password"
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  placeholder="비밀번호를 다시 입력하세요"
                  required
                  className="w-full rounded-xl border border-warm-200 bg-warm-50 px-4 py-3 text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-100 transition-all"
                />
                {password && confirmPw && password !== confirmPw && (
                  <p className="mt-1 text-sm text-error-500">
                    비밀번호가 일치하지 않습니다.
                  </p>
                )}
              </div>
            )}

            {error && (
              <div className="rounded-xl bg-error-500/10 px-4 py-3 text-sm text-error-500">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || (!isLogin && password !== confirmPw)}
              className="w-full rounded-xl bg-primary-500 py-3.5 text-base font-semibold text-white transition-all hover:bg-primary-600 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '처리 중...' : isLogin ? '로그인' : '가입하기'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
