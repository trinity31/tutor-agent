import { useState, useRef, useEffect } from 'react';

export default function ChatInput({
  onSend,
  disabled,
  placeholder = '메시지를 입력하세요',
  inputDisabled = false,
  preparing = false,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
  placeholder?: string;
  inputDisabled?: boolean;
  /** 업로드·인덱싱 중 — 대화 비활성화 + '준비중' 표시 */
  preparing?: boolean;
}) {
  const isDisabled = disabled || inputDisabled || preparing;
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!disabled) inputRef.current?.focus();
  }, [disabled]);

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || isDisabled) return;
    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  if (preparing) {
    return (
      <div className="border-t border-warm-100 bg-white px-4 py-4">
        <div className="mx-auto flex max-w-3xl items-center justify-center gap-2 text-sm font-medium text-warm-500">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-warm-300 border-t-primary-500" />
          자료 준비 중… 인덱싱이 끝나면 대화할 수 있어요
        </div>
      </div>
    );
  }

  return (
    <div className="border-t border-warm-100 bg-white px-4 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isDisabled}
          rows={1}
          className="flex-1 resize-none rounded-xl border border-warm-200 bg-warm-50 px-4 py-3 text-[15px] text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-100 disabled:opacity-50 transition-all"
          style={{ maxHeight: '120px' }}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 120) + 'px';
          }}
        />
        <button
          onClick={handleSubmit}
          disabled={isDisabled || !text.trim()}
          className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-xl bg-primary-500 text-white hover:bg-primary-600 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path
              d="M3.5 10h13M11 4.5L16.5 10 11 15.5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}
