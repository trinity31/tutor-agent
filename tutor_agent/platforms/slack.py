"""Slack Bolt 앱: 슬래시 커맨드 + 퀴즈 전송 + 버튼 인터랙션 핸들러.

Quiz-Bot의 slack_app.py를 TutorAgent에 맞게 포팅.
GCS 대신 SQLite, quiz_manager 대신 LangGraph 그래프 사용.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp

from ..auth import (
    get_classes,
    get_quiz_result,
    get_quiz_results,
    mark_completion_generated,
    save_completion,
    save_quiz_result,
    save_study_note,
    update_quiz_result,
)

load_dotenv()

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")

# Slack 슬래시 커맨드용 기본 사용자 (Railway Variables에 설정)
SLACK_DEFAULT_USER_EMAIL = os.getenv("SLACK_DEFAULT_USER_EMAIL", "")

# Slack Bolt 앱 — 토큰이 없으면 더미 모드
if SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET:
    slack_app = AsyncApp(
        token=SLACK_BOT_TOKEN,
        signing_secret=SLACK_SIGNING_SECRET,
    )
    slack_handler = AsyncSlackRequestHandler(slack_app)
else:
    slack_app = None
    slack_handler = None
    logger.warning("SLACK_BOT_TOKEN 미설정 — Slack 기능 비활성")

# 스레드 상태 (인메모리 — 재시작 시 소실, 충분한 수준)
_thread_states: dict[str, dict] = {}

# 드롭다운 자료 매핑 (Slack value 151자 제한 대응)
# key: "{class_id}:{index}" → value: material_name
_material_map: dict[str, str] = {}


def _build_material_options(class_id: str, materials: list[str]) -> list[dict]:
    """자료 목록을 Slack 드롭다운 옵션으로 변환합니다. value는 짧은 키로."""
    options = []
    for i, m in enumerate(materials[:25]):
        key = f"{class_id}:{i}"
        _material_map[key] = m
        options.append({
            "text": {"type": "plain_text", "text": m[:75]},
            "value": key,
        })
    return options


def _resolve_material(value: str) -> tuple[str, str]:
    """드롭다운 value에서 (class_id, material_name)을 반환합니다."""
    class_id = value.split(":")[0]
    material_name = _material_map.get(value, "")
    return class_id, material_name


def _parse_note_input(user_input: str) -> tuple[str, str] | None:
    """LLM으로 사용자 입력에서 자료명과 메모 내용을 분리합니다.

    예: '양택풍수론 6주차 일주문의 의미가 중요'
      → ('양택풍수론 6주차', '일주문의 의미가 중요')
    """
    from ..file_search import get_client, GEMINI_MODEL
    from google.genai import types

    client = get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            f'사용자 입력: "{user_input}"\n\n'
            "위 텍스트에서 '과목명과 주차 정보'와 '메모 내용'을 분리해주세요.\n"
            "과목명+주차는 강의 자료를 식별하는 부분이고, 나머지가 메모입니다.\n\n"
            '반드시 아래 JSON 형식으로만 응답: {"subject": "과목명 주차", "note": "메모 내용"}'
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    try:
        result = json.loads(response.text)
        subject = result.get("subject", "").strip()
        note = result.get("note", "").strip()
        if subject and note:
            return subject, note
    except (json.JSONDecodeError, AttributeError):
        logger.warning(f"노트 파싱 실패: {user_input}")
    return None


def _find_class_for_subject(user_email: str, subject: str) -> tuple[str, str] | None:
    """사용자의 클래스 목록에서 subject와 매칭되는 클래스+자료를 찾습니다.

    Returns:
        (class_id, material_display_name) 또는 None
    """
    from ..auth import get_classes
    from ..file_search import find_matching_file, load_manifest

    classes = get_classes(user_email)
    for cls in classes:
        # 클래스 이름이 subject에 포함되어 있으면 우선 탐색
        manifest = load_manifest(user_email, cls["id"])
        if not manifest:
            continue
        matched = find_matching_file(subject, user_email, cls["id"])
        if matched:
            return cls["id"], matched

    return None


# ── 퀴즈 Block Kit 빌더 ─────────────────────────────────────


def build_question_blocks(quiz: dict, question: dict) -> list[dict]:
    """퀴즈 문제를 Slack Block으로 변환."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{quiz['material_name']} 퀴즈",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*문제 {question['number']}/{quiz['total']}*\n\n{question['question']}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join(question["options"]),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": label},
                    "action_id": f"quiz_answer_{label}",
                    "value": json.dumps({
                        "quiz_id": quiz["id"],
                        "question_number": question["number"],
                        "answer": label,
                    }),
                }
                for label in ["A", "B", "C", "D"][:len(question["options"])]
            ],
        },
    ]


