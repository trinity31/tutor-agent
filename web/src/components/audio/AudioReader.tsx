import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { useAudioStore, audioPositionKey } from '../../stores/audioStore';
import { track } from '../../lib/analytics';

// pdf.js 번들이 커서 PDF 뷰를 열 때만 로드
const PdfPageView = lazy(() => import('./PdfPageView'));

const VIEW_KEY = 'tutor-audio-view';
const FONT_KEY = 'tutor-audio-font';
const FONT_SIZES = [14, 16, 18, 20, 22];

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

  // "이 페이지부터 듣기" — 해당 페이지의 첫 청크로 시크
  const listenFromPage = (page: number) => {
    if (!manifest) return;
    const target =
      manifest.chunks.find((c) => c.page === page) ??
      manifest.chunks.find((c) => (c.page ?? 0) > page);
    if (target) seekTo(target.start);
  };

  return (
    <div className="flex h-full flex-col">
      {/* 섹션·음성 선택 */}
      <div className="flex items-center gap-2 border-b border-warm-100 bg-white px-4 py-2">
        {sections.length > 1 && (
          <select
            value={section ?? ''}
            onChange={(e) => selectSection(e.target.value)}
            className="min-w-0 flex-1 rounded-md border border-warm-200 bg-white px-2 py-1 text-xs text-warm-700"
          >
            {sections.map((s) => (
              <option key={s.section} value={s.section}>
                {s.title}
              </option>
            ))}
          </select>
        )}
        <select
          value={voice}
          onChange={(e) => setVoice(e.target.value)}
          className="rounded-md border border-warm-200 bg-white px-2 py-1 text-xs text-warm-700"
          title="음성 선택"
        >
          {Object.entries(voices).map(([name, label]) => (
            <option key={name} value={name}>
              {label}
            </option>
          ))}
        </select>
        <button
          onClick={toggleView}
          className="shrink-0 rounded-md border border-warm-200 bg-white px-2 py-1 text-xs font-medium text-warm-600 hover:bg-warm-100 transition-colors"
          title={viewMode === 'pdf' ? '낭독 텍스트 보기' : 'PDF 원본 보기'}
        >
          {viewMode === 'pdf' ? '📝 텍스트' : '📄 원본'}
        </button>
        {viewMode === 'text' && (
          <div className="flex shrink-0 items-center rounded-md border border-warm-200 bg-white">
            <button
              onClick={() => stepFont(-1)}
              disabled={fontSize <= FONT_SIZES[0]}
              className="px-1.5 py-1 text-[11px] text-warm-600 hover:bg-warm-100 disabled:opacity-30 transition-colors"
              title="글자 작게"
            >
              A−
            </button>
            <button
              onClick={() => stepFont(1)}
              disabled={fontSize >= FONT_SIZES[FONT_SIZES.length - 1]}
              className="border-l border-warm-200 px-1.5 py-1 text-[13px] text-warm-600 hover:bg-warm-100 disabled:opacity-30 transition-colors"
              title="글자 크게"
            >
              A+
            </button>
          </div>
        )}
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
          <div className="space-y-3 leading-relaxed" style={{ fontSize }}>
            {manifest.chunks.map((chunk, ci) => (
              <p
                key={ci}
                ref={(el) => {
                  chunkRefs.current[ci] = el;
                }}
                className={`rounded-md px-2 py-1 text-warm-800 transition-colors ${
                  ci === currentChunk
                    ? 'bg-primary-50 shadow-[inset_0_-2px_0_theme(colors.primary.300)]'
                    : ''
                }`}
              >
                {chunk.sentences.map((sent, si) => (
                  <span
                    key={si}
                    onClick={() => seekToSentence(ci, si)}
                    className="cursor-pointer rounded px-0.5 hover:bg-warm-100"
                  >
                    {sent}{' '}
                  </span>
                ))}
              </p>
            ))}
          </div>
        )}
      </div>
      )}

      {/* 플레이어 */}
      {status === 'ready' && fileUrl && (
        <div className="border-t border-warm-200 bg-white px-4 py-3">
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
          {/* 진행바 */}
          <div className="mb-2 flex items-center gap-2">
            <span className="w-10 text-right text-[10px] tabular-nums text-warm-500">
              {formatTime(currentTime)}
            </span>
            <input
              type="range"
              min={0}
              max={duration || manifest?.duration || 0}
              step={0.1}
              value={currentTime}
              onChange={(e) => seekTo(Number(e.target.value))}
              className="flex-1 accent-primary-500"
            />
            <span className="w-10 text-[10px] tabular-nums text-warm-500">
              {formatTime(duration || manifest?.duration || 0)}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={togglePlay}
              className="rounded-full bg-primary-500 px-4 py-1.5 text-xs font-semibold text-white hover:bg-primary-600 transition-colors"
            >
              {playing ? '⏸ 일시정지' : '▶ 재생'}
            </button>
            <div className="flex flex-1 items-center gap-1.5 text-[10px] text-warm-500">
              <span>배속</span>
              <input
                type="range"
                min={0.7}
                max={2}
                step={0.1}
                value={rate}
                onChange={(e) => setRate(Number(e.target.value))}
                className="w-20 accent-primary-500"
              />
              <span className="tabular-nums">{rate.toFixed(1)}×</span>
            </div>
            {currentChunk >= 0 && manifest && (
              <span className="text-[10px] tabular-nums text-warm-400">
                {currentChunk + 1}/{manifest.chunks.length}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
