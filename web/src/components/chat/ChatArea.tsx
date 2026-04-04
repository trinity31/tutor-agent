import { useRef, useEffect } from 'react';
import { useChatStore } from '../../stores/chatStore';
import MessageBubble from './MessageBubble';
import AgentStatus from './AgentStatus';
import ChatInput from './ChatInput';
import OnboardingCards from '../onboarding/OnboardingCards';
import QuizCard from '../quiz/QuizCard';
import QuizResult from '../quiz/QuizResult';
import ErrorMessage from '../common/ErrorMessage';

export default function ChatArea() {
  const {
    messages,
    isStreaming,
    agentStatus,
    error,
    quizData,
    quizIndex,
    quizAnswers,
    sendMessage,
    answerQuiz,
    quitQuiz,
    clearError,
  } = useChatStore();

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, quizIndex, agentStatus]);

  const showOnboarding = messages.length === 0 && !quizData && !isStreaming;
  const showQuizResult =
    quizData && quizIndex >= quizData.questions.length && quizAnswers.length > 0;
  const showQuizQuestion =
    quizData && quizIndex < quizData.questions.length;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {showOnboarding ? (
          <OnboardingCards onSend={sendMessage} />
        ) : (
          <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {/* Agent status */}
            {isStreaming && <AgentStatus status={agentStatus} />}

            {/* Quiz */}
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
              <QuizResult answers={quizAnswers} onClose={quitQuiz} />
            )}

            {/* Error */}
            {error && (
              <ErrorMessage
                message={error}
                onRetry={() => {
                  clearError();
                  const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
                  if (lastUserMsg) sendMessage(lastUserMsg.content);
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
        <ChatInput onSend={sendMessage} disabled={isStreaming} />
      )}
    </div>
  );
}
