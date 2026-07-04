const API_BASE = '/api';

function getToken(): string | null {
  return localStorage.getItem('token');
}

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '요청에 실패했습니다.' }));
    throw new Error(err.detail || '요청에 실패했습니다.');
  }
  return res.json();
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '요청에 실패했습니다.' }));
    throw new Error(err.detail || '요청에 실패했습니다.');
  }
  return res.json();
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '업로드에 실패했습니다.' }));
    throw new Error(err.detail || '업로드에 실패했습니다.');
  }
  return res.json();
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '삭제에 실패했습니다.' }));
    throw new Error(err.detail || '삭제에 실패했습니다.');
  }
  return res.json();
}

// --- Study Notes ---

export interface StudyNote {
  id: string;
  material_name: string;
  content: string;
  created_at: string;
}

export async function saveStudyNote(data: { class_id: string; material_name: string; content: string }) {
  return apiPost<StudyNote>('/notes', data);
}

export async function getStudyNotes(classId: string, materialName?: string) {
  const params = materialName ? `?class_id=${classId}&material_name=${encodeURIComponent(materialName)}` : `?class_id=${classId}`;
  return apiGet<{ notes: StudyNote[] }>(`/notes${params}`);
}

export async function deleteStudyNote(noteId: string) {
  return apiDelete<{ status: string }>(`/notes/${noteId}`);
}

// --- Quiz Results & Completions ---

export async function saveQuizResult(data: {
  class_id: string;
  material_name: string;
  quiz_title?: string;
  questions: unknown[];
  answers: unknown[];
  score: number;
  total: number;
}) {
  return apiPost<{ id: string; score: number; total: number; wrong_count: number }>(
    '/quiz-results',
    data,
  );
}

export async function scheduleQuizRetry(
  quizId: string,
  data: { scheduled_date: string; schedule_mode: string; review_notes?: string },
) {
  return apiPost<{ id: string; type: string; scheduled_date: string }>(
    `/quiz-results/${quizId}/schedule`,
    data,
  );
}

export async function markComplete(data: { class_id: string; material_name: string }) {
  return apiPost<{ id: string; type: string }>('/completions', data);
}

export async function getCompletedMaterials(classId: string) {
  return apiGet<{ materials: string[] }>(`/classes/${classId}/completed-materials`);
}

// --- Material Index ---

export async function getMaterialIndex(classId: string, materialName: string) {
  return apiGet<{ status: 'ready' | 'not_ready'; content: string }>(
    `/classes/${classId}/materials/${encodeURIComponent(materialName)}/index`,
  );
}

export async function regenerateMaterialIndex(classId: string, materialName: string) {
  return apiPost<{ status: 'ready'; content: string }>(
    `/classes/${classId}/materials/${encodeURIComponent(materialName)}/index/regenerate`,
    {},
  );
}

// --- 원문 낭독 (Audio) ---

export interface AudioSection {
  section: string;
  title: string;
}

export interface AudioChunk {
  text: string;
  start: number;
  end: number;
  sentences: string[];
}

export interface AudioManifest {
  voice: string;
  format: string;
  duration: number;
  chunks: AudioChunk[];
}

export type AudioStatus = 'none' | 'pending' | 'generating' | 'ready' | 'failed';

function audioBase(classId: string, materialName: string): string {
  return `/classes/${classId}/materials/${encodeURIComponent(materialName)}/audio`;
}

export async function getAudioSections(classId: string, materialName: string) {
  return apiGet<{
    sections: AudioSection[];
    voices: Record<string, string>;
    default_voice: string;
  }>(`${audioBase(classId, materialName)}/sections`);
}

export async function requestAudio(
  classId: string,
  materialName: string,
  section: string,
  voice: string,
) {
  return apiPost<{ status: AudioStatus; duration?: number }>(
    audioBase(classId, materialName),
    { section, voice },
  );
}

export async function getAudioStatus(
  classId: string,
  materialName: string,
  section: string,
  voice: string,
) {
  return apiGet<{ status: AudioStatus; duration: number }>(
    `${audioBase(classId, materialName)}/status?section=${encodeURIComponent(section)}&voice=${voice}`,
  );
}

export async function getAudioManifest(
  classId: string,
  materialName: string,
  section: string,
  voice: string,
) {
  return apiGet<AudioManifest>(
    `${audioBase(classId, materialName)}/manifest?section=${encodeURIComponent(section)}&voice=${voice}`,
  );
}

export function audioFileUrl(
  classId: string,
  materialName: string,
  section: string,
  voice: string,
): string {
  // <audio> 태그는 Authorization 헤더를 붙일 수 없어 token 쿼리 파라미터 사용
  const token = getToken() ?? '';
  return `${API_BASE}${audioBase(classId, materialName)}/file?section=${encodeURIComponent(section)}&voice=${voice}&token=${encodeURIComponent(token)}`;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export async function streamChat(
  message: string,
  threadId: string,
  classId: string,
  materialName: string,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ message, thread_id: threadId, class_id: classId, material_name: materialName || undefined }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '채팅 요청에 실패했습니다.' }));
    throw new Error(err.detail || '채팅 요청에 실패했습니다.');
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('스트리밍을 지원하지 않습니다.');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let currentEvent = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          onEvent({ event: currentEvent, data });
        } catch {
          // skip malformed JSON
        }
        currentEvent = '';
      }
    }
  }
}
