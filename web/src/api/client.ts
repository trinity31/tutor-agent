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
