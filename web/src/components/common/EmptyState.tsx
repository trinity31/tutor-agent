export default function EmptyState({
  icon,
  title,
  description,
  action,
  onAction,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-warm-100 text-warm-400">
        {icon}
      </div>
      <h3 className="mb-1 text-base font-semibold text-warm-800">{title}</h3>
      <p className="mb-4 max-w-xs text-sm text-warm-500">{description}</p>
      {action && onAction && (
        <button
          onClick={onAction}
          className="rounded-xl bg-primary-500 px-6 py-2.5 text-sm font-semibold text-white hover:bg-primary-600 active:scale-[0.98] transition-all"
        >
          {action}
        </button>
      )}
    </div>
  );
}