def build_score_blocks(quiz: dict) -> list[dict]:
    """퀴즈 결과 + 재시험 버튼 Block."""
    score = quiz["score"]
    total = quiz["total"]
    wrong_questions = quiz.get("wrong_questions", [])

    if score >= total * 0.8:
        comment = "훌륭합니다!"
    elif score >= total * 0.5:
        comment = "좋습니다! 조금만 더 복습하면 완벽해요."
    else:
        comment = "복습이 필요합니다. 다시 한번 학습해보세요!"

    wrong_msg = f"\n\n틀린 문제: {len(wrong_questions)}개" if wrong_questions else ""

    base_message = quiz["material_name"].replace(" (오답 복습)", "")
    btn_value = json.dumps({
        "quiz_id": quiz["id"],
        "material_name": base_message,
        "user_email": quiz["user_email"],
        "class_id": quiz["class_id"],
    })

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "퀴즈 결과"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{quiz['material_name']}*\n\n"
                    f"점수: *{score}/{total}*\n"
                    f"{comment}{wrong_msg}"
                ),
            },
        },
    ]

    retry_elements = []
    if wrong_questions:
        retry_elements.extend([
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "🔄 내일 틀린 문제만 다시"},
                "action_id": "retry_tomorrow",
                "value": btn_value,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "📅 날짜 지정 · 틀린 문제만"},
                "action_id": "retry_schedule",
                "value": btn_value,
            },
        ])
    retry_elements.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "📅 날짜 지정 · 전체 퀴즈"},
        "action_id": "full_schedule",
        "value": btn_value,
    })
    blocks.append({"type": "actions", "elements": retry_elements})

    return blocks


# ── 퀴즈 Slack 전송 ─────────────────────────────────────────


async def post_quiz_to_slack(quiz: dict):
    """퀴즈의 첫 번째 문제를 Slack 채널에 전송합니다."""
    if not slack_app:
        logger.warning("Slack 앱 미초기화 — 퀴즈 전송 스킵")
        return

    questions = quiz["questions"]
    if not questions:
        return

    first_q = questions[0]
    blocks = build_question_blocks(quiz, first_q)

    result = await slack_app.client.chat_postMessage(
        channel=SLACK_CHANNEL_ID,
        blocks=blocks,
        text=f"{quiz['material_name']} 퀴즈",
    )

    update_quiz_result(
        quiz["id"],
        slack_channel=SLACK_CHANNEL_ID,
        slack_thread_ts=result["ts"],
    )


# ── 답변 핸들러 (A/B/C/D) ───────────────────────────────────

