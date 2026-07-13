import { create } from 'zustand';
import {
  audioFileUrl,
  getAudioManifest,
  getAudioSections,
  getAudioStatus,
  requestAudio,
  type AudioManifest,
  type AudioSection,
  type AudioStatus,
} from '../api/client';

const RATE_KEY = 'tutor-audio-rate';
const VOICE_KEY = 'tutor-audio-voice';
const POLL_INTERVAL = 3000;

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
  init: (classId: string, materialName: string) => Promise<void>;
  selectSection: (section: string) => void;
  setVoice: (voice: string) => void;
  setRate: (rate: number) => void;
  setCurrentChunk: (idx: number) => void;
  requestGeneration: (force?: boolean) => Promise<void>;
  regenerate: () => void;
  prefetchNext: () => void;
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

  init: async (classId: string, materialName: string) => {
    pollGeneration++;
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
      const voice = get().voice in res.voices ? get().voice : res.default_voice;
      set({
        sections: res.sections,
        voices: res.voices,
        section: res.sections[0]?.section ?? null,
        voice,
      });
      await get().requestGeneration();
    } catch (e) {
      set({ status: 'error', error: e instanceof Error ? e.message : '오디오 정보를 불러오지 못했습니다.' });
    }
  },

  selectSection: (section: string) => {
    if (section === get().section) return;
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
    set({ manifest: null, fileUrl: null, currentChunk: -1 });
    get().requestGeneration(true);
  },

  requestGeneration: async (force = false) => {
    const { classId, materialName, section, voice } = get();
    if (!classId || !materialName || !section) return;
    const generation = ++pollGeneration;
    set({ status: 'loading', error: '' });

    const finishReady = async () => {
      const manifest = await getAudioManifest(classId, materialName, section, voice);
      if (generation !== pollGeneration) return;
      set({
        manifest,
        fileUrl: audioFileUrl(classId, materialName, section, voice),
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
