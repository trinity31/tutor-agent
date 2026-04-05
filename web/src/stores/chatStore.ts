import { create } from 'zustand';
import { streamChat, apiPost, type SSEEvent } from '../api/client';

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

interface ChatState {
  messages: Message[];
  threadId: string;
  isStreaming: boolean;
  agentStatus: { agent: string; label: string } | null;
  error: string | null;
  quizData: QuizData | null;
  quizIndex: number;
  quizAnswers: QuizAnswer[];
  sendMessage: (text: string, classId?: string, materialName?: string) => Promise<void>;
  newChat: () => Promise<void>;
  answerQuiz: (selected: string) => void;
  quitQuiz: () => void;
  clearError: () => void;
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

  sendMessage: async (text: string, classId?: string, materialName?: string) => {
    const { threadId } = get();

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
    const isCorrect = selected === correctAnswer;

    set({
      quizAnswers: [
        ...quizAnswers,
        {
          question: q.question,
          selected,
          answer: correctAnswer,
          correct: isCorrect,
          explanation: q.explanation,
        },
      ],
      quizIndex: quizIndex + 1,
    });
  },

  quitQuiz: () => {
    set({ quizData: null, quizIndex: 0, quizAnswers: [] });
  },

  clearError: () => set({ error: null }),
}));
