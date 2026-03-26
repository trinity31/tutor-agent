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
2. **transfer_to_agent** → 퀴즈 생성 등 다른 작업이 필요할 때 전환

## 답변 원칙

1. 반드시 search_material로 자료를 먼저 검색하세요
2. 자료에 있는 내용만으로 답변하세요
3. 자료에 없는 내용은 "자료에서 확인할 수 없습니다"라고 답변하세요
4. 핵심 개념 → 예시 → 요약 순서로 설명하세요
5. 한국어로 친절하게 답변하세요
""" + TRANSFER_SUFFIX

qna_agent = create_agent(
    model=DEFAULT_MODEL,
    tools=QNA_AGENT_TOOLS,
    system_prompt=QNA_AGENT_PROMPT,
)
