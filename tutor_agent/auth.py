"""JWT + SQLite 인증 모듈."""

import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from jose import JWTError, jwt

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "tutor-agent-dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 30  # 30일

DB_PATH = Path(__file__).parent.parent / "data" / "users.db"


def _hash_password(password: str) -> str:
    """SHA-256 pre-hash + bcrypt으로 비밀번호를 해싱합니다.

    bcrypt의 72바이트 제한을 우회하기 위해 SHA-256으로 먼저 해싱합니다.
    """
    sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return bcrypt.hashpw(sha256.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """비밀번호를 검증합니다."""
    sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return bcrypt.checkpw(sha256.encode("utf-8"), hashed.encode("utf-8"))


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    return conn


def create_user(email: str, password: str, name: str = "") -> dict:
    """새 사용자를 생성합니다. 이미 존재하면 ValueError를 발생시킵니다."""
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO users (email, name, hashed_password) VALUES (?, ?, ?)",
            (email.lower(), name or email, _hash_password(password)),
        )
        conn.commit()
        return {"email": email.lower(), "name": name or email}
    except sqlite3.IntegrityError:
        raise ValueError("이미 등록된 이메일입니다.")
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> dict | None:
    """이메일과 비밀번호로 사용자를 인증합니다. 실패 시 None을 반환합니다."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()
        if row and _verify_password(password, row["hashed_password"]):
            return {"email": row["email"], "name": row["name"]}
        return None
    finally:
        conn.close()


def get_user(email: str) -> dict | None:
    """이메일로 사용자를 조회합니다."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT email, name FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_access_token(email: str) -> str:
    """JWT 액세스 토큰을 생성합니다."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": email, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> str | None:
    """토큰을 검증하고 이메일을 반환합니다. 실패 시 None을 반환합니다."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def migrate_from_yaml(yaml_path: str = "auth_config.yaml") -> int:
    """기존 auth_config.yaml에서 사용자를 마이그레이션합니다."""
    import yaml

    path = Path(yaml_path)
    if not path.exists():
        return 0

    with open(path) as f:
        config = yaml.safe_load(f)

    usernames = config.get("credentials", {}).get("usernames", {})
    migrated = 0
    conn = _get_db()
    try:
        for username, data in usernames.items():
            email = data.get("email", username).lower()
            name = data.get("name", email)
            hashed_pw = data.get("password", "")
            try:
                conn.execute(
                    "INSERT INTO users (email, name, hashed_password) VALUES (?, ?, ?)",
                    (email, name, hashed_pw),
                )
                migrated += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        return migrated
    finally:
        conn.close()
