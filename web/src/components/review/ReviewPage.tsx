import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useReviewStore } from '../../stores/reviewStore';
import { completeReviewQuiz, type QuizResultRow } from '../../api/client';
import type { QuizAnswer } from '../../stores/chatStore';
import QuizCard from '../quiz/QuizCard';
import QuizResult from '../quiz/QuizResult';

export default function ReviewPage() {
  const navigate = useNavigate();
  const { pending, loaded, load, removeCompleted } = useReviewStore();

  // 퀴즈 풀이 중 상태 (한 번에 한 퀴즈)
  const [active, setActive] = useState<QuizResultRow | null>(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<QuizAnswer[]>([]);
  const [done, setDone] = useState(false);

  useEffect(() => {
    load();
  }, [load]);

  const start = (quiz: QuizResultRow) => {
    setActive(quiz);
    setIndex(0);
    setAnswers([]);
    setDone(false);
  };

  const backToList = () => {
    setActive(null);
    setDone(false);
  };

  const handleAnswer = (selected: string) => {
    if (!active) return;
    const q = active.questions[index];
    const correctAnswer = q.answer || q.correct || '';
    const ans: QuizAnswer = {
      question: q.question,
      selected,
      answer: correctAnswer,
      correct: selected === correctAnswer,
      explanation: q.explanation,
    };
    const newAnswers = [...answers, ans];
    setAnswers(newAnswers);

    if (index + 1 >= active.questions.length) {
      // 마지막 문제 → 완료 처리(in_progress → completed)
      const score = newAnswers.filter((a) => a.correct).length;
      const wrongQuestions = active.questions.filter((_, i) => !newAnswers[i]?.correct);
      completeReviewQuiz(active.id, {
        answers: newAnswers,
        score,
        wrong_questions: wrongQuestions,
      }).catch(() => {});
      removeCompleted(active.id);
      setDone(true);
    } else {
      setIndex(index + 1);
    }
  };

  // --- 풀이 결과 화면 ---
  if (active && done) {
    return (
      <div className="min-h-dvh bg-warm-50">
        <Header title="복습 결과" onBack={backToList} />
        <div className="mx-auto max-w-xl px-4 py-6">
          <QuizResult answers={answers} quizResultId={active.id} onClose={backToList} />
          <button
            onClick={backToList}
            className="mt-6 w-full rounded-xl border border-warm-200 py-3 text-sm font-semibold text-warm-600 active:scale-[0.99] transition-transform"
          >
            복습 목록으로
          </button>
        </div>
      </div>
    );
  }

  // --- 퀴즈 풀이 화면 ---
  if (active) {
    return (
      <div className="min-h-dvh bg-warm-50">
        <Header title={active.quiz_title || active.material_name} onBack={backToList} />
        <div className="py-6">
          <QuizCard
            key={index}
            question={active.questions[index]}
            index={index}
            total={active.questions.length}
            onAnswer={handleAnswer}
            onQuit={backToList}
          />
        </div>
      </div>
    );
  }

  // --- 복습 목록 ---
  return (
    <div className="min-h-dvh bg-warm-50">
      <Header title="복습" onBack={() => navigate('/')} />
      <div className="mx-auto max-w-xl px-4 py-6">
        {!loaded ? (
          <p className="py-16 text-center text-sm text-warm-400">불러오는 중...</p>
        ) : pending.length === 0 ? (
          <div className="py-20 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-50 text-2xl">
              🎉
            </div>
            <p className="text-base font-bold text-warm-900">복습할 퀴즈가 없어요</p>
            <p className="mt-1.5 text-sm text-warm-500">
              학습을 완료하면 다음 날 복습 퀴즈가 여기에 생겨요.
            </p>
          </div>
        ) : (
          <>
            <p className="mb-4 text-sm text-warm-500">
              오늘 풀 복습 퀴즈 <b className="text-warm-800">{pending.length}</b>개
            </p>
            <div className="space-y-3">
              {pending.map((q) => (
                <button
                  key={q.id}
                  onClick={() => start(q)}
                  className="flex w-full items-center gap-3 rounded-2xl border border-warm-200 bg-white p-4 text-left transition-all active:scale-[0.99] hover:border-primary-300"
                >
                  <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary-50 text-lg">
                    🔁
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-[15px] font-bold text-warm-900">
                      {q.quiz_title || q.material_name}
                    </h3>
                    <p className="truncate text-xs text-warm-500">
                      {q.material_name} · {q.questions.length}문항
                    </p>
                  </div>
                  <span className="shrink-0 rounded-full bg-primary-500 px-3 py-1.5 text-xs font-bold text-white">
                    복습하기
                  </span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Header({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <header className="sticky top-0 z-10 flex items-center gap-2 border-b border-warm-100 bg-white px-3 py-3">
      <button
        onClick={onBack}
        className="grid h-9 w-9 place-items-center rounded-lg text-warm-600 hover:bg-warm-100"
        title="뒤로"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path d="M15 18l-6-6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <h1 className="truncate text-base font-bold text-warm-900">{title}</h1>
    </header>
  );
}
