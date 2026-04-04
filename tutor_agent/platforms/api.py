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

from ..auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_user,
    migrate_from_yaml,
    verify_token,
)
from ..service import (
    generate_example_messages,
    get_materials,
    new_thread_id,
    stream_chat,
    upload_material,
)

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


# --- Chat Endpoints ---


class ChatRequest(BaseModel):
    message: str
    thread_id: str


@app.post("/api/chat")
async def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    """SSE 스트리밍으로 에이전트 응답을 반환합니다."""

    async def event_generator():
        async for event in stream_chat(
            user_message=body.message,
            user_id=user["email"],
            thread_id=body.thread_id,
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


# --- Materials Endpoints ---


@app.get("/api/materials")
async def list_materials(user: dict = Depends(get_current_user)):
    materials = get_materials(user["email"])
    return {"materials": materials}


@app.post("/api/materials/upload")
async def upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
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
        result = upload_material(user["email"], tmp_path, display_name)
    finally:
        os.unlink(tmp_path)

    if result["status"] == "duplicate":
        raise HTTPException(
            status_code=409, detail=f"이미 업로드된 파일입니다: {result['name']}"
        )

    return result


# --- Example Messages ---


@app.get("/api/examples")
async def examples(user: dict = Depends(get_current_user)):
    return {"examples": generate_example_messages(user["email"])}


# --- Static Files (프로덕션: React 빌드 서빙) ---

_web_dist = Path(__file__).parent.parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="static")
