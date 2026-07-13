import { useEffect, useRef, useState } from "react";
import { markComplete, getMaterialStatus } from "../../api/client";
import { useClassStore } from "../../stores/classStore";
import { useUIStore } from "../../stores/uiStore";
import { useChatStore } from "../../stores/chatStore";

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
    desc: "이번 차시 내용을 문제로 점검해요",
    fallback: "이 강의자료의 내용을 바탕으로 퀴즈를 내주세요",
    color: "bg-[#5b8def]/10 border-[#5b8def]/25",
    iconBg: "bg-[#5b8def]",
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
  onOpenIndex,
}: {
  onSend: (text: string) => void;
  hasClasses: boolean;
  selectedClassId: string | null;
  onOpenIndex?: (mode: 'index' | 'audio') => void;
}) {
  const openSidebar = useUIStore((s) => s.openSidebar);
  const bumpStatus = useUIStore((s) => s.bumpStatus);
  const statusVersion = useUIStore((s) => s.statusVersion);
  const { createClass, selectClass, materials, selectedMaterials, uploadMaterial } = useClassStore();
  const promptGreeting = useChatStore((s) => s.promptGreeting);
  const [completedSet, setCompletedSet] = useState<Set<string>>(new Set());
  const [newClassName, setNewClassName] = useState("");
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);

  // 선택 자료의 완료 여부 로드 (중복 완료 방지 — save_completion은 멱등이 아님)
  useEffect(() => {
    if (!selectedClassId || selectedMaterials.length === 0) {
      setCompletedSet(new Set());
      return;
    }
    getMaterialStatus(selectedClassId)
      .then((res) => setCompletedSet(new Set(res.completed)))
      .catch(() => setCompletedSet(new Set()));
  }, [selectedClassId, selectedMaterials, statusVersion]);

  const allCompleted =
    selectedMaterials.length > 0 && selectedMaterials.every((m) => completedSet.has(m));

  const handleComplete = () => {
    if (!selectedClassId) return;
    const classId = selectedClassId;
    const targets = selectedMaterials.filter((m) => !completedSet.has(m));
    if (targets.length === 0) return;
    // 낙관적 업데이트 — 누르는 즉시 '학습 완료됨' 표시, API는 백그라운드
    setCompletedSet((prev) => new Set([...prev, ...targets]));
    bumpStatus(); // 사이드바 배지 동기화
    Promise.all(
      targets.map((m) => markComplete({ class_id: classId, material_name: m })),
    ).catch(() => {
      // 실패 시 되돌림
      setCompletedSet((prev) => {
        const next = new Set(prev);
        targets.forEach((t) => next.delete(t));
        return next;
      });
      bumpStatus();
    });
  };

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

  // 클래스는 있지만 선택 안 됨 — 실행 가능한 CTA (모바일엔 사이드바가 없으므로)
  if (!selectedClassId) {
    return (
      <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center px-6 py-12 text-center">
        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-[20px] bg-primary-500 text-3xl font-bold text-white shadow-[0_10px_22px_-8px_rgba(18,184,134,0.6)]">
          T
        </div>
        <h2 className="text-xl font-bold text-warm-900">어떤 수업을 공부할까요?</h2>
        <p className="mt-2 mb-6 text-sm leading-relaxed text-warm-500">
          클래스를 고르면 그 강의 자료를 바탕으로
          <br />
          과외·Q&amp;A·퀴즈를 바로 시작할 수 있어요.
        </p>
        <button
          onClick={openSidebar}
          className="flex h-[52px] items-center rounded-2xl bg-primary-500 px-7 text-base font-bold text-white shadow-[0_8px_18px_-6px_rgba(18,184,134,0.6)] transition-transform active:scale-[0.98]"
        >
          클래스 선택하기
        </button>
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

  // 클래스 + 자료 있음: 카드 (가로형·축소, 4개가 한눈에)
  return (
    <div className="mx-auto max-w-xl px-4 py-8">
      <div className="mb-6 text-center">
        <h2 className="text-xl font-bold text-warm-900">무엇을 도와드릴까요?</h2>
        <p className="mt-1.5 text-sm font-semibold text-primary-600">아래를 누르거나 바로 질문해 보세요</p>
      </div>

      <div className="space-y-2.5">
        {CARDS.map((card) => {
          // 과외·Q&A는 임의 질문 대신 안내만 띄우고 사용자 입력을 기다린다.
          // 퀴즈는 바로 생성 요청을 보낸다.
          const handleClick = () => {
            if (card.type === "tutor") {
              promptGreeting(
                "무엇을 도와드릴까요? 이해가 어려운 부분이나 더 알고 싶은 주제를 편하게 말씀해 주세요.",
              );
            } else if (card.type === "qna") {
              promptGreeting("무엇을 도와드릴까요? 모르는 용어나 개념을 물어보세요.");
            } else {
              onSend(card.fallback);
            }
          };
          return (
            <button
              key={card.type}
              onClick={handleClick}
              className={`flex w-full items-center gap-3 rounded-2xl border p-3.5 text-left transition-all active:scale-[0.99] ${card.color}`}
            >
              <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${card.iconBg}`}>
                {card.icon}
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-[15px] font-extrabold text-warm-900">{card.title}</h3>
                <p className="truncate text-xs text-warm-500">{card.desc}</p>
              </div>
              <span className="text-lg text-warm-300">›</span>
            </button>
          );
        })}

        {/* 인덱스 / 듣기 — 자료 선택 시 (서로 다른 모드로 분리) */}
        {onOpenIndex && (
          <>
            <button
              onClick={() => onOpenIndex('index')}
              className="flex w-full items-center gap-3 rounded-2xl border border-[#a06ff0]/25 bg-[#a06ff0]/10 p-3.5 text-left transition-all active:scale-[0.99]"
            >
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#a06ff0] text-lg">
                📑
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-[15px] font-extrabold text-warm-900">인덱스</h3>
                <p className="truncate text-xs text-warm-500">핵심 목차로 이번 차시를 한눈에</p>
              </div>
              <span className="text-lg text-warm-300">›</span>
            </button>
            <button
              onClick={() => onOpenIndex('audio')}
              className="flex w-full items-center gap-3 rounded-2xl border border-[#15aabf]/25 bg-[#15aabf]/10 p-3.5 text-left transition-all active:scale-[0.99]"
            >
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#15aabf] text-lg">
                🎧
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-[15px] font-extrabold text-warm-900">듣기</h3>
                <p className="truncate text-xs text-warm-500">원문을 문장 하이라이트와 함께 낭독</p>
              </div>
              <span className="text-lg text-warm-300">›</span>
            </button>
          </>
        )}
      </div>

      {/* 학습 완료 — 자료 선택 시. 완료하면 다음날 복습 퀴즈 생성 */}
      {selectedMaterials.length > 0 && (
        <div className="mt-4 border-t border-warm-100 pt-4">
          {allCompleted ? (
            <div className="flex w-full items-center justify-center gap-2 rounded-2xl border border-primary-200 bg-primary-50 py-3.5 text-[15px] font-bold text-primary-600">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M5 12l4.5 4.5L19 7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              학습 완료됨
            </div>
          ) : (
            <button
              onClick={handleComplete}
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-primary-500 py-3.5 text-[15px] font-bold text-white shadow-[0_8px_18px_-8px_rgba(18,184,134,0.6)] transition-transform active:scale-[0.99]"
            >
              학습 완료
            </button>
          )}
          <p className="mt-2 text-center text-[11px] text-warm-400">
            완료하면 다음 날 복습 퀴즈가 만들어져요
          </p>
        </div>
      )}
    </div>
  );
}
