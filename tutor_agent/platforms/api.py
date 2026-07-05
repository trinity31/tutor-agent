"""FastAPI REST API — Platform Adapter (Layer 3).

모든 요청은 service.py를 통해 처리됩니다.
"""

import json
import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
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
    delete_study_note,
    get_class,
    get_classes,
    get_completed_materials,
    get_quiz_result,
    get_quiz_results,
    get_study_notes,
    get_user,
    save_completion,
    save_quiz_result,
    save_study_note,
    update_quiz_result,
    verify_token,
)
from ..service import (
    finish_indexing,
    generate_audio_asset,
    generate_example_messages,
    get_audio_file,
    get_audio_manifest,
    get_audio_sections,
    get_audio_status,
    get_material_index,
    get_material_indexing_status,
    get_material_path,
    get_materials,
    new_thread_id,
    parse_schedule_date,
    regenerate_material_index,
    request_audio,
    stream_chat,
    upload_material,
)
from ..tts import DEFAULT_VOICE, VOICES
from ..usage import add_usage, check_limit
from .slack import slack_handler

load_dotenv()

security = HTTPBearer()


# --- Lifecycle ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 프로덕션(Railway)에서 개발용 기본 시크릿으로 뜨는 것을 거부
    if os.getenv("RAILWAY_ENVIRONMENT"):
        missing = [
            name
            for name in ("JWT_SECRET_KEY", "CRON_SECRET")
            if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                f"프로덕션 환경변수 누락: {', '.join(missing)} — "
                "기본 시크릿으로는 기동할 수 없습니다."
            )
    yield


app = FastAPI(title="TutorAgent API", lifespan=lifespan)

# CORS — ALLOWED_ORIGINS(콤마 구분)로 재정의, 기본은 로컬 개발 origin.
# 프로덕션은 프론트를 같은 호스트에서 서빙하므로 추가 origin이 없어도 동작한다.
_allowed_origins = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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


# 초대 코드 — 설정되어 있으면 가입 시 요구 (베타 가입 제한). 미설정이면 개방.
INVITE_CODE = os.getenv("INVITE_CODE", "")


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    invite_code: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register", status_code=201)
async def register(body: RegisterRequest):
    if INVITE_CODE and body.invite_code.strip() != INVITE_CODE:
        raise HTTPException(status_code=403, detail="초대 코드가 올바르지 않습니다.")
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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    cls = get_class(class_id)
    if not cls or cls["user_email"] != user["email"]:
        raise HTTPException(status_code=404, detail="클래스를 찾을 수 없습니다.")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    if over := check_limit(user["email"], "uploads_monthly"):
        raise HTTPException(status_code=429, detail=over)

    display_name = os.path.splitext(file.filename)[0]

    MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="파일 크기는 30MB 이하여야 합니다.")
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

    add_usage(user["email"], "uploads_monthly")

    # 인덱싱 + 마크다운 인덱스 생성을 백그라운드에서 완료
    background_tasks.add_task(
        finish_indexing,
        result.pop("_op"),
        result.pop("_store_name"),
        display_name,
        user["email"],
        class_id,
    )

    return result


@app.get("/api/classes/{class_id}/materials/status")
async def materials_status(class_id: str, user: dict = Depends(get_current_user)):
    """각 자료의 인덱싱 상태를 반환합니다."""
    cls = get_class(class_id)
    if not cls or cls["user_email"] != user["email"]:
        raise HTTPException(status_code=404, detail="클래스를 찾을 수 없습니다.")

    from ..service import get_materials as _get_materials

    names = _get_materials(user["email"], class_id)
    return {
        "statuses": {
            name: get_material_indexing_status(user["email"], class_id, name)
            for name in names
        }
    }


@app.get("/api/classes/{class_id}/materials/{material_name}/index")
async def material_index(
    class_id: str,
    material_name: str,
    user: dict = Depends(get_current_user),
):
    """자료의 학습용 마크다운 인덱스를 반환합니다."""
    cls = get_class(class_id)
    if not cls or cls["user_email"] != user["email"]:
        raise HTTPException(status_code=404, detail="클래스를 찾을 수 없습니다.")

    content = get_material_index(user["email"], class_id, material_name)
    if content is None:
        return {"status": "not_ready", "content": ""}
    return {"status": "ready", "content": content}


