"""신규 가입 사용자에게 샘플 클래스(낭독 체험)를 시딩한다.

seeds/onboarding/의 사전 작성 PDF + 사전 생성 오디오를 사용자 dir로 복사하고
자료 manifest·audio_assets DB 레코드를 만들어, 업로드 없이 첫 낭독을 즉시 체험하게 한다.
자료명은 오디오 캐시 키(§6-1 NFC 함정)와 일치하도록 NFC로 통일한다.
"""
import json
import logging
import shutil
import unicodedata
from pathlib import Path

from . import service
from .auth import (
    create_audio_asset,
    create_class,
    get_audio_asset,
    update_audio_asset,
)
from .file_search import save_manifest

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).parent.parent / "seeds" / "onboarding"
_SAMPLE_AUDIO_DIR = _SEED_DIR / "audio"
SAMPLE_MATERIAL = unicodedata.normalize("NFC", "기억과 복습의 과학")
SAMPLE_CLASS_NAME = "샘플 · 낭독 체험"


def _find_sample_pdf() -> Path | None:
    """시드 PDF를 glob으로 찾는다 — 파일명 NFC/NFD 정규화(§6-1)가
    macOS↔Linux 간 달라져도 리터럴 경로 불일치로 건너뛰지 않도록."""
    pdfs = sorted(_SEED_DIR.glob("*.pdf"))
    return pdfs[0] if pdfs else None


def seed_sample_class(user_email: str) -> None:
    """가입 직후 호출. 실패해도 가입은 유지되도록 예외를 삼킨다."""
    try:
        sample_pdf = _find_sample_pdf()
        if not sample_pdf:
            logger.warning("샘플 시드 PDF 없음 — 시딩 건너뜀")
            return
        email = user_email.lower()
        class_id = create_class(email, SAMPLE_CLASS_NAME)["id"]

        # 1) 자료 PDF + manifest (자료는 파일시스템 기반)
        mat_dir = service._MATERIALS_DIR / email / class_id
        mat_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(sample_pdf, mat_dir / f"{SAMPLE_MATERIAL}.pdf")
        save_manifest([SAMPLE_MATERIAL], email, class_id)

        # 사전 생성된 학습 인덱스(.md)도 복사 — 온보딩에서 인덱스 탭이
        # "생성" 버튼 대신 바로 내용을 보여주도록. 없으면 건너뜀(생성 버튼 폴백).
        seed_md = next(iter(_SEED_DIR.glob("*.md")), None)
        if seed_md:
            shutil.copy(seed_md, mat_dir / f"{SAMPLE_MATERIAL}.md")

        # 2) 사전 생성 오디오 + audio_assets 레코드 (오디오 경로엔 class_id 없음, NFC 자료명)
        audio_dir = service._AUDIO_DIR / email / SAMPLE_MATERIAL
        audio_dir.mkdir(parents=True, exist_ok=True)
        for mp3 in sorted(_SAMPLE_AUDIO_DIR.glob("*.mp3")):
            section, voice = mp3.stem.split("_", 1)  # "p1-1", "ko-KR-Neural2-C"
            shutil.copy(mp3, audio_dir / mp3.name)

            manifest_src = mp3.parent / f"{mp3.stem}.manifest.json"
            duration = 0.0
            if manifest_src.exists():
                shutil.copy(manifest_src, audio_dir / manifest_src.name)
                duration = json.loads(
                    manifest_src.read_text(encoding="utf-8")
                ).get("duration", 0.0)

            if create_audio_asset(email, class_id, SAMPLE_MATERIAL, section, voice):
                asset = get_audio_asset(email, class_id, SAMPLE_MATERIAL, section, voice)
                if asset:
                    update_audio_asset(
                        asset["id"],
                        status="ready",
                        duration=duration,
                        file_path=str(audio_dir / mp3.name),
                    )
        logger.info(f"샘플 클래스 시딩 완료: {email} (class {class_id})")
    except Exception:
        logger.exception(f"샘플 클래스 시딩 실패: {user_email}")
