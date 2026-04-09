"""Slack Bolt 앱: 퀴즈 전송 + 버튼 인터랙션 핸들러.

Quiz-Bot의 slack_app.py를 TutorAgent에 맞게 포팅.
GCS 대신 SQLite, quiz_manager 대신 LangGraph 그래프 사용.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp

from ..auth import (
    get_quiz_result,
    mark_completion_generated,
    save_completion,
    update_quiz_result,
)

load_dotenv()

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")

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
                for label in ["A", "B", "C", "D"]
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
        """스레드 내 날짜 입력 처리."""
        if event.get("bot_id") or event.get("subtype"):
            return

        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return

        state = _thread_states.get(thread_ts)
        if not state or state["type"] != "reschedule":
            return

        text = event.get("text", "").strip()
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
