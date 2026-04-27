import { useRef, useEffect, useState } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { useClassStore } from '../../stores/classStore';
import MessageBubble from './MessageBubble';
import AgentStatus from './AgentStatus';
import ChatInput from './ChatInput';
import OnboardingCards from '../onboarding/OnboardingCards';
import QuizCard from '../quiz/QuizCard';
import QuizResult from '../quiz/QuizResult';
import ErrorMessage from '../common/ErrorMessage';
import MaterialIndexPanel from '../material/MaterialIndexPanel';

export default function ChatArea() {
  const {
    messages,
    isStreaming,
    agentStatus,
    error,
    quizData,
    quizIndex,
    quizAnswers,
    lastQuizResultId,
    sendMessage,
    answerQuiz,
    quitQuiz,
    clearError,
  } = useChatStore();

  const { classes, selectedClassId, selectedMaterials } = useClassStore();
  const selectedClass = classes.find((c) => c.id === selectedClassId);

  const indexableMaterial =
    selectedClassId && selectedMaterials.length === 1 ? selectedMaterials[0] : null;
  const [indexPanelOpen, setIndexPanelOpen] = useState(true);

  useEffect(() => {
    if (indexableMaterial) setIndexPanelOpen(true);
  }, [indexableMaterial]);

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, quizIndex, agentStatus]);

  const lastMsg = messages.length > 0 ? messages[messages.length - 1] : null;
  const showQuickReplies =
    lastMsg?.role === 'assistant' &&
    !isStreaming &&
    !quizData &&
    (lastMsg.agent === 'tutor_agent' || lastMsg.agent === 'qna_agent');

  const quickReplies =
    lastMsg?.agent === 'tutor_agent'
      ? ['네', '아니오', '더 설명해 주세요', '퀴즈 내주세요']
      : ['더 자세히 알려주세요', '퀴즈 내주세요'];

  const showOnboarding = messages.length === 0 && !quizData && !isStreaming;
  const showQuizResult =
    quizData && quizIndex >= quizData.questions.length && quizAnswers.length > 0;
  const showQuizQuestion =
    quizData && quizIndex < quizData.questions.length;

  const handleSend = (text: string) => {
    const materialNames = selectedMaterials.length > 0 ? selectedMaterials.join('|') : undefined;
    sendMessage(text, selectedClassId || undefined, materialNames);
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex flex-1 flex-col overflow-hidden">
      {/* Context bar */}
      {selectedClass && (
        <div className="flex items-center gap-2 border-b border-warm-100 bg-primary-50/50 px-4 py-2">
          <span className="text-xs font-semibold text-primary-600">
            {selectedClass.name}
          </span>
          {selectedMaterials.length > 0 && (
            <>
              <span className="text-xs text-warm-400">/</span>
              <span className="text-xs font-medium text-primary-500 truncate max-w-xs">
                {selectedMaterials.length === 1
                  ? selectedMaterials[0]
                  : `${selectedMaterials.length}개 자료 선택`}
              </span>
            </>
          )}
          {indexableMaterial && !indexPanelOpen && (
            <button
              onClick={() => setIndexPanelOpen(true)}
              className="ml-auto rounded-md border border-primary-200 bg-white px-2 py-0.5 text-[11px] font-medium text-primary-600 hover:bg-primary-50 transition-colors"
              title="학습 인덱스 열기"
            >
              인덱스 보기
            </button>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {showOnboarding ? (
          <OnboardingCards
            onSend={handleSend}
            hasClasses={classes.length > 0}
            selectedClassId={selectedClassId}
          />
        ) : (
          <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {showQuickReplies && (
              <div className="flex flex-wrap gap-2 pl-11">
                {quickReplies.map((text) => (
                  <button
                    key={text}
                    onClick={() => handleSend(text)}
                    className="rounded-full border border-primary-300 bg-white px-3 py-1.5 text-xs font-medium text-primary-600 hover:bg-primary-50 active:scale-95 transition-all"
                  >
                    {text}
                  </button>
                ))}
              </div>
            )}

            {isStreaming && <AgentStatus status={agentStatus} />}

            {showQuizQuestion && (
              <QuizCard
                key={quizIndex}
                question={quizData!.questions[quizIndex]}
                index={quizIndex}
                total={quizData!.questions.length}
                onAnswer={answerQuiz}
                onQuit={quitQuiz}
              />
            )}

            {showQuizResult && (
              <QuizResult answers={quizAnswers} quizResultId={lastQuizResultId} onClose={quitQuiz} />
            )}

            {error && (
              <ErrorMessage
                message={error}
                onRetry={() => {
                  clearError();
                  const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
                  if (lastUserMsg) handleSend(lastUserMsg.content);
                }}
                onDismiss={clearError}
              />
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      {!showQuizQuestion && !showQuizResult && (
        <ChatInput
          onSend={handleSend}
          disabled={isStreaming}
          placeholder={
            !selectedClassId
              ? '사이드바에서 클래스를 선택해 주세요'
              : '메시지를 입력하세요'
          }
          inputDisabled={!selectedClassId}
        />
      )}
      </div>

      {/* Index panel (자료 1개 선택 시) */}
      {indexableMaterial && indexPanelOpen && selectedClassId && (
        <div className="hidden w-md shrink-0 md:block lg:w-lg">
          <MaterialIndexPanel
            classId={selectedClassId}
            materialName={indexableMaterial}
            onClose={() => setIndexPanelOpen(false)}
          />
        </div>
      )}
    </div>
  );
}