if slack_app:

    # ── 슬래시 커맨드 ───────────────────────────────────────

    @slack_app.command("/note")
    async def handle_note(ack, command, say):
        """자료에 학습 노트를 추가합니다 — 클래스 선택 드롭다운 표시."""
        await ack()
        if not SLACK_DEFAULT_USER_EMAIL:
            await say(text="SLACK_DEFAULT_USER_EMAIL 환경변수가 설정되지 않았습니다.")
            return

        classes = get_classes(SLACK_DEFAULT_USER_EMAIL)
        if not classes:
            await say(text="등록된 클래스가 없습니다. 웹에서 클래스를 먼저 생성해주세요.")
            return

        options = [
            {"text": {"type": "plain_text", "text": cls["name"][:75]}, "value": cls["id"]}
            for cls in classes[:25]
        ]
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "노트를 추가할 *클래스*를 선택하세요:"}},
            {
                "type": "actions",
                "elements": [{
                    "type": "static_select",
                    "placeholder": {"type": "plain_text", "text": "클래스 선택"},
                    "action_id": "note_select_class",
                    "options": options,
                }],
            },
        ]
        await say(blocks=blocks, text="노트: 클래스를 선택하세요")

    @slack_app.action("note_select_class")
    async def handle_note_select_class(ack, body, say, action):
        """클래스 선택 후 자료 목록 표시."""
        await ack()
        class_id = action["selected_option"]["value"]
        class_name = action["selected_option"]["text"]["text"]

        from ..file_search import load_manifest
        materials = load_manifest(SLACK_DEFAULT_USER_EMAIL, class_id)
        if not materials:
            await say(text=f"'{class_name}' 클래스에 자료가 없습니다.")
            return

        options = _build_material_options(class_id, materials)
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{class_name}* — 노트를 추가할 *자료*를 선택하세요:"}},
            {
                "type": "actions",
                "elements": [{
                    "type": "static_select",
                    "placeholder": {"type": "plain_text", "text": "자료 선택"},
                    "action_id": "note_select_material",
                    "options": options,
                }],
            },
        ]
        await say(blocks=blocks, text="노트: 자료를 선택하세요")

    @slack_app.action("note_select_material")
    async def handle_note_select_material(ack, body, say, action):
        """자료 선택 후 노트 입력 안내."""
        await ack()
        class_id, material_name = _resolve_material(action["selected_option"]["value"])
        msg = body["message"]
        thread_ts = msg.get("thread_ts", msg["ts"])

        _thread_states[thread_ts] = {
            "type": "note_input",
            "class_id": class_id,
            "material_name": material_name,
        }
        await say(
            text=f"'{material_name}'에 추가할 노트를 입력해주세요:",
            thread_ts=thread_ts,
        )

    @slack_app.command("/done")
    async def handle_done(ack, command, say):
        """학습 완료 등록 — 클래스/자료 선택 드롭다운."""
        await ack()
        if not SLACK_DEFAULT_USER_EMAIL:
            await say(text="SLACK_DEFAULT_USER_EMAIL 환경변수가 설정되지 않았습니다.")
            return

        classes = get_classes(SLACK_DEFAULT_USER_EMAIL)
        if not classes:
            await say(text="등록된 클래스가 없습니다. 웹에서 클래스를 먼저 생성해주세요.")
            return

        options = [
            {"text": {"type": "plain_text", "text": cls["name"][:75]}, "value": cls["id"]}
            for cls in classes[:25]
        ]
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "학습 완료할 *클래스*를 선택하세요:"}},
            {
                "type": "actions",
                "elements": [{
                    "type": "static_select",
                    "placeholder": {"type": "plain_text", "text": "클래스 선택"},
                    "action_id": "done_select_class",
                    "options": options,
                }],
            },
        ]
        await say(blocks=blocks, text="학습 완료: 클래스를 선택하세요")

    @slack_app.action("done_select_class")
    async def handle_done_select_class(ack, body, say, action):
        """클래스 선택 후 자료 목록 표시."""
        await ack()
        class_id = action["selected_option"]["value"]
        class_name = action["selected_option"]["text"]["text"]

        from ..file_search import load_manifest
        materials = load_manifest(SLACK_DEFAULT_USER_EMAIL, class_id)
        if not materials:
            await say(text=f"'{class_name}' 클래스에 자료가 없습니다.")
            return

        options = _build_material_options(class_id, materials)
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{class_name}* — 학습 완료할 *자료*를 선택하세요:"}},
            {
                "type": "actions",
                "elements": [{
                    "type": "static_select",
                    "placeholder": {"type": "plain_text", "text": "자료 선택"},
                    "action_id": "done_select_material",
                    "options": options,
                }],
            },
        ]
        await say(blocks=blocks, text="학습 완료: 자료를 선택하세요")

    @slack_app.action("done_select_material")
    async def handle_done_select_material(ack, body, say, action):
        """자료 선택 → 학습 완료 등록."""
        await ack()
        class_id, material_name = _resolve_material(action["selected_option"]["value"])
        save_completion(
            user_email=SLACK_DEFAULT_USER_EMAIL,
            class_id=class_id,
            material_name=material_name,
        )
        await say(text=f"'{material_name}' 학습 완료가 등록되었습니다. 내일 오전에 퀴즈가 출제됩니다.")

    @slack_app.command("/quiz")
    async def handle_quiz(ack, command, say):
        """즉시 퀴즈 생성 — 클래스/자료 선택 드롭다운."""
        await ack()
        if not SLACK_DEFAULT_USER_EMAIL:
            await say(text="SLACK_DEFAULT_USER_EMAIL 환경변수가 설정되지 않았습니다.")
            return

        classes = get_classes(SLACK_DEFAULT_USER_EMAIL)
        if not classes:
            await say(text="등록된 클래스가 없습니다. 웹에서 클래스를 먼저 생성해주세요.")
            return

        options = [
            {"text": {"type": "plain_text", "text": cls["name"][:75]}, "value": cls["id"]}
            for cls in classes[:25]
        ]
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "퀴즈를 생성할 *클래스*를 선택하세요:"}},
            {
                "type": "actions",
                "elements": [{
                    "type": "static_select",
                    "placeholder": {"type": "plain_text", "text": "클래스 선택"},
                    "action_id": "quiz_select_class",
                    "options": options,
                }],
            },
        ]
        await say(blocks=blocks, text="퀴즈: 클래스를 선택하세요")

    @slack_app.action("quiz_select_class")
    async def handle_quiz_select_class(ack, body, say, action):
        """클래스 선택 후 자료 목록 표시."""
        await ack()
        class_id = action["selected_option"]["value"]
        class_name = action["selected_option"]["text"]["text"]

        from ..file_search import load_manifest
        materials = load_manifest(SLACK_DEFAULT_USER_EMAIL, class_id)
        if not materials:
            await say(text=f"'{class_name}' 클래스에 자료가 없습니다.")
            return

        options = _build_material_options(class_id, materials)
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{class_name}* — 퀴즈를 생성할 *자료*를 선택하세요:"}},
            {
                "type": "actions",
                "elements": [{
                    "type": "static_select",
                    "placeholder": {"type": "plain_text", "text": "자료 선택"},
                    "action_id": "quiz_select_material",
                    "options": options,
                }],
            },
        ]
        await say(blocks=blocks, text="퀴즈: 자료를 선택하세요")

    @slack_app.action("quiz_select_material")
    async def handle_quiz_select_material(ack, body, say, action):
        """자료 선택 → 퀴즈 생성 + Slack 전송."""
        await ack()
        class_id, material_name = _resolve_material(action["selected_option"]["value"])

        await say(text=f"'{material_name}' 퀴즈를 생성 중입니다... 잠시만 기다려주세요.")

        try:
            from ..service import (
                _graph,
                _store_name_for,
                extract_ai_content,
                parse_quiz,
            )
            from langchain_core.messages import HumanMessage

            store_name = _store_name_for(SLACK_DEFAULT_USER_EMAIL, class_id)
            thread_id = str(uuid.uuid4())
            config = {"configurable": {
                "thread_id": f"{SLACK_DEFAULT_USER_EMAIL}_{thread_id}",
                "user_id": SLACK_DEFAULT_USER_EMAIL,
                "class_id": class_id,
                "store_name": store_name,
                "material_name": material_name,
            }}

            graph_result = await asyncio.to_thread(
                _graph.invoke,
                {
                    "messages": [HumanMessage(content=f"{material_name}에 대한 퀴즈를 내줘")],
                    "user_id": SLACK_DEFAULT_USER_EMAIL,
                    "class_id": class_id,
                    "store_name": store_name,
                    "material_name": material_name,
                },
                config,
            )

            ai_content = extract_ai_content(graph_result)
            logger.info(f"/quiz AI 응답 길이: {len(ai_content)}자")
            quiz_data = parse_quiz(ai_content)

            if not quiz_data or not quiz_data.get("questions"):
                logger.warning(f"/quiz parse_quiz 실패. ai_content 앞 500자: {ai_content[:500]}")
                await say(text=f"'{material_name}' 퀴즈 JSON 파싱에 실패했습니다. 다시 시도해주세요.")
                return

            questions = quiz_data["questions"]
            quiz_result = save_quiz_result(
                user_email=SLACK_DEFAULT_USER_EMAIL,
                class_id=class_id,
                material_name=material_name,
                quiz_title=quiz_data.get("quiz_title", material_name),
                questions=questions,
                answers={},
                score=0,
                total=len(questions),
                status="in_progress",
            )

            quiz = get_quiz_result(quiz_result["id"])
            if quiz:
                await post_quiz_to_slack(quiz)

        except Exception as e:
            logger.error(f"/quiz 실패: {e}")
            await say(text=f"퀴즈 생성 중 오류가 발생했습니다: {e}")

    @slack_app.command("/ask")
    async def handle_ask(ack, command, say):
        """자료 기반 Q&A 답변."""
        await ack()
        text = command.get("text", "").strip()
        if not text:
            await say(text="사용법: `/ask 질문` (예: `/ask 음양오행의 관계는?`)")
            return
        if not SLACK_DEFAULT_USER_EMAIL:
            await say(text="SLACK_DEFAULT_USER_EMAIL 환경변수가 설정되지 않았습니다.")
            return

        await say(text="질문을 처리 중입니다... 잠시만 기다려주세요.")

        try:
            from ..service import (
                _graph,
                _store_name_for,
                extract_ai_content,
            )
            from ..auth import get_classes
            from langchain_core.messages import HumanMessage

            # 첫 번째 클래스를 기본으로 사용 (전체 자료 검색)
            classes = get_classes(SLACK_DEFAULT_USER_EMAIL)
            class_id = classes[0]["id"] if classes else ""
            store_name = _store_name_for(SLACK_DEFAULT_USER_EMAIL, class_id) if class_id else ""

            thread_id = str(uuid.uuid4())
            config = {"configurable": {
                "thread_id": f"{SLACK_DEFAULT_USER_EMAIL}_{thread_id}",
                "user_id": SLACK_DEFAULT_USER_EMAIL,
                "class_id": class_id,
                "store_name": store_name,
                "material_name": "",
            }}

            graph_result = await asyncio.to_thread(
                _graph.invoke,
                {
                    "messages": [HumanMessage(content=text)],
                    "user_id": SLACK_DEFAULT_USER_EMAIL,
                    "class_id": class_id,
                    "store_name": store_name,
                    "material_name": "",
                },
                config,
            )

            answer = extract_ai_content(graph_result)
            if answer:
                await say(text=answer)
            else:
                await say(text="답변을 생성하지 못했습니다. 질문을 다시 시도해주세요.")

        except Exception as e:
            logger.error(f"/ask 실패: {e}")
            await say(text=f"답변 생성 중 오류가 발생했습니다: {e}")

    # ── 퀴즈 답변 핸들러 (A/B/C/D) ──────────────────────────

    for _label in ["A", "B", "C", "D"]:

        @slack_app.action(f"quiz_answer_{_label}")
        async def handle_quiz_answer(ack, body, say, action):
            await ack()

            data = json.loads(action["value"])
            quiz_id = data["quiz_id"]
            q_number = data["question_number"]
            user_answer = data["answer"]

            quiz = get_quiz_result(quiz_id)
            if not quiz or quiz["status"] == "completed":
                return

            question = quiz["questions"][q_number - 1]
            is_correct = user_answer == question["correct"]
            thread_ts = quiz["slack_thread_ts"]

            # 상태 업데이트
            answers = quiz["answers"]
            if isinstance(answers, list):
                answers = {}
            answers[str(q_number)] = user_answer
            new_score = quiz["score"] + (1 if is_correct else 0)

            # 정답/오답 피드백
            if is_correct:
                feedback = f"*정답입니다!*\n{question.get('explanation', '')}"
            else:
                feedback = (
                    f"*오답입니다.*\n"
                    f"정답: {question['correct']}\n"
                    f"{question.get('explanation', '')}"
                )
            await say(text=feedback, thread_ts=thread_ts)

            # 다음 문제 또는 최종 점수
            if q_number < len(quiz["questions"]):
                update_quiz_result(
                    quiz_id,
                    answers=answers,
                    score=new_score,
                    current_question=q_number,
                )
                next_q = quiz["questions"][q_number]
                # quiz dict에 반영 (build용)
                quiz["id"] = quiz_id
                blocks = build_question_blocks(quiz, next_q)
                await say(blocks=blocks, text=f"문제 {q_number + 1}", thread_ts=thread_ts)
            else:
                # 퀴즈 완료 — 틀린 문제 추출
                wrong_questions = []
                for q in quiz["questions"]:
                    if answers.get(str(q["number"])) != q["correct"]:
                        wrong_questions.append(q)
                for i, q in enumerate(wrong_questions, 1):
                    q["number"] = i

                update_quiz_result(
                    quiz_id,
                    answers=answers,
                    score=new_score,
                    status="completed",
                    wrong_questions=wrong_questions,
                )

                quiz["score"] = new_score
                quiz["wrong_questions"] = wrong_questions
                quiz["id"] = quiz_id
                score_blocks = build_score_blocks(quiz)
                await say(
                    blocks=score_blocks,
                    text=f"퀴즈 결과: {new_score}/{quiz['total']}",
                    thread_ts=thread_ts,
                )

    # ── 재시험 핸들러 ────────────────────────────────────────

    @slack_app.action("retry_tomorrow")
    async def handle_retry_tomorrow(ack, body, say, action):
        """내일 틀린 문제만 다시 출제."""
        await ack()
        data = json.loads(action["value"])
        msg = body["message"]
        thread_ts = msg.get("thread_ts", msg["ts"])

        quiz = get_quiz_result(data["quiz_id"])
        if not quiz:
            await say(text="퀴즈 정보를 찾을 수 없습니다.", thread_ts=thread_ts)
            return

        wrong_questions = quiz.get("wrong_questions", [])
        tomorrow = (datetime.now(KST) + timedelta(days=1)).strftime("%Y-%m-%d")

        save_completion(
            user_email=data["user_email"],
            class_id=data["class_id"],
            material_name=f"{data['material_name']} (오답 복습)",
            completion_type="retry",
            scheduled_date=tomorrow,
            source_quiz_id=data["quiz_id"],
            wrong_questions=wrong_questions,
        )
        await say(
            text=f"틀린 {len(wrong_questions)}문제가 내일({tomorrow}) 다시 출제됩니다.",
            thread_ts=thread_ts,
        )

    @slack_app.action("retry_schedule")
    async def handle_retry_schedule(ack, body, say, action):
        """날짜 지정 → 틀린 문제만 다시 출제."""
        await ack()
        data = json.loads(action["value"])
        msg = body["message"]
        thread_ts = msg.get("thread_ts", msg["ts"])

        _thread_states[thread_ts] = {
            "type": "reschedule",
            "retry_mode": "wrong_only",
            **data,
        }
        await say(
            text="언제 다시 퀴즈를 받고 싶으신가요? (예: '3일 후', '다음 주 월요일')",
            thread_ts=thread_ts,
        )

    @slack_app.action("full_schedule")
    async def handle_full_schedule(ack, body, say, action):
        """날짜 지정 → 전체 퀴즈 다시 출제."""
        await ack()
        data = json.loads(action["value"])
        msg = body["message"]
        thread_ts = msg.get("thread_ts", msg["ts"])

        _thread_states[thread_ts] = {
            "type": "reschedule",
            "retry_mode": "full",
            **data,
        }
        await say(
            text="언제 다시 퀴즈를 받고 싶으신가요? (예: '3일 후', '다음 주 월요일')",
            thread_ts=thread_ts,
        )

    # ── 스레드 메시지 핸들러 ─────────────────────────────────

    @slack_app.event("message")
    async def handle_message(event, say):
        """스레드 내 후속 입력 처리 (날짜, 노트)."""
        if event.get("bot_id") or event.get("subtype"):
            return

        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return

        state = _thread_states.get(thread_ts)
        if not state:
            return

        text = event.get("text", "").strip()

        # 노트 입력 처리
        if state["type"] == "note_input":
            if not text:
                return
            save_study_note(
                SLACK_DEFAULT_USER_EMAIL,
                state["class_id"],
                state["material_name"],
                text,
            )
            del _thread_states[thread_ts]
            await say(
                text=f"'{state['material_name']}'에 노트가 저장되었습니다.\n> {text}",
                thread_ts=thread_ts,
            )
            return

        # 재시험 날짜 입력 처리
        if state["type"] != "reschedule":
            return

        from ..service import parse_schedule_date

        parsed_date = parse_schedule_date(text)
        if not parsed_date:
            await say(
                text="날짜를 인식하지 못했습니다. '3일 후', '다음 주 월요일' 등으로 다시 시도해주세요.",
                thread_ts=thread_ts,
            )
            return

        retry_mode = state.get("retry_mode", "wrong_only")
        quiz_id = state.get("quiz_id")

        wrong_questions = None
        material_name = state.get("material_name", "")
        if retry_mode == "wrong_only" and quiz_id:
            quiz = get_quiz_result(quiz_id)
            if quiz:
                wrong_questions = quiz.get("wrong_questions", [])
                material_name = f"{material_name} (오답 복습)"

        save_completion(
            user_email=state.get("user_email", ""),
            class_id=state.get("class_id", ""),
            material_name=material_name,
            completion_type="scheduled",
            scheduled_date=parsed_date,
            schedule_mode=retry_mode,
            source_quiz_id=quiz_id,
            wrong_questions=wrong_questions,
        )

        del _thread_states[thread_ts]
        await say(
            text=f"'{state.get('material_name', '')}' 재퀴즈가 {parsed_date}에 예약되었습니다.",
            thread_ts=thread_ts,
        )
