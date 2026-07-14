"""이메일 발송 — SMTP(표준 라이브러리). Gmail·Resend 등 SMTP 제공자 공용.

SMTP_HOST 미설정 시 전체 no-op — 로컬·미설정 환경에서 안전하게 스킵한다.
설정 예:
- Gmail: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USER=you@gmail.com,
  SMTP_PASSWORD=<앱 비밀번호>, MAIL_FROM=you@gmail.com
- Resend: SMTP_HOST=smtp.resend.com, SMTP_USER=resend, SMTP_PASSWORD=<API 키>,
  MAIL_FROM=ai-tutor@yourdomain
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

logger = logging.getLogger(__name__)


def _config() -> dict | None:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return None
    user = os.getenv("SMTP_USER", "").strip()
    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": user,
        "password": os.getenv("SMTP_PASSWORD", ""),
        "sender": os.getenv("MAIL_FROM", "").strip() or user,
    }


def send_email(to: str, subject: str, html: str, text: str = "") -> bool:
    """단일 수신자에게 메일을 보냅니다. 미설정·실패 시 False(예외 삼킴)."""
    cfg = _config()
    if not cfg or not to:
        logger.warning("SMTP 미설정 — 이메일 발송 스킵 (to=%s)", to)
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("AI Tutor", cfg["sender"]))
    msg["To"] = to
    msg.set_content(text or "HTML을 지원하는 메일 클라이언트에서 확인해 주세요.")
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        logger.info("이메일 발송 완료 (to=%s)", to)
        return True
    except Exception as e:
        logger.error("이메일 발송 실패 (to=%s): %s", to, e)
        return False


def send_reset_email(to: str, token: str) -> bool:
    """비밀번호 재설정 메일. 재설정 페이지 링크(토큰 포함)를 담는다."""
    base = os.getenv("APP_BASE_URL", "https://ai-tutor.davinci-apps.online").rstrip("/")
    link = f"{base}/reset?token={token}"
    subject = "[AI Tutor] 비밀번호 재설정"
    html = f"""\
<div style="max-width:480px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#222;">
  <h2 style="color:#12b886;margin:0 0 8px;">비밀번호 재설정</h2>
  <p style="margin:0 0 16px;color:#556;">아래 버튼을 눌러 새 비밀번호를 설정하세요. 이 링크는 1시간 후 만료됩니다.</p>
  <a href="{link}" style="display:inline-block;background:#12b886;color:#fff;text-decoration:none;font-weight:700;padding:12px 24px;border-radius:12px;">비밀번호 재설정</a>
  <p style="margin:20px 0 0;font-size:12px;color:#99a;">본인이 요청하지 않았다면 이 메일을 무시하세요.<br/>AI Tutor · 교재를 귀로</p>
</div>"""
    text = f"비밀번호 재설정 링크(1시간 후 만료): {link}\n\n본인이 요청하지 않았다면 무시하세요."
    return send_email(to, subject, html, text)


def send_review_email(to: str, quiz_titles: list[str]) -> bool:
    """복습 퀴즈 준비 알림 메일. 앱 '복습' 화면 링크를 담는다."""
    base = os.getenv("APP_BASE_URL", "https://ai-tutor.davinci-apps.online").rstrip("/")
    link = f"{base}/review"
    n = len(quiz_titles)
    subject = f"[AI Tutor] 오늘의 복습 퀴즈 {n}개가 준비됐어요"
    items = "".join(
        f'<li style="margin:4px 0;color:#334;">{t}</li>' for t in quiz_titles
    )
    html = f"""\
<div style="max-width:480px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#222;">
  <h2 style="color:#12b886;margin:0 0 8px;">오늘의 복습 퀴즈 {n}개 🔁</h2>
  <p style="margin:0 0 12px;color:#556;">잊을 때쯤 다시 물어봐요. 아래 자료의 복습 퀴즈가 준비됐어요.</p>
  <ul style="padding-left:18px;margin:0 0 20px;">{items}</ul>
  <a href="{link}" style="display:inline-block;background:#12b886;color:#fff;text-decoration:none;font-weight:700;padding:12px 24px;border-radius:12px;">지금 복습하기</a>
  <p style="margin:20px 0 0;font-size:12px;color:#99a;">AI Tutor · 교재를 귀로</p>
</div>"""
    text = (
        f"오늘의 복습 퀴즈 {n}개가 준비됐어요.\n\n"
        + "\n".join(f"- {t}" for t in quiz_titles)
        + f"\n\n지금 복습하기: {link}"
    )
    return send_email(to, subject, html, text)
