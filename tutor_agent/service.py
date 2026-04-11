"""Service Layer — 그래프 실행의 유일한 진입점.

모든 플랫폼 어댑터(API, Slack 등)는 이 모듈만 호출합니다.
"""

import json
import logging
import os
import re
import shutil
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from pathlib import Path
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


def _store_name_for(user_id: str, class_id: str) -> str:
    """클래스별 Gemini Store 이름을 생성합니다."""
    return get_or_create_store(f"tutor-agent-{user_id}-{class_id}")


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
    # 1차: ```json ... ``` 코드블록에서 추출 (greedy로 전체 JSON 매칭)
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict) and "questions" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # 2차: 텍스트에서 { ... } 직접 추출
    m2 = re.search(r"\{.*\"questions\".*\}", text, re.DOTALL)
    if m2:
        try:
            data = json.loads(m2.group(0))
            if isinstance(data, dict) and "questions" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # 3차: 전체 텍스트를 JSON으로 시도
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "questions" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    return None


async def stream_chat(
    user_message: str,
    user_id: str,
    thread_id: str,
    class_id: str,
    material_name: str = "",
) -> AsyncGenerator[dict[str, Any], None]:
    """채팅 메시지를 처리하고 SSE 이벤트를 yield합니다."""
    store_name = _store_name_for(user_id, class_id)
    config = {
        "configurable": {
            "thread_id": f"{user_id}_{thread_id}",
            "user_id": user_id,
            "class_id": class_id,
            "store_name": store_name,
            "material_name": material_name,
        }
    }

    try:
        for event in _graph.stream(
            {
                "messages": [HumanMessage(content=user_message)],
                "user_id": user_id,
                "class_id": class_id,
                "store_name": store_name,
                "material_name": material_name,
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


def get_materials(user_id: str, class_id: str) -> list[str]:
    """클래스의 자료 목록을 반환합니다."""
    return load_manifest(user_id, class_id)


_MATERIALS_DIR = Path(__file__).parent.parent / "data" / "materials"


def upload_material(user_id: str, file_path: str, display_name: str, class_id: str) -> dict:
    """PDF를 클래스에 업로드합니다."""
    store_name = _store_name_for(user_id, class_id)
    existing = load_manifest(user_id, class_id)

    if display_name in existing:
        return {"status": "duplicate", "name": display_name}

    upload_pdf(store_name, file_path, display_name)
    save_manifest(existing + [display_name], user_id, class_id)

    # PDF를 로컬에 보관 (뷰어용)
    local_dir = _MATERIALS_DIR / user_id / class_id
    local_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, local_dir / f"{display_name}.pdf")

    return {"status": "uploaded", "name": display_name}


def get_material_path(user_id: str, class_id: str, display_name: str) -> Path | None:
    """로컬에 저장된 PDF 경로를 반환합니다."""
    path = _MATERIALS_DIR / user_id / class_id / f"{display_name}.pdf"
    return path if path.exists() else None


def generate_example_messages(user_id: str, class_id: str, material_names: str = "") -> list[dict]:
    """선택된 자료 본문에서 Q&A 예시 질문 1개를 빠르게 생성합니다."""
    manifest = load_manifest(user_id, class_id)
    if not manifest:
        return []

    store_name = _store_name_for(user_id, class_id)
    client = get_genai_client()
    from google.genai import types

    # 선택된 자료가 있으면 해당 자료에서만 검색하도록 힌트 추가
    material_hint = ""
    if material_names:
        names = [n.strip() for n in material_names.split("|") if n.strip()]
        material_hint = f"\n다음 자료에서만 찾아주세요: {', '.join(names)}\n"

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            f"이 강의 자료에서 랜덤으로 하나의 핵심 용어나 개념을 골라서, "
            f"학생이 물어볼 법한 짧은 질문 1개를 만들어주세요.{material_hint}\n"
            f'예: "아비투스란 무엇인가요?", "문화자본의 세 가지 유형은?"\n\n'
            f"질문만 출력하세요. 다른 설명은 불필요합니다."
        ),
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[store_name]
                    )
                )
            ],
        ),
    )
    question = (response.text or "").strip().strip('"')
    if question:
        return [{"type": "qna", "message": question}]
    return []


def new_thread_id() -> str:
    """새 스레드 ID를 생성합니다."""
    return str(uuid.uuid4())


