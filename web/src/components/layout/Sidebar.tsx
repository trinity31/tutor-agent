import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  markComplete,
  getMaterialStatus,
  saveStudyNote,
  getStudyNotes,
  deleteStudyNote,
  type StudyNote,
} from '../../api/client';
import { useAuthStore } from '../../stores/authStore';
import { useChatStore } from '../../stores/chatStore';
import { useClassStore } from '../../stores/classStore';
import { useUIStore } from '../../stores/uiStore';
import { useReviewStore } from '../../stores/reviewStore';

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const statusVersion = useUIStore((s) => s.statusVersion);
  const bumpStatus = useUIStore((s) => s.bumpStatus);
  const navigate = useNavigate();
  const reviewCount = useReviewStore((s) => s.pending.length);
  const { user, logout } = useAuthStore();
  const { newChat } = useChatStore();
  const {
    classes,
    selectedClassId,
    selectedMaterials,
    materials,
    indexingMaterials,
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
  const [inProgressMaterials, setInProgressMaterials] = useState<string[]>([]);
  const [notes, setNotes] = useState<StudyNote[]>([]);
  const [noteText, setNoteText] = useState('');
  const [showNoteFor, setShowNoteFor] = useState<string | null>(null);
  const [noteSaving, setNoteSaving] = useState(false);
  const [expandedNoteId, setExpandedNoteId] = useState<string | null>(null);
  const [confirmDeleteClassId, setConfirmDeleteClassId] = useState<string | null>(null);
  const [completingMaterial, setCompletingMaterial] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadClasses();
  }, [loadClasses]);

  // 클래스 변경 시 자료별 상태(완료/학습중) 로드
  useEffect(() => {
    if (selectedClassId) {
      getMaterialStatus(selectedClassId)
        .then((res) => {
          setCompletedMaterials(res.completed);
          setInProgressMaterials(res.in_progress);
        })
        .catch(() => {
          setCompletedMaterials([]);
          setInProgressMaterials([]);
        });
    } else {
      setCompletedMaterials([]);
      setInProgressMaterials([]);
    }
  }, [selectedClassId, statusVersion]);

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
      // 클래스 선택 시엔 자료 목록을 펼치기만 하고 모달은 유지 — 닫기는 자료 선택 시에만
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
    setCompletingMaterial(name);
    try {
      await markComplete({ class_id: classId, material_name: name });
      setCompletedMaterials((prev) => [...prev, name]);
      bumpStatus(); // 홈의 학습완료 버튼 상태도 동기화
    } catch { /* ignore */ }
    setCompletingMaterial(null);
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

  // 이름 미설정(백엔드가 name을 email로 저장) 시 이메일 아이디를 이름으로
  const displayName =
    user?.name && user.name !== user.email
      ? user.name
      : (user?.email?.split('@')[0] ?? '');

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-30 bg-black/20 md:hidden" onClick={onClose} />
      )}

      <aside
        className={`fixed z-40 flex h-dvh w-full flex-col border-r border-warm-200 bg-white transition-transform duration-200 md:relative md:w-72 md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* 계정: 아바타 + 이름 + 이메일 + (모바일 닫기) + 로그아웃 */}
        <div className="flex items-center gap-2.5 border-b border-warm-100 px-4 py-3.5">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary-100 text-sm font-bold text-primary-600">
            {(displayName || '·').charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold text-warm-900">{displayName}</p>
            <p className="truncate text-xs text-warm-500">{user?.email}</p>
          </div>
          <button
            onClick={onClose}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-warm-500 hover:bg-warm-100 hover:text-warm-800 transition-colors md:hidden"
            title="닫기"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M5 5l8 8M13 5l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
          <button
            onClick={logout}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-warm-400 hover:bg-warm-100 hover:text-warm-700 transition-colors"
            title="로그아웃"
          >
            ⏻
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
          <button
            onClick={() => {
              navigate('/review');
              onClose();
            }}
            className="mt-2 flex w-full items-center gap-2 rounded-xl border border-warm-200 px-4 py-2.5 text-sm font-semibold text-warm-700 hover:bg-warm-50 active:scale-[0.98] transition-all"
          >
            <span className="text-base">🔁</span>
            복습
            {reviewCount > 0 && (
              <span className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-primary-500 px-1.5 text-[11px] font-bold text-white">
                {reviewCount}
              </span>
            )}
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
                      {isSelected && materials.length > 0 && (
                        <span
                          className={`ml-auto shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold tabular-nums ${
                            isSelected ? 'bg-white text-primary-600' : 'bg-warm-100 text-warm-500'
                          }`}
                        >
                          {completedMaterials.length}/{materials.length}
                        </span>
                      )}
                    </button>

                    {/* Expanded: materials */}
                    {isExpanded && (
                      <div className="ml-5 mt-1 space-y-0.5">
                        {materials.map((name) => {
                          const isChecked = selectedMaterials.includes(name);
                          const isCompleted = completedMaterials.includes(name);
                          const isIndexing = indexingMaterials.has(name);

                          return (
                            <div key={name}>
                              {/* 자료 행: 이름 + 상태 배지 하나 + 메모 아이콘 */}
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={() => {
                                    if (isIndexing) return;
                                    toggleMaterial(name);
                                    onClose();
                                  }}
                                  className={`flex flex-1 items-center truncate rounded-md px-3 py-2 text-[13px] text-left transition-colors ${
                                    isIndexing
                                      ? 'text-warm-400 cursor-wait'
                                      : isChecked
                                        ? 'bg-primary-50 font-bold text-warm-900'
                                        : 'text-warm-600 hover:bg-warm-50'
                                  }`}
                                  title={isIndexing ? '인덱싱 중...' : name}
                                >
                                  <span className="truncate">{name}</span>
                                </button>

                                {/* 상태 배지 — 미완료는 탭하면 학습 완료 처리 */}
                                {isIndexing ? (
                                  <span className="shrink-0 rounded-full bg-accent-50 px-2 py-0.5 text-[11px] font-bold text-accent-500 animate-pulse">
                                    인덱싱
                                  </span>
                                ) : isCompleted ? (
                                  <span className="shrink-0 rounded-full bg-primary-100 px-2 py-0.5 text-[11px] font-bold text-primary-600">
                                    완료
                                  </span>
                                ) : (
                                  <button
                                    onClick={() => handleMarkComplete(cls.id, name)}
                                    disabled={completingMaterial === name}
                                    className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold transition-colors ${
                                      inProgressMaterials.includes(name)
                                        ? 'bg-accent-50 text-accent-500'
                                        : 'bg-warm-100 text-warm-400'
                                    }`}
                                    title="탭하여 학습 완료로 표시"
                                  >
                                    {completingMaterial === name
                                      ? '처리중'
                                      : inProgressMaterials.includes(name)
                                        ? '학습중'
                                        : '미시작'}
                                  </button>
                                )}

                                {/* 메모 */}
                                {isChecked && (
                                  <button
                                    onClick={() => setShowNoteFor(showNoteFor === name ? null : name)}
                                    className="shrink-0 px-1.5 py-0.5 text-base text-primary-600 hover:text-primary-700 transition-colors"
                                    title="메모"
                                  >
                                    ✎
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
                                            <span className="text-xs text-warm-400 shrink-0">{isExpNote ? '▾' : '▸'}</span>
                                            <p className="flex-1 text-xs text-warm-600 truncate">{n.content}</p>
                                          </button>
                                          <button
                                            onClick={async () => {
                                              await deleteStudyNote(n.id);
                                              setNotes((prev) => prev.filter((x) => x.id !== n.id));
                                            }}
                                            className="shrink-0 px-1 text-sm text-warm-300 hover:text-error-500 transition-colors"
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
                        {confirmDeleteClassId === cls.id ? (
                          <div className="flex items-center gap-1.5 px-3 py-1.5">
                            <span className="text-xs text-error-500">정말 삭제?</span>
                            <button
                              onClick={async () => {
                                await deleteClass(cls.id);
                                setConfirmDeleteClassId(null);
                                if (expandedId === cls.id) setExpandedId(null);
                              }}
                              className="rounded-md bg-error-500 px-2 py-0.5 text-xs font-medium text-white"
                            >
                              삭제
                            </button>
                            <button
                              onClick={() => setConfirmDeleteClassId(null)}
                              className="rounded-md border border-warm-200 px-2 py-0.5 text-xs text-warm-600"
                            >
                              취소
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setConfirmDeleteClassId(cls.id)}
                            className="flex w-full items-center gap-1 rounded-md px-3 py-1.5 text-xs font-medium text-error-500 hover:bg-error-50 transition-colors"
                          >
                            클래스 삭제
                          </button>
                        )}
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
