"""Service Layer — 그래프 실행의 유일한 진입점.

모든 플랫폼 어댑터(API, Slack 등)는 이 모듈만 호출합니다.
"""

import json
import os
import re
import tempfile
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from .agents.graph import build_graph
from .file_search import (
    get_client as get_genai_client,
    get_or_create_store,
    load_manifest,
    save_manifest,
    upload_pdf,
    GEMINI_MODEL,
)

# --- 그래프 싱글턴 ---
_checkpointer = MemorySaver()
_graph = build_graph(checkpointer=_checkpointer)

# 에이전트 한글 레이블
AGENT_LABELS = {
    "supervisor_agent": "Supervisor",
    "search_agent": "자료 검색",
    "quiz_agent": "퀴즈 생성",
    "qna_agent": "Q&A 답변",
    "tutor_agent": "1:1 과외",
}


def extract_ai_content(result: dict) -> str:
    """그래프 결과에서 AI 텍스트 응답을 추출합니다."""
    for msg in reversed(result.get("messages", [])):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if not content:
            continue
        if isinstance(content, list):
            text_parts = [
                p["text"] if isinstance(p, dict) else str(p)
                for p in content
                if (isinstance(p, dict) and p.get("type") == "text")
                or isinstance(p, str)
            ]
            content = "\n".join(text_parts)
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def parse_quiz(text: str) -> dict | None:
    """AI 응답에서 퀴즈 JSON을 추출합니다."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    json_str = m.group(1) if m else text
    try:
        data = json.loads(json_str)
        if isinstance(data, dict) and "questions" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


async def stream_chat(
    user_message: str,
    user_id: str,
    thread_id: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """채팅 메시지를 처리하고 SSE 이벤트를 yield합니다.

    Yields:
        {"event": "agent_status", "data": {"agent": str, "label": str}}
        {"event": "message", "data": {"content": str, "agent": str}}
        {"event": "quiz", "data": {...quiz JSON...}}
        {"event": "error", "data": {"message": str}}
        {"event": "done", "data": {}}
    """
    store_name = get_or_create_store(f"tutor-agent-{user_id}")
    config = {"configurable": {"thread_id": f"{user_id}_{thread_id}"}}

    try:
        for event in _graph.stream(
            {
                "messages": [HumanMessage(content=user_message)],
                "user_id": user_id,
                "store_name": store_name,
            },
            config=config,
            stream_mode="updates",
        ):
            for node_name in event:
                if node_name != "supervisor_agent":
                    label = AGENT_LABELS.get(node_name, node_name)
                    yield {
                        "event": "agent_status",
                        "data": {"agent": node_name, "label": label},
                    }

        # 최종 상태에서 응답 추출
        snapshot = _graph.get_state(config)
        final_values = snapshot.values
        current_agent = final_values.get("current_agent", "")
        ai_content = extract_ai_content(final_values)

        if not ai_content:
            yield {
                "event": "error",
                "data": {"message": "응답을 생성하지 못했습니다. 다시 시도해 주세요."},
            }
        else:
            # 퀴즈 JSON 감지
            quiz_data = parse_quiz(ai_content)
            if quiz_data and quiz_data.get("questions"):
                yield {"event": "quiz", "data": quiz_data}
            else:
                yield {
                    "event": "message",
                    "data": {
                        "content": ai_content,
                        "agent": current_agent,
                        "label": AGENT_LABELS.get(current_agent, current_agent),
                    },
                }

    except Exception as e:
        yield {"event": "error", "data": {"message": f"처리 중 오류가 발생했습니다: {e}"}}

    yield {"event": "done", "data": {}}


def get_materials(user_id: str) -> list[str]:
    """사용자의 업로드된 자료 목록을 반환합니다."""
    return load_manifest(user_id)


def upload_material(user_id: str, file_path: str, display_name: str) -> dict:
    """PDF를 업로드하고 결과를 반환합니다."""
    store_name = get_or_create_store(f"tutor-agent-{user_id}")
    existing = load_manifest(user_id)

    if display_name in existing:
        return {"status": "duplicate", "name": display_name}

    upload_pdf(store_name, file_path, display_name)
    save_manifest(existing + [display_name], user_id)

    return {"status": "uploaded", "name": display_name}


def generate_example_messages(user_id: str) -> list[dict]:
    """업로드된 파일 기반으로 에이전트별 예시 메시지를 생성합니다."""
    manifest = load_manifest(user_id)
    if not manifest:
        return []

    sample = manifest[:10]
    file_names = "\n".join(f"- {f}" for f in sample)

    client = get_genai_client()
    from google.genai import types

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            f"아래는 학생이 업로드한 강의 자료 파일명 목록입니다:\n{file_names}\n\n"
            "이 자료를 기반으로 학생이 AI 과외 선생님에게 보낼 만한 예시 메시지를 3개 생성해주세요.\n"
            "각 메시지는 서로 다른 에이전트를 활성화하도록 작성하세요:\n"
            '1. tutor: 주제에 대한 설명/학습 요청 (예: "~에 대해 쉽게 설명해 줘")\n'
            '2. qna: 특정 용어/개념의 짧은 질문 (예: "~가 뭐야?")\n'
            '3. quiz: 퀴즈 요청 (예: "~에 대한 퀴즈를 내줘")\n\n'
            "반드시 아래 JSON 형식으로만 응답하세요:\n"
            '[{"type":"tutor","message":"..."},{"type":"qna","message":"..."},{"type":"quiz","message":"..."}]'
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, ValueError):
        return []


def new_thread_id() -> str:
    """새 스레드 ID를 생성합니다."""
    return str(uuid.uuid4())
