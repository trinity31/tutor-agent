import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { getMaterialIndex, regenerateMaterialIndex } from '../../api/client';
import AudioReader from '../audio/AudioReader';

interface Props {
  classId: string;
  materialName: string;
  onClose: () => void;
  /** 패널이 처음 열릴 때 보여줄 모드 (인덱스/듣기 카드에서 지정) */
  initialMode?: 'index' | 'audio';
}

export default function MaterialIndexPanel({
  classId,
  materialName,
  onClose,
  initialMode = 'index',
}: Props) {
  const [content, setContent] = useState('');
  const [status, setStatus] = useState<'loading' | 'ready' | 'not_ready' | 'error'>('loading');
  const [regenerating, setRegenerating] = useState(false);
  const [mode, setMode] = useState<'index' | 'audio'>(initialMode);

  useEffect(() => {
    setMode(initialMode);
  }, [classId, materialName, initialMode]);

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    setContent('');

    const load = async () => {
      try {
        const res = await getMaterialIndex(classId, materialName);
        if (cancelled) return;
        setContent(res.content);
        setStatus(res.status);
      } catch {
        if (!cancelled) setStatus('error');
      }
    };
    load();

    return () => {
      cancelled = true;
    };
  }, [classId, materialName]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const res = await regenerateMaterialIndex(classId, materialName);
      setContent(res.content);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
    setRegenerating(false);
  };

  return (
    <aside className="flex h-full w-full flex-col border-l border-warm-200 bg-warm-50/50">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-warm-100 bg-white px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wider text-warm-500">
            {mode === 'audio' ? '원문 낭독' : '학습 인덱스'}
          </p>
          <p className="truncate text-sm font-medium text-warm-800" title={materialName}>
            {materialName}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {mode === 'index' && status === 'ready' && (
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className="rounded-md px-2 py-1 text-xs font-medium text-warm-500 hover:bg-warm-100 hover:text-warm-700 disabled:opacity-40 transition-colors"
              title="인덱스 재생성"
            >
              {regenerating ? '재생성 중...' : '재생성'}
            </button>
          )}
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-warm-500 hover:bg-warm-100 hover:text-warm-700 transition-colors"
            title="닫기"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M4 4l8 8M12 4l-8 8"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
      </header>

      {/* Content */}
      {mode === 'audio' ? (
        <div className="flex-1 overflow-hidden">
          <AudioReader classId={classId} materialName={materialName} />
        </div>
      ) : (
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {status === 'loading' && (
          <p className="text-sm text-warm-400">인덱스를 불러오는 중...</p>
        )}
        {status === 'not_ready' && (
          <div className="space-y-3">
            <p className="text-sm text-warm-500">
              이 자료의 학습 인덱스가 아직 준비되지 않았습니다. 업로드 직후라면 잠시 후 다시
              시도하거나, 지금 바로 생성할 수 있습니다.
            </p>
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className="rounded-lg bg-primary-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-600 disabled:opacity-40 transition-colors"
            >
              {regenerating ? '생성 중...' : '인덱스 생성'}
            </button>
          </div>
        )}
        {status === 'error' && (
          <p className="text-sm text-error-500">
            인덱스를 불러오지 못했습니다. 새로고침 후 다시 시도해 주세요.
          </p>
        )}
        {status === 'ready' && (
          <div className="markdown-content prose prose-sm max-w-none text-warm-800">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}
      </div>
      )}
    </aside>
  );
}
