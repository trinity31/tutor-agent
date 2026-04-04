export default function AgentStatus({
  status,
}: {
  status: { agent: string; label: string } | null;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-100">
        <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary-500" />
      </div>
      <span className="text-sm text-warm-600">
        {status ? (
          <>
            <span className="font-medium text-primary-600">{status.label}</span>{' '}
            에이전트 답변 중...
          </>
        ) : (
          '잠시만 기다려 주세요...'
        )}
      </span>
    </div>
  );
}
