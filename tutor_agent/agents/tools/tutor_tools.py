"""학습 도우미 도메인 도구 (dummy 구현)."""

import json
from langchain_core.tools import tool


@tool
def search_material(subject: str) -> str:
    """강의 자료를 검색합니다.

    Args:
        subject: 과목명과 주차 (예: '양택풍수론 4주차')

    Returns:
        검색된 강의 자료 내용 (JSON 문자열)
    """
    print(f"[TOOL] search_material — subject={subject}")

    # --- dummy 데이터 ---
    result = {
        "subject": subject,
        "content": (
            f"[{subject}] 강의 자료 내용\n\n"
            f"1. 핵심 개념: {subject}의 기본 원리와 역사적 배경\n"
            f"2. 주요 용어: 용어A(정의), 용어B(정의), 용어C(정의)\n"
            f"3. 중요 내용: 이론적 프레임워크와 실제 적용 사례\n"
            f"4. 심화 내용: 최신 연구 동향과 학술적 논의\n"
            f"5. 실습 요소: 현장 적용 방법론과 분석 기법\n"
        ),
        "char_count": 500,
    }
    # --- dummy 끝 ---

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
