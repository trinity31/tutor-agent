import { useEffect, useState } from 'react';
import {
  saveStudyNote,
  getStudyNotes,
  deleteStudyNote,
  type StudyNote,
} from '../../api/client';

/** 학습 메모 — 자료별 메모 작성·목록·삭제 (패널 '메모' 모드에서 사용) */
export default function StudyNotes({
  classId,
  materialName,
}: {
  classId: string;
  materialName: string;
}) {
  const [notes, setNotes] = useState<StudyNote[]>([]);
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getStudyNotes(classId, materialName)
      .then((r) => setNotes(r.notes))
      .catch(() => setNotes([]));
  }, [classId, materialName]);

  const save = async () => {
    if (!text.trim()) return;
    setSaving(true);
    try {
      const note = await saveStudyNote({
        class_id: classId,
        material_name: materialName,
        content: text.trim(),
      });
      setNotes((p) => [note, ...p]);
      setText('');
    } catch {
      /* ignore */
    }
    setSaving(false);
  };

  const remove = async (id: string) => {
    setNotes((p) => p.filter((n) => n.id !== id));
    deleteStudyNote(id).catch(() => {});
  };

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-warm-100 p-4">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="기억할 내용을 메모하세요"
          rows={3}
          className="w-full resize-none rounded-xl border border-warm-200 bg-warm-50 px-3.5 py-2.5 text-sm text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none"
        />
        <button
          onClick={save}
          disabled={!text.trim() || saving}
          className="mt-2 w-full rounded-xl bg-primary-500 py-2.5 text-sm font-semibold text-white active:scale-[0.99] disabled:opacity-40 transition-transform"
        >
          {saving ? '저장 중...' : '메모 저장'}
        </button>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-4">
        {notes.length === 0 ? (
          <p className="py-12 text-center text-sm text-warm-400">
            아직 메모가 없어요. 위에 적어 저장해 보세요.
          </p>
        ) : (
          notes.map((n) => (
            <div key={n.id} className="rounded-xl bg-warm-50 p-3">
              <div className="flex items-start gap-2">
                <p className="flex-1 whitespace-pre-wrap break-words text-sm text-warm-800">
                  {n.content}
                </p>
                <button
                  onClick={() => remove(n.id)}
                  className="shrink-0 px-1 text-warm-300 hover:text-error-500 transition-colors"
                  title="삭제"
                >
                  ✕
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
