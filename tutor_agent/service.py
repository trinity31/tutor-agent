"""Service Layer — 그래프 실행의 유일한 진입점.

모든 플랫폼 어댑터(API, Slack 등)는 이 모듈만 호출합니다.
"""

import json
import logging
import os
import re
import shutil
import struct
import subprocess
import uuid
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from .agents.graph import build_graph
from .file_search import (
    generate_material_index,
    generate_material_index_from_store,
    get_client as get_genai_client,
    get_or_create_store,
    get_indexing_status,
    load_manifest,
    load_material_index,
    save_manifest,
    save_material_index,
    set_indexing_status,
    upload_pdf,
    upload_pdf_start,
    wait_for_indexing,
    GEMINI_MODEL,
)
from .narration import build_narration_chunks_paged
from .tts import GeminiTTSEngine, PCM_RATE, pcm_duration

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
        # 도구를 많이 호출하는 자료(섹션이 많은 인덱스)에서도 최종 응답까지
        # 도달하도록 기본값(25)보다 여유를 둔다.
        "recursion_limit": 50,
        "configurable": {
            "thread_id": f"{user_id}_{thread_id}",
            "user_id": user_id,
            "class_id": class_id,
            "store_name": store_name,
            "material_name": material_name,
        }
    }
    graph_input = {
        "messages": [HumanMessage(content=user_message)],
        "user_id": user_id,
        "class_id": class_id,
        "store_name": store_name,
        "material_name": material_name,
    }

    # 그래프를 한 번 실행하며 agent_status 이벤트를 yield하는 동기 제너레이터.
    def _stream_statuses():
        for event in _graph.stream(graph_input, config=config, stream_mode="updates"):
            for node_name in event:
                if node_name != "supervisor_agent":
                    label = AGENT_LABELS.get(node_name, node_name)
                    yield {
                        "event": "agent_status",
                        "data": {"agent": node_name, "label": label},
                    }

    # 이번 턴에 새로 추가된 메시지에서만 응답을 추출한다.
    # (전체 히스토리를 스캔하면 supervisor가 빈 응답을 내어 이번 턴 답이 없을 때
    #  이전 턴의 옛 퀴즈를 잘못 재사용하게 된다.)
    def _extract_turn(before: int) -> tuple[str, str]:
        final_values = _graph.get_state(config).values
        turn_messages = final_values.get("messages", [])[before:]
        return (
            extract_ai_content({"messages": turn_messages}),
            final_values.get("current_agent", ""),
        )

    try:
        before = len(_graph.get_state(config).values.get("messages", []))
        for ev in _stream_statuses():
            yield ev
        ai_content, current_agent = _extract_turn(before)

        # 빈 응답(LLM이 텍스트·tool 호출 없는 응답을 반환)이면 1회 자동 재시도.
        # gemini-2.5-flash가 간헐적으로 빈 응답을 내는 것을 서버가 흡수한다.
        if not ai_content:
            logger.warning("빈 응답 감지 — 자동 재시도합니다.")
            before = len(_graph.get_state(config).values.get("messages", []))
            for ev in _stream_statuses():
                yield ev
            ai_content, current_agent = _extract_turn(before)

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
    """PDF를 클래스에 업로드합니다. 인덱싱은 시작만 하고 즉시 반환합니다."""
    store_name = _store_name_for(user_id, class_id)
    existing = load_manifest(user_id, class_id)

    if display_name in existing:
        return {"status": "duplicate", "name": display_name}

    op = upload_pdf_start(store_name, file_path, display_name)
    save_manifest(existing + [display_name], user_id, class_id)

    # PDF를 로컬에 보관 (뷰어용)
    local_dir = _MATERIALS_DIR / user_id / class_id
    local_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, local_dir / f"{display_name}.pdf")

    return {"status": "indexing", "name": display_name, "_op": op, "_store_name": store_name}


logger = logging.getLogger(__name__)


def finish_indexing(op, store_name: str, display_name: str, user_id: str = "", class_id: str = ""):
    """백그라운드에서 인덱싱 완료를 대기하고 마크다운 인덱스를 생성합니다."""
    try:
        wait_for_indexing(op)
        logger.info(f"인덱싱 완료: {display_name}")

        if user_id and class_id:
            pdf_path = _MATERIALS_DIR / user_id / class_id / f"{display_name}.pdf"
            if pdf_path.exists() and not load_material_index(user_id, class_id, display_name):
                try:
                    md = generate_material_index(str(pdf_path), display_name)
                    if md:
                        save_material_index(user_id, class_id, display_name, md)
                except Exception:
                    logger.exception(f"인덱스 생성 실패: {display_name}")

        set_indexing_status(store_name, display_name, "ready")
    except Exception:
        set_indexing_status(store_name, display_name, "error")
        logger.exception(f"인덱싱 실패: {display_name}")