@app.post("/api/classes/{class_id}/materials/{material_name}/index/regenerate")
async def material_index_regenerate(
    class_id: str,
    material_name: str,
    user: dict = Depends(get_current_user),
):
    """자료의 마크다운 인덱스를 재생성합니다."""
    cls = get_class(class_id)
    if not cls or cls["user_email"] != user["email"]:
        raise HTTPException(status_code=404, detail="클래스를 찾을 수 없습니다.")

    content = regenerate_material_index(user["email"], class_id, material_name)
    if content is None:
        raise HTTPException(
            status_code=500,
            detail="인덱스 생성에 실패했습니다. 잠시 후 다시 시도하거나 자료를 다시 업로드해 주세요.",
        )
    return {"status": "ready", "content": content}


# --- 원문 낭독 (Read-Aloud) Endpoints ---


def _check_class_owner(class_id: str, user: dict):
    cls = get_class(class_id)
    if not cls or cls["user_email"] != user["email"]:
        raise HTTPException(status_code=404, detail="클래스를 찾을 수 없습니다.")


def _check_voice(voice: str):
    if voice not in VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 음성입니다. ({', '.join(VOICES)})",
        )


class AudioRequest(BaseModel):
    section: str
    voice: str = DEFAULT_VOICE


@app.get("/api/classes/{class_id}/materials/{material_name}/audio/sections")
async def material_audio_sections(
    class_id: str, material_name: str, user: dict = Depends(get_current_user)
):
    """자료의 낭독 섹션(페이지 그룹) 목록을 반환합니다."""
    _check_class_owner(class_id, user)
    sections = get_audio_sections(user["email"], class_id, material_name)
    if sections is None:
        raise HTTPException(status_code=404, detail="PDF 원본을 찾을 수 없습니다.")
    return {"sections": sections, "voices": VOICES, "default_voice": DEFAULT_VOICE}


