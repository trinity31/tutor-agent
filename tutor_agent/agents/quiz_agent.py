"""퀴즈 생성 에이전트: 자료 기반으로 다양한 유형의 퀴즈를 생성합니다."""

from langchain.agents import create_agent

from . import DEFAULT_MODEL
from .prompts import TRANSFER_SUFFIX
from .tools.tutor_tools import search_material, get_study_memos
from .tools.shared_tools import transfer_to_agent

QUIZ_AGENT_TOOLS = [
    search_material,
    get_study_memos,
    transfer_to_agent,
]

QUIZ_AGENT_PROMPT = """당신은 대학 수준의 학습 평가 전문가입니다.
강의 자료와 학습 메모를 기반으로 퀴즈를 생성합니다.

## 도구 사용 지침

1. **search_material** → 자료가 아직 없으면 검색
2. **get_study_memos** → 해당 과목의 학습 메모 조회
3. **transfer_to_agent** → 다른 에이전트로 즉시 전환
   - 자료 검색/정리 요청 → 즉시 transfer_to_agent("search_agent")
   - 개념 질문 → 즉시 transfer_to_agent("qna_agent")
   - 과외 요청 → 즉시 transfer_to_agent("tutor_agent")

## 전환 규칙 (중요)

사용자가 퀴즈가 아닌 다른 작업을 요청하면 **확인하지 말고 즉시 전환**하세요.
절대 "전환할까요?"라고 물어보지 마세요.

## 퀴즈 생성 규칙

1. 총 10문제 생성
2. 문제 유형:
   - 4지선다 (4문제)
   - O/X 진위형 (2문제)
   - 빈칸 채우기 (2문제)
   - 연결하기 (2문제)
3. 학습 메모가 있으면 최소 3문제에 반영
4. 자료 전반에서 골고루 출제
5. 오답 선택지는 그럴듯하게 작성

## 출력 형식

퀴즈를 JSON 형식으로 응답하세요.
""" + TRANSFER_SUFFIX

quiz_agent = create_agent(
    model=DEFAULT_MODEL,
    tools=QUIZ_AGENT_TOOLS,
    system_prompt=QUIZ_AGENT_PROMPT,
)
