"""학습 도우미 도메인 도구."""

import json
import logging

from langchain_core.tools import tool

from tutor_agent.file_search import search as file_search

logger = logging.getLogger(__name__)

_MIN_MATERIAL_LENGTH = 1500


@tool
def search_material(subject: str) -> str:
    """강의 자료를 검색합니다.

    Args:
        subject: 과목명과 주차 (예: '양택풍수론 4주차')

    Returns:
        검색된 강의 자료 내용 (JSON 문자열)
    """
    logger.info(f"[TOOL] search_material — subject={subject}")

    # 1차 검색
    query = f"{subject} 강의의 핵심 개념, 주요 용어, 중요 내용을 모두 정리해줘"
    content = file_search(query=query, user_message=subject)

    # 결과 부족 시 2차 검색 (쿼리 변형)
    if len(content.strip()) < _MIN_MATERIAL_LENGTH:
        logger.info(f"[TOOL] 1차 검색 결과 부족 ({len(content.strip())}자), 재시도")
        query2 = f"{subject} 강의 전체 내용을 최대한 상세하게 정리해줘"
        content = file_search(query=query2, user_message=subject)

    result = {
        "subject": subject,
        "content": content,
        "char_count": len(content),
    }
    return json.dumps(result, ensure_ascii=False)


@tool
def get_study_memos(subject: str) -> str:
    """해당 과목의 학습 메모를 조회합니다.

    Args:
        subject: 과목명과 주차 (예: '양택풍수론 4주차')

    Returns:
        저장된 메모 목록 (JSON 문자열)
    """
    print(f"[TOOL] get_study_memos — subject={subject}")

    # --- dummy 데이터 ---
    result = {
        "subject": subject,
        "memos": [
            "한옥 지붕의 팔작지붕과 우진각지붕 차이 중요",
            "기단의 삼분할 개념 시험에 나올듯",
        ],
        "count": 2,
    }
    # --- dummy 끝 ---

    return json.dumps(result, ensure_ascii=False)