def get_material_index(user_id: str, class_id: str, display_name: str) -> str | None:
    """저장된 마크다운 인덱스를 반환합니다 (없으면 None)."""
    return load_material_index(user_id, class_id, display_name)


def regenerate_material_index(user_id: str, class_id: str, display_name: str) -> str | None:
    """마크다운 인덱스를 재생성하여 저장합니다.

    PDF 원본이 디스크에 있으면 PDF 직접 입력 방식 사용 (정확도 우선),
    없으면 File Search Store fallback 사용 (옛 자료용).
    """
    pdf_path = _MATERIALS_DIR / user_id / class_id / f"{display_name}.pdf"
    md: str | None = None

    if pdf_path.exists():
        try:
            md = generate_material_index(str(pdf_path), display_name)
        except Exception:
            logger.exception(f"PDF 기반 인덱스 생성 실패: {display_name}")

    if not md:
        store_name = _store_name_for(user_id, class_id)
        try:
            md = generate_material_index_from_store(store_name, display_name)
        except Exception:
            logger.exception(f"Store 기반 인덱스 생성 실패: {display_name}")
            return None

    if md:
        save_material_index(user_id, class_id, display_name, md)
    return md or None


def get_material_indexing_status(user_id: str, class_id: str, display_name: str) -> str:
    """자료의 인덱싱 상태를 반환합니다."""
    store_name = _store_name_for(user_id, class_id)
    return get_indexing_status(store_name, display_name)


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


# --- 원문 낭독 (Read-Aloud) ---

_AUDIO_DIR = Path(__file__).parent.parent / "data" / "audio"

# 섹션(챕터) = 페이지 그룹. 요청된 섹션만 온디맨드로 생성하여 TTS 비용을 제한한다.
AUDIO_SECTION_PAGES = 8
_SECTION_RE = re.compile(r"p(\d+)-(\d+)$")
# TTS 동시 호출 수 (rate limit과 첫 재생 대기 시간의 균형)
_TTS_CONCURRENCY = 3

_tts_engine = GeminiTTSEngine()


def _audio_base(user_id: str, material_id: str, section: str, voice: str) -> Path:
    """오디오 파일 경로의 확장자 없는 base를 반환합니다."""
    return _AUDIO_DIR / user_id / material_id / f"{section}_{voice}"


def _pdf_page_count(pdf_path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(pdf_path)).pages)


def get_audio_sections(user_id: str, class_id: str, material_name: str) -> list[dict] | None:
    """자료의 낭독 섹션 목록을 반환합니다. PDF가 없으면 None."""
    pdf_path = get_material_path(user_id, class_id, material_name)
    if not pdf_path:
        return None
    total = _pdf_page_count(pdf_path)
    sections = []
    for start in range(1, total + 1, AUDIO_SECTION_PAGES):
        end = min(start + AUDIO_SECTION_PAGES - 1, total)
        sections.append({"section": f"p{start}-{end}", "title": f"{start}~{end}쪽"})
    return sections


def _parse_section(section: str) -> tuple[int, int] | None:
    """섹션 ID('p1-8')를 페이지 범위(1-based)로 파싱합니다."""
    m = _SECTION_RE.match(section)
    if not m:
        return None
    start, end = int(m.group(1)), int(m.group(2))
    if start < 1 or end < start:
        return None
    return start, end


def request_audio(
    user_id: str, class_id: str, material_name: str, section: str, voice: str
) -> dict:
    """오디오 생성을 요청합니다. 캐시가 있으면 즉시 ready를 반환합니다.

    Returns:
        {"status": ..., "duration": ...} — "_start"가 True면 호출자가
        백그라운드 생성(generate_audio_asset)을 시작해야 합니다.
    """
    from .auth import create_audio_asset, get_audio_asset, reset_audio_asset

    asset = get_audio_asset(user_id, class_id, material_name, section, voice)
    if asset:
        if asset["status"] == "ready" and Path(asset["file_path"]).exists():
            return {"status": "ready", "duration": asset["duration"]}
        if asset["status"] in ("pending", "generating"):
            return {"status": asset["status"]}
        # failed 또는 파일이 사라진 ready → 재생성 선점
        if reset_audio_asset(asset["id"]):
            return {"status": "pending", "_start": True}
        return {"status": "pending"}

    if create_audio_asset(user_id, class_id, material_name, section, voice):
        return {"status": "pending", "_start": True}
    # 동시 요청이 먼저 선점한 경우
    asset = get_audio_asset(user_id, class_id, material_name, section, voice)
    return {"status": asset["status"] if asset else "pending"}


