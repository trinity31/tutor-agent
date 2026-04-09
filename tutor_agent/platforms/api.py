"""FastAPI REST API — Platform Adapter (Layer 3).

모든 요청은 service.py를 통해 처리됩니다.
"""

import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from starlette.requests import Request

from ..auth import (
    authenticate_user,
    create_access_token,
    create_class,
    create_user,
    delete_class,
    get_class,
    get_classes,
    get_quiz_result,
    get_quiz_results,
    get_user,
    save_completion,
    save_quiz_result,
    update_quiz_result,
    verify_token,
)
from ..service import (
    generate_example_messages,
    get_materials,
    new_thread_id,
    parse_schedule_date,
    stream_chat,
    upload_material,
)
from .slack import slack_handler

load_dotenv()

security = HTTPBearer()


# --- Lifecycle ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="TutorAgent API", lifespan=lifespan)

# CORS (개발용 — 프로덕션에서는 origin 제한)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth Dependency ---


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    email = verify_token(credentials.credentials)
    if not email:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    user = get_user(email)
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
    return user


# --- Auth Endpoints ---


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register", status_code=201)
async def register(body: RegisterRequest):
    try:
        user = create_user(body.email, body.password, body.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = create_access_token(user["email"])
    return {"token": token, "user": user}


@app.post("/api/auth/login")
async def login(body: LoginRequest):
    user = authenticate_user(body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다."
        )
    token = create_access_token(user["email"])
    return {"token": token, "user": user}


@app.get("/api/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": user}


# --- Classes Endpoints ---


class CreateClassRequest(BaseModel):
    name: str


@app.get("/api/classes")
async def list_classes(user: dict = Depends(get_current_user)):
    classes = get_classes(user["email"])
    return {"classes": classes}


@app.post("/api/classes", status_code=201)
async def create_class_endpoint(body: CreateClassRequest, user: dict = Depends(get_current_user)):
    cls = create_class(user["email"], body.name)
    return cls


@app.delete("/api/classes/{class_id}")
async def delete_class_endpoint(class_id: str, user: dict = Depends(get_current_user)):
    cls = get_class(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="클래스를 찾을 수 없습니다.")
    if cls["user_email"] != user["email"]:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    delete_class(class_id)
    return {"status": "deleted"}


# --- Materials Endpoints ---


@app.get("/api/classes/{class_id}/materials")
async def list_materials(class_id: str, user: dict = Depends(get_current_user)):
    materials = get_materials(user["email"], class_id)
    return {"materials": materials}


@app.post("/api/classes/{class_id}/materials/upload")
async def upload(
    class_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    cls = get_class(class_id)
    if not cls or cls["user_email"] != user["email"]:
        raise HTTPException(status_code=404, detail="클래스를 찾을 수 없습니다.")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    display_name = os.path.splitext(file.filename)[0]

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="파일 크기는 10MB 이하여야 합니다.")
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = upload_material(user["email"], tmp_path, display_name, class_id)
    finally:
        os.unlink(tmp_path)

    if result["status"] == "duplicate":
        raise HTTPException(
            status_code=409, detail=f"이미 업로드된 파일입니다: {result['name']}"
        )

    return result


# --- Chat Endpoints ---


class ChatRequest(BaseModel):
    message: str
    thread_id: str
    class_id: str
    material_name: str = ""


@app.post("/api/chat")
async def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    """SSE 스트리밍으로 에이전트 응답을 반환합니다."""

    async def event_generator():
        async for event in stream_chat(
            user_message=body.message,
            user_id=user["email"],
            thread_id=body.thread_id,
            class_id=body.class_id,
            material_name=body.material_name,
        ):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/new")
async def new_chat(user: dict = Depends(get_current_user)):
    """새 스레드를 생성합니다."""
    return {"thread_id": new_thread_id()}


# --- Example Messages ---


@app.get("/api/classes/{class_id}/examples")
async def examples(class_id: str, materials: str = "", user: dict = Depends(get_current_user)):
    return {"examples": generate_example_messages(user["email"], class_id, materials)}


# --- Quiz Results Endpoints ---


class SaveQuizResultRequest(BaseModel):
    class_id: str
    material_name: str
    quiz_title: str = ""
    questions: list[dict]
    answers: list[dict]
    score: int
    total: int
    quiz_type: str = "normal"
    source_quiz_id: str | None = None


@app.post("/api/quiz-results", status_code=201)
async def save_quiz_result_endpoint(body: SaveQuizResultRequest, user: dict = Depends(get_current_user)):
    result = save_quiz_result(
        user_email=user["email"],
        class_id=body.class_id,
        material_name=body.material_name,
        quiz_title=body.quiz_title,
        questions=body.questions,
        answers=body.answers,
        score=body.score,
        total=body.total,
        quiz_type=body.quiz_type,
        source_quiz_id=body.source_quiz_id,
    )
    return result


@app.get("/api/quiz-results")
async def list_quiz_results(class_id: str = "", user: dict = Depends(get_current_user)):
    results = get_quiz_results(user["email"], class_id or None)
    return {"results": results}


class ScheduleQuizRequest(BaseModel):
    scheduled_date: str  # YYYY-MM-DD 또는 자연어
    schedule_mode: str = "wrong_only"  # wrong_only | full
    review_notes: str = ""


@app.post("/api/quiz-results/{quiz_id}/schedule")
async def schedule_quiz_retry(quiz_id: str, body: ScheduleQuizRequest, user: dict = Depends(get_current_user)):
    quiz = get_quiz_result(quiz_id)
    if not quiz or quiz["user_email"] != user["email"]:
        raise HTTPException(status_code=404, detail="퀴즈를 찾을 수 없습니다.")

    parsed_date = parse_schedule_date(body.scheduled_date)
    if not parsed_date:
        raise HTTPException(status_code=400, detail="날짜를 인식하지 못했습니다.")

    wrong_questions = quiz.get("wrong_questions") if body.schedule_mode == "wrong_only" else None
    material_name = quiz["material_name"]
    if body.schedule_mode == "wrong_only" and wrong_questions:
        material_name = f"{material_name.replace(' (오답 복습)', '')} (오답 복습)"

    comp = save_completion(
        user_email=user["email"],
        class_id=quiz["class_id"],
        material_name=material_name,
        completion_type="scheduled",
        scheduled_date=parsed_date,
        schedule_mode=body.schedule_mode,
        source_quiz_id=quiz_id,
        wrong_questions=wrong_questions,
        review_notes=body.review_notes,
    )
    return comp


class UpdateReviewNotesRequest(BaseModel):
    review_notes: str


@app.patch("/api/quiz-results/{quiz_id}/review-notes")
async def update_review_notes(quiz_id: str, body: UpdateReviewNotesRequest, user: dict = Depends(get_current_user)):
    quiz = get_quiz_result(quiz_id)
    if not quiz or quiz["user_email"] != user["email"]:
        raise HTTPException(status_code=404, detail="퀴즈를 찾을 수 없습니다.")
    update_quiz_result(quiz_id, review_notes=body.review_notes)
    return {"status": "updated"}


# --- Completions Endpoints ---


class MarkCompleteRequest(BaseModel):
    class_id: str
    material_name: str


@app.post("/api/completions", status_code=201)
async def mark_complete(body: MarkCompleteRequest, user: dict = Depends(get_current_user)):
    """학습 완료를 등록합니다. 다음날 Slack 퀴즈가 자동 생성됩니다."""
    comp = save_completion(
        user_email=user["email"],
        class_id=body.class_id,
        material_name=body.material_name,
    )
    return comp


# --- Slack Events ---


if slack_handler:
    @app.post("/slack/events")
    async def slack_events(req: Request):
        return await slack_handler.handle(req)


# --- Cron: 예약 퀴즈 생성 ---

CRON_SECRET = os.getenv("CRON_SECRET", "dev-cron-secret")


@app.post("/api/generate-scheduled-quizzes")
async def generate_scheduled_quizzes(secret: str = ""):
    """크론 엔드포인트: 예약된 퀴즈를 생성하고 Slack으로 전송합니다."""
    if secret != CRON_SECRET:
        raise HTTPException(status_code=403, detail="Invalid cron secret")
    from ..service import run_scheduled_quiz_generation

    results = await run_scheduled_quiz_generation()
    return {"generated": len([r for r in results if r["status"] == "generated"]), "results": results}


# --- Static Files (프로덕션: React 빌드 서빙) ---

_web_dist = Path(__file__).parent.parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="static")
