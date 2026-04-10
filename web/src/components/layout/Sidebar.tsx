import { useEffect, useRef, useState } from 'react';
import {
  markComplete,
  getCompletedMaterials,
  saveStudyNote,
  getStudyNotes,
  deleteStudyNote,
  type StudyNote,
} from '../../api/client';
import { useAuthStore } from '../../stores/authStore';
import { useChatStore } from '../../stores/chatStore';
import { useClassStore } from '../../stores/classStore';

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, logout } = useAuthStore();
  const { newChat } = useChatStore();
  const {
    classes,
    selectedClassId,
    selectedMaterials,
    materials,
    loadClasses,
    createClass,
    deleteClass,
    selectClass,
    toggleMaterial,
    uploadMaterial,
  } = useClassStore();

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [newClassName, setNewClassName] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');

  // 자료별 상태
  const [completedMaterials, setCompletedMaterials] = useState<string[]>([]);
  const [notes, setNotes] = useState<StudyNote[]>([]);
  const [noteText, setNoteText] = useState('');
  const [showNoteFor, setShowNoteFor] = useState<string | null>(null);
  const [noteSaving, setNoteSaving] = useState(false);
  const [expandedNoteId, setExpandedNoteId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadClasses();
  }, [loadClasses]);

  // 클래스 변경 시 완료 목록 로드
  useEffect(() => {
    if (selectedClassId) {
      getCompletedMaterials(selectedClassId)
        .then((res) => setCompletedMaterials(res.materials))
        .catch(() => setCompletedMaterials([]));
    } else {
      setCompletedMaterials([]);
    }
  }, [selectedClassId]);

  // 선택된 자료 변경 시 노트 로드
  useEffect(() => {
    if (selectedClassId && selectedMaterials.length === 1) {
      getStudyNotes(selectedClassId, selectedMaterials[0])
        .then((res) => setNotes(res.notes))
        .catch(() => setNotes([]));
    } else {
      setNotes([]);
    }
    setShowNoteFor(null);
    setNoteText('');
  }, [selectedClassId, selectedMaterials]);

  const handleCreateClass = async () => {
    const name = newClassName.trim();
    if (!name) return;
    await createClass(name);
    setNewClassName('');
    setShowCreateForm(false);
  };

  const handleToggle = (classId: string) => {
    if (expandedId === classId) {
      setExpandedId(null);
    } else {
      setExpandedId(classId);
      selectClass(classId);
    }
  };

  const handleUpload = async (classId: string, e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;
    setUploading(true);
    setUploadMsg('');
    let uploaded = 0;
    for (const file of Array.from(files)) {
      try {
        await uploadMaterial(classId, file);
        uploaded++;
      } catch (err) {
        setUploadMsg((err as Error).message);
      }
    }
    if (uploaded > 0) setUploadMsg(`${uploaded}개 파일 업로드 완료!`);
    setUploading(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const handleMarkComplete = async (classId: string, name: string) => {
    try {
      await markComplete({ class_id: classId, material_name: name });
      setCompletedMaterials((prev) => [...prev, name]);
    } catch { /* ignore */ }
  };

  const handleSaveNote = async (classId: string, materialName: string) => {
    if (!noteText.trim()) return;
    setNoteSaving(true);
    try {
      const note = await saveStudyNote({
        class_id: classId,
        material_name: materialName,
        content: noteText.trim(),
      });
      setNotes((prev) => [note, ...prev]);
      setNoteText('');
      setShowNoteFor(null);
    } catch { /* ignore */ }
    setNoteSaving(false);
  };

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-30 bg-black/20 md:hidden" onClick={onClose} />
      )}

      <aside
        className={`fixed z-40 flex h-dvh w-72 flex-col border-r border-warm-200 bg-white transition-transform duration-200 md:relative md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-warm-100 px-5 py-4">
          <div>
            <p className="text-sm font-semibold text-warm-900">{user?.name || user?.email}</p>
            <p className="text-xs text-warm-500">{user?.email}</p>
          </div>
          <button
            onClick={logout}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-warm-500 hover:bg-warm-100 hover:text-warm-700 transition-colors"
          >
            로그아웃
          </button>
        </div>

        {/* New Chat */}
        <div className="px-4 py-3">
          <button
            onClick={async () => {
              await newChat();
              onClose();
            }}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-600 active:scale-[0.98] transition-all"
          >
            <span className="text-lg">+</span>
            새 대화
          </button>
        </div>

        {/* Classes */}
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-warm-500">
              클래스
            </h3>
            <button
              onClick={() => setShowCreateForm(!showCreateForm)}
              className="rounded-md px-2 py-1 text-xs font-medium text-primary-600 hover:bg-primary-50 transition-colors"
            >
              + 추가
            </button>
          </div>

          {/* Create form */}
          {showCreateForm && (
            <div className="mb-3 flex gap-2">
              <input
                type="text"
                value={newClassName}
                onChange={(e) => setNewClassName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreateClass()}
                placeholder="클래스 이름"
                autoFocus
                className="flex-1 rounded-lg border border-warm-200 bg-warm-50 px-3 py-2 text-sm text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none transition-colors"
              />
              <button
                onClick={handleCreateClass}
                disabled={!newClassName.trim()}
                className="rounded-lg bg-primary-500 px-3 py-2 text-xs font-medium text-white hover:bg-primary-600 disabled:opacity-30 transition-colors"
              >
                생성
              </button>
            </div>
          )}

          {classes.length === 0 && !showCreateForm ? (
            <p className="py-4 text-center text-sm text-warm-400">
              클래스를 추가해 보세요
            </p>
          ) : (
            <ul className="space-y-1">
              {classes.map((cls) => {
                const isExpanded = expandedId === cls.id;
                const isSelected = selectedClassId === cls.id;

                return (
                  <li key={cls.id}>
                    <button
                      onClick={() => handleToggle(cls.id)}
                      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium text-left transition-colors ${
                        isSelected
                          ? 'bg-primary-50 text-primary-700'
                          : 'text-warm-700 hover:bg-warm-50'
                      }`}
                    >
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 14 14"
                        className={`shrink-0 text-warm-400 transition-transform ${
                          isExpanded ? 'rotate-90' : ''
                        }`}
                      >
                        <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none" />
                      </svg>
                      <span className="truncate">{cls.name}</span>
                    </button>

                    {/* Expanded: materials */}
                    {isExpanded && (
                      <div className="ml-5 mt-1 space-y-0.5">
                        {materials.map((name) => {
                          const isChecked = selectedMaterials.includes(name);
                          const isCompleted = completedMaterials.includes(name);

                          return (
                            <div key={name}>
                              {/* 자료 행: 선택 + 이름 + 액션 버튼 */}
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={() => toggleMaterial(name)}
                                  className={`flex flex-1 items-center gap-2 text-left rounded-md px-3 py-1.5 text-xs truncate transition-colors ${
                                    isChecked
                                      ? 'bg-primary-100 text-primary-700 font-medium'
                                      : 'text-warm-600 hover:bg-warm-50'
                                  }`}
                                  title={name}
                                >
                                  <span className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border transition-colors ${
                                    isChecked ? 'bg-primary-500 border-primary-500' : 'border-warm-300'
                                  }`}>
                                    {isChecked && (
                                      <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                                        <path d="M1.5 4l2 2 3-3.5" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                                      </svg>
                                    )}
                                  </span>
                                  <span className="truncate">{name}</span>
                                </button>

                                {/* 학습 완료 버튼 */}
                                {isChecked && !isCompleted && (
                                  <button
                                    onClick={() => handleMarkComplete(cls.id, name)}
                                    className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-amber-600 hover:bg-amber-50 transition-colors"
                                    title="학습 완료 등록"
                                  >
                                    완료
                                  </button>
                                )}
                                {isCompleted && (
                                  <span className="shrink-0 text-[10px] text-success-500 font-medium px-1.5">
                                    완료
                                  </span>
                                )}

                                {/* 노트 버튼 */}
                                {isChecked && (
                                  <button
                                    onClick={() => setShowNoteFor(showNoteFor === name ? null : name)}
                                    className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-primary-600 hover:bg-primary-50 transition-colors"
                                    title="노트 추가"
                                  >
                                    메모
                                  </button>
                                )}
                              </div>

                              {/* 노트 입력/목록 (선택된 자료에만) */}
                              {isChecked && showNoteFor === name && (
                                <div className="ml-5 mt-1 mb-1 space-y-1.5">
                                  <div className="space-y-1.5">
                                    <textarea
                                      value={noteText}
                                      onChange={(e) => setNoteText(e.target.value)}
                                      placeholder="기억할 내용을 메모하세요"
                                      rows={2}
                                      className="w-full rounded-md border border-warm-200 bg-warm-50 px-2 py-1.5 text-xs text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none"
                                    />
                                    <div className="flex gap-1.5">
                                      <button
                                        onClick={() => { setShowNoteFor(null); setNoteText(''); }}
                                        className="flex-1 rounded-md border border-warm-200 py-1 text-xs text-warm-600"
                                      >
                                        취소
                                      </button>
                                      <button
                                        onClick={() => handleSaveNote(cls.id, name)}
                                        disabled={!noteText.trim() || noteSaving}
                                        className="flex-1 rounded-md bg-primary-500 py-1 text-xs font-medium text-white disabled:opacity-30"
                                      >
                                        저장
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              )}

                              {/* 저장된 노트 — 클릭 시 펼치기 */}
                              {isChecked && notes.length > 0 && (
                                <div className="ml-5 mt-1 mb-1 space-y-0.5">
                                  {notes.map((n) => {
                                    const isExpNote = expandedNoteId === n.id;
                                    return (
                                      <div key={n.id} className="group rounded-md bg-warm-50 px-2 py-1">
                                        <div className="flex items-center gap-1">
                                          <button
                                            onClick={() => setExpandedNoteId(isExpNote ? null : n.id)}
                                            className="flex flex-1 items-center gap-1 text-left min-w-0"
                                          >
                                            <span className="text-[10px] text-warm-400 shrink-0">{isExpNote ? '▾' : '▸'}</span>
                                            <p className="flex-1 text-xs text-warm-600 truncate">{n.content}</p>
                                          </button>
                                          <button
                                            onClick={async () => {
                                              await deleteStudyNote(n.id);
                                              setNotes((prev) => prev.filter((x) => x.id !== n.id));
                                            }}
                                            className="shrink-0 text-warm-400 opacity-0 group-hover:opacity-100 hover:text-error-500 transition-all text-[10px]"
                                            title="삭제"
                                          >
                                            ✕
                                          </button>
                                        </div>
                                        {isExpNote && (
                                          <p className="mt-1 text-xs text-warm-700 whitespace-pre-wrap pl-3">{n.content}</p>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          );
                        })}

                        {/* Upload */}
                        <label
                          className={`flex cursor-pointer items-center gap-1 rounded-md px-3 py-1.5 text-xs text-primary-500 hover:bg-primary-50 transition-colors ${
                            uploading ? 'opacity-50 pointer-events-none' : ''
                          }`}
                        >
                          <input
                            ref={fileRef}
                            type="file"
                            accept=".pdf"
                            multiple
                            className="hidden"
                            onChange={(e) => handleUpload(cls.id, e)}
                          />
                          {uploading ? '업로드 중...' : '+ 자료 업로드'}
                        </label>

                        {uploadMsg && (
                          <p
                            className={`px-3 text-xs ${
                              uploadMsg.includes('완료') ? 'text-success-500' : 'text-error-500'
                            }`}
                          >
                            {uploadMsg}
                          </p>
                        )}

                        {/* 클래스 삭제 */}
                        <button
                          onClick={async () => {
                            if (window.confirm(`'${cls.name}' 클래스와 모든 자료를 삭제하시겠습니까?`)) {
                              await deleteClass(cls.id);
                              if (expandedId === cls.id) setExpandedId(null);
                            }
                          }}
                          className="flex w-full items-center gap-1 rounded-md px-3 py-1.5 text-xs font-medium text-error-500 hover:bg-error-50 transition-colors"
                        >
                          클래스 삭제
                        </button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
