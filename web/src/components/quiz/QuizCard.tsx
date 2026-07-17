import { useState } from 'react';
import { isCorrectAnswer, stripOptionPrefix, type QuizQuestion } from '../../stores/chatStore';

export default function QuizCard({
  question,
  index,
  total,
  onAnswer,
  onQuit,
}: {
  question: QuizQuestion;
  index: number;
  total: number;
  onAnswer: (selected: string) => void;
  onQuit: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [showResult, setShowResult] = useState(false);

  const correctAnswer = question.answer || question.correct || '';

  let options = question.options || [];
  if (!options.length && question.type?.toLowerCase().includes('o/x')) {
    options = ['O', 'X'];
  }

  const isCorrect = selected != null && isCorrectAnswer(selected, correctAnswer, options);

  const handleSelect = (opt: string) => {
    if (showResult) return;
    setSelected(opt);
    setShowResult(true);
  };

  const handleNext = () => {
    if (selected) onAnswer(selected);
  };

  return (
    <div className="mx-auto max-w-xl px-4">
      {/* Progress */}
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm font-semibold text-warm-600">
          Q{index + 1} / {total}
        </span>
        <button
          onClick={onQuit}
          className="rounded-lg px-3 py-1.5 text-xs font-medium text-warm-500 hover:bg-warm-100 hover:text-warm-700 transition-colors"
        >
          그만하기
        </button>
      </div>

      {/* Progress bar */}
      <div className="mb-6 h-2 overflow-hidden rounded-full bg-warm-100">
        <div
          className="h-full rounded-full bg-primary-500 transition-all duration-500"
          style={{ width: `${((index + 1) / total) * 100}%` }}
        />
      </div>

      {/* Question */}
      <div className="mb-6 rounded-2xl bg-white p-6 shadow-sm">
        <p className="text-lg font-semibold text-warm-900 leading-relaxed">
          {question.question}
        </p>
      </div>

      {/* Options */}
      <div className="space-y-3">
        {options.map((opt, i) => {
          let style = 'border-warm-200 bg-white hover:border-primary-400 hover:bg-primary-50';
          if (showResult && opt === selected) {
            style = isCorrect
              ? 'border-success-500 bg-success-400/10 text-success-500'
              : 'border-error-500 bg-error-500/10 text-error-500';
          } else if (showResult && isCorrectAnswer(opt, correctAnswer, options)) {
            style = 'border-success-500 bg-success-400/10 text-success-500';
          } else if (showResult) {
            style = 'border-warm-100 bg-warm-50 opacity-50';
          }

          return (
            <button
              key={i}
              onClick={() => handleSelect(opt)}
              disabled={showResult}
              className={`flex w-full items-center gap-3 rounded-xl border-2 px-5 py-4 text-left text-[15px] font-medium transition-all ${style}`}
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-warm-100 text-xs font-bold text-warm-600">
                {String.fromCharCode(65 + i)}
              </span>
              {stripOptionPrefix(opt)}
            </button>
          );
        })}
      </div>

      {/* Result feedback */}
      {showResult && (
        <>
          <div
            className={`mt-4 rounded-xl p-4 text-sm leading-relaxed ${
              isCorrect
                ? 'bg-success-400/10 text-success-500'
                : 'bg-error-500/10 text-error-500'
            }`}
          >
            <p className="font-semibold mb-1">
              {isCorrect ? '정답입니다!' : `오답! 정답: ${stripOptionPrefix(correctAnswer)}`}
            </p>
            {question.explanation && (
              <p className="text-warm-700">{question.explanation}</p>
            )}
          </div>
          <button
            onClick={handleNext}
            className="mt-4 w-full rounded-xl bg-primary-500 py-3 text-sm font-semibold text-white hover:bg-primary-600 active:scale-[0.98] transition-all"
          >
            다음 문제
          </button>
        </>
      )}
    </div>
  );
}
