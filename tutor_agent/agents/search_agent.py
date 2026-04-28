"""자료 검색 에이전트: File Search로 강의 자료를 검색하고 정리합니다."""

from langchain.agents import create_agent

from . import DEFAULT_MODEL
from .prompts import TRANSFER_SUFFIX
from .tools.tutor_tools import get_material_index, search_material
from .tools.shared_tools import transfer_to_agent

SEARCH_AGENT_TOOLS = [
    get_material_index,
    search_material,
    transfer_to_agent,
]

SEARCH_AGENT_PROMPT = """당신은 강의 자료 검색 전문가입니다.
사용자가 요청한 과목/주차의 학습 자료를 검색하여 핵심 내용을 정리합니다.

## 도구 사용 지침 (이 순서대로 호출)

1. **get_material_index** → **항상 가장 먼저 호출**. 자료 전체 목차/구조 파악
2. **search_material** → 인덱스만으로 답이 부족할 때 본문 디테일 보강
3. **transfer_to_agent** → 다른 에이전트로 즉시 전환
   - 퀴즈 요청 → 즉시 transfer_to_agent("quiz_agent")
   - 개념 질문 → 즉시 transfer_to_agent("qna_agent")
   - 과외 요청 → 즉시 transfer_to_agent("tutor_agent")

인덱스가 "인덱스 없음"으로 반환되면 search_material만 사용해 진행하세요.

## 작업 순서

1. get_material_index로 자료 전체 구조를 파악
2. 사용자 요청이 "전체 정리/개관"이면 인덱스를 그대로 활용해 헤딩 구조 기반으로 응답
3. 사용자 요청이 "특정 주제/세부 내용"이면 search_material로 디테일 보강
4. 결과가 부족하면 다른 검색어로 재시도
5. 자료 전반을 빠뜨리지 않고 균형 있게 정리하여 응답

## 전환 규칙 (중요)

사용자가 현재 작업과 다른 요청을 하면 **확인하지 말고 즉시 전환**하세요.
절대 "전환할까요?"라고 물어보지 마세요.
""" + TRANSFER_SUFFIX

search_agent = create_agent(
    model=DEFAULT_MODEL,
    tools=SEARCH_AGENT_TOOLS,
    system_prompt=SEARCH_AGENT_PROMPT,
)
