import { useEffect, useState } from "react";
import { apiGet } from "../../api/client";

const CARDS = [
  {
    type: "tutor",
    title: "1:1 과외",
    desc: "주제를 쉽게 설명하고 이해도를 확인해요",
    example: "음식인문학 1주차 내용 복습을 도와주세요",
    color: "bg-primary-50 border-primary-200",
    iconBg: "bg-primary-500",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 6.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5zM7 20v-1a5 5 0 0110 0v1"
          stroke="white"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <path
          d="M17 14a3 3 0 013 3v1M17 10a2 2 0 100-4"
          stroke="white"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  {
    type: "qna",
    title: "Q&A",
    desc: "모르는 용어나 개념을 간단히 물어보세요",
    example: "아비투스란 무엇인가요?",
    color: "bg-accent-300/15 border-accent-400/30",
    iconBg: "bg-accent-400",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="1.5" />
        <path
          d="M9.5 10a2.5 2.5 0 015 0c0 1.5-2.5 2-2.5 3.5M12 17h.01"
          stroke="white"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  {
    type: "quiz",
    title: "퀴즈",
    desc: "학습자료 기반 퀴즈를 풀어보세요",
    example: "음식인문학 1주차 퀴즈 내줘",
    color: "bg-success-400/10 border-success-400/30",
    iconBg: "bg-success-500",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <rect
          x="4"
          y="4"
          width="16"
          height="16"
          rx="3"
          stroke="white"
          strokeWidth="1.5"
        />
        <path
          d="M9 12l2 2 4-4"
          stroke="white"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
];

interface ExampleMsg {
  type: string;
  message: string;
}

export default function OnboardingCards({
  onSend,
}: {
  onSend: (text: string) => void;
}) {
  const [examples, setExamples] = useState<ExampleMsg[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiGet<{ examples: ExampleMsg[] }>("/examples")
      .then((res) => setExamples(res.examples))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const getExample = (type: string) => {
    const found = examples.find((e) => e.type === type);
    return found?.message;
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-500 text-2xl font-bold text-white">
          T
        </div>
        <h2 className="text-xl font-bold text-warm-900">
          안녕하세요! AI 과외 선생님이에요
        </h2>
        <p className="mt-2 text-sm text-warm-500">
          아래 카드를 눌러 시작하거나, 직접 메시지를 입력해 보세요
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-warm-500">
          <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary-400" />
          메시지 카드 불러오는 중...
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          {CARDS.map((card) => {
            const customExample = getExample(card.type);
            return (
              <button
                key={card.type}
                onClick={() => onSend(customExample || card.example)}
                className={`group flex flex-col items-start rounded-2xl border p-5 text-left transition-all hover:scale-[1.02] hover:shadow-md active:scale-[0.98] ${card.color}`}
              >
                <div
                  className={`mb-3 flex h-10 w-10 items-center justify-center rounded-xl ${card.iconBg}`}
                >
                  {card.icon}
                </div>
                <h3 className="mb-1 text-sm font-bold text-warm-900">
                  {card.title}
                </h3>
                <p className="mb-3 text-xs text-warm-500 leading-relaxed">
                  {card.desc}
                </p>
                <p className="text-xs font-medium text-warm-600 group-hover:text-primary-600 transition-colors">
                  &ldquo;{customExample || card.example}&rdquo;
                </p>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
