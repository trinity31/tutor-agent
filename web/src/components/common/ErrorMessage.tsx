export default function ErrorMessage({
  message,
  onRetry,
  onDismiss,
}: {
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
}) {
  return (
    <div className="rounded-xl border border-error-400/20 bg-error-500/5 px-4 py-3">
      <p className="text-sm text-error-500">{message}</p>
      <div className="mt-2 flex gap-2">
        {onRetry && (
          <button
            onClick={onRetry}
            className="rounded-lg bg-error-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-error-400 transition-colors"
          >
            다시 시도
          </button>
        )}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-warm-500 hover:text-warm-700 transition-colors"
          >
            닫기
          </button>
        )}
      </div>
    </div>
  );
}
