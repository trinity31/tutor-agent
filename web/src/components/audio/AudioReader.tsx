import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAudioStore, audioPositionKey } from '../../stores/audioStore';
import { track } from '../../lib/analytics';

// pdf.js 번들이 커서 PDF 뷰를 열 때만 로드
const PdfPageView = lazy(() => import('./PdfPageView'));

const VIEW_KEY = 'tutor-audio-view';
const FONT_KEY = 'tutor-audio-font';
const FONT_SIZES = [14, 16, 18, 20, 22];
// 배속 프리셋 (슬라이더 대신 시트에서 칩으로 선택)
const RATE_PRESETS = [0.8, 1, 1.25, 1.5, 2];
const fmtRate = (r: number) => (Number.isInteger(r) ? r.toFixed(1) : String(r));

interface Props {
  classId: string;
  materialName: string;
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function AudioReader({ classId, materialName }: Props) {
  const {
    sections,
    voices,
    section,
    voice,
    status,
    manifest,
    fileUrl,
    currentChunk,
    rate,
    error,
    init,
    selectSection,
    setVoice,
    setRate,
    setCurrentChunk,
    requestGeneration,
  } = useAudioStore();

  const audioRef = useRef<HTMLAudioElement>(null);
  const chunkRefs = useRef<(HTMLParagraphElement | null)[]>([]);
  // 섹션 자동 이어듣기: 다음 섹션 오디오가 로드되면 바로 재생
  const autoAdvanceRef = useRef(false);
  // 다른 섹션의 특정 페이지로 "이 페이지부터 듣기": 섹션 전환 후 로드되면 그 페이지로 시크
  const pendingSeekPageRef = useRef<number | null>(null);

  // 청취 계측(T9): 재생 시작 시점·컨텍스트를 스냅샷해 두고
  // 일시정지·종료·섹션전환·언마운트에서 구간(초)을 합산 전송한다.
  const playStartRef = useRef<number | null>(null);
  const playCtxRef = useRef<Record<string, string> | null>(null);
  const listenStartFiredRef = useRef(false);

  const flushListen = useCallback(() => {
    if (playStartRef.current == null || !playCtxRef.current) return;
    const seconds = Math.round((Date.now() - playStartRef.current) / 1000);
    const ctx = playCtxRef.current;
    playStartRef.current = null;
    playCtxRef.current = null;
    if (seconds >= 1) track('listen_session', { ...ctx, seconds });
  }, []);

  // Media Session(T11): 잠금화면 진행바 동기화
  const updatePositionState = useCallback(() => {
    if (!('mediaSession' in navigator) || !navigator.mediaSession.setPositionState) return;
    const audio = audioRef.current;
    if (!audio || !Number.isFinite(audio.duration) || audio.duration <= 0) return;
    navigator.mediaSession.setPositionState({
      duration: audio.duration,
      position: Math.min(audio.currentTime, audio.duration),
      playbackRate: audio.playbackRate || 1,
    });
  }, []);

  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [viewMode, setViewMode] = useState<'text' | 'pdf'>(
    () => (localStorage.getItem(VIEW_KEY) === 'pdf' ? 'pdf' : 'text'),
  );

  const toggleView = () => {
    const next = viewMode === 'pdf' ? 'text' : 'pdf';
    localStorage.setItem(VIEW_KEY, next);
    setViewMode(next);
  };

  // 낭독 텍스트 글자 크기 (A− / A+)
  const [fontSize, setFontSize] = useState(() => {
    const saved = Number(localStorage.getItem(FONT_KEY));
    return FONT_SIZES.includes(saved) ? saved : 14;
  });
  const stepFont = (dir: 1 | -1) => {
    const idx = FONT_SIZES.indexOf(fontSize) + dir;
    const next = FONT_SIZES[Math.min(Math.max(idx, 0), FONT_SIZES.length - 1)];
    localStorage.setItem(FONT_KEY, String(next));
    setFontSize(next);
  };

  useEffect(() => {
    init(classId, materialName);
    return () => useAudioStore.getState().reset();
  }, [classId, materialName, init]);

  // 자료·섹션 전환 또는 언마운트 시: 진행 중이던 청취 구간을 집계하고
  // listen_start 재발화가 가능하도록 플래그를 리셋한다.
  useEffect(() => {
    return () => {
      flushListen();
      listenStartFiredRef.current = false;
    };
  }, [classId, materialName, section, flushListen]);

  // Media Session(T11): 잠금화면·알림센터에 제목·컨트롤 노출. 재생 준비되면 설정.
  useEffect(() => {
    if (!('mediaSession' in navigator) || status !== 'ready') return;
    const ms = navigator.mediaSession;
    const sectionTitle = sections.find((s) => s.section === section)?.title ?? '';
    ms.metadata = new MediaMetadata({
      // 잠금화면 제목엔 자료명을 우선 노출하고 섹션을 뒤에 붙인다
      title: sectionTitle ? `${materialName} · ${sectionTitle}` : materialName,
      artist: 'TutorAgent',
      album: materialName,
      artwork: [{ src: '/pwa-512.png', sizes: '512x512', type: 'image/png' }],
    });
    const skip = (delta: number) => {
      const a = audioRef.current;
      if (!a) return;
      a.currentTime = Math.max(0, Math.min(a.duration || 0, a.currentTime + delta));
      updatePositionState();
    };
    ms.setActionHandler('play', () => audioRef.current?.play());
    ms.setActionHandler('pause', () => audioRef.current?.pause());
    ms.setActionHandler('seekbackward', (d) => skip(-(d.seekOffset || 15)));
    ms.setActionHandler('seekforward', (d) => skip(d.seekOffset || 15));
    ms.setActionHandler('seekto', (d) => {
      const a = audioRef.current;
      if (a && d.seekTime != null) {
        a.currentTime = d.seekTime;
        updatePositionState();
      }
    });
    return () => {
      // 섹션·자료 교체 시 잔존 핸들러 제거
      (['play', 'pause', 'seekbackward', 'seekforward', 'seekto'] as const).forEach((a) =>
        ms.setActionHandler(a, null),
      );
    };
  }, [status, section, materialName, sections, updatePositionState]);

  const posKey =
    section && audioPositionKey(classId, materialName, section, voice);

  // 재생 준비 완료 시: 배속 적용 + 저장된 위치에서 이어듣기
  const handleLoadedMetadata = () => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.playbackRate = rate;
    setDuration(audio.duration);
    // 다른 섹션에서 "이 페이지부터 듣기"로 넘어온 경우: 저장 위치 대신 요청 페이지로
    if (pendingSeekPageRef.current != null) {
      const page = pendingSeekPageRef.current;
      pendingSeekPageRef.current = null;
      const target =
        manifest?.chunks.find((c) => c.page === page) ??
        manifest?.chunks.find((c) => (c.page ?? 0) >= page) ??
        manifest?.chunks[0];
      audio.currentTime = target ? target.start : 0;
      audio.play();
      updatePositionState();
      return;
    }
    const saved = posKey ? Number(localStorage.getItem(posKey)) : 0;
    if (saved > 0 && saved < audio.duration - 1) {
      audio.currentTime = saved;
    }
    if (autoAdvanceRef.current) {
      autoAdvanceRef.current = false;
      audio.play();
    }
    updatePositionState();
  };

