import { useEffect, useRef, useState } from 'react';
import { useAuthStore } from '../../stores/authStore';
import { useChatStore } from '../../stores/chatStore';
import { apiGet, apiUpload } from '../../api/client';

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, logout } = useAuthStore();
  const { newChat } = useChatStore();
  const [materials, setMaterials] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const loadMaterials = async () => {
    try {
      const res = await apiGet<{ materials: string[] }>('/materials');
      setMaterials(res.materials);
    } catch {
      // silent
    }
  };

  useEffect(() => {
    loadMaterials();
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;

    setUploading(true);
    setUploadMsg('');
    let uploaded = 0;

    for (const file of Array.from(files)) {
      try {
        await apiUpload('/materials/upload', file);
        uploaded++;
      } catch (err) {
        setUploadMsg((err as Error).message);
      }
    }

    if (uploaded > 0) {
      setUploadMsg(`${uploaded}개 파일 업로드 완료!`);
      await loadMaterials();
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/20 md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed z-40 flex h-dvh w-72 flex-col border-r border-warm-200 bg-white transition-transform duration-200 md:relative md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-warm-100 px-5 py-4">
          <div>
            <p className="text-sm font-semibold text-warm-900">
              {user?.name || user?.email}
            </p>
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

        {/* Materials */}
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <div className="mb-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-warm-500">
              학습자료
            </h3>

            <label
              className={`flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed border-warm-200 px-4 py-3 text-sm text-warm-500 hover:border-primary-400 hover:text-primary-600 transition-colors ${
                uploading ? 'opacity-50 pointer-events-none' : ''
              }`}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                multiple
                className="hidden"
                onChange={handleUpload}
              />
              {uploading ? '업로드 중...' : 'PDF 파일 업로드'}
            </label>

            {uploadMsg && (
              <p
                className={`mt-2 text-xs ${
                  uploadMsg.includes('완료') ? 'text-success-500' : 'text-error-500'
                }`}
              >
                {uploadMsg}
              </p>
            )}
          </div>

          {materials.length > 0 ? (
            <ul className="space-y-1">
              {materials.map((name) => (
                <li
                  key={name}
                  className="rounded-lg px-3 py-2 text-sm text-warm-700 hover:bg-warm-50 transition-colors truncate"
                  title={name}
                >
                  {name}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-center text-sm text-warm-400 py-4">
              아직 업로드된 자료가 없습니다
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
