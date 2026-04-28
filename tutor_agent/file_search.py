"""Gemini File Search Store 서비스 — 업로드, 검색, manifest 관리.

이 모듈이 File Search Store의 유일한 접근점입니다.
CLI(setup_store.py), REST API, LangGraph 도구 모두 이 모듈을 통해 접근합니다.

사용자별 구조:
    materials/{user_id}/           ← PDF 보관
    materials/{user_id}/manifest.json  ← 자동 생성
    Store display_name: tutor-{user_id}
"""

import json
import logging
import os
import shutil
import tempfile
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logger = logging.getLogger(__name__)

# --- 설정 ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
FILE_SEARCH_STORE_NAME = os.environ.get("FILE_SEARCH_STORE_NAME", "")
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Volume 마운트 경로 (/app/data) 아래에 저장하여 배포 간 유지
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_MATERIALS_DIR = os.path.join(_DATA_DIR, "materials")

# --- 클라이언트 (싱글턴) ---
_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Gemini API 클라이언트를 반환합니다 (싱글턴)."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


def _get_manifest_path(user_id: str = "", class_id: str = "") -> str:
    """사용자/클래스별 manifest 경로를 반환합니다."""
    if user_id and class_id:
        return os.path.join(_MATERIALS_DIR, user_id, class_id, "manifest.json")
    if user_id:
        return os.path.join(_MATERIALS_DIR, user_id, "manifest.json")
    return os.path.join(_PROJECT_ROOT, "file_manifest.json")


# ============================================================
# Store 관리 (setup_store.py에서 호출)
# ============================================================


def get_or_create_store(display_name: str) -> str:
    """File Search Store를 찾거나 새로 생성합니다.

    Returns:
        store_name (예: 'fileSearchStores/xxx')
    """
    client = get_client()

    # 기존 스토어 검색
    for store in client.file_search_stores.list():
        if store.display_name == display_name:
            logger.info(f"기존 스토어 발견: {store.name}")
            return store.name

    # 새 스토어 생성
    store = client.file_search_stores.create(
        config={"display_name": display_name}
    )
    logger.info(f"스토어 생성 완료: {store.name}")
    return store.name


def delete_store(store_name: str):
    """File Search Store를 삭제합니다."""
    client = get_client()
    client.file_search_stores.delete(name=store_name, config={"force": True})
    logger.info(f"스토어 삭제: {store_name}")


def upload_pdf(store_name: str, file_path: str, display_name: str):
    """PDF 파일을 File Search Store에 업로드하고 인덱싱합니다 (동기, 완료까지 대기).

    CLI/배치 용도. 웹 API에서는 upload_pdf_start + wait_for_indexing을 사용하세요.
    """
    op = upload_pdf_start(store_name, file_path, display_name)
    wait_for_indexing(op)
    logger.info(f"업로드 완료: {display_name}")


# --- 인덱싱 상태 추적 ---
# key: "{store_name}:{display_name}", value: "indexing" | "ready" | "error"
_indexing_status: dict[str, str] = {}


def _status_key(store_name: str, display_name: str) -> str:
    return f"{store_name}:{display_name}"


def get_indexing_status(store_name: str, display_name: str) -> str:
    """자료의 인덱싱 상태를 반환합니다. 추적 중이 아니면 "ready"."""
    return _indexing_status.get(_status_key(store_name, display_name), "ready")


def set_indexing_status(store_name: str, display_name: str, status: str):
    key = _status_key(store_name, display_name)
    if status == "ready":
        _indexing_status.pop(key, None)
    else:
        _indexing_status[key] = status


def upload_pdf_start(store_name: str, file_path: str, display_name: str):
    """PDF를 업로드하고 인덱싱을 시작합니다. Operation 객체를 반환합니다 (대기 없음)."""
    client = get_client()

    with tempfile.TemporaryDirectory() as tmpdir:
        safe_name = "upload.pdf"
        tmp_path = os.path.join(tmpdir, safe_name)
        shutil.copy2(file_path, tmp_path)

        uploaded = client.files.upload(
            file=tmp_path, config={"display_name": display_name}
        )

        op = client.file_search_stores.import_file(
            file_search_store_name=store_name,
            file_name=uploaded.name,
        )

    set_indexing_status(store_name, display_name, "indexing")
    return op


def wait_for_indexing(op):
    """인덱싱 완료까지 동기 대기합니다."""
    client = get_client()
    while not op.done:
        time.sleep(2)
        op = client.operations.get(op)


# ============================================================
# 자료 마크다운 인덱스 생성 (PDF → 학습용 요약)
# ============================================================

