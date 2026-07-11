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
  const [zoomed, setZoomed] = useState(false);

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
    <div className="relative h-full overflow-hidden bg-warm-100/60">
      {/* PDF 지면 (크롬 제거 — 전체를 콘텐츠에) */}
      <div className="h-full overflow-auto">
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
            className={`mx-auto block ${zoomed ? 'w-[165%] max-w-none' : 'w-full max-w-full'}`}
            onLoad={() => setLoading(false)}
            onError={() => {
              setLoading(false);
              setFailed(true);
            }}
          />
        )}
      </div>

      {/* "이 페이지부터 듣기" — 재생 페이지와 다를 때만 플로팅 */}
      {onListenFromPage && manualPage !== null && manualPage !== playbackPage && (
        <button
          onClick={() => onListenFromPage(page)}
          className="absolute left-1/2 top-3 -translate-x-1/2 rounded-full bg-primary-500 px-4 py-1.5 text-xs font-semibold text-white shadow-lg"
        >
          이 페이지부터 듣기
        </button>
      )}

      {/* 플로팅 페이지 네비 (하단 중앙) */}
      <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-0.5 rounded-full bg-warm-900/90 px-1.5 py-1 text-white backdrop-blur">
        <button
          onClick={() => setManualPage(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="grid h-8 w-9 place-items-center rounded-full text-sm disabled:opacity-30"
        >
          ‹
        </button>
        <span className="px-2 text-xs font-bold tabular-nums">
          {page} / {numPages || '–'}
        </span>
        <button
          onClick={() => setManualPage(Math.min(numPages || page, page + 1))}
          disabled={numPages > 0 && page >= numPages}
          className="grid h-8 w-9 place-items-center rounded-full text-sm disabled:opacity-30"
        >
          ›
        </button>
      </div>

      {/* 확대 토글 (우하단) */}
      <button
        onClick={() => setZoomed((z) => !z)}
        className="absolute bottom-4 right-3 grid h-9 w-9 place-items-center rounded-xl bg-warm-900/90 text-white backdrop-blur"
        title={zoomed ? '원래 크기' : '확대'}
      >
        {zoomed ? '⤡' : '⤢'}
      </button>
    </div>
  );
}
