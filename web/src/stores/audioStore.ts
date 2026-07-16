import { create } from 'zustand';
import {
  audioFileUrl,
  getAudioManifest,
  getAudioSections,
  getAudioStatus,
  getMaterialProgress,
  requestAudio,
  type AudioManifest,
  type AudioSection,
  type AudioStatus,
} from '../api/client';

const RATE_KEY = 'tutor-audio-rate';
const VOICE_KEY = 'tutor-audio-voice';
const POLL_INTERVAL = 3000;
// 재접속 시 마지막으로 듣던 자료로 바로 복귀하기 위한 키
export const LAST_MATERIAL_KEY = 'tutor-last-material';
const sectionKey = (classId: string, materialName: string) =>
  `tutor-audio-section:${classId}:${materialName}`;

/** 이어듣기용 재생 위치 localStorage 키 */
export function audioPositionKey(
  classId: string,
  materialName: string,
  section: string,
  voice: string,
): string {
  return `tutor-audio-pos:${classId}:${materialName}:${section}:${voice}`;
}

interface AudioState {
  classId: string | null;
  materialName: string | null;
  sections: AudioSection[];
  voices: Record<string, string>;
  section: string | null;
  voice: string;
  status: 'idle' | 'loading' | 'error' | AudioStatus;
  manifest: AudioManifest | null;
  fileUrl: string | null;
  currentChunk: number;
  rate: number;
  error: string;
  /** 실패가 재시도 가능한지 (스캔 PDF 등 근본 불가면 false → '다시 시도' 숨김) */
  retryable: boolean;
  init: (classId: string, materialName: string) => Promise<void>;
  selectSection: (section: string) => void;
  setVoice: (voice: string) => void;
  setRate: (rate: number) => void;
  setCurrentChunk: (idx: number) => void;
  requestGeneration: (force?: boolean) => Promise<void>;
  regenerate: () => void;
  regenerateAll: () => Promise<void>;
  /** 전체 재생성 진행 상황 (null이면 미진행) */
  regenProgress: { done: number; total: number } | null;
  /** 오디오 캐시버스트용 — 재생성 시 증가시켜 <audio> src를 새로 받게 한다 */
  fileVersion: number;
  prefetchNext: () => void;
  /** 자료 열면 모든 차시를 백그라운드에서 순차 생성 (한번에 준비) */
  generateAllSections: () => Promise<void>;
  advanceToNext: () => boolean;
  reset: () => void;
}

// init/reset 시 증가 — 이전 폴링 루프를 무효화한다
let pollGeneration = 0;

