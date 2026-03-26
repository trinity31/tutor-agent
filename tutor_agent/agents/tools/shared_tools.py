"""에이전트 간 전환 도구 (catbot-backend shared_tools 패턴)."""

from langchain_core.tools import tool
from langgraph.types import Command


@tool
def transfer_to_agent(agent_name: str):
    """다른 전문 에이전트로 전환합니다.

    Args:
        agent_name: 전환할 에이전트 이름
            - "search_agent": 강의 자료 검색
            - "quiz_agent": 퀴즈 생성
            - "qna_agent": Q&A (질문 답변)
            - "tutor_agent": 1:1 과외 (에이전트 주도 학습)
    """
    print(f"[TOOL] transfer_to_agent — goto={agent_name}")
    return Command(
        goto=agent_name,
        graph=Command.PARENT,
        update={"current_agent": agent_name},
    )
