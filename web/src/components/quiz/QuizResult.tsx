import { useState } from 'react';
import type { QuizAnswer } from '../../stores/chatStore';

export default function QuizResult({
  answers,
  onClose,
}: {
  answers: QuizAnswer[];
  onClose: () => void;
}) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const correct = answers.filter((a) => a.correct).length;
  const total = answers.length;
  const pct = Math.round((correct / total) * 100);

  return (
    <div className="mx-auto max-w-xl px-4 py-6">
      {/* Score */}
      <div className="mb-6 rounded-2xl bg-white p-8 text-center shadow-sm">
        <div className="relative mx-auto mb-4 h-28 w-28">
          <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="#E8E8E3"
              strokeWidth="8"
            />
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke={pct >= 70 ? '#51CF66' : pct >= 40 ? '#FCC419' : '#FA5252'}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${(pct / 100) * 264} 264`}
              className="transition-all duration-1000"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold text-warm-900">{pct}%</span>
          </div>
        </div>
        <p className="text-lg font-bold text-warm-900">
          {total}문제 중 {correct}문제 정답
        </p>
        <p className="mt-1 text-sm text-warm-500">
          {pct >= 80
            ? '훌륭합니다! 완벽에 가까워요'
            : pct >= 60
              ? '잘하고 있어요! 조금만 더 복습하면 완벽'
              : '아직 갈 길이 있어요. 한번 더 도전해 보세요!'}
        </p>
      </div>

      {/* Review */}
      <div className="space-y-2">
        {answers.map((a, i) => (
          <div key={i} className="rounded-xl bg-white overflow-hidden shadow-sm">
            <button
              onClick={() =>
                setExpandedIdx(expandedIdx === i ? null : i)
              }
              className="flex w-full items-center gap-3 px-4 py-3 text-left"
            >
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold text-white ${
                  a.correct ? 'bg-success-500' : 'bg-error-500'
                }`}
              >
                {a.correct ? 'O' : 'X'}
              </span>
              <span className="flex-1 text-sm text-warm-800 truncate">
                Q{i + 1}. {a.question}
              </span>
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                className={`shrink-0 text-warm-400 transition-transform ${
                  expandedIdx === i ? 'rotate-180' : ''
                }`}
              >
                <path
                  d="M4 6l4 4 4-4"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </button>
            {expandedIdx === i && (
              <div className="border-t border-warm-100 px-4 py-3 text-sm">
                <p className="text-warm-600">
                  <span className="font-medium">내 답:</span> {a.selected}
                </p>
                <p className="text-warm-600">
                  <span className="font-medium">정답:</span> {a.answer}
                </p>
                {a.explanation && (
                  <p className="mt-2 rounded-lg bg-primary-50 px-3 py-2 text-warm-700">
                    {a.explanation}
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Close */}
      <button
        onClick={onClose}
        className="mt-6 w-full rounded-xl bg-primary-500 py-3 text-sm font-semibold text-white hover:bg-primary-600 active:scale-[0.98] transition-all"
      >
        대화로 돌아가기
      </button>
    </div>
  );
}