export const useAudioStore = create<AudioState>((set, get) => ({
  classId: null,
  materialName: null,
  sections: [],
  voices: {},
  section: null,
  voice: localStorage.getItem(VOICE_KEY) || 'Charon',
  status: 'idle',
  manifest: null,
  fileUrl: null,
  currentChunk: -1,
  rate: Number(localStorage.getItem(RATE_KEY)) || 1.0,
  error: '',
  retryable: true,
  regenProgress: null,
  fileVersion: 0,

  init: async (classId: string, materialName: string) => {
    pollGeneration++;
    // 재접속 복귀용: 마지막으로 연 자료를 기록
    localStorage.setItem(LAST_MATERIAL_KEY, JSON.stringify({ classId, materialName }));
    set({
      classId,
      materialName,
      status: 'loading',
      manifest: null,
      fileUrl: null,
      currentChunk: -1,
      error: '',
    });
    try {
      const res = await getAudioSections(classId, materialName);
      let voice = get().voice in res.voices ? get().voice : res.default_voice;
      // 서버 이어듣기 위치(기기 간)를 localStorage에 심어, 아래 복원이 서버 값으로
      // 이어지게 한다. 서버 실패 시 기존 localStorage 값 사용.
      try {
        const sp = await getMaterialProgress(classId, materialName);
        if (sp?.section && res.sections.some((s) => s.section === sp.section)) {
          localStorage.setItem(sectionKey(classId, materialName), sp.section);
          if (sp.voice && sp.voice in res.voices) {
            voice = sp.voice;
            localStorage.setItem(VOICE_KEY, sp.voice);
          }
          if (typeof sp.position === 'number' && sp.position > 0) {
            localStorage.setItem(
              audioPositionKey(classId, materialName, sp.section, voice),
              String(sp.position),
            );
          }
        }
      } catch {
        /* 서버 미설정·실패 시 localStorage 값 사용 */
      }
      // 마지막으로 듣던 차시로 복귀 (없거나 사라졌으면 첫 차시)
      const savedSection = localStorage.getItem(sectionKey(classId, materialName));
      const section = res.sections.some((s) => s.section === savedSection)
        ? savedSection
        : (res.sections[0]?.section ?? null);
      set({
        sections: res.sections,
        voices: res.voices,
        section,
        voice,
      });
      await get().requestGeneration();
      // 나머지 차시도 백그라운드에서 순차 생성 (한번에 준비)
      get().generateAllSections();
    } catch (e) {
      set({ status: 'error', error: e instanceof Error ? e.message : '오디오 정보를 불러오지 못했습니다.' });
    }
  },

  selectSection: (section: string) => {
    if (section === get().section) return;
    const { classId, materialName } = get();
    if (classId && materialName) {
      localStorage.setItem(sectionKey(classId, materialName), section);
    }
    set({ section, manifest: null, fileUrl: null, currentChunk: -1 });
    get().requestGeneration();
  },

  setVoice: (voice: string) => {
    if (voice === get().voice) return;
    localStorage.setItem(VOICE_KEY, voice);
    set({ voice, manifest: null, fileUrl: null, currentChunk: -1 });
    get().requestGeneration();
  },

  setRate: (rate: number) => {
    localStorage.setItem(RATE_KEY, String(rate));
    set({ rate });
  },

  setCurrentChunk: (idx: number) => {
    if (idx !== get().currentChunk) set({ currentChunk: idx });
  },

  regenerate: () => {
    // 캐시된 오디오를 무시하고 최신 파이프라인으로 다시 생성
    set((s) => ({ manifest: null, fileUrl: null, currentChunk: -1, fileVersion: s.fileVersion + 1 }));
    get().requestGeneration(true);
  },

  regenerateAll: async () => {
    // 이 자료의 모든 차시를 순차 재생성 (한 번에 서버가 몰리지 않게 하나씩)
    const { classId, materialName, sections, voice, section } = get();
    if (!classId || !materialName || sections.length === 0) return;
    set((s) => ({
      regenProgress: { done: 0, total: sections.length },
      fileVersion: s.fileVersion + 1,
    }));
    for (const s of sections) {
      try {
        await requestAudio(classId, materialName, s.section, voice, true);
        // 완료(ready/failed)까지 폴링 — 섹션당 최대 ~10분 안전장치
        for (let i = 0; i < 200; i++) {
          const st = await getAudioStatus(classId, materialName, s.section, voice);
          if (st.status === 'ready' || st.status === 'failed') break;
          await new Promise((r) => setTimeout(r, POLL_INTERVAL));
        }
      } catch {
        /* 한 차시 실패해도 다음 진행 */
      }
      set((state) => ({
        regenProgress: state.regenProgress
          ? { done: state.regenProgress.done + 1, total: state.regenProgress.total }
          : null,
      }));
    }
    set({ regenProgress: null });
    // 현재 보고 있는 차시를 새 결과로 갱신 (텍스트·하이라이트·오디오)
    if (section) {
      set({ manifest: null, fileUrl: null, currentChunk: -1 });
      await get().requestGeneration(false);
    }
  },

  requestGeneration: async (force = false) => {
    const { classId, materialName, section, voice } = get();
    if (!classId || !materialName || !section) return;
    const generation = ++pollGeneration;
    set({ status: 'loading', error: '', retryable: true });

    const finishReady = async () => {
      const manifest = await getAudioManifest(classId, materialName, section, voice);
      if (generation !== pollGeneration) return;
      const v = get().fileVersion;
      set({
        manifest,
        fileUrl: audioFileUrl(classId, materialName, section, voice) + (v ? `&v=${v}` : ''),
        status: 'ready',
      });
      // 다음 섹션을 미리 생성해 두면 자동 이어듣기 시 대기가 없다
      get().prefetchNext();
    };

    try {
      const res = await requestAudio(classId, materialName, section, voice, force);
      if (generation !== pollGeneration) return;
      if (res.status === 'ready') {
        await finishReady();
        return;
      }
      set({ status: res.status });

      // 생성 완료까지 폴링
      const poll = async () => {
        if (generation !== pollGeneration) return;
        try {
          const s = await getAudioStatus(classId, materialName, section, voice);
          if (generation !== pollGeneration) return;
          if (s.status === 'ready') {
            await finishReady();
          } else if (s.status === 'failed') {
            set({
              status: 'failed',
              error: s.error || '오디오 생성에 실패했습니다. 다시 시도해 주세요.',
              retryable: s.retryable !== false,
            });
          } else {
            set({ status: s.status });
            setTimeout(poll, POLL_INTERVAL);
          }
        } catch {
          // 폴링 실패 시 조용히 재시도
          setTimeout(poll, POLL_INTERVAL);
        }
      };
      setTimeout(poll, POLL_INTERVAL);
    } catch (e) {
      if (generation !== pollGeneration) return;
      set({ status: 'error', error: e instanceof Error ? e.message : '오디오 생성 요청에 실패했습니다.' });
    }
  },

  prefetchNext: () => {
    const { classId, materialName, sections, section, voice } = get();
    if (!classId || !materialName || !section) return;
    const idx = sections.findIndex((s) => s.section === section);
    const next = sections[idx + 1];
    if (!next) return;
    // 서버가 캐시·중복 생성을 알아서 처리하므로 fire-and-forget
    requestAudio(classId, materialName, next.section, voice).catch(() => {});
  },

  generateAllSections: async () => {
    // 자료를 열면 모든 차시를 순차로 생성해 둔다(한번에 하나씩 — 서버 과부하 방지).
    // 이미 생성된 차시는 서버가 즉시 ready를 반환하므로 건너뛴다.
    const { classId, materialName, sections, voice } = get();
    if (!classId || !materialName || sections.length <= 1) return;
    const gen = pollGeneration; // 자료·차시·음성이 바뀌면 중단
    for (const s of sections) {
      if (gen !== pollGeneration) return;
      try {
        const res = await requestAudio(classId, materialName, s.section, voice, false);
        if (res.status === 'ready') continue;
        for (let i = 0; i < 200; i++) {
          if (gen !== pollGeneration) return;
          const st = await getAudioStatus(classId, materialName, s.section, voice);
          if (st.status === 'ready' || st.status === 'failed') break;
          await new Promise((r) => setTimeout(r, POLL_INTERVAL));
        }
      } catch {
        /* 한 차시 실패해도 다음 진행 */
      }
    }
  },

  advanceToNext: () => {
    const { sections, section } = get();
    const idx = sections.findIndex((s) => s.section === section);
    const next = sections[idx + 1];
    if (!next) return false;
    get().selectSection(next.section);
    return true;
  },

  reset: () => {
    pollGeneration++;
    set({
      classId: null,
      materialName: null,
      sections: [],
      section: null,
      status: 'idle',
      manifest: null,
      fileUrl: null,
      currentChunk: -1,
      error: '',
    });
  },
}));