  // 배속 변경을 재생 중인 오디오에 반영
  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = rate;
    updatePositionState();
  }, [rate, updatePositionState]);

  const handleTimeUpdate = () => {
    const audio = audioRef.current;
    if (!audio || !manifest) return;
    const t = audio.currentTime;
    setCurrentTime(t);
    if (posKey) localStorage.setItem(posKey, String(t));
    const idx = manifest.chunks.findIndex((c) => t >= c.start && t < c.end);
    if (idx >= 0) setCurrentChunk(idx);
    updatePositionState();
  };

  // 현재 청크 하이라이트 따라 자동 스크롤
  useEffect(() => {
    if (currentChunk >= 0 && playing) {
      chunkRefs.current[currentChunk]?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [currentChunk, playing]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      audio.play();
    } else {
      audio.pause();
    }
  }, []);

  const seekTo = (time: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = time;
    if (audio.paused) audio.play();
  };

  // 문장 클릭 → 청크 내 글자 비율로 시점을 추정해 시크
  const seekToSentence = (chunkIdx: number, sentIdx: number) => {
    if (!manifest) return;
    const chunk = manifest.chunks[chunkIdx];
    const totalChars = chunk.sentences.reduce((n, s) => n + s.length, 0);
    const charsBefore = chunk.sentences
      .slice(0, sentIdx)
      .reduce((n, s) => n + s.length, 0);
    const offset =
      totalChars > 0
        ? (charsBefore / totalChars) * (chunk.end - chunk.start)
        : 0;
    seekTo(chunk.start + offset);
  };

  const handleEnded = () => {
    setPlaying(false);
    flushListen();
    track('listen_complete_section', {
      class_id: classId,
      material_name: materialName,
      section: section ?? '',
      voice,
    });
    if (posKey) localStorage.removeItem(posKey);
    setCurrentChunk(-1);
    // 다음 섹션이 있으면 자동으로 이어듣기 (미생성이면 생성 후 이어짐)
    if (useAudioStore.getState().advanceToNext()) {
      autoAdvanceRef.current = true;
    }
  };

  const generating = status === 'loading' || status === 'pending' || status === 'generating';

  // PDF 뷰: 재생 위치의 페이지 (구버전 매니페스트는 페이지 정보 없음)
  const hasPages = manifest?.chunks.some((c) => c.page != null) ?? false;
  const playbackPage =
    manifest?.chunks[Math.max(currentChunk, 0)]?.page ?? manifest?.chunks[0]?.page ?? 1;
  // 총 페이지 수 — 마지막 섹션 ID("p25-31")의 끝 페이지에서 계산
  const numPages =
    sections.reduce((max, s) => {
      const m = s.section.match(/-(\d+)$/);
      return m ? Math.max(max, Number(m[1])) : max;
    }, 0) || 1;

  // 섹션 ID("p9-16")에서 페이지 범위 추출
  const sectionPageRange = (id: string): [number, number] => {
    const m = id.match(/(\d+)\s*-\s*(\d+)/);
    return m ? [Number(m[1]), Number(m[2])] : [0, 0];
  };

  // "이 페이지부터 듣기" — 페이지가 현재 섹션 밖이면 해당 섹션으로 전환 후 시크
  const listenFromPage = (page: number) => {
    // 1) 현재 섹션 안의 페이지면 바로 시크
    const here = manifest?.chunks.find((c) => c.page === page);
    if (here) {
      seekTo(here.start);
      return;
    }
    // 2) 다른 섹션이면 그 섹션으로 전환 → 로드되면 handleLoadedMetadata에서 시크
    const targetSection = sections.find((s) => {
      const [st, en] = sectionPageRange(s.section);
      return page >= st && page <= en;
    });
    if (targetSection && targetSection.section !== section) {
      pendingSeekPageRef.current = page;
      selectSection(targetSection.section);
      return;
    }
    // 3) 폴백: 현재 매니페스트에서 페이지 이상인 첫 청크
    const fallback =
      manifest?.chunks.find((c) => (c.page ?? 0) >= page) ?? manifest?.chunks[0];
    if (fallback) seekTo(fallback.start);
  };

  const skipBy = (delta: number) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = Math.max(0, Math.min(a.duration || 0, a.currentTime + delta));
    updatePositionState();
  };

  // 현재 청크 안에서 재생 시각의 글자 비율로 현재 문장을 추정 (비용 0)
  const currentSentIdx = useMemo(() => {
    if (!manifest || currentChunk < 0) return -1;
    const chunk = manifest.chunks[currentChunk];
    if (!chunk?.sentences.length) return -1;
    const span = chunk.end - chunk.start;
    const ratio = span > 0 ? Math.min(1, Math.max(0, (currentTime - chunk.start) / span)) : 0;
    const total = chunk.sentences.reduce((n, s) => n + s.length, 0) || 1;
    let acc = 0;
    for (let i = 0; i < chunk.sentences.length; i++) {
      acc += chunk.sentences[i].length;
      if (ratio <= acc / total) return i;
    }
    return chunk.sentences.length - 1;
  }, [manifest, currentChunk, currentTime]);

  // 배속 칩 활성 표시용 — 현재 배속에 가장 가까운 프리셋
  const activePreset = RATE_PRESETS.reduce(
    (a, b) => (Math.abs(b - rate) < Math.abs(a - rate) ? b : a),
    RATE_PRESETS[0],
  );

  return (
    <div className="relative flex h-full flex-col bg-white">
      {/* 상단: 텍스트 / 원본 세그먼트 (설정은 하단 배속 칩 → 시트로 이동) */}
      <div className="flex items-center justify-center border-b border-warm-100 bg-white px-4 py-2">
        <div className="flex rounded-lg bg-warm-100 p-0.5">
          <button
            onClick={() => viewMode === 'pdf' && toggleView()}
            className={`rounded-md px-5 py-1.5 text-sm font-bold transition-colors ${
              viewMode === 'text' ? 'bg-white text-warm-900 shadow-sm' : 'text-warm-500'
            }`}
          >
            텍스트
          </button>
          <button
            onClick={() => viewMode === 'text' && toggleView()}
            className={`rounded-md px-5 py-1.5 text-sm font-bold transition-colors ${
              viewMode === 'pdf' ? 'bg-white text-warm-900 shadow-sm' : 'text-warm-500'
            }`}
          >
            원본
          </button>
        </div>
      </div>

      {/* 본문: PDF 원본 (페이지 자동 넘김) 또는 낭독 텍스트 (청크 하이라이트) */}
      {status === 'ready' && viewMode === 'pdf' ? (
        <div className="flex-1 overflow-hidden">
          <Suspense
            fallback={<p className="p-4 text-sm text-warm-400">PDF 뷰어를 불러오는 중...</p>}
          >
            <PdfPageView
              classId={classId}
              materialName={materialName}
              numPages={numPages}
              playbackPage={playbackPage}
              onListenFromPage={hasPages ? listenFromPage : undefined}
              highlight={
                currentChunk >= 0 && manifest?.chunks[currentChunk]?.bbox
                  ? { page: playbackPage, box: manifest.chunks[currentChunk].bbox as number[] }
                  : undefined
              }
            />
          </Suspense>
        </div>
      ) : (
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {generating && (
          <div className="space-y-2">
            <p className="text-sm text-warm-500">
              {status === 'generating' || status === 'pending'
                ? '오디오를 생성하고 있습니다... (섹션당 1~2분 정도 걸립니다)'
                : '오디오 정보를 불러오는 중...'}
            </p>
            <div className="h-1 w-full overflow-hidden rounded bg-warm-100">
              <div className="h-full w-1/3 animate-pulse rounded bg-primary-400" />
            </div>
          </div>
        )}
        {(status === 'failed' || status === 'error') && (
          <div className="space-y-3">
            <p className="text-sm text-error-500">{error}</p>
            <button
              onClick={requestGeneration}
              className="rounded-lg bg-primary-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-600 transition-colors"
            >
              다시 시도
            </button>
          </div>
        )}
        {status === 'ready' && manifest && (
          <div className="space-y-4" style={{ fontSize, lineHeight: 1.85 }}>
            {manifest.chunks.map((chunk, ci) => (
              <p
                key={ci}
                ref={(el) => {
                  chunkRefs.current[ci] = el;
                }}
                className="text-warm-800"
              >
                {chunk.sentences.map((sent, si) => {
                  const on = ci === currentChunk && si === currentSentIdx;
                  return (
                    <span
                      key={si}
                      onClick={() => seekToSentence(ci, si)}
                      className={`cursor-pointer rounded px-0.5 transition-colors ${
                        on ? 'bg-highlight text-warm-900' : 'hover:bg-warm-100'
                      }`}
                    >
                      {sent}{' '}
                    </span>
                  );
                })}
              </p>
            ))}
          </div>
        )}
      </div>
      )}

      {/* 미니 플레이어 — 진행바 + −15/재생/+15 + 배속칩(시트) */}
      {status === 'ready' && fileUrl && (
        <div className="flex-none border-t border-warm-100 bg-white px-4 pt-2.5 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
          <audio
            ref={audioRef}
            src={fileUrl}
            preload="metadata"
            onLoadedMetadata={handleLoadedMetadata}
            onTimeUpdate={handleTimeUpdate}
            onPlay={() => {
              setPlaying(true);
              if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'playing';
              updatePositionState();
              if (playStartRef.current == null) {
                playStartRef.current = Date.now();
                playCtxRef.current = {
                  class_id: classId,
                  material_name: materialName,
                  section: section ?? '',
                  voice,
                };
              }
              if (!listenStartFiredRef.current) {
                listenStartFiredRef.current = true;
                track('listen_start', {
                  class_id: classId,
                  material_name: materialName,
                  section: section ?? '',
                  voice,
                });
              }
            }}
            onPause={() => {
              setPlaying(false);
              if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'paused';
              flushListen();
            }}
            onEnded={handleEnded}
          />
          <input
            type="range"
            min={0}
            max={duration || manifest?.duration || 0}
            step={0.1}
            value={currentTime}
            onChange={(e) => seekTo(Number(e.target.value))}
            className="mb-2.5 h-1.5 w-full accent-primary-500"
          />
          <div className="flex items-center gap-2.5">
            <span className="w-9 text-xs tabular-nums text-warm-400">{formatTime(currentTime)}</span>
            <button
              onClick={() => skipBy(-15)}
              className="flex h-11 w-11 flex-col items-center justify-center rounded-xl border border-warm-200 text-[10px] font-bold leading-none text-warm-600 hover:bg-warm-50 transition-colors"
              title="15초 뒤로"
            >
              <span className="text-base leading-none">↺</span>15
            </button>
            <button
              onClick={togglePlay}
              className="grid h-14 w-14 place-items-center rounded-full bg-primary-500 text-lg text-white shadow-[0_6px_14px_-4px_rgba(18,184,134,0.55)]"
              title={playing ? '일시정지' : '재생'}
            >
              {playing ? '❚❚' : '▶'}
            </button>
            <button
              onClick={() => skipBy(15)}
              className="flex h-11 w-11 flex-col items-center justify-center rounded-xl border border-warm-200 text-[10px] font-bold leading-none text-warm-600 hover:bg-warm-50 transition-colors"
              title="15초 앞으로"
            >
              <span className="text-base leading-none">↻</span>15
            </button>
            <button
              onClick={() => setSheetOpen(true)}
              className="ml-auto flex h-9 items-center gap-1 rounded-[10px] bg-primary-100 px-3 text-[13px] font-extrabold text-primary-600"
              title="배속·음성·설정"
            >
              {fmtRate(rate)}× <span className="text-[10px] text-warm-400">▲</span>
            </button>
          </div>
        </div>
      )}

      {/* 바텀시트: 배속·음성·범위·글자 크기 */}
      {sheetOpen && status === 'ready' && (
        <>
          <div
            className="absolute inset-0 z-40 bg-black/30"
            onClick={() => setSheetOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 z-50 rounded-t-2xl bg-white px-4 pt-2.5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-[0_-10px_30px_-12px_rgba(0,0,0,0.25)]">
            <div className="mx-auto mb-4 h-1 w-9 rounded-full bg-warm-300" />

            <div className="mb-4">
              <div className="mb-2 text-[11px] font-extrabold tracking-wide text-warm-400">배속</div>
              <div className="flex flex-wrap gap-1.5">
                {RATE_PRESETS.map((r) => (
                  <button
                    key={r}
                    onClick={() => setRate(r)}
                    className={`rounded-full border px-3.5 py-2 text-sm font-bold tabular-nums transition-colors ${
                      activePreset === r
                        ? 'border-primary-500 bg-primary-500 text-white'
                        : 'border-warm-200 bg-white text-warm-600'
                    }`}
                  >
                    {fmtRate(r)}×
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4">
              <div className="mb-2 text-[11px] font-extrabold tracking-wide text-warm-400">
                음성 · 범위
              </div>
              <div className="flex gap-2">
                <select
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                  className="h-11 flex-1 rounded-xl border border-warm-200 bg-white px-3 text-sm font-medium text-warm-800"
                >
                  {Object.entries(voices).map(([name, label]) => (
                    <option key={name} value={name}>
                      {label}
                    </option>
                  ))}
                </select>
                {sections.length > 1 && (
                  <select
                    value={section ?? ''}
                    onChange={(e) => selectSection(e.target.value)}
                    className="h-11 flex-1 rounded-xl border border-warm-200 bg-white px-3 text-sm font-medium text-warm-800"
                  >
                    {sections.map((s) => (
                      <option key={s.section} value={s.section}>
                        {s.title}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            {viewMode === 'text' && (
              <div>
                <div className="mb-2 text-[11px] font-extrabold tracking-wide text-warm-400">
                  글자 크기
                </div>
                <div className="flex h-11 w-28 overflow-hidden rounded-xl border border-warm-200">
                  <button
                    onClick={() => stepFont(-1)}
                    disabled={fontSize <= FONT_SIZES[0]}
                    className="flex-1 text-sm font-bold text-warm-600 disabled:opacity-30"
                  >
                    A−
                  </button>
                  <button
                    onClick={() => stepFont(1)}
                    disabled={fontSize >= FONT_SIZES[FONT_SIZES.length - 1]}
                    className="flex-1 border-l border-warm-200 text-sm font-bold text-warm-600 disabled:opacity-30"
                  >
                    A+
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
