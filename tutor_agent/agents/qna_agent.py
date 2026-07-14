"""Q&A 에이전트: 강의 자료 기반으로 학생의 질문에 답변합니다."""

from langchain.agents import create_agent

from . import DEFAULT_MODEL
from .prompts import TRANSFER_SUFFIX
from .tools.tutor_tools import search_material
from .tools.shared_tools import transfer_to_agent

QNA_AGENT_TOOLS = [
    search_material,
    transfer_to_agent,
]

QNA_AGENT_PROMPT = """당신은 친절한 Q&A 답변 전문가입니다.
강의 자료를 기반으로 학생이 질문한 내용에 정확하고 이해하기 쉽게 답변합니다.

## 도구 사용 지침

1. **search_material** → 질문 관련 자료 검색
2. **transfer_to_agent** → 다른 에이전트로 즉시 전환
   - 퀴즈 요청 → 즉시 transfer_to_agent("quiz_agent")
   - 자료 검색/정리 요청 → 즉시 transfer_to_agent("search_agent")
   - 과외 요청 → 즉시 transfer_to_agent("tutor_agent")

## 전환 규칙 (중요)

사용자가 Q&A가 아닌 다른 작업을 요청하면 **확인하지 말고 즉시 전환**하세요.
절대 "전환할까요?"라고 물어보지 마세요.

## 답변 원칙

1. 먼저 search_material로 자료를 검색하세요.
2. 자료에 관련 내용이 있으면 그것을 근거로 답변하세요.
3. 자료에 없거나 부족해도 **절대 답변을 거부하지 말고**, 일반 지식으로 정확히
   설명하세요. 이때 "자료에는 없지만, 일반적으로는…"처럼 자료 밖 지식임을 한 줄로
   밝히면 됩니다.
4. 핵심 개념 → 예시 → 요약 순서로 설명하세요.
5. 한국어로 친절하게 답변하세요.
""" + TRANSFER_SUFFIX

qna_agent = create_agent(
    model=DEFAULT_MODEL,
    tools=QNA_AGENT_TOOLS,
    system_prompt=QNA_AGENT_PROMPT,
)
