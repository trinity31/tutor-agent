"""File Search Store 초기화 — 사용자별 PDF 업로드 + manifest 자동 생성.

사용자별 Store 세팅:
  uv run python setup_store.py --user-id test_user --knowledge-dir ./materials/test_user

재생성:
  uv run python setup_store.py --user-id test_user --knowledge-dir ./materials/test_user --reset

업로드 대상 확인:
  uv run python setup_store.py --user-id test_user --knowledge-dir ./materials/test_user --dry-run

폴더 구조:
  materials/
  └── {user_id}/
      ├── 양택풍수론/
      │   └── 04주.pdf
      ├── 풍수학개론/
      │   └── 03주.pdf
      └── manifest.json  ← 자동 생성
"""

import argparse
import os
import re

from dotenv import set_key

from tutor_agent.file_search import (
    delete_store,
    get_or_create_store,
    save_manifest,
    upload_pdfs,
)

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")

# 제외 패턴
COMBINED_PDF_PATTERN = re.compile(r"\d{2}-\d{2}\.pdf$|\d{2}-\d{2}\s*\(.*\)\.pdf$")
EXCLUDE_PATTERNS = [
    re.compile(r"^00[_ ]"),
    re.compile(r"Quiz-Bot", re.IGNORECASE),
    re.compile(r"인포그래픽"),
]


def should_exclude(filepath: str) -> bool:
    """제외 대상 파일인지 확인."""
    basename = os.path.basename(filepath)
    if COMBINED_PDF_PATTERN.search(basename):
        return True
    for pattern in EXCLUDE_PATTERNS:
        if pattern.search(basename) or pattern.search(filepath):
            return True
    return False


def collect_pdfs(knowledge_dir: str) -> list[tuple[str, str]]:
    """업로드 대상 PDF 수집. (절대경로, display_name) 튜플 리스트 반환."""
    files = []
    for root, dirs, filenames in os.walk(knowledge_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in sorted(filenames):
            if not filename.lower().endswith(".pdf"):
                continue
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, knowledge_dir)
            if should_exclude(rel_path):
                continue
            display_name = rel_path.replace("/", " - ").removesuffix(".pdf")
            files.append((filepath, display_name))
    return files


def main():
    parser = argparse.ArgumentParser(description="Gemini File Search Store 초기화")
    parser.add_argument(
        "--user-id", required=True, help="사용자 ID (예: test_user)"
    )
    parser.add_argument(
        "--knowledge-dir",
        help="PDF 디렉토리 경로 (미지정 시 materials/{user_id})",
    )
    parser.add_argument(
        "--reset", action="store_true", help="기존 스토어 삭제 후 재생성"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="업로드 대상 파일만 확인"
    )
    args = parser.parse_args()

    user_id = args.user_id
    store_display_name = f"tutor-{user_id}"

    # knowledge_dir 결정
    if args.knowledge_dir:
        knowledge_dir = os.path.expanduser(args.knowledge_dir)
    else:
        knowledge_dir = os.path.join(os.path.dirname(__file__), "materials", user_id)

    if not os.path.isdir(knowledge_dir):
        print(f"디렉토리가 존재하지 않습니다: {knowledge_dir}")
        print(f"먼저 {knowledge_dir} 에 PDF 파일을 넣어주세요.")
        return

    files = collect_pdfs(knowledge_dir)
    if args.dry_run:
        print(f"[{user_id}] 업로드 대상 PDF {len(files)}개:")
        for _, display_name in files:
            print(f"  {display_name}")
        return

    # Store 생성/확인
    store_name = get_or_create_store(store_display_name)

    if args.reset:
        delete_store(store_name)
        store_name = get_or_create_store(store_display_name)

    # 파일 업로드
    if files:
        upload_pdfs(store_name, files)
    else:
        print("업로드 대상 PDF가 없습니다.")

    # manifest 자동 생성 (materials/{user_id}/manifest.json)
    display_names = [dn for _, dn in files]
    manifest = save_manifest(display_names, user_id)
    print(f"\nmanifest 생성: {len(manifest)}개 파일")

    # .env에 Store 이름 저장 (개발용 기본값)
    set_key(ENV_FILE, "FILE_SEARCH_STORE_NAME", store_name)
    print(f".env에 FILE_SEARCH_STORE_NAME={store_name} 저장 완료")


if __name__ == "__main__":
    main()
