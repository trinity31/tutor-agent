import ReactMarkdown from 'react-markdown';
import type { Message } from '../../stores/chatStore';

const AGENT_COLORS: Record<string, string> = {
  search_agent: 'bg-primary-50 text-primary-700',
  quiz_agent: 'bg-accent-300/20 text-accent-500',
  qna_agent: 'bg-success-400/20 text-success-500',
  tutor_agent: 'bg-primary-100 text-primary-700',
};

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-primary-500 px-4 py-3 text-[15px] text-white leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start gap-3">
      {/* AI avatar */}
      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-500 text-sm font-bold text-white">
        T
      </div>
      <div className="max-w-[80%]">
        {message.agentLabel && (
          <span
            className={`mb-1 inline-block rounded-md px-2 py-0.5 text-xs font-medium ${
              AGENT_COLORS[message.agent || ''] || 'bg-warm-100 text-warm-600'
            }`}
          >
            {message.agentLabel}
          </span>
        )}
        <div className="rounded-2xl rounded-tl-md bg-white px-4 py-3 text-[15px] text-warm-800 shadow-sm leading-relaxed">
          {message.type === 'quiz' ? (
            <p className="font-medium text-primary-600">{message.content}</p>
          ) : (
            <div className="markdown-content">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
