import { useEffect, useState } from 'react';
import { pdfPageUrl } from '../../api/client';

interface Props {
  classId: string;
  materialName: string;
  /** 총 페이지 수 (매니페스트/섹션에서 계산) */
  numPages: number;
  /** 재생 위치에 해당하는 페이지 — 바뀌면 자동으로 넘어간다 */
  playbackPage: number;
  /** 페이지 단위 시크 ("이 페이지부터 듣기"). 페이지 정보 없는 구버전 매니페스트면 undefined */
  onListenFromPage?: (page: number) => void;
}

export default function PdfPageView({
  classId,
  materialName,
  numPages,
  playbackPage,
  onListenFromPage,
}: Props) {
  // 사용자가 직접 넘긴 페이지 — 재생 위치가 바뀌면 다시 재생 페이지를 따라간다
  const [manualPage, setManualPage] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  // 재생 위치가 움직이면 수동 탐색을 해제하고 재생 페이지로 복귀
  useEffect(() => {
    setManualPage(null);
  }, [playbackPage]);

  const page = Math.max(1, Math.min(manualPage ?? playbackPage, numPages || 1));

  // 페이지가 바뀌면 로딩 상태 초기화
  useEffect(() => {
    setLoading(true);
    setFailed(false);
  }, [page]);

  return (
    <div className="flex h-full flex-col">
      <div className="relative flex-1 overflow-y-auto bg-warm-100/60">
        {loading && !failed && (
          <p className="absolute inset-x-0 top-4 text-center text-sm text-warm-400">
            페이지를 불러오는 중...
          </p>
        )}
        {failed ? (
          <p className="p-4 text-sm text-error-500">페이지를 불러오지 못했습니다.</p>
        ) : (
          <img
            src={pdfPageUrl(classId, materialName, page)}
            alt={`${page}쪽`}
            className="mx-auto block w-full max-w-full"
            onLoad={() => setLoading(false)}
            onError={() => {
              setLoading(false);
              setFailed(true);
            }}
          />
        )}
      </div>

      {/* 페이지 내비게이션 */}
      <div className="flex items-center justify-between border-t border-warm-100 bg-white px-3 py-1.5">
        <button
          onClick={() => setManualPage(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="rounded-md px-2.5 py-1.5 text-xs text-warm-600 hover:bg-warm-100 disabled:opacity-30 transition-colors"
        >
          ◀ 이전
        </button>
        <div className="flex items-center gap-2">
          <span className="text-xs tabular-nums text-warm-500">
            {page} / {numPages || '–'}쪽
          </span>
          {onListenFromPage && manualPage !== null && manualPage !== playbackPage && (
            <button
              onClick={() => onListenFromPage(page)}
              className="rounded-full bg-primary-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-600 transition-colors"
            >
              이 페이지부터 듣기
            </button>
          )}
        </div>
        <button
          onClick={() => setManualPage(Math.min(numPages || page, page + 1))}
          disabled={numPages > 0 && page >= numPages}
          className="rounded-md px-2.5 py-1.5 text-xs text-warm-600 hover:bg-warm-100 disabled:opacity-30 transition-colors"
        >
          다음 ▶
        </button>
      </div>
    </div>
  );
}
