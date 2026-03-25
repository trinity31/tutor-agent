"""TutorAgent 그래프: Supervisor Router 패턴 (catbot-backend 참조)."""

from langgraph.graph import START, StateGraph, END

from .state import TutorAgentState
from .supervisor_agent import supervisor_agent
from .material_searcher import material_searcher
from .quiz_generator import quiz_generator
from .learning_coach import learning_coach

# 에이전트 이름 → 노드 매핑
AGENT_NODES = {
    "supervisor_agent": supervisor_agent,
    "material_searcher": material_searcher,
    "quiz_generator": quiz_generator,
    "learning_coach": learning_coach,
}


def _build_graph() -> StateGraph:
    """TutorAgent 그래프를 빌드합니다.

    흐름:
        START → supervisor_agent → (transfer_to_agent) → 전문 에이전트 → END
    """
    graph_builder = StateGraph(TutorAgentState)

    # 모든 에이전트 노드 추가
    for name, agent in AGENT_NODES.items():
        graph_builder.add_node(name, agent)

    # START → supervisor_agent
    graph_builder.add_edge(START, "supervisor_agent")

    # 각 에이전트 → END (Command로 다른 에이전트 전환도 가능)
    for name in AGENT_NODES:
        graph_builder.add_edge(name, END)

    return graph_builder


def build_graph():
    """컴파일된 그래프를 반환합니다."""
    return _build_graph().compile()


# LangSmith Studio용 (모듈 레벨 컴파일)
tutor_agent = _build_graph().compile()