@app.post("/api/classes/{class_id}/materials/{material_name}/audio")
async def material_audio_request(
    class_id: str,
    material_name: str,
    body: AudioRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """섹션 오디오 생성을 요청합니다. 캐시가 있으면 즉시 ready를 반환합니다."""
    _check_class_owner(class_id, user)
    _check_voice(body.voice)
    sections = get_audio_sections(user["email"], class_id, material_name)
    if sections is None:
        raise HTTPException(status_code=404, detail="PDF 원본을 찾을 수 없습니다.")
    if body.section not in {s["section"] for s in sections}:
        raise HTTPException(status_code=400, detail="유효하지 않은 섹션입니다.")

    # 캐시된 오디오 재생은 한도와 무관 — 새로 생성해야 할 때만 검사
    status = get_audio_status(user["email"], class_id, material_name, body.section, body.voice)
    if status["status"] != "ready":
        if over := check_limit(user["email"], "tts_chars_monthly"):
            raise HTTPException(status_code=429, detail=over)

    result = request_audio(
        user["email"], class_id, material_name, body.section, body.voice
    )
    if result.pop("_start", False):
        background_tasks.add_task(
            generate_audio_asset,
            user["email"],
            class_id,
            material_name,
            body.section,
            body.voice,
        )
    return result


@app.get("/api/classes/{class_id}/materials/{material_name}/audio/status")
async def material_audio_status(
    class_id: str,
    material_name: str,
    section: str,
    voice: str = DEFAULT_VOICE,
    user: dict = Depends(get_current_user),
):
    """오디오 생성 상태를 폴링합니다."""
    _check_class_owner(class_id, user)
    return get_audio_status(user["email"], class_id, material_name, section, voice)


@app.get("/api/classes/{class_id}/materials/{material_name}/audio/manifest")
async def material_audio_manifest(
    class_id: str,
    material_name: str,
    section: str,
    voice: str = DEFAULT_VOICE,
    user: dict = Depends(get_current_user),
):
    """하이라이트 동기화용 매니페스트 JSON을 반환합니다."""
    _check_class_owner(class_id, user)
    manifest = get_audio_manifest(user["email"], class_id, material_name, section, voice)
    if manifest is None:
        raise HTTPException(status_code=404, detail="매니페스트가 아직 없습니다.")
    return manifest


_AUDIO_STREAM_CHUNK = 256 * 1024


@app.get("/api/classes/{class_id}/materials/{material_name}/audio/file")
async def material_audio_file(
    class_id: str,
    material_name: str,
    request: Request,
    section: str,
    voice: str = DEFAULT_VOICE,
    token: str = "",
):
    """오디오 파일을 스트리밍합니다 (HTTP Range 지원 — 모바일 탐색·이어듣기용).

    <audio> 태그는 Authorization 헤더를 붙일 수 없으므로 token 쿼리 파라미터도 허용.
    """
    auth_header = request.headers.get("authorization", "")
    raw_token = auth_header.removeprefix("Bearer ").strip() or token
    email = verify_token(raw_token) if raw_token else None
    user = get_user(email) if email else None
    if not user:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    _check_class_owner(class_id, user)

    found = get_audio_file(user["email"], class_id, material_name, section, voice)
    if not found:
        raise HTTPException(status_code=404, detail="오디오가 아직 준비되지 않았습니다.")
    path, media_type = found
    file_size = path.stat().st_size

    # Range 헤더 파싱 (bytes=start-end)
    start, end = 0, file_size - 1
    range_header = request.headers.get("range", "")
    is_partial = False
    m = re.match(r"bytes=(\d*)-(\d*)$", range_header)
    if m and (m.group(1) or m.group(2)):
        is_partial = True
        if m.group(1):
            start = int(m.group(1))
            if m.group(2):
                end = min(int(m.group(2)), file_size - 1)
        else:
            # suffix range: 마지막 N바이트
            start = max(file_size - int(m.group(2)), 0)
        if start >= file_size:
            raise HTTPException(status_code=416, detail="요청 범위가 파일 크기를 벗어났습니다.")

    def iter_range():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(_AUDIO_STREAM_CHUNK, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }
    if is_partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return StreamingResponse(
        iter_range(),
        status_code=206 if is_partial else 200,
        media_type=media_type,
        headers=headers,
    )


@app.get("/api/classes/{class_id}/materials/{material_name}/pdf")
async def material_pdf(
    class_id: str,
    material_name: str,
    request: Request,
    token: str = "",
):
    """PDF 원본을 반환합니다 (낭독 화면의 원본 보기용).

    pdf.js 뷰어는 Authorization 헤더를 붙일 수 없으므로 token 쿼리도 허용.
    """
    auth_header = request.headers.get("authorization", "")
    raw_token = auth_header.removeprefix("Bearer ").strip() or token
    email = verify_token(raw_token) if raw_token else None
    user = get_user(email) if email else None
    if not user:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    _check_class_owner(class_id, user)

    path = get_material_path(user["email"], class_id, material_name)
    if not path:
        raise HTTPException(status_code=404, detail="PDF 원본을 찾을 수 없습니다.")
    return FileResponse(path, media_type="application/pdf")


# --- Chat Endpoints ---


class ChatRequest(BaseModel):
    message: str
    thread_id: str
    class_id: str
    material_name: str = ""


@app.post("/api/chat")
async def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    """SSE 스트리밍으로 에이전트 응답을 반환합니다."""
    if over := check_limit(user["email"], "chat_daily"):
        raise HTTPException(status_code=429, detail=over)
    add_usage(user["email"], "chat_daily")

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


@app.get("/api/classes/{class_id}/completed-materials")
async def list_completed_materials(class_id: str, user: dict = Depends(get_current_user)):
    """학습 완료된 자료명 목록을 반환합니다."""
    return {"materials": get_completed_materials(user["email"], class_id)}


# --- Study Notes Endpoints ---


class SaveNoteRequest(BaseModel):
    class_id: str
    material_name: str
    content: str


@app.post("/api/notes", status_code=201)
async def save_note(body: SaveNoteRequest, user: dict = Depends(get_current_user)):
    return save_study_note(user["email"], body.class_id, body.material_name, body.content)


@app.get("/api/notes")
async def list_notes(class_id: str = "", material_name: str = "", user: dict = Depends(get_current_user)):
    return {"notes": get_study_notes(user["email"], class_id or None, material_name or None)}


@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: str, user: dict = Depends(get_current_user)):
    if not delete_study_note(note_id, user["email"]):
        raise HTTPException(status_code=404, detail="노트를 찾을 수 없습니다.")
    return {"status": "deleted"}


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
