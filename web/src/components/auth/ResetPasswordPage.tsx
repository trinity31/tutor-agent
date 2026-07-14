import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { resetPassword } from '../../api/client';

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 6) {
      setError('비밀번호는 6자 이상이어야 합니다.');
      return;
    }
    if (password !== confirm) {
      setError('비밀번호가 일치하지 않습니다.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError((err as Error).message || '재설정에 실패했습니다.');
    }
    setLoading(false);
  };

  return (
    <div className="flex min-h-dvh items-center justify-center bg-warm-50 p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-xl bg-primary-500 text-3xl text-white">
            T
          </div>
          <h1 className="text-2xl font-bold text-warm-900">AI Tutor</h1>
        </div>

        <div className="rounded-2xl bg-white p-8 shadow-sm">
          <h2 className="mb-1 text-lg font-bold text-warm-900">새 비밀번호 설정</h2>

          {!token ? (
            <div className="mt-4 space-y-4">
              <p className="text-sm text-error-500">유효하지 않은 링크입니다. 다시 요청해 주세요.</p>
              <button
                onClick={() => navigate('/login')}
                className="w-full rounded-xl border border-warm-200 py-3 text-sm font-semibold text-warm-600 hover:bg-warm-50"
              >
                로그인으로 돌아가기
              </button>
            </div>
          ) : done ? (
            <div className="mt-4 space-y-4">
              <div className="rounded-xl bg-primary-50 px-4 py-3 text-sm text-primary-700">
                비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요.
              </div>
              <button
                onClick={() => navigate('/login')}
                className="w-full rounded-xl bg-primary-500 py-3.5 text-base font-semibold text-white hover:bg-primary-600 active:scale-[0.98]"
              >
                로그인하기
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="새 비밀번호 (6자 이상)"
                required
                minLength={6}
                className="w-full rounded-xl border border-warm-200 bg-warm-50 px-4 py-3 text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-100 transition-all"
              />
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="새 비밀번호 확인"
                required
                className="w-full rounded-xl border border-warm-200 bg-warm-50 px-4 py-3 text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-100 transition-all"
              />
              {error && (
                <div className="rounded-xl bg-error-500/10 px-4 py-3 text-sm text-error-500">
                  {error}
                </div>
              )}
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-xl bg-primary-500 py-3.5 text-base font-semibold text-white transition-all hover:bg-primary-600 active:scale-[0.98] disabled:opacity-50"
              >
                {loading ? '변경 중...' : '비밀번호 변경'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