def get_audio_status(
    user_id: str, class_id: str, material_name: str, section: str, voice: str
) -> dict:
    """오디오 생성 상태를 반환합니다."""
    from .auth import get_audio_asset

    asset = get_audio_asset(user_id, class_id, material_name, section, voice)
    if not asset:
        return {"status": "none", "duration": 0}
    return {"status": asset["status"], "duration": asset["duration"]}


def get_audio_file(
    user_id: str, class_id: str, material_name: str, section: str, voice: str
) -> tuple[Path, str] | None:
    """ready 상태인 오디오 파일 경로와 media type을 반환합니다."""
    from .auth import get_audio_asset

    asset = get_audio_asset(user_id, class_id, material_name, section, voice)
    if not asset or asset["status"] != "ready":
        return None
    path = Path(asset["file_path"])
    if not path.exists():
        return None
    media_type = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
    return path, media_type


def get_audio_manifest(
    user_id: str, class_id: str, material_name: str, section: str, voice: str
) -> dict | None:
    """오디오 매니페스트 JSON을 반환합니다 (프론트 하이라이트 동기화용)."""
    manifest_path = Path(
        f"{_audio_base(user_id, material_name, section, voice)}.manifest.json"
    )
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


# 본문 폰트 크기의 95% 미만 텍스트(각주·푸터·쪽번호)는 낭독에서 제외
_BODY_FONT_RATIO = 0.95


def _effective_font_size(tm, font_size) -> float:
    """텍스트 렌더링 행렬을 반영한 실제 폰트 크기를 계산합니다."""
    if not font_size:
        return 0.0
    return abs(font_size * tm[3]) if tm and tm[3] else font_size


def _dominant_font_size(reader) -> float:
    """문서 본문 폰트 크기(글자 수 기준 최빈값)를 계산합니다."""
    from collections import Counter

    sizes: Counter = Counter()

    def visitor(text, cm, tm, font_dict, font_size):
        t = text.strip()
        if t:
            eff = _effective_font_size(tm, font_size)
            if eff:
                sizes[round(eff, 1)] += len(t)

    for page in reader.pages:
        try:
            page.extract_text(visitor_text=visitor)
        except Exception:
            continue
    return sizes.most_common(1)[0][0] if sizes else 0.0


def _extract_body_pages(reader, start: int, end: int) -> list[tuple[int, str]]:
    """섹션 페이지(1-based, 양끝 포함)의 본문 텍스트를 페이지별로 추출합니다.

    각주·푸터·쪽번호·URL 줄은 본문보다 작은 폰트로 조판되므로
    본문 폰트 크기 95% 미만인 텍스트를 걸러 낭독에서 제외한다.
    페이지 번호는 PDF 뷰의 재생 위치 동기화(자동 넘김)에 쓰인다.
    """
    threshold = _dominant_font_size(reader) * _BODY_FONT_RATIO
    plain_pages: list[tuple[int, str]] = []
    body_pages: list[tuple[int, str]] = []

    for page_no, page in enumerate(reader.pages[start - 1 : end], start=start):
        chunks: list[str] = []

        def visitor(text, cm, tm, font_dict, font_size):
            if text and (
                not threshold or _effective_font_size(tm, font_size) >= threshold
            ):
                chunks.append(text)

        try:
            plain_pages.append((page_no, page.extract_text(visitor_text=visitor) or ""))
        except Exception:
            plain_pages.append((page_no, page.extract_text() or ""))
        body_pages.append((page_no, "".join(chunks)))

    body_len = sum(len(t.strip()) for _, t in body_pages)
    plain_len = sum(len(t.strip()) for _, t in plain_pages)
    # 과도하게 걸러진 경우(특이한 조판) 원본 추출로 폴백
    if body_len < plain_len * 0.3:
        return plain_pages
    return body_pages


