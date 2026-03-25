"""자료 검색 에이전트: File Search로 강의 자료를 검색하고 정리합니다."""

from langchain.agents import create_agent

from . import DEFAULT_MODEL
from .prompts import TRANSFER_SUFFIX
from .tools.tutor_tools import search_material
from .tools.shared_tools import transfer_to_agent

MATERIAL_SEARCHER_TOOLS = [
    search_material,
    transfer_to_agent,
]

MATERIAL_SEARCHER_PROMPT = """당신은 강의 자료 검색 전문가입니다.
사용자가 요청한 과목/주차의 학습 자료를 검색하여 핵심 내용을 정리합니다.

## 도구 사용 지침

1. **search_material** → 과목명과 주차를 전달하여 자료 검색
2. **transfer_to_agent** → 자료 검색 완료 후 다음 에이전트로 전환
   - 퀴즈 생성이 필요하면 → transfer_to_agent("quiz_generator")
   - 질문 답변이 필요하면 → transfer_to_agent("learning_coach")

## 작업 순서

1. search_material 도구로 자료 검색
2. 검색 결과가 충분한지 확인 (500자 이상)
3. 부족하면 다른 검색어로 재시도
4. 충분하면 검색 결과를 정리하여 응답
""" + TRANSFER_SUFFIX

material_searcher = create_agent(
    model=DEFAULT_MODEL,
    tools=MATERIAL_SEARCHER_TOOLS,
    system_prompt=MATERIAL_SEARCHER_PROMPT,
)
