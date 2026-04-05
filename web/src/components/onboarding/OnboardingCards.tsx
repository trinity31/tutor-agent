import { useEffect, useRef, useState } from "react";
import { apiGet } from "../../api/client";
import { useClassStore } from "../../stores/classStore";

const CARDS = [
  {
    type: "tutor",
    title: "1:1 과외",
    desc: "주제를 쉽게 설명하고 이해도를 확인해요",
    fallback: "이 강의 자료에 나온 개념을 좀 더 쉽게 설명해 주세요",
    color: "bg-primary-50 border-primary-200",
    iconBg: "bg-primary-500",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path d="M12 6.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5zM7 20v-1a5 5 0 0110 0v1" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M17 14a3 3 0 013 3v1M17 10a2 2 0 100-4" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    type: "qna",
    title: "Q&A",
    desc: "모르는 용어나 개념을 간단히 물어보세요",
    fallback: "핵심 개념을 정리해 줘",
    color: "bg-accent-300/15 border-accent-400/30",
    iconBg: "bg-accent-400",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="1.5" />
        <path d="M9.5 10a2.5 2.5 0 015 0c0 1.5-2.5 2-2.5 3.5M12 17h.01" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    type: "quiz",
    title: "퀴즈",
    desc: "학습자료 기반 퀴즈를 풀어보세요",
    fallback: "이 강의자료의 내용을 바탕으로 퀴즈를 내주세요",
    color: "bg-success-400/10 border-success-400/30",
    iconBg: "bg-success-500",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <rect x="4" y="4" width="16" height="16" rx="3" stroke="white" strokeWidth="1.5" />
        <path d="M9 12l2 2 4-4" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

export default function OnboardingCards({
  onSend,
  hasClasses,
  selectedClassId,
}: {
  onSend: (text: string) => void;
  hasClasses: boolean;
  selectedClassId: string | null;
}) {
  const { createClass, selectClass, materials, selectedMaterials, uploadMaterial } = useClassStore();
  const [examples, setExamples] = useState<Record<string, string>>({});
  const [loadingExamples, setLoadingExamples] = useState(false);
  const [newClassName, setNewClassName] = useState("");
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);

  // 자료가 선택되었을 때만 LLM으로 예시 질문 생성
  useEffect(() => {
    if (!selectedClassId || selectedMaterials.length === 0) return;
    setExamples({});
    setLoadingExamples(true);
    apiGet<{ examples: { type: string; message: string }[] }>(
      `/classes/${selectedClassId}/examples?materials=${encodeURIComponent(selectedMaterials.join('|'))}`,
    )
      .then((res) => {
        const map: Record<string, string> = {};
        for (const ex of res.examples) map[ex.type] = ex.message;
        setExamples(map);
      })
      .catch(() => {})
      .finally(() => setLoadingExamples(false));
  }, [selectedClassId, selectedMaterials]);
  const [uploadMsg, setUploadMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleCreateClass = async () => {
    const name = newClassName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const cls = await createClass(name);
      selectClass(cls.id);
      setNewClassName("");
    } finally {
      setCreating(false);
    }
  };

  // 클래스가 없을 때: 클래스 생성 안내
  if (!hasClasses) {
    return (
      <div className="mx-auto max-w-md px-4 py-12 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-500 text-2xl font-bold text-white">
          T
        </div>
        <h2 className="text-xl font-bold text-warm-900">
          안녕하세요! AI 과외 선생님이에요
        </h2>
        <p className="mt-2 mb-6 text-sm text-warm-500">
          시작하려면 클래스를 만들어 보세요!
          <br />
          클래스를 만들고 강의자료(PDF)를 업로드하면
          <br />
          1:1 과외, Q&A, 퀴즈를 시작할 수 있어요.
        </p>
        <div className="mx-auto flex max-w-xs gap-2">
          <input
            type="text"
            value={newClassName}
            onChange={(e) => setNewClassName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreateClass()}
            placeholder="클래스 이름 (예: 음식인문학)"
            className="flex-1 rounded-xl border border-warm-200 bg-warm-50 px-4 py-3 text-sm text-warm-900 placeholder:text-warm-400 focus:border-primary-500 focus:outline-none transition-colors"
          />
          <button
            onClick={handleCreateClass}
            disabled={!newClassName.trim() || creating}
            className="rounded-xl bg-primary-500 px-5 py-3 text-sm font-semibold text-white hover:bg-primary-600 active:scale-[0.98] disabled:opacity-50 transition-all"
          >
            만들기
          </button>
        </div>
      </div>
    );
  }

  // 클래스는 있지만 선택 안 됨
  if (!selectedClassId) {
    return (
      <div className="mx-auto max-w-md px-4 py-12 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-500 text-2xl font-bold text-white">
          T
        </div>
        <h2 className="text-xl font-bold text-warm-900">클래스를 선택해 주세요</h2>
        <p className="mt-2 text-sm text-warm-500">
          왼쪽 사이드바에서 클래스를 선택하면
          <br />
          해당 강의자료 기반으로 학습을 시작할 수 있어요.
        </p>
      </div>
    );
  }

  const handleUploadOnboarding = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length || !selectedClassId) return;
    setUploading(true);
    setUploadMsg("");
    let uploaded = 0;
    for (const file of Array.from(files)) {
      try {
        await uploadMaterial(selectedClassId, file);
        uploaded++;
      } catch (err) {
        setUploadMsg((err as Error).message);
      }
    }
    if (uploaded > 0) setUploadMsg(`${uploaded}개 파일 업로드 완료!`);
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  // 클래스 선택됨 + 자료 없음
  if (materials.length === 0) {
    return (
      <div className="mx-auto max-w-md px-4 py-12 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-400 text-2xl font-bold text-white">
          +
        </div>
        <h2 className="text-xl font-bold text-warm-900">강의자료를 업로드해 주세요</h2>
        <p className="mt-2 mb-6 text-sm text-warm-500">
          PDF 파일을 업로드하면 AI 과외를 시작할 수 있어요.
        </p>
        <label
          className={`inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary-500 px-6 py-3 text-sm font-semibold text-white hover:bg-primary-600 active:scale-[0.98] transition-all ${
            uploading ? "opacity-50 pointer-events-none" : ""
          }`}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".pdf"
            multiple
            className="hidden"
            onChange={handleUploadOnboarding}
          />
          {uploading ? "업로드 중..." : "PDF 파일 선택"}
        </label>
        {uploadMsg && (
          <p className={`mt-3 text-sm ${uploadMsg.includes("완료") ? "text-success-500" : "text-error-500"}`}>
            {uploadMsg}
          </p>
        )}
      </div>
    );
  }

  // 클래스 + 자료 있음: 기존 3개 카드
  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-500 text-2xl font-bold text-white">
          T
        </div>
        <h2 className="text-xl font-bold text-warm-900">무엇을 도와드릴까요?</h2>
        <p className="mt-2 text-sm text-warm-500">
          아래 카드를 눌러 시작하거나, 직접 메시지를 입력해 보세요
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {CARDS.map((card) => {
          const isQna = card.type === "qna";
          const message = isQna
            ? (examples[card.type] || card.fallback)
            : card.fallback;
          const isLoading = isQna && loadingExamples;
          return (
            <button
              key={card.type}
              onClick={() => !isLoading && onSend(message)}
              disabled={isLoading}
              className={`group flex flex-col items-start rounded-2xl border p-5 text-left transition-all hover:scale-[1.02] hover:shadow-md active:scale-[0.98] disabled:opacity-70 disabled:cursor-wait ${card.color}`}
            >
              <div className={`mb-3 flex h-10 w-10 items-center justify-center rounded-xl ${card.iconBg}`}>
                {card.icon}
              </div>
              <h3 className="mb-1 text-sm font-bold text-warm-900">{card.title}</h3>
              <p className="mb-3 text-xs text-warm-500 leading-relaxed">{card.desc}</p>
              <p className="text-xs font-medium text-warm-600 group-hover:text-primary-600 transition-colors">
                {isLoading ? (
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-warm-400" />
                    질문 생성 중...
                  </span>
                ) : (
                  <>&ldquo;{message}&rdquo;</>
                )}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
