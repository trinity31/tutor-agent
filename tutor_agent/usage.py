"""사용자별 사용량 카운터와 한도 — 베타 단계 비용 폭주 방지.

API 키가 전역 공유이므로, 사용자별로 일 채팅 수·월 TTS 문자 수·
월 업로드 수를 세고 한도를 넘으면 요청을 거부한다.
한도는 환경변수로 조정하며 0 이하는 무제한을 뜻한다.
"""

import os
from datetime import datetime, timedelta, timezone

from .auth import _get_db

KST = timezone(timedelta(hours=9))

# metric 이름은 "_daily" / "_monthly" 접미사로 리셋 주기를 표현한다
LIMITS = {
    "chat_daily": int(os.getenv("LIMIT_CHAT_DAILY", "100")),
    "tts_chars_monthly": int(os.getenv("LIMIT_TTS_CHARS_MONTHLY", "300000")),
    "uploads_monthly": int(os.getenv("LIMIT_UPLOADS_MONTHLY", "20")),
}

_LIMIT_MESSAGES = {
    "chat_daily": "오늘의 채팅 한도({limit}회)를 모두 사용했습니다. 내일 다시 이용해 주세요.",
    "tts_chars_monthly": "이번 달 낭독 생성 한도를 모두 사용했습니다. 다음 달 1일에 초기화됩니다.",
    "uploads_monthly": "이번 달 자료 업로드 한도({limit}개)를 모두 사용했습니다.",
}


def _period(metric: str) -> str:
    now = datetime.now(KST)
    return now.strftime("%Y-%m-%d") if metric.endswith("_daily") else now.strftime("%Y-%m")


def get_usage(user_email: str, metric: str) -> int:
    """현재 주기의 사용량을 반환합니다."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT count FROM usage_counters WHERE user_email = ? AND metric = ? AND period = ?",
            (user_email.lower(), metric, _period(metric)),
        ).fetchone()
        return row["count"] if row else 0
    finally:
        conn.close()


def add_usage(user_email: str, metric: str, amount: int = 1):
    """사용량을 누적합니다."""
    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO usage_counters (user_email, metric, period, count)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_email, metric, period)
               DO UPDATE SET count = count + excluded.count""",
            (user_email.lower(), metric, _period(metric), amount),
        )
        conn.commit()
    finally:
        conn.close()


def check_limit(user_email: str, metric: str) -> str | None:
    """한도 초과 시 사용자 안내 문구를, 여유가 있으면 None을 반환합니다."""
    limit = LIMITS.get(metric, 0)
    if limit <= 0:
        return None
    if get_usage(user_email, metric) >= limit:
        return _LIMIT_MESSAGES[metric].format(limit=limit)
    return None
