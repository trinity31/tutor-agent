import { create } from 'zustand';
import { streamChat, apiPost, saveQuizResult, type SSEEvent } from '../api/client';
import { useClassStore } from './classStore';
import { track } from '../lib/analytics';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  agent?: string;
  agentLabel?: string;
  type?: 'text' | 'quiz';
}

export interface QuizData {
  quiz_title?: string;
  questions: QuizQuestion[];
}

export interface QuizQuestion {
  question: string;
  type: string;
  options: string[];
  answer: string;
  correct?: string;
  explanation?: string;
}

/** 보기·정답 앞의 번호/접두어("A.", "나)", "①")와 잉여 공백을 제거한다.
 *  LLM이 보기엔 "A. "를 붙이고 answer엔 안 붙이는 경우가 있어, 이걸 무시해야 정확히 비교된다. */
export function stripOptionPrefix(s: string): string {
  return (s || '')
    .trim()
    .replace(/^[A-Za-z0-9가-힣]\s*[.)．、]\s*/, '')
    .replace(/^[①-⑳]\s*/, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/** 접두어·공백 차이를 무시하고 정답 여부를 판정한다.
 *  answer가 보기 문자(A~D)만 있으면 실제 선택지 텍스트로 환원해 비교한다. */
export function isCorrectAnswer(selected: string, answer: string, options: string[] = []): boolean {
  let ans = (answer || '').trim();
  const letter = ans.match(/^([A-Da-d])$/);
  if (letter && options.length) {
    const idx = letter[1].toUpperCase().charCodeAt(0) - 65;
    if (options[idx] != null) ans = options[idx];
  }
  return stripOptionPrefix(selected) === stripOptionPrefix(ans);
}

interface ChatState {
  messages: Message[];
  threadId: string;
  isStreaming: boolean;
  agentStatus: { agent: string; label: string } | null;
  error: string | null;
  quizData: QuizData | null;
  quizIndex: number;
  quizAnswers: QuizAnswer[];
  lastQuizResultId: string | null;
  sendMessage: (text: string, classId?: string, materialName?: string) => Promise<void>;
  newChat: () => Promise<void>;
  answerQuiz: (selected: string) => void;
  quitQuiz: () => void;
  clearError: () => void;
  /** 카드로 대화 시작 시 임의 질문 대신 안내 메시지만 띄운다(사용자 입력 대기) */
  promptGreeting: (greeting: string) => void;
}

export interface QuizAnswer {
  question: string;
  selected: string;
  answer: string;
  correct: boolean;
  explanation?: string;
}

let _nextId = 0;
const msgId = () => `msg-${++_nextId}`;

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  threadId: crypto.randomUUID(),
  isStreaming: false,
  agentStatus: null,
  error: null,
  quizData: null,
  quizIndex: 0,
  quizAnswers: [],
  lastQuizResultId: null,

  sendMessage: async (text: string, classId?: string, materialName?: string) => {
    const { threadId } = get();

    // 메시지 본문은 보내지 않고 발생 사실만 계측
    track('chat_message', { class_id: classId || '', has_material: !!materialName });

    // 사용자 메시지 추가
    set((s) => ({
      messages: [...s.messages, { id: msgId(), role: 'user', content: text }],
      isStreaming: true,
      agentStatus: null,
      error: null,
    }));

    try {
      let assistantContent = '';
      let assistantAgent = '';
      let assistantLabel = '';

      await streamChat(text, threadId, classId || '', materialName || '', (event: SSEEvent) => {
        switch (event.event) {
          case 'agent_status':
            set({
              agentStatus: {
                agent: event.data.agent as string,
                label: event.data.label as string,
              },
            });
            break;
          case 'message':
            assistantContent = event.data.content as string;
            assistantAgent = event.data.agent as string;
            assistantLabel = event.data.label as string;
            break;
          case 'quiz':
            set({
              quizData: event.data as unknown as QuizData,
              quizIndex: 0,
              quizAnswers: [],
            });
            set((s) => ({
              messages: [
                ...s.messages,
                {
                  id: msgId(),
                  role: 'assistant',
                  content: '퀴즈가 생성되었습니다!',
                  type: 'quiz',
                },
              ],
            }));
            break;
          case 'error':
            set({ error: event.data.message as string });
            break;
        }
      });

      // 일반 메시지인 경우 추가
      if (assistantContent) {
        set((s) => ({
          messages: [
            ...s.messages,
            {
              id: msgId(),
              role: 'assistant',
              content: assistantContent,
              agent: assistantAgent,
              agentLabel: assistantLabel,
            },
          ],
        }));
      }
    } catch (e) {
      set({ error: (e as Error).message });
    } finally {
      set({ isStreaming: false, agentStatus: null });
    }
  },

  newChat: async () => {
    try {
      const res = await apiPost<{ thread_id: string }>('/chat/new', {});
      set({
        messages: [],
        threadId: res.thread_id,
        quizData: null,
        quizIndex: 0,
        quizAnswers: [],
        error: null,
      });
    } catch {
      set({ messages: [], threadId: crypto.randomUUID(), quizData: null });
    }
  },

  answerQuiz: (selected: string) => {
    const { quizData, quizIndex, quizAnswers } = get();
    if (!quizData) return;

    const q = quizData.questions[quizIndex];
    const correctAnswer = q.answer || q.correct || '';
    const isCorrect = isCorrectAnswer(selected, correctAnswer, q.options || []);

    const newAnswer: QuizAnswer = {
      question: q.question,
      selected,
      answer: correctAnswer,
      correct: isCorrect,
      explanation: q.explanation,
    };
    const newAnswers = [...quizAnswers, newAnswer];

    set({
      quizAnswers: newAnswers,
      quizIndex: quizIndex + 1,
    });

    // 마지막 문제 → 결과 자동 저장
    if (quizIndex + 1 >= quizData.questions.length) {
      const score = newAnswers.filter((a) => a.correct).length;
      const classState = useClassStore.getState();
      saveQuizResult({
        class_id: classState.selectedClassId || '',
        material_name: classState.selectedMaterials.join('|') || '',
        quiz_title: quizData.quiz_title || '',
        questions: quizData.questions,
        answers: newAnswers,
        score,
        total: newAnswers.length,
      })
        .then((res) => set({ lastQuizResultId: res.id }))
        .catch(() => {});
    }
  },

  quitQuiz: () => {
    set({ quizData: null, quizIndex: 0, quizAnswers: [] });
  },

  promptGreeting: (greeting: string) => {
    set((s) => ({
      messages: [
        ...s.messages,
        { id: msgId(), role: 'assistant', content: greeting },
      ],
    }));
  },

  clearError: () => set({ error: null }),
}));
