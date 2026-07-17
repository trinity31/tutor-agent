import { useEffect, useState } from 'react';
import { scheduleQuizRetry } from '../../api/client';
import { track } from '../../lib/analytics';
import { isCorrectAnswer, type QuizAnswer } from '../../stores/chatStore';

/** 저장된 correct가 옛 채점 로직(접두어 불일치)으로 틀렸을 수 있어 다시 확인한다.
 *  false→true로만 교정하므로(정답인데 오답 처리된 경우), 오답을 정답으로 뒤집지 않는다. */
const isAnswerCorrect = (a: QuizAnswer): boolean =>
  a.correct || isCorrectAnswer(a.selected, a.answer);

export default function QuizResult({
  answers,
  quizResultId,
  onClose,
}: {
  answers: QuizAnswer[];
  quizResultId: string | null;
  onClose: () => void;
}) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [scheduledMsg, setScheduledMsg] = useState('');
  const [scheduling, setScheduling] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState<'wrong_only' | 'full' | null>(null);
  const [dateInput, setDateInput] = useState('');

  const correct = answers.filter(isAnswerCorrect).length;
  const total = answers.length;
  const pct = Math.round((correct / total) * 100);
  const wrongCount = total - correct;

  // 채점 결과 화면 진입 = 퀴즈 완료 (마운트 시 1회)
  useEffect(() => {
    track('quiz_complete', { correct, total, pct });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSchedule = async (date: string, mode: string) => {
    if (!quizResultId || !date) return;
    setScheduling(true);
    try {
      const res = await scheduleQuizRetry(quizResultId, {
        scheduled_date: date,
        schedule_mode: mode,
      });
      setScheduledMsg(`${res.scheduled_date}에 재시험이 예약되었습니다.`);
      setShowDatePicker(null);
    } catch {
      setScheduledMsg('예약에 실패했습니다.');
    } finally {
      setScheduling(false);
    }
  };

  const tomorrow = () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().split('T')[0];
  };

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
        {answers.map((a, i) => {
          const ok = isAnswerCorrect(a);
          return (
          <div key={i} className="rounded-xl bg-white overflow-hidden shadow-sm">
            <button
              onClick={() =>
                setExpandedIdx(expandedIdx === i ? null : i)
              }
              className="flex w-full items-center gap-3 px-4 py-3 text-left"
            >
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold text-white ${
                  ok ? 'bg-success-500' : 'bg-error-500'
                }`}
              >
                {ok ? 'O' : 'X'}
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
          );
        })}
      </div>

      {/* Scheduling */}
      {quizResultId && !scheduledMsg && (
        <div className="mt-6 space-y-2">
          <p className="mb-1 text-center text-xs text-warm-400">
            예약일에 복습 퀴즈를 만들어 이메일로 보내드려요.
          </p>
          {wrongCount > 0 && (
            <button
              onClick={() => setShowDatePicker('wrong_only')}
              disabled={scheduling}
              className="w-full rounded-xl border-2 border-primary-500 py-3 text-sm font-semibold text-primary-500 hover:bg-primary-50 active:scale-[0.98] transition-all disabled:opacity-50"
            >
              날짜 지정 (틀린 문제만)
            </button>
          )}
          <button
            onClick={() => setShowDatePicker('full')}
            disabled={scheduling}
            className="w-full rounded-xl border-2 border-warm-300 py-3 text-sm font-semibold text-warm-600 hover:bg-warm-50 active:scale-[0.98] transition-all disabled:opacity-50"
          >
            날짜 지정 (전체 재시험)
          </button>
        </div>
      )}

      {/* Date Picker */}
      {showDatePicker && (
        <div className="mt-3 rounded-xl bg-white p-4 shadow-sm space-y-3">
          <p className="text-sm font-medium text-warm-700">
            {showDatePicker === 'wrong_only' ? '틀린 문제 재시험' : '전체 재시험'} 날짜
          </p>
          <input
            type="date"
            value={dateInput}
            onChange={(e) => setDateInput(e.target.value)}
            min={tomorrow()}
            className="w-full rounded-lg border border-warm-200 px-3 py-2 text-sm"
          />
          <div className="flex gap-2">
            <button
              onClick={() => {
                setShowDatePicker(null);
                setDateInput('');
              }}
              className="flex-1 rounded-lg border border-warm-200 py-2 text-sm text-warm-600"
            >
              취소
            </button>
            <button
              onClick={() => handleSchedule(dateInput, showDatePicker)}
              disabled={!dateInput || scheduling}
              className="flex-1 rounded-lg bg-primary-500 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              예약
            </button>
          </div>
        </div>
      )}

      {/* Scheduled confirmation */}
      {scheduledMsg && (
        <div className="mt-4 rounded-xl bg-success-50 px-4 py-3 text-sm text-success-700">
          {scheduledMsg}
        </div>
      )}

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
