"""TTS 엔진 추상화 — Gemini TTS 구현.

TTSEngine 프로토콜을 만족하는 구현체를 교체하면
Google Cloud TTS/Speechify 등으로 전환할 수 있습니다.
"""

import logging
import time
from typing import Protocol

from google.genai import types

from .file_search import get_client, reset_client

logger = logging.getLogger(__name__)

TTS_MODEL = "gemini-2.5-flash-preview-tts"

# Gemini TTS 출력 포맷: 24kHz 16bit(2바이트) mono PCM
PCM_RATE = 24000
PCM_BYTES_PER_SECOND = PCM_RATE * 2

# 검증된 음성 3종 (tts-demo 참조). 기본값은 Charon.
VOICES = {
    "Kore": "여성",
    "Charon": "남성 저음",
    "Puck": "남성 밝음",
}
DEFAULT_VOICE = "Charon"

_NARRATION_PROMPT = "다음 텍스트를 차분한 강의 낭독 톤으로 읽어주세요:\n\n"


def pcm_duration(pcm: bytes) -> float:
    """PCM 바이트 길이로 재생 시간(초)을 계산합니다."""
    return len(pcm) / PCM_BYTES_PER_SECOND


class TTSEngine(Protocol):
    """텍스트를 24kHz s16le mono PCM으로 합성하는 엔진."""

    def synthesize(self, text: str, voice: str) -> bytes: ...


class GeminiTTSEngine:
    """Gemini 2.5 Flash TTS 구현체."""

    MAX_ATTEMPTS = 3

    def synthesize(self, text: str, voice: str) -> bytes:
        """텍스트를 PCM으로 합성합니다. 빈 응답·일시 오류 시 자동 재시도합니다.

        (gemini가 간헐적으로 빈 응답을 내는 것을 흡수 — stream_chat의 재시도 패턴 참조.
        병렬 호출 중 공유 클라이언트가 닫히는 오류는 클라이언트를 재생성해 복구한다.)
        """
        last_error: Exception | None = None
        for attempt in range(self.MAX_ATTEMPTS):
            if attempt:
                time.sleep(2**attempt)  # 2s, 4s 백오프
            try:
                pcm = self._call(text, voice)
            except Exception as e:
                last_error = e
                logger.warning(
                    "TTS 호출 실패 (%d/%d): %s", attempt + 1, self.MAX_ATTEMPTS, e
                )
                reset_client()
                continue
            if pcm:
                return pcm
            logger.warning(
                "TTS 빈 응답 감지 — 재시도합니다. (%d/%d, voice=%s)",
                attempt + 1, self.MAX_ATTEMPTS, voice,
            )
        raise RuntimeError(f"TTS 합성에 실패했습니다: {last_error or '빈 응답'}")

    def _call(self, text: str, voice: str) -> bytes:
        response = get_client().models.generate_content(
            model=TTS_MODEL,
            contents=_NARRATION_PROMPT + text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice
                        )
                    )
                ),
            ),
        )
        try:
            part = response.candidates[0].content.parts[0]
            return part.inline_data.data or b""
        except (AttributeError, IndexError, TypeError):
            return b""
