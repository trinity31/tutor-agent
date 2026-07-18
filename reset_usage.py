"""사용량 카운터 리셋 — 일회성 관리 스크립트.

TTS 월 한도(tts_chars_monthly) 등에 걸렸을 때 특정 사용자의 사용량만
현재 주기에서 초기화한다. Railway 셸에서 실행하면 프로덕션 DB(볼륨)에 적용된다.

안전장치: 기본은 '현황만 표시'(dry-run)이며, 실제 삭제는 --yes 를 줘야 한다.

사용 예:
  uv run python reset_usage.py you@example.com                       # 현황만(삭제 안 함)
  uv run python reset_usage.py you@example.com --yes                 # 이번 달 tts_chars_monthly 리셋
  uv run python reset_usage.py you@example.com --metric uploads_monthly --yes
  uv run python reset_usage.py you@example.com --period 2026-07 --yes
"""

import argparse

from tutor_agent.auth import _get_db
from tutor_agent.usage import LIMITS, _period


def main() -> None:
    parser = argparse.ArgumentParser(description="사용자 사용량 카운터 리셋")
    parser.add_argument("email", help="대상 사용자 이메일")
    parser.add_argument(
        "--metric",
        default="tts_chars_monthly",
        help="리셋할 지표 (기본: tts_chars_monthly)",
    )
    parser.add_argument(
        "--period",
        default=None,
        help="주기 (기본: 지표에 맞는 현재 주기, 예: 2026-07)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="실제로 삭제 (없으면 현황만 표시)",
    )
    args = parser.parse_args()

    email = args.email.lower()
    period = args.period or _period(args.metric)

    conn = _get_db()
    try:
        # 삭제 전 현황 전체를 먼저 보여준다(확인용)
        rows = conn.execute(
            "SELECT metric, period, count FROM usage_counters "
            "WHERE user_email = ? ORDER BY period DESC, metric",
            (email,),
        ).fetchall()

        print(f"\n[{email}] 현재 사용량 (전체 주기):")
        if not rows:
            print("  (기록 없음)")
        for row in rows:
            limit = LIMITS.get(row["metric"], 0)
            cap = f" / {limit}" if limit > 0 else " / 무제한"
            print(f"  - {row['metric']:<22} {row['period']:<10} {row['count']}{cap}")

        target = conn.execute(
            "SELECT count FROM usage_counters "
            "WHERE user_email = ? AND metric = ? AND period = ?",
            (email, args.metric, period),
        ).fetchone()
        current = target["count"] if target else 0

        print(
            f"\n리셋 대상 → metric={args.metric}, period={period}, 현재값={current}"
        )

        if not args.yes:
            print("\n(dry-run) 실제로 초기화하려면 --yes 를 붙여 다시 실행하세요.")
            return

        cur = conn.execute(
            "DELETE FROM usage_counters "
            "WHERE user_email = ? AND metric = ? AND period = ?",
            (email, args.metric, period),
        )
        conn.commit()
        print(
            f"\n삭제 완료: {cur.rowcount}행. "
            f"{args.metric}({period}) 사용량이 0으로 초기화됐습니다."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
