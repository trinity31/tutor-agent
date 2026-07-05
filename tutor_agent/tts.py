"""TTS 엔진 추상화 — Google Cloud TTS(기본)와 Gemini TTS 구현.

TTS_ENGINE 환경변수로 엔진을 선택합니다: "gcp"(기본) | "gemini".
TTSEngine 프로토콜을 만족하는 구현체를 추가하면 다른 엔진으로도
교체할 수 있습니다 (예: Supertone).
"""

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import ClassVar, Protocol

from google import genai
from google.genai import types

from .file_search import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

# 파이프라인 공통 오디오 포맷: 24kHz 16bit(2바이트) mono PCM
PCM_RATE = 24000
PCM_BYTES_PER_SECOND = PCM_RATE * 2


def pcm_duration(pcm: bytes) -> float:
    """PCM 바이트 길이로 재생 시간(초)을 계산합니다."""
    return len(pcm) / PCM_BYTES_PER_SECOND


def _is_daily_quota_error(e: Exception) -> bool:
    """일일 쿼터 초과(재시도 무의미) 오류인지 판별합니다."""
    msg = str(e)
    return "RESOURCE_EXHAUSTED" in msg and ("PerDay" in msg or "per_day" in msg)


class TTSEngine(Protocol):
    """텍스트를 24kHz s16le mono PCM으로 합성하는 엔진."""

    VOICES: ClassVar[dict[str, str]]  # 음성 이름 → 표시 레이블
    DEFAULT_VOICE: ClassVar[str]

    def synthesize(self, text: str, voice: str) -> bytes: ...


class _RetryingSynthesis:
    """빈 응답·일시 오류 자동 재시도 공통 로직.

    (gemini가 간헐적으로 빈 응답을 내는 것을 흡수 — stream_chat의 재시도 패턴 참조.)
    일일 쿼터 초과는 재시도해도 소용없으므로 즉시 실패합니다.
    """

    MAX_ATTEMPTS = 3

    def _call(self, text: str, voice: str) -> bytes:  # 구현체가 정의
        raise NotImplementedError

    def synthesize(self, text: str, voice: str) -> bytes:
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
                if _is_daily_quota_error(e):
                    break
                continue
            if pcm:
                return pcm
            logger.warning(
                "TTS 빈 응답 감지 — 재시도합니다. (%d/%d, voice=%s)",
                attempt + 1, self.MAX_ATTEMPTS, voice,
            )
        raise RuntimeError(f"TTS 합성에 실패했습니다: {last_error or '빈 응답'}")


# --- Google Cloud TTS (기본 엔진) ---

_GCP_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"


def _strip_wav_header(wav: bytes) -> bytes:
    """LINEAR16 응답의 WAV 헤더를 제거하고 raw PCM을 반환합니다."""
    if not wav.startswith(b"RIFF"):
        return wav
    idx = wav.find(b"data")
    if idx == -1:
        return wav
    return wav[idx + 8 :]


class GoogleCloudTTSEngine(_RetryingSynthesis):
    """Google Cloud Text-to-Speech 구현체.

    Neural2/WaveNet은 월 100만 자까지 무료라 강의 낭독 볼륨에 적합.
    키는 GCP_TTS_API_KEY, 없으면 GOOGLE_API_KEY 재사용
    (해당 키에 Cloud Text-to-Speech API 접근이 허용되어 있어야 함).
    """

    VOICES = {
        "ko-KR-Neural2-C": "남성 차분",
        "ko-KR-Wavenet-D": "남성 밝음",
        "ko-KR-Neural2-A": "여성",
    }
    DEFAULT_VOICE = "ko-KR-Neural2-C"

    def _call(self, text: str, voice: str) -> bytes:
        api_key = os.environ.get("GCP_TTS_API_KEY") or GOOGLE_API_KEY
        body = json.dumps({
            "input": {"text": text},
            "voice": {"languageCode": "ko-KR", "name": voice},
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": PCM_RATE,
            },
        }).encode()
        req = urllib.request.Request(
            f"{_GCP_TTS_URL}?key={api_key}",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"Cloud TTS 오류 {e.code}: {detail}") from e
        wav = base64.b64decode(payload.get("audioContent", ""))
        return _strip_wav_header(wav)


# --- Gemini TTS ---

TTS_MODEL = "gemini-2.5-flash-preview-tts"

_NARRATION_PROMPT = "다음 텍스트를 차분한 강의 낭독 톤으로 읽어주세요:\n\n"


class GeminiTTSEngine(_RetryingSynthesis):
    """Gemini 2.5 Flash TTS 구현체.

    낭독 톤이 자연스럽지만 일일 쿼터(Tier 1 기준 100회)가 낮다.
    """

    VOICES = {
        "Kore": "여성",
        "Charon": "남성 저음",
        "Puck": "남성 밝음",
    }
    DEFAULT_VOICE = "Charon"

    def _call(self, text: str, voice: str) -> bytes:
        # 호출마다 독립 클라이언트 사용 — 병렬 호출 중 한 스레드의 오류가
        # 공유 클라이언트를 닫아 다른 스레드까지 죽이는 것을 방지
        client = genai.Client(api_key=GOOGLE_API_KEY)
        response = client.models.generate_content(
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


# --- 엔진 선택 ---

_ENGINES = {
    "gcp": GoogleCloudTTSEngine,
    "gemini": GeminiTTSEngine,
}


def _create_engine() -> TTSEngine:
    name = os.environ.get("TTS_ENGINE", "gcp").lower()
    engine_cls = _ENGINES.get(name)
    if engine_cls is None:
        logger.warning("알 수 없는 TTS_ENGINE=%s — gcp를 사용합니다.", name)
        engine_cls = GoogleCloudTTSEngine
    return engine_cls()


_engine: TTSEngine = _create_engine()


def get_engine() -> TTSEngine:
    """설정된 TTS 엔진 싱글턴을 반환합니다."""
    return _engine


# 현재 엔진의 음성 목록 (API 검증·프론트 표시용)
VOICES = _engine.VOICES
DEFAULT_VOICE = _engine.DEFAULT_VOICE
