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
  /** 현재 낭독 중인 문단의 원본 영역 [x0,y0,x1,y1] 정규화(0~1) + 그 페이지 */
  highlight?: { page: number; box: number[] };
  /** "이 페이지에서 질문" — 페이지 번호·질문을 채팅으로 보낸다 */
  onAskPage?: (page: number, question: string) => void;
}

export default function PdfPageView({
  classId,
  materialName,
  numPages,
  playbackPage,
  onListenFromPage,
  highlight,
  onAskPage,
}: Props) {
  // 사용자가 직접 넘긴 페이지 — 재생 위치가 바뀌면 다시 재생 페이지를 따라간다
  const [manualPage, setManualPage] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [zoomed, setZoomed] = useState(false);
  const [asking, setAsking] = useState(false);
  const [question, setQuestion] = useState('');

  // 재생 위치가 움직이면 수동 탐색을 해제하고 재생 페이지로 복귀
  useEffect(() => {
    setManualPage(null);
  }, [playbackPage]);

  const page = Math.max(1, Math.min(manualPage ?? playbackPage, numPages || 1));

  const submitQuestion = () => {
    const q = question.trim();
    if (!q || !onAskPage) return;
    onAskPage(page, q);
    setQuestion('');
    setAsking(false);
  };

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
          <div
            className={`relative mx-auto block ${zoomed ? 'w-[165%] max-w-none' : 'w-full max-w-full'}`}
          >
            <img
              src={pdfPageUrl(classId, materialName, page)}
              alt={`${page}쪽`}
              className="block w-full"
              onLoad={() => setLoading(false)}
              onError={() => {
                setLoading(false);
                setFailed(true);
              }}
            />
            {/* 현재 낭독 문단 하이라이트 — 표시 페이지가 재생 페이지와 같을 때만 */}
            {highlight && highlight.page === page && highlight.box?.length === 4 && (
              <div
                className="pointer-events-none absolute rounded-sm bg-highlight/45 shadow-[0_0_0_1.5px_rgba(240,160,32,0.55)] transition-all duration-300"
                style={{
                  left: `${highlight.box[0] * 100}%`,
                  top: `${highlight.box[1] * 100}%`,
                  width: `${(highlight.box[2] - highlight.box[0]) * 100}%`,
                  height: `${(highlight.box[3] - highlight.box[1]) * 100}%`,
                }}
              />
            )}
          </div>
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

      {/* "이 페이지에서 질문" — 우상단 플로팅 → 하단 입력바 */}
      {onAskPage && !asking && (
        <button
          onClick={() => setAsking(true)}
          className="absolute right-3 top-3 flex items-center gap-1 rounded-full bg-warm-900/85 px-3.5 py-1.5 text-xs font-semibold text-white shadow-lg backdrop-blur active:scale-95"
        >
          💬 이 페이지에서 질문
        </button>
      )}
      {onAskPage && asking && (
        <div className="absolute inset-x-0 bottom-0 z-30 flex items-center gap-2 border-t border-warm-200 bg-white p-2.5 shadow-[0_-8px_20px_-12px_rgba(0,0,0,0.25)]">
          <input
            autoFocus
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submitQuestion()}
            placeholder={`${page}페이지에 대해 질문하기`}
            className="min-w-0 flex-1 rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-sm text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none"
          />
          <button
            onClick={submitQuestion}
            disabled={!question.trim()}
            className="shrink-0 rounded-xl bg-primary-500 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-40"
          >
            질문
          </button>
          <button
            onClick={() => {
              setAsking(false);
              setQuestion('');
            }}
            className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-warm-500 hover:bg-warm-100"
            title="닫기"
          >
            ✕
          </button>
        </div>
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
