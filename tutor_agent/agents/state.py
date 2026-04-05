"""TutorAgent 상태 정의."""

from typing import Annotated
from langgraph.graph import MessagesState


class TutorAgentState(MessagesState):
    """TutorAgent 그래프의 공유 상태.

    MessagesState를 상속하여 messages 필드를 기본 포함합니다.
    """

    # 현재 활성 에이전트
    current_agent: str = ""

    # 명령 정보
    command_type: str = ""          # "start" | "done" | "quiz" | "ask" | "memo"
    user_message: str = ""          # "풍수학개론 3주차"

    # 학습 세션
    session_active: bool = False
    session_subject: str = ""       # 현재 세션 과목/주차
    memos: list[str] = []           # 세션 중 누적된 메모

    # 자료 검색 결과
    material: str = ""
    material_valid: bool = False

    # 퀴즈
    quiz: dict = {}
    quiz_valid: bool = False
    generation_attempts: int = 0

    # 질문 답변
    answer: str = ""

    # 사용자 정보
    user_id: str = ""
    class_id: str = ""
    material_name: str = ""
    store_name: str = ""

    # 에러
    error: str = ""