_INDEX_PROMPT = """첨부된 PDF 강의자료를 한눈에 훑을 수 있는 **초압축 목차**로 정리해줘.
요약본/정리본이 아니다. 각 섹션이 무엇을 다루는지만 한 줄로 적는다.

**분량 상한**: 자료 전체가 PDF 페이지 수의 2배 줄 이내 (예: 10페이지 → 20줄 이내).

**핵심 형식 (반드시 준수)**:

1. 헤딩(##, ###) **바로 뒤에 콜론(:)을 붙이고 같은 줄에 키워드 3~10개를 콤마로 나열**한다.
2. 헤딩 다음 줄에 별도 본문을 쓰지 않는다. 풀어쓰기·문장·sub-bullet 일체 금지.
3. **예외**: 헤딩이 명백히 분류된 하위 항목(2~5개)을 가질 때만, 다음 줄에 짧은 불릿으로 분류 항목을 나열. 각 불릿도 "이름: 키워드 3~5개" 한 줄.
4. 핵심 용어, 인명, 연도, 한자 원어는 보존 (예: 주역(周易), 왕필(王弼, 226-249)).
5. 도식·그림·각주는 거의 다 생략. 정말 중요할 때만 "[그림: 한 줄]".
6. JSON·코드블록·인사말 없이 마크다운만 출력. 첫 줄은 "# {자료 제목}".

**완성 예시** (이 패턴 그대로 따라):

# 9주 도시풍수: 전주와 나주
## 가. 전주
### 1. 전주의 역사: 호남 중심지, 통일신라 완산주(完山州), 견훤(甄萱) 수도, 조선 발상지, 1894 동학농민혁명 집강소(執綱所)
### 2. 풍남문(豐南門): 풍패지향(豊沛之鄕), 전주부성 남문, 한 고조 유방 고향 의미
### 3. 객사(客舍): 왕명 봉안, 사신 영접, 지역 위계의 중심
## 나. 나주
### 1. 나주의 역사: 나주 목, 영산강 수운, 호남 행정 중심
### 2. 도시 구조: 객사·향교·읍성, 풍수 형국 분석

**금지 패턴** (절대 이렇게 쓰지 말 것):

### 1. 전주의 역사
- 호남의 중심지였다.
- 통일신라 시대에 완산주로 불렸다.
- 견훤이 수도로 삼았다.
"""


def generate_material_index(file_path: str, display_name: str) -> str:
    """PDF 파일을 Gemini에 직접 입력해 학습용 마크다운 인덱스를 생성합니다.

    Args:
        file_path: 로컬 PDF 경로
        display_name: 자료 표시 이름 (제목 힌트로 사용)

    Returns:
        마크다운 텍스트
    """
    client = get_client()
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            f"자료 제목: {display_name}\n\n{_INDEX_PROMPT}",
        ],
    )
    return (response.text or "").strip()


