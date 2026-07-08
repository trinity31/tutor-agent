import { create } from 'zustand';
import { apiGet, apiPost, apiDelete, apiUpload } from '../api/client';
import { track } from '../lib/analytics';

export interface ClassInfo {
  id: string;
  name: string;
  created_at: string;
}

interface ClassState {
  classes: ClassInfo[];
  selectedClassId: string | null;
  selectedMaterials: string[];
  viewingMaterial: string | null;
  materials: string[];
  indexingMaterials: Set<string>;
  loading: boolean;
  loadClasses: () => Promise<void>;
  createClass: (name: string) => Promise<ClassInfo>;
  deleteClass: (classId: string) => Promise<void>;
  selectClass: (classId: string) => void;
  toggleMaterial: (name: string) => void;
  selectAllMaterials: () => void;
  clearMaterialSelection: () => void;
  viewMaterial: (name: string | null) => void;
  clearSelection: () => void;
  loadMaterials: (classId: string) => Promise<void>;
  uploadMaterial: (classId: string, file: File) => Promise<void>;
  pollIndexingStatus: (classId: string) => void;
}

export const useClassStore = create<ClassState>((set, get) => ({
  classes: [],
  selectedClassId: null,
  selectedMaterials: [],
  viewingMaterial: null,
  materials: [],
  indexingMaterials: new Set(),
  loading: false,

  loadClasses: async () => {
    try {
      const res = await apiGet<{ classes: ClassInfo[] }>('/classes');
      set({ classes: res.classes });
    } catch {
      // silent
    }
  },

  createClass: async (name: string) => {
    const cls = await apiPost<ClassInfo>('/classes', { name });
    set((s) => ({ classes: [...s.classes, cls] }));
    return cls;
  },

  deleteClass: async (classId: string) => {
    await apiDelete(`/classes/${classId}`);
    set((s) => ({
      classes: s.classes.filter((c) => c.id !== classId),
      selectedClassId: s.selectedClassId === classId ? null : s.selectedClassId,
      materials: s.selectedClassId === classId ? [] : s.materials,
    }));
  },

  selectClass: (classId: string) => {
    set({ selectedClassId: classId, selectedMaterials: [], materials: [] });
    get().loadMaterials(classId);
  },

  toggleMaterial: (name: string) => {
    set((s) => ({
      selectedMaterials: s.selectedMaterials.includes(name) ? [] : [name],
    }));
  },

  selectAllMaterials: () => {
    set((s) => ({ selectedMaterials: [...s.materials] }));
  },

  clearMaterialSelection: () => {
    set({ selectedMaterials: [] });
  },

  viewMaterial: (name: string | null) => {
    set({ viewingMaterial: name });
  },

  clearSelection: () => {
    set({ selectedClassId: null, selectedMaterials: [], viewingMaterial: null, materials: [] });
  },

  loadMaterials: async (classId: string) => {
    try {
      const res = await apiGet<{ materials: string[] }>(
        `/classes/${classId}/materials`,
      );
      set({ materials: res.materials });
    } catch {
      set({ materials: [] });
    }
  },

  uploadMaterial: async (classId: string, file: File) => {
    const res = await apiUpload<{ status: string; name: string }>(
      `/classes/${classId}/materials/upload`,
      file,
    );
    track('material_upload', { class_id: classId, material_name: res.name });
    await get().loadMaterials(classId);
    if (res.status === 'indexing') {
      set((s) => ({ indexingMaterials: new Set([...s.indexingMaterials, res.name]) }));
      get().pollIndexingStatus(classId);
    }
  },

  pollIndexingStatus: (classId: string) => {
    const poll = async () => {
      try {
        const res = await apiGet<{ statuses: Record<string, string> }>(
          `/classes/${classId}/materials/status`,
        );
        const stillIndexing = Object.entries(res.statuses)
          .filter(([, s]) => s === 'indexing')
          .map(([name]) => name);
        set({ indexingMaterials: new Set(stillIndexing) });
        if (stillIndexing.length > 0) {
          setTimeout(poll, 3000);
        }
      } catch {
        // 폴링 실패 시 조용히 중단
      }
    };
    setTimeout(poll, 3000);
  },
}));
