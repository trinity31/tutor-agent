"""학습 도우미 도메인 도구."""

import json
import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from tutor_agent.file_search import search as file_search

logger = logging.getLogger(__name__)

_MIN_MATERIAL_LENGTH = 1500


@tool
def search_material(subject: str, config: RunnableConfig) -> str:
    """강의 자료를 검색합니다.

    Args:
        subject: 검색할 내용 또는 사용자 요청 (예: '핵심 개념 정리해줘')

    Returns:
        검색된 강의 자료 내용 (JSON 문자열)
    """
    cfg = config.get("configurable", {})
    user_id = cfg.get("user_id", "")
    class_id = cfg.get("class_id", "")
    material_name = cfg.get("material_name", "")
    store_name = cfg.get("store_name", "")
    print(f"[TOOL] search_material — subject={subject}, user_id={user_id}, class_id={class_id}, material={material_name}, store={store_name}")

    # material_name이 있으면 해당 파일에서 검색 (subject가 모호해도 OK)
    effective_subject = material_name or subject
    query = f"{effective_subject} 강의의 핵심 개념, 주요 용어, 중요 내용을 모두 정리해줘. 사용자 요청: {subject}"
    content = file_search(
        query=query,
        user_message=subject,
        display_name=material_name,
        store_name=store_name,
        user_id=user_id,
        class_id=class_id,
    )

    # 결과 부족 시 2차 검색 (쿼리 변형)
    if len(content.strip()) < _MIN_MATERIAL_LENGTH:
        logger.info(f"[TOOL] 1차 검색 결과 부족 ({len(content.strip())}자), 재시도")
        query2 = f"{effective_subject} 강의 전체 내용을 최대한 상세하게 정리해줘. 사용자 요청: {subject}"
        content = file_search(
            query=query2,
            user_message=subject,
            display_name=material_name,
            store_name=store_name,
            user_id=user_id,
            class_id=class_id,
        )

    result = {
        "subject": subject,
        "content": content,
        "char_count": len(content),
    }
    return json.dumps(result, ensure_ascii=False)


@tool
def get_study_memos(subject: str, config: RunnableConfig) -> str:
    """해당 과목의 학습 메모를 조회합니다.

    Args:
        subject: 과목명과 주차 (예: '양택풍수론 4주차')

    Returns:
        저장된 메모 목록 (JSON 문자열)
    """
    cfg = config.get("configurable", {})
    user_id = cfg.get("user_id", "")
    print(f"[TOOL] get_study_memos — subject={subject}, user_id={user_id}")

    # TODO: GCS 연동 후 실제 메모 조회 구현
    result = {
        "subject": subject,
        "memos": [],
        "count": 0,
    }

    return json.dumps(result, ensure_ascii=False)
