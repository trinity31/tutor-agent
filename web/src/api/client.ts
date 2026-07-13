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

export async function getMaterialStatus(classId: string) {
  return apiGet<{ completed: string[]; in_progress: string[] }>(
    `/classes/${classId}/material-status`,
  );
}

/** 자료 학습 시작(과외·Q&A·퀴즈·인덱스·듣기) 기록 → '학습중'. 실패해도 조용히 무시. */
export function markMaterialStarted(classId: string, materialName: string) {
  if (!classId || !materialName) return;
  apiPost('/material-activity', { class_id: classId, material_name: materialName }).catch(
    () => {},
  );
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
  page?: number; // PDF 원본 페이지 (1-based) — 구버전 매니페스트에는 없음
  /** 원본 PDF 상 문단 영역 [x0,y0,x1,y1] 정규화(0~1) — 원본 뷰 하이라이트용. 구버전엔 없음 */
  bbox?: number[] | null;
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
  force = false,
) {
  return apiPost<{ status: AudioStatus; duration?: number }>(
    audioBase(classId, materialName),
    { section, voice, force },
  );
}

export async function getAudioStatus(
  classId: string,
  materialName: string,
  section: string,
  voice: string,
) {
  return apiGet<{ status: AudioStatus; duration: number; error?: string }>(
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

export function pdfPageUrl(
  classId: string,
  materialName: string,
  page: number,
): string {
  // 서버에서 렌더한 페이지 PNG. <img>는 Authorization 헤더를 붙일 수 없어 token 쿼리 사용
  const token = getToken() ?? '';
  return `${API_BASE}/classes/${classId}/materials/${encodeURIComponent(materialName)}/pdf/page/${page}?token=${encodeURIComponent(token)}`;
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
  // event 타입은 read() 청크 경계를 넘어 유지돼야 한다. 루프 안에서 초기화하면
  // 모바일처럼 네트워크가 잘게 쪼개질 때 'event: quiz'와 'data:' 줄이 다른
  // 청크에 걸려 이벤트 타입이 유실된다(퀴즈가 안 뜨는 원인).
  let currentEvent = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

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