def generate_material_index_from_store(store_name: str, display_name: str) -> str:
    """File Search Store에 인덱싱된 자료로부터 마크다운 인덱스를 생성합니다.

    원본 PDF가 디스크에 없을 때 (옛 자료 등) 사용하는 fallback.
    Gemini File Search RAG로 자료를 검색·요약합니다.
    """
    client = get_client()
    prompt = (
        f"자료 제목: {display_name}\n\n"
        f"이 자료의 모든 내용을 검색하여 학습 인덱스를 만들어주세요.\n\n"
        f"{_INDEX_PROMPT}"
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
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
    return (response.text or "").strip()


def get_index_path(user_id: str, class_id: str, display_name: str) -> str:
    """자료 인덱스 마크다운 파일 경로를 반환합니다."""
    return os.path.join(_MATERIALS_DIR, user_id, class_id, f"{display_name}.md")


def save_material_index(user_id: str, class_id: str, display_name: str, content: str):
    """마크다운 인덱스를 파일로 저장합니다."""
    path = get_index_path(user_id, class_id, display_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"인덱스 저장: {path} ({len(content)}자)")


def load_material_index(user_id: str, class_id: str, display_name: str) -> str | None:
    """저장된 마크다운 인덱스를 로드합니다. 없으면 None."""
    path = get_index_path(user_id, class_id, display_name)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def upload_pdfs(store_name: str, files: list[tuple[str, str]]):
    """여러 PDF 파일을 일괄 업로드합니다.

    Args:
        store_name: File Search Store 이름
        files: (절대경로, display_name) 튜플 리스트
    """
    client = get_client()
    print(f"\n총 {len(files)}개 PDF 업로드 시작...\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        operations = []
        for i, (file_path, display_name) in enumerate(files):
            safe_name = f"course_{i:03d}.pdf"
            tmp_path = os.path.join(tmpdir, safe_name)
            shutil.copy2(file_path, tmp_path)

            print(f"  [{i + 1}/{len(files)}] 업로드: {display_name}")
            uploaded = client.files.upload(
                file=tmp_path, config={"display_name": display_name}
            )

            op = client.file_search_stores.import_file(
                file_search_store_name=store_name,
                file_name=uploaded.name,
            )
            operations.append((display_name, op))

        print("\n인덱싱 대기 중...")
        for display_name, op in operations:
            while not op.done:
                time.sleep(2)
                op = client.operations.get(op)
            print(f"  완료: {display_name}")

    print(f"\n전체 {len(files)}개 PDF 업로드 및 인덱싱 완료!")


def save_manifest(display_names: list[str], user_id: str = "", class_id: str = "") -> list[str]:
    """display_name 목록을 manifest.json에 저장합니다.

    Args:
        display_names: 파일 display_name 리스트
        user_id: 사용자 ID
        class_id: 클래스 ID

    Returns:
        정렬된 display_name 리스트
    """
    display_names = sorted(display_names)

    manifest_path = _get_manifest_path(user_id, class_id)
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    with open(manifest_path, "w") as f:
        json.dump(display_names, f, ensure_ascii=False, indent=2)

    logger.info(f"manifest 저장: {len(display_names)}개 → {manifest_path}")
    return display_names


# ============================================================
# 검색 (tutor_tools.py에서 호출)
# ============================================================

# manifest 캐시 (하위 호환용으로 변수 유지)
_manifest_cache: dict[str, list[str]] = {}


def load_manifest(user_id: str = "", class_id: str = "") -> list[str]:
    """manifest.json에서 display_name 목록을 로드합니다."""
    manifest_path = _get_manifest_path(user_id, class_id)
    try:
        with open(manifest_path) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def find_matching_file(subject: str, user_id: str = "", class_id: str = "") -> str | None:
    """LLM을 사용하여 사용자 입력과 가장 일치하는 파일 display_name을 찾습니다.

    예: '양택풍수론 4주차' → '양택풍수론 - 제04주차_전통건축의 이해 한옥과 문화재 풍수'
    """
    display_names = load_manifest(user_id or DEFAULT_USER_ID, class_id)
    if not display_names:
        return None

    client = get_client()
    manifest_list = "\n".join(f"- {name}" for name in display_names)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            f"사용자 입력: \"{subject}\"\n\n"
            f"아래 파일 목록에서 사용자가 요청한 과목과 주차에 가장 정확히 일치하는 파일을 하나만 골라주세요.\n"
            f"일치하는 파일이 없으면 null을 반환하세요.\n\n"
            f"파일 목록:\n{manifest_list}\n\n"
            '반드시 아래 JSON 형식으로만 응답: {"match": "파일명" 또는 null}'
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    try:
        result = json.loads(response.text)
        matched = result.get("match")
        if matched and matched in display_names:
            logger.info(f"매칭: '{subject}' → '{matched}'")
            return matched
    except (json.JSONDecodeError, AttributeError):
        logger.warning(f"매칭 파싱 실패: {subject}")

    return None


def search(
    query: str,
    user_message: str = "",
    display_name: str = "",
    store_name: str = "",
    user_id: str = "",
    class_id: str = "",
) -> str:
    """Gemini File Search로 강좌 자료를 검색합니다.

    Args:
        query: 검색 쿼리 (예: '풍수학개론 3주차 핵심 내용')
        user_message: 원본 사용자 입력 — LLM으로 파일 매칭 (자연어 입력 시)
        display_name: 정확한 파일 display_name — LLM 매칭 건너뜀 (버튼 선택 시)
        store_name: Store 이름 (미지정 시 환경변수 사용)
        user_id: 사용자 ID (사용자별 manifest 로드용)
        class_id: 클래스 ID (클래스별 manifest 로드용)

    Returns:
        검색된 자료 텍스트
    """
    target_store = store_name or FILE_SEARCH_STORE_NAME
    if not target_store:
        return "FILE_SEARCH_STORE_NAME이 설정되지 않았습니다. setup_store.py를 먼저 실행하세요."

    # display_name이 직접 주어지면 LLM 매칭 건너뜀
    # display_name은 '|'로 구분된 복수 파일명일 수 있음
    file_hint = ""
    effective_user_id = user_id or DEFAULT_USER_ID
    if display_name and "|" in display_name:
        file_names = [n.strip() for n in display_name.split("|") if n.strip()]
        file_list = ", ".join(f'"{n}"' for n in file_names)
        file_hint = f"\n검색 대상 파일: {file_list}\n이 파일들의 내용만 정리해주세요."
    elif display_name:
        file_hint = (
            f"\n검색 대상 파일: \"{display_name}\"\n"
            "이 파일의 내용만 정리해주세요."
        )
    else:
        matched_file = (
            find_matching_file(user_message, effective_user_id, class_id) if user_message else None
        )
        if matched_file:
            file_hint = (
                f"\n검색 대상 파일: \"{matched_file}\"\n"
                "이 파일의 내용만 정리해주세요."
            )

    client = get_client()

    if file_hint:
        prompt = (
            f"다음 강좌 자료에서 관련 내용을 찾아서 핵심 개념, 주요 용어, "
            f"중요 내용을 상세히 정리해줘: {query}\n\n"
            f"중요: 반드시 요청된 특정 주차/강의 자료의 내용만 정리해주세요. "
            f"다른 주차나 다른 강의의 내용은 절대 포함하지 마세요."
            f"{file_hint}"
        )
    else:
        prompt = (
            f"다음 강좌 자료 전체에서 관련 내용을 찾아서 핵심 개념, 주요 용어, "
            f"중요 내용을 상세히 정리해줘: {query}\n\n"
            f"모든 자료를 검색하여 관련된 내용을 찾아주세요."
        )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[target_store]
                    )
                )
            ]
        ),
    )
    return response.text