# --- 복습 스케줄링 ---

_logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


def parse_schedule_date(user_input: str) -> str | None:
    """자연어 날짜를 YYYY-MM-DD로 변환합니다. 실패 시 None."""
    # 이미 YYYY-MM-DD 형식이면 그대로 반환
    if re.match(r"\d{4}-\d{2}-\d{2}$", user_input.strip()):
        return user_input.strip()

    client = get_genai_client()
    today = datetime.now(KST).strftime("%Y-%m-%d")
    from google.genai import types

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            f"오늘 날짜: {today}\n"
            f'사용자 입력: "{user_input}"\n\n'
            "위 텍스트에서 사용자가 원하는 날짜를 YYYY-MM-DD 형식으로 추출하세요.\n"
            "날짜를 파싱할 수 없으면 date를 null로 설정하세요.\n\n"
            '반드시 아래 JSON 형식으로만 응답: {"date": "YYYY-MM-DD"}'
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    try:
        result = json.loads(response.text)
        parsed = result.get("date")
        if parsed and re.match(r"\d{4}-\d{2}-\d{2}$", parsed):
            return parsed
    except (json.JSONDecodeError, AttributeError):
        _logger.warning(f"날짜 파싱 실패: {user_input}")
    return None


async def run_scheduled_quiz_generation() -> list[dict]:
    """오늘 예정된 completion을 찾아 퀴즈를 생성하고 Slack으로 전송합니다."""
    from .auth import (
        get_pending_completions,
        mark_completion_generated,
        save_quiz_result,
    )
    from .platforms.slack import post_quiz_to_slack

    today = datetime.now(KST).strftime("%Y-%m-%d")
    completions = get_pending_completions(today)
    _logger.info(f"[크론] 예약 퀴즈 대상: {len(completions)}건 (date={today})")

    results = []
    for comp in completions:
        try:
            wrong_questions = comp.get("wrong_questions", [])

            if wrong_questions:
                # 틀린 문제 재출제 — LLM 불필요
                questions = wrong_questions
                quiz_title = comp["material_name"]
            else:
                # 새 퀴즈 생성 — LangGraph 그래프 사용
                store_name = _store_name_for(comp["user_email"], comp["class_id"])
                thread_id = str(uuid.uuid4())
                config = {"configurable": {
                    "thread_id": f"{comp['user_email']}_{thread_id}",
                    "user_id": comp["user_email"],
                    "class_id": comp["class_id"],
                    "store_name": store_name,
                    "material_name": comp["material_name"],
                }}

                prompt = f"{comp['material_name']}에 대한 퀴즈를 내줘"
                graph_result = _graph.invoke(
                    {
                        "messages": [HumanMessage(content=prompt)],
                        "user_id": comp["user_email"],
                        "class_id": comp["class_id"],
                        "store_name": store_name,
                        "material_name": comp["material_name"],
                    },
                    config=config,
                )

                ai_content = extract_ai_content(graph_result)
                quiz_data = parse_quiz(ai_content)
                if not quiz_data or not quiz_data.get("questions"):
                    results.append({"completion_id": comp["id"], "status": "failed", "reason": "퀴즈 생성 실패"})
                    continue

                questions = quiz_data["questions"]
                quiz_title = quiz_data.get("quiz_title", comp["material_name"])

            # DB에 퀴즈 저장
            quiz_result = save_quiz_result(
                user_email=comp["user_email"],
                class_id=comp["class_id"],
                material_name=comp["material_name"],
                quiz_title=quiz_title,
                questions=questions,
                answers={},
                score=0,
                total=len(questions),
                quiz_type=comp["type"],
                source_quiz_id=comp.get("source_quiz_id"),
                status="in_progress",
            )

            # Slack 전송
            from .auth import get_quiz_result
            quiz = get_quiz_result(quiz_result["id"])
            if quiz:
                await post_quiz_to_slack(quiz)

            mark_completion_generated(comp["id"], quiz_result["id"])
            results.append({"completion_id": comp["id"], "status": "generated", "quiz_id": quiz_result["id"]})

        except Exception as e:
            _logger.error(f"[크론] 퀴즈 생성 실패: {comp['id']} — {e}")
            results.append({"completion_id": comp["id"], "status": "error", "reason": str(e)})

    return results