def _extract_body_text(reader, start: int, end: int) -> str:
    """섹션 본문 텍스트를 하나의 문자열로 반환합니다 (페이지 정보 불필요 시)."""
    return "\n".join(t for _, t in _extract_body_pages(reader, start, end))


def _pcm_to_wav(pcm: bytes, path: Path, rate: int = PCM_RATE) -> None:
    """PCM(s16le mono)에 WAV 헤더를 붙여 저장합니다 (tts-demo 참조)."""
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", len(pcm)) + pcm)


def _encode_audio(pcm: bytes, base: Path) -> Path:
    """PCM을 MP3로 인코딩합니다. ffmpeg이 없으면 WAV로 폴백합니다."""
    base.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        mp3_path = base.with_suffix(".mp3")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1", "-i", "pipe:0",
                "-b:a", "64k", str(mp3_path),
            ],
            input=pcm,
            check=True,
            capture_output=True,
        )
        return mp3_path
    wav_path = base.with_suffix(".wav")
    _pcm_to_wav(pcm, wav_path)
    return wav_path


def generate_audio_asset(
    user_id: str, class_id: str, material_name: str, section: str, voice: str
):
    """백그라운드에서 섹션 오디오를 생성합니다.

    PDF 섹션 텍스트 → 낭독 정제 → 청크별 TTS → 병합 + 매니페스트 저장.
    Gemini TTS는 타임스탬프를 주지 않으므로 청크별 PCM 길이로
    정확한 재생 시간을 계산해 매니페스트에 기록한다.
    """
    from pypdf import PdfReader

    from .auth import get_audio_asset, update_audio_asset

    asset = get_audio_asset(user_id, class_id, material_name, section, voice)
    if not asset or asset["status"] not in ("pending", "generating"):
        return

    def _fail(reason: str):
        logger.error(f"오디오 생성 실패: {material_name}/{section} — {reason}")
        update_audio_asset(asset["id"], status="failed")

    try:
        update_audio_asset(asset["id"], status="generating")

        pdf_path = get_material_path(user_id, class_id, material_name)
        pages = _parse_section(section)
        if not pdf_path or not pages:
            return _fail("PDF 또는 섹션을 찾을 수 없음")

        reader = PdfReader(str(pdf_path))
        start, end = pages
        chunks = build_narration_chunks_paged(_extract_body_pages(reader, start, end))
        if not chunks:
            return _fail("낭독할 문장이 없음 (이미지 기반 PDF일 수 있음)")

        # 청크별 TTS 호출 (제한된 동시성)
        with ThreadPoolExecutor(max_workers=_TTS_CONCURRENCY) as pool:
            pcms = list(
                pool.map(
                    lambda c: _tts_engine.synthesize(" ".join(c["sentences"]), voice),
                    chunks,
                )
            )

        # 병합 + 청크별 정확한 재생 시간 계산 (하이라이트·페이지 동기화 근거)
        manifest_chunks = []
        cursor = 0.0
        for chunk, pcm in zip(chunks, pcms):
            duration = pcm_duration(pcm)
            manifest_chunks.append({
                "text": " ".join(chunk["sentences"]),
                "start": round(cursor, 2),
                "end": round(cursor + duration, 2),
                "sentences": chunk["sentences"],
                "page": chunk["page"],
            })
            cursor += duration

        base = _audio_base(user_id, material_name, section, voice)
        file_path = _encode_audio(b"".join(pcms), base)

        manifest = {
            "voice": voice,
            "format": file_path.suffix.lstrip("."),
            "duration": round(cursor, 2),
            "chunks": manifest_chunks,
        }
        with open(f"{base}.manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

        update_audio_asset(
            asset["id"],
            status="ready",
            duration=round(cursor, 2),
            file_path=str(file_path),
        )
        logger.info(
            f"오디오 생성 완료: {material_name}/{section} ({voice}, {cursor:.0f}초, {len(chunks)}청크)"
        )
    except Exception:
        logger.exception(f"오디오 생성 실패: {material_name}/{section}")
        update_audio_asset(asset["id"], status="failed")


# --- 복습 스케줄링 ---

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
        logger.warning(f"날짜 파싱 실패: {user_input}")
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
    logger.info(f"[크론] 예약 퀴즈 대상: {len(completions)}건 (date={today})")

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
                config = {"recursion_limit": 50, "configurable": {
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
            logger.error(f"[크론] 퀴즈 생성 실패: {comp['id']} — {e}")
            results.append({"completion_id": comp["id"], "status": "error", "reason": str(e)})

    return results
