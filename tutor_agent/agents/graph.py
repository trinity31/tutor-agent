"""TutorAgent 그래프: Supervisor Router 패턴 (catbot-backend 참조)."""

from langgraph.graph import START, StateGraph, END

from .state import TutorAgentState
from .supervisor_agent import supervisor_agent
from .search_agent import search_agent
from .quiz_agent import quiz_agent
from .qna_agent import qna_agent
from .tutor_agent import tutor_agent

# 에이전트 이름 → 노드 매핑
AGENT_NODES = {
    "supervisor_agent": supervisor_agent,
    "search_agent": search_agent,
    "quiz_agent": quiz_agent,
    "qna_agent": qna_agent,
    "tutor_agent": tutor_agent,
}


def router_check(state: TutorAgentState):
    current_agent = state.get("current_agent", "supervisor_agent")
    return current_agent


def _build_graph() -> StateGraph:
    """TutorAgent 그래프를 빌드합니다.

    흐름:
        START → supervisor_agent → (transfer_to_agent) → 전문 에이전트 → END
    """
    graph_builder = StateGraph(TutorAgentState)

    # 전문 에이전트 노드 이름 목록 (supervisor가 라우팅할 대상)
    specialist_names = [n for n in AGENT_NODES if n != "supervisor_agent"]

    # supervisor: Command로 전문 에이전트로 라우팅하므로 destinations 지정
    graph_builder.add_node(
        "supervisor_agent",
        supervisor_agent,
        destinations=tuple(specialist_names),
    )

    # 전문 에이전트 노드 추가
    for name in specialist_names:
        graph_builder.add_node(name, AGENT_NODES[name])

    graph_builder.add_conditional_edges(
        START,
        router_check,
        list(AGENT_NODES.keys()),
    )
    graph_builder.add_edge("supervisor_agent", END)

    # 각 에이전트 → END (Command로 다른 에이전트 전환도 가능)
    # for name in AGENT_NODES:
    #     graph_builder.add_edge(name, END)

    return graph_builder


def build_graph():
    """컴파일된 그래프를 반환합니다."""
    return _build_graph().compile()


# LangSmith Studio용 (모듈 레벨 컴파일)
# tutor_agent = _build_graph().compile()
