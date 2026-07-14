import { useRef, useEffect, useState } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { useClassStore } from '../../stores/classStore';
import { LAST_MATERIAL_KEY, useAudioStore } from '../../stores/audioStore';
import { markMaterialStarted } from '../../api/client';
import MessageBubble from './MessageBubble';
import AgentStatus from './AgentStatus';
import ChatInput from './ChatInput';
import OnboardingCards from '../onboarding/OnboardingCards';
import QuizCard from '../quiz/QuizCard';
import QuizResult from '../quiz/QuizResult';
import ErrorMessage from '../common/ErrorMessage';
import MaterialIndexPanel from '../material/MaterialIndexPanel';

export default function ChatArea() {
  const {
    messages,
    isStreaming,
    agentStatus,
    error,
    quizData,
    quizIndex,
    quizAnswers,
    lastQuizResultId,
    sendMessage,
    answerQuiz,
    quitQuiz,
    clearError,
  } = useChatStore();

  const { classes, selectedClassId, selectedMaterials, materials, selectClass, toggleMaterial } =
    useClassStore();
  const selectedClass = classes.find((c) => c.id === selectedClassId);

  const indexableMaterial =
    selectedClassId && selectedMaterials.length === 1 ? selectedMaterials[0] : null;
  const [indexPanelOpen, setIndexPanelOpen] = useState(true);
  const [panelMode, setPanelMode] = useState<'index' | 'audio' | 'note'>('index');

  // 과외·Q&A·퀴즈·인덱스·듣기 중 하나라도 하면 '학습중'으로 기록 (자료당 세션 1회)
  const markedRef = useRef<Set<string>>(new Set());
  const markStarted = (material: string | null | undefined) => {
    if (!selectedClassId || !material) return;
    const key = `${selectedClassId}::${material}`;
    if (markedRef.current.has(key)) return;
    markedRef.current.add(key);
    markMaterialStarted(selectedClassId, material);
  };

  const openPanel = (mode: 'index' | 'audio' | 'note') => {
    setPanelMode(mode);
    setIndexPanelOpen(true);
    markStarted(indexableMaterial); // 인덱스·듣기·메모
  };

  // 모바일(<md)에서는 패널을 전체 화면 오버레이로 띄운다
  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia('(max-width: 767px)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const sync = () => setIsMobile(mq.matches);
    mq.addEventListener('change', sync);
    window.addEventListener('resize', sync);
    return () => {
      mq.removeEventListener('change', sync);
      window.removeEventListener('resize', sync);
    };
  }, []);

  useEffect(() => {
    // 데스크톱은 자료 선택 시 자동으로 열고(= 인덱스 활동), 모바일은 버튼으로 연다
    if (indexableMaterial) {
      setIndexPanelOpen(!isMobile);
      if (!isMobile) markStarted(indexableMaterial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indexableMaterial]);

  // --- 재접속 복귀: 마지막으로 듣던 자료의 낭독을 다시 연다 ---
  const resumedRef = useRef(false);
  const pendingResumeRef = useRef<string | null>(null);
  const [resuming, setResuming] = useState(false);

  // 1) 최초 1회, 아직 아무것도 선택 안 했을 때 저장된 자료의 클래스를 선택
  useEffect(() => {
    if (resumedRef.current) return;
    if (selectedClassId) {
      resumedRef.current = true; // 사용자가 이미 선택함 — 복원 안 함
      return;
    }
    if (classes.length === 0) return; // 클래스 로드 대기
    resumedRef.current = true;
    try {
      const raw = localStorage.getItem(LAST_MATERIAL_KEY);
      if (!raw) return;
      const { classId, materialName } = JSON.parse(raw);
      if (classId && materialName && classes.some((c) => c.id === classId)) {
        pendingResumeRef.current = materialName;
        setResuming(true);
        selectClass(classId); // 자료 목록 로드
      }
    } catch {
      /* ignore */
    }
  }, [classes, selectedClassId, selectClass]);

  // 2) 자료 목록이 로드되면 마지막 자료 선택
  useEffect(() => {
    const pending = pendingResumeRef.current;
    if (pending && materials.includes(pending) && selectedMaterials.length === 0) {
      pendingResumeRef.current = null;
      toggleMaterial(pending);
    }
  }, [materials, selectedMaterials, toggleMaterial]);

  // 3) 자료가 선택되면 낭독 패널을 연다 (자동 열림/닫힘 효과 이후에 확실히)
  useEffect(() => {
    if (resuming && indexableMaterial) {
      setPanelMode('audio');
      setIndexPanelOpen(true);
      setResuming(false);
    }
  }, [resuming, indexableMaterial]);

  // 패널 폭 — 좌측 가장자리 드래그로 조절, localStorage에 유지
  const [panelWidth, setPanelWidth] = useState(
    () => Number(localStorage.getItem('tutor-panel-width')) || 448,
  );

  const startPanelResize = (e: React.MouseEvent) => {
    e.preventDefault();
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    let latest = panelWidth;
    const onMove = (ev: MouseEvent) => {
      const max = Math.min(900, window.innerWidth * 0.7);
      latest = Math.min(Math.max(window.innerWidth - ev.clientX, 360), max);
      setPanelWidth(latest);
    };
    const onUp = () => {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      localStorage.setItem('tutor-panel-width', String(latest));
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, quizIndex, agentStatus]);

  const lastMsg = messages.length > 0 ? messages[messages.length - 1] : null;
  const showQuickReplies =
    lastMsg?.role === 'assistant' &&
    !isStreaming &&
    !quizData &&
    (lastMsg.agent === 'tutor_agent' || lastMsg.agent === 'qna_agent');

  const quickReplies =
    lastMsg?.agent === 'tutor_agent'
      ? ['네', '아니오', '더 설명해 주세요', '퀴즈 내주세요']
      : ['더 자세히 알려주세요', '퀴즈 내주세요'];

  const showOnboarding = messages.length === 0 && !quizData && !isStreaming;
  const showQuizResult =
    quizData && quizIndex >= quizData.questions.length && quizAnswers.length > 0;
  const showQuizQuestion =
    quizData && quizIndex < quizData.questions.length;

  const handleSend = (text: string) => {
    const materialNames = selectedMaterials.length > 0 ? selectedMaterials.join('|') : undefined;
    selectedMaterials.forEach(markStarted); // 과외·Q&A·퀴즈(및 직접 입력)
    sendMessage(text, selectedClassId || undefined, materialNames);
  };

  // 원본 뷰 "이 페이지에서 질문" — 그 페이지 텍스트를 맥락으로 붙여 채팅으로 보낸다
  const handleAskPage = (page: number, question: string) => {
    const manifest = useAudioStore.getState().manifest;
    const pageText = (manifest?.chunks ?? [])
      .filter((c) => c.page === page)
      .map((c) => c.text)
      .join(' ')
      .trim();
    const composed = pageText
      ? `다음은 교재 ${page}페이지 내용입니다:\n"""\n${pageText}\n"""\n\n위 페이지를 참고해 답해 주세요. 페이지에 없으면 일반 지식으로 설명해도 됩니다.\n질문: ${question}`
      : `교재 ${page}페이지에 대한 질문(자료에 없으면 일반 지식으로 답해도 됨): ${question}`;
    handleSend(composed);
    if (isMobile) setIndexPanelOpen(false); // 모바일은 패널을 닫아 답변이 보이게
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="relative flex flex-1 flex-col overflow-hidden">
      {/* Context bar */}
      {selectedClass && (
        <div className="flex items-center gap-2 border-b border-warm-100 bg-primary-50/50 px-4 py-2">
          <span className="text-xs font-semibold text-primary-600">
            {selectedClass.name}
          </span>
          {selectedMaterials.length > 0 && (
            <>
              <span className="text-xs text-warm-400">/</span>
              <span className="text-xs font-medium text-primary-500 truncate max-w-xs">
                {selectedMaterials.length === 1
                  ? selectedMaterials[0]
                  : `${selectedMaterials.length}개 자료 선택`}
              </span>
            </>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {showOnboarding ? (
          <OnboardingCards
            onSend={handleSend}
            hasClasses={classes.length > 0}
            selectedClassId={selectedClassId}
            onOpenIndex={indexableMaterial ? openPanel : undefined}
          />
        ) : (
          <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {showQuickReplies && (
              <div className="flex flex-wrap gap-2 pl-11">
                {quickReplies.map((text) => (
                  <button
                    key={text}
                    onClick={() => handleSend(text)}
                    className="rounded-full border border-primary-300 bg-white px-3 py-1.5 text-xs font-medium text-primary-600 hover:bg-primary-50 active:scale-95 transition-all"
                  >
                    {text}
                  </button>
                ))}
              </div>
            )}

            {isStreaming && <AgentStatus status={agentStatus} />}

            {showQuizQuestion && (
              <QuizCard
                key={quizIndex}
                question={quizData!.questions[quizIndex]}
                index={quizIndex}
                total={quizData!.questions.length}
                onAnswer={answerQuiz}
                onQuit={quitQuiz}
              />
            )}

            {showQuizResult && (
              <QuizResult answers={quizAnswers} quizResultId={lastQuizResultId} onClose={quitQuiz} />
            )}

            {error && (
              <ErrorMessage
                message={error}
                onRetry={() => {
                  clearError();
                  const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
                  if (lastUserMsg) handleSend(lastUserMsg.content);
                }}
                onDismiss={clearError}
              />
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* 듣기로 바로가기 — 컴포저 위 오른쪽 플로팅 (자료 선택됨 + 패널 닫힘) */}
      {indexableMaterial && !indexPanelOpen && !showQuizQuestion && !showQuizResult && (
        <button
          onClick={() => openPanel('audio')}
          className="absolute right-4 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-20 flex items-center gap-1.5 rounded-full bg-primary-500 px-4 py-2.5 text-sm font-bold text-white shadow-[0_8px_20px_-6px_rgba(18,184,134,0.6)] active:scale-95 transition-transform"
        >
          🎧 듣기
        </button>
      )}

      {/* Input */}
      {!showQuizQuestion && !showQuizResult && (
        <ChatInput
          onSend={handleSend}
          disabled={isStreaming}
          placeholder={
            !selectedClassId
              ? '클래스를 먼저 선택해 주세요'
              : '메시지를 입력하세요'
          }
          inputDisabled={!selectedClassId}
        />
      )}
      </div>

      {/* Index panel (자료 1개 선택 시) — 데스크톱: 사이드 패널(드래그 폭 조절),
          모바일: 전체 화면 오버레이. 오디오 요소 중복을 피하기 위해 한쪽만 렌더링 */}
      {indexableMaterial && indexPanelOpen && selectedClassId && (
        isMobile ? (
          <div className="fixed inset-0 z-50 bg-white">
            <MaterialIndexPanel
              classId={selectedClassId}
              materialName={indexableMaterial}
              onClose={() => setIndexPanelOpen(false)}
              initialMode={panelMode}
              onAskPage={handleAskPage}
            />
          </div>
        ) : (
          <div className="flex shrink-0" style={{ width: panelWidth }}>
            <div
              onMouseDown={startPanelResize}
              className="w-1.5 shrink-0 cursor-col-resize bg-transparent hover:bg-primary-300 active:bg-primary-400 transition-colors"
              title="드래그하여 패널 크기 조절"
            />
            <div className="min-w-0 flex-1">
              <MaterialIndexPanel
                classId={selectedClassId}
                materialName={indexableMaterial}
                onClose={() => setIndexPanelOpen(false)}
                initialMode={panelMode}
                onAskPage={handleAskPage}
              />
            </div>
          </div>
        )
      )}
    </div>
  );
}
