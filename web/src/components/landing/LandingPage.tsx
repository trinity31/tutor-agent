import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';

const FEATURES = [
  {
    icon: '🎧',
    title: '원문 낭독',
    desc: 'PDF 교재를 문장 하이라이트와 함께 귀로 정독. 통근길에도 잠금화면으로.',
  },
  {
    icon: '🔁',
    title: '복습 루프',
    desc: '잊을 때쯤 다시 물어봐 주는 퀴즈로, 흐릿해진 기억을 다시 또렷하게.',
  },
  {
    icon: '💬',
    title: '1:1 과외',
    desc: '내 교재를 아는 AI에게 언제든 질문하고 개념을 확인.',
  },
];

export default function LandingPage() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);

  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) a.play();
    else a.pause();
  };

  return (
    <div className="min-h-dvh bg-warm-50 text-warm-900">
      {/* Header */}
      <header className="mx-auto flex max-w-3xl items-center justify-between px-5 py-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-500 text-lg font-bold text-white">
            T
          </div>
          <span className="font-bold">AI Tutor</span>
        </div>
        <Link
          to="/login"
          className="text-sm font-medium text-warm-600 hover:text-warm-900"
        >
          로그인
        </Link>
      </header>

      {/* Hero */}
      <main className="mx-auto max-w-3xl px-5">
        <section className="pt-10 pb-8 text-center sm:pt-16">
          <h1 className="text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl">
            교재를 귀로 정독하세요
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-warm-600 sm:text-lg">
            내 PDF 강의자료를 낭독으로 듣고, 잊을 때쯤 다시 물어봐 주는 학습
            루프. 방송대·사이버대·자격증 공부를 귀로 이어가세요.
          </p>
          <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Link
              to="/login?mode=register"
              className="w-full rounded-xl bg-primary-500 px-8 py-3.5 text-base font-semibold text-white transition-all hover:bg-primary-600 active:scale-[0.98] sm:w-auto"
            >
              무료로 시작하기
            </Link>
            <Link
              to="/login"
              className="w-full rounded-xl border-2 border-warm-200 px-8 py-3.5 text-base font-semibold text-warm-700 transition-all hover:bg-warm-100 active:scale-[0.98] sm:w-auto"
            >
              로그인
            </Link>
          </div>
        </section>

        {/* Narration demo */}
        <section className="mb-10 rounded-2xl bg-white p-6 shadow-sm">
          <div className="flex items-center gap-4">
            <button
              onClick={toggle}
              aria-label={playing ? '일시정지' : '낭독 미리듣기 재생'}
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary-500 text-xl text-white transition-all hover:bg-primary-600 active:scale-95"
            >
              {playing ? '⏸' : '▶'}
            </button>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-warm-900">
                낭독 미리듣기 · 「기억은 어떻게 오래 남는가」
              </p>
              <p className="mt-0.5 text-sm text-warm-500">
                실제 교재 낭독을 30초만 들어 보세요. 가입하면 이 자료가 바로
                준비돼 있어요.
              </p>
            </div>
          </div>
          <audio
            ref={audioRef}
            src="/sample-narration.mp3"
            preload="none"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
          />
        </section>

        {/* Features */}
        <section className="grid gap-4 pb-14 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl bg-white p-5 shadow-sm">
              <div className="text-2xl">{f.icon}</div>
              <h3 className="mt-3 font-bold text-warm-900">{f.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-warm-600">
                {f.desc}
              </p>
            </div>
          ))}
        </section>
      </main>

      <footer className="border-t border-warm-100 py-6 text-center text-xs text-warm-400">
        AI Tutor · 교재를 귀로
      </footer>
    </div>
  );
}
