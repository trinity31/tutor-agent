"""JWT + SQLite 인증 모듈 + 퀴즈/학습 완료 데이터."""

import hashlib
import json
import os
import secrets
import sqlite3
import uuid
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
    # 다중 사용자 동시 접근 대비: WAL(읽기-쓰기 병행) + 잠금 대기
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS classes (
            id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_email) REFERENCES users(email)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_results (
            id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            class_id TEXT NOT NULL,
            material_name TEXT NOT NULL DEFAULT '',
            quiz_title TEXT NOT NULL DEFAULT '',
            questions TEXT NOT NULL,
            answers TEXT NOT NULL DEFAULT '{}',
            score INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            wrong_questions TEXT NOT NULL DEFAULT '[]',
            review_notes TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL DEFAULT 'normal',
            source_quiz_id TEXT,
            status TEXT NOT NULL DEFAULT 'completed',
            slack_channel TEXT DEFAULT '',
            slack_thread_ts TEXT DEFAULT '',
            current_question INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_email) REFERENCES users(email)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS completions (
            id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            class_id TEXT NOT NULL,
            material_name TEXT NOT NULL DEFAULT '',
            review_notes TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL DEFAULT 'normal',
            scheduled_date TEXT,
            schedule_mode TEXT,
            source_quiz_id TEXT,
            wrong_questions TEXT NOT NULL DEFAULT '[]',
            quiz_generated INTEGER NOT NULL DEFAULT 0,
            generated_quiz_id TEXT,
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_email) REFERENCES users(email)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audio_assets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            class_id TEXT NOT NULL,
            material_id TEXT NOT NULL,
            section TEXT NOT NULL,
            voice TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            duration REAL NOT NULL DEFAULT 0,
            file_path TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, class_id, material_id, section, voice)
        )
        """
    )
    # 기존 DB 마이그레이션: 실패 사유 컬럼 (없으면 추가)
    try:
        conn.execute("ALTER TABLE audio_assets ADD COLUMN error TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_counters (
            user_email TEXT NOT NULL,
            metric TEXT NOT NULL,
            period TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_email, metric, period)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS indexing_status (
            key TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS study_notes (
            id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            class_id TEXT NOT NULL,
            material_name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_email) REFERENCES users(email)
        )
        """
    )
    # 학습중 판정용 활동 마커: 과외·Q&A·퀴즈·인덱스·듣기 중 하나라도 하면 1행
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_starts (
            user_email TEXT NOT NULL,
            class_id TEXT NOT NULL,
            material_name TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_email, class_id, material_name)
        )
        """
    )
    conn.commit()
    return conn


# --- 클래스 CRUD ---


def create_class(user_email: str, name: str) -> dict:
    """클래스를 생성합니다."""
    conn = _get_db()
    try:
        class_id = str(uuid.uuid4())[:8]
        conn.execute(
            "INSERT INTO classes (id, user_email, name) VALUES (?, ?, ?)",
            (class_id, user_email.lower(), name),
        )
        conn.commit()
        return {"id": class_id, "name": name}
    finally:
        conn.close()


def get_classes(user_email: str) -> list[dict]:
    """사용자의 클래스 목록을 반환합니다."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, created_at FROM classes WHERE user_email = ? ORDER BY created_at",
            (user_email.lower(),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_class(class_id: str) -> dict | None:
    """클래스를 조회합니다."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT id, user_email, name FROM classes WHERE id = ?", (class_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_class(class_id: str):
    """클래스와 연관 데이터를 모두 삭제합니다."""
    conn = _get_db()
    try:
        conn.execute("DELETE FROM study_notes WHERE class_id = ?", (class_id,))
        conn.execute("DELETE FROM quiz_results WHERE class_id = ?", (class_id,))
        conn.execute("DELETE FROM completions WHERE class_id = ?", (class_id,))
        conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        conn.commit()
    finally:
        conn.close()


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


def create_reset_token(email: str, ttl_hours: int = 1) -> str | None:
    """비밀번호 재설정 토큰을 생성·저장합니다. 계정이 없으면 None."""
    email = email.lower()
    conn = _get_db()
    try:
        if not conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone():
            return None
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO password_reset_tokens (token, email, expires_at) "
            "VALUES (?, ?, datetime('now', ?))",
            (token, email, f"+{ttl_hours} hours"),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def verify_reset_token(token: str) -> str | None:
    """유효한(미사용·미만료) 재설정 토큰이면 이메일을 반환합니다."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT email FROM password_reset_tokens "
            "WHERE token = ? AND used = 0 AND expires_at > datetime('now')",
            (token,),
        ).fetchone()
        return row["email"] if row else None
    finally:
        conn.close()


def reset_password(token: str, new_password: str) -> bool:
    """재설정 토큰을 검증해 비밀번호를 변경하고 토큰을 폐기합니다."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT email FROM password_reset_tokens "
            "WHERE token = ? AND used = 0 AND expires_at > datetime('now')",
            (token,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE users SET hashed_password = ? WHERE email = ?",
            (_hash_password(new_password), row["email"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (token,)
        )
        conn.commit()
        return True
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


# --- 퀴즈 결과 CRUD ---


def save_quiz_result(
    user_email: str,
    class_id: str,
    material_name: str,
    quiz_title: str,
    questions: list[dict],
    answers: list[dict] | dict,
    score: int,
    total: int,
    quiz_type: str = "normal",
    source_quiz_id: str | None = None,
    status: str = "completed",
) -> dict:
    """퀴즈 결과를 저장합니다. 틀린 문제를 자동 추출합니다."""
    quiz_id = f"q-{uuid.uuid4().hex[:8]}"

    # 문제 형식 정규화 (TutorAgent → Slack 호환)
    LABELS = ["A", "B", "C", "D"]
    for i, q in enumerate(questions):
        if "number" not in q:
            q["number"] = i + 1
        # answer → correct 매핑 (Slack 핸들러용)
        if "correct" not in q and "answer" in q:
            answer_text = q["answer"]
            # options에 레이블이 없으면 추가
            if q.get("options") and not any(o.startswith("A.") for o in q["options"]):
                labeled = [f"{LABELS[j]}. {o}" for j, o in enumerate(q["options"][:4])]
                # 정답 레이블 찾기
                for j, o in enumerate(q["options"][:4]):
                    if o == answer_text:
                        q["correct"] = LABELS[j]
                        break
                else:
                    q["correct"] = "A"
                q["options"] = labeled
            else:
                q["correct"] = answer_text

    # 틀린 문제 추출
    wrong_questions = []
    if isinstance(answers, list):
        for i, a in enumerate(answers):
            if not a.get("correct", False) and i < len(questions):
                wrong_questions.append(questions[i])
    elif isinstance(answers, dict):
        for q in questions:
            q_num = str(q.get("number", ""))
            if q_num in answers and answers[q_num] != q.get("correct"):
                wrong_questions.append(q)

    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO quiz_results
               (id, user_email, class_id, material_name, quiz_title,
                questions, answers, score, total, wrong_questions,
                type, source_quiz_id, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                quiz_id,
                user_email.lower(),
                class_id,
                material_name,
                quiz_title,
                json.dumps(questions, ensure_ascii=False),
                json.dumps(answers, ensure_ascii=False),
                score,
                total,
                json.dumps(wrong_questions, ensure_ascii=False),
                quiz_type,
                source_quiz_id,
                status,
            ),
        )
        conn.commit()
        return {
            "id": quiz_id,
            "score": score,
            "total": total,
            "wrong_count": len(wrong_questions),
        }
    finally:
        conn.close()


def get_quiz_result(quiz_id: str) -> dict | None:
    """퀴즈 결과를 조회합니다."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM quiz_results WHERE id = ?", (quiz_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for field in ("questions", "answers", "wrong_questions"):
            d[field] = json.loads(d[field])
        return d
    finally:
        conn.close()


def get_quiz_results(user_email: str, class_id: str | None = None) -> list[dict]:
    """사용자의 퀴즈 결과 목록을 반환합니다."""
    conn = _get_db()
    try:
        if class_id:
            rows = conn.execute(
                "SELECT * FROM quiz_results WHERE user_email = ? AND class_id = ? ORDER BY completed_at DESC",
                (user_email.lower(), class_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM quiz_results WHERE user_email = ? ORDER BY completed_at DESC",
                (user_email.lower(),),
            ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            for field in ("questions", "answers", "wrong_questions"):
                d[field] = json.loads(d[field])
            results.append(d)
        return results
    finally:
        conn.close()


def update_quiz_result(quiz_id: str, **fields) -> bool:
    """퀴즈 결과를 부분 업데이트합니다."""
    if not fields:
        return False
    json_fields = {"questions", "answers", "wrong_questions"}
    set_clauses = []
    values = []
    for k, v in fields.items():
        set_clauses.append(f"{k} = ?")
        values.append(json.dumps(v, ensure_ascii=False) if k in json_fields else v)
    values.append(quiz_id)
    conn = _get_db()
    try:
        conn.execute(
            f"UPDATE quiz_results SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


# --- 학습 완료 / 재시험 예약 CRUD ---


def save_completion(
    user_email: str,
    class_id: str,
    material_name: str,
    completion_type: str = "normal",
    scheduled_date: str | None = None,
    schedule_mode: str | None = None,
    source_quiz_id: str | None = None,
    wrong_questions: list[dict] | None = None,
    review_notes: str = "",
) -> dict:
    """학습 완료 또는 재시험 예약을 기록합니다."""
    comp_id = str(uuid.uuid4())[:8]
    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO completions
               (id, user_email, class_id, material_name, review_notes,
                type, scheduled_date, schedule_mode,
                source_quiz_id, wrong_questions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                comp_id,
                user_email.lower(),
                class_id,
                material_name,
                review_notes,
                completion_type,
                scheduled_date,
                schedule_mode,
                source_quiz_id,
                json.dumps(wrong_questions or [], ensure_ascii=False),
            ),
        )
        conn.commit()
        return {"id": comp_id, "type": completion_type, "scheduled_date": scheduled_date}
    finally:
        conn.close()


def get_pending_completions(target_date: str) -> list[dict]:
    """예정된 퀴즈 생성 대상 completion을 조회합니다.

    - type=scheduled: scheduled_date == target_date
    - type=normal/retry: completed_at의 날짜 == target_date 전날 (어제 완료 → 오늘 생성)
    """
    conn = _get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM completions
               WHERE quiz_generated = 0
               AND (
                   (type = 'scheduled' AND scheduled_date = ?)
                   OR (type != 'scheduled' AND date(completed_at) = date(?, '-1 day'))
               )""",
            (target_date, target_date),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["wrong_questions"] = json.loads(d["wrong_questions"])
            results.append(d)
        return results
    finally:
        conn.close()


def get_completed_materials(user_email: str, class_id: str) -> list[str]:
    """학습 완료된 자료명 목록을 반환합니다."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT material_name FROM completions WHERE user_email = ? AND class_id = ?",
            (user_email.lower(), class_id),
        ).fetchall()
        return [r["material_name"] for r in rows]
    finally:
        conn.close()


def mark_material_started(user_email: str, class_id: str, material_name: str) -> None:
    """자료 학습 시작을 기록합니다(멱등).

    과외·Q&A·퀴즈·인덱스·듣기 중 하나라도 하면 호출되어 '학습중' 상태로 만든다.
    """
    if not material_name:
        return
    conn = _get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO material_starts (user_email, class_id, material_name) "
            "VALUES (?, ?, ?)",
            (user_email.lower(), class_id, material_name),
        )
        conn.commit()
    finally:
        conn.close()


def get_material_activity(user_email: str, class_id: str) -> dict:
    """자료별 학습 상태 계산용 집합을 반환합니다.

    completed: 학습 완료(completions) 자료.
    in_progress: 완료는 아니지만 활동(과외·Q&A·퀴즈·인덱스·듣기·노트)이 있는 자료.
    (둘 다 아닌 자료는 프론트에서 '미시작'으로 처리)
    """
    email = user_email.lower()
    conn = _get_db()
    try:
        completed = {
            r["material_name"]
            for r in conn.execute(
                "SELECT DISTINCT material_name FROM completions WHERE user_email=? AND class_id=?",
                (email, class_id),
            )
        }
        active: set[str] = set()
        for tbl in ("quiz_results", "study_notes", "material_starts"):
            active |= {
                r["material_name"]
                for r in conn.execute(
                    f"SELECT DISTINCT material_name FROM {tbl} WHERE user_email=? AND class_id=?",
                    (email, class_id),
                )
            }
        active -= completed
        completed.discard("")
        active.discard("")
        return {"completed": sorted(completed), "in_progress": sorted(active)}
    finally:
        conn.close()


def mark_completion_generated(completion_id: str, quiz_id: str):
    """completion을 퀴즈 생성 완료로 표시합니다."""
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE completions SET quiz_generated = 1, generated_quiz_id = ? WHERE id = ?",
            (quiz_id, completion_id),
        )
        conn.commit()
    finally:
        conn.close()


# --- 인덱싱 상태 (자료 업로드 진행 추적) ---

# 이 시간이 지난 'indexing' 상태는 중단된 것으로 간주 (서버 재시작 등)
_INDEXING_STALE_MINUTES = 30


def set_indexing_status_db(key: str, status: str):
    """인덱싱 상태를 기록합니다. 'ready'는 행 삭제로 표현합니다."""
    conn = _get_db()
    try:
        if status == "ready":
            conn.execute("DELETE FROM indexing_status WHERE key = ?", (key,))
        else:
            conn.execute(
                """INSERT INTO indexing_status (key, status, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(key) DO UPDATE
                   SET status = excluded.status, updated_at = excluded.updated_at""",
                (key, status),
            )
        conn.commit()
    finally:
        conn.close()


def get_indexing_status_db(key: str) -> str:
    """인덱싱 상태를 반환합니다. 기록이 없으면 'ready',
    오래 방치된 'indexing'은 'error'로 간주합니다."""
    conn = _get_db()
    try:
        row = conn.execute(
            f"""SELECT status,
                       (updated_at < datetime('now', '-{_INDEXING_STALE_MINUTES} minutes'))
                       AS stale
                FROM indexing_status WHERE key = ?""",
            (key,),
        ).fetchone()
        if not row:
            return "ready"
        if row["status"] == "indexing" and row["stale"]:
            return "error"
        return row["status"]
    finally:
        conn.close()


# --- 오디오 에셋 CRUD (원문 낭독) ---


def get_audio_asset(
    user_id: str, class_id: str, material_id: str, section: str, voice: str
) -> dict | None:
    """오디오 에셋을 조회합니다."""
    conn = _get_db()
    try:
        row = conn.execute(
            """SELECT * FROM audio_assets
               WHERE user_id = ? AND class_id = ? AND material_id = ?
               AND section = ? AND voice = ?""",
            (user_id.lower(), class_id, material_id, section, voice),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_audio_asset(
    user_id: str, class_id: str, material_id: str, section: str, voice: str
) -> bool:
    """오디오 에셋을 pending으로 생성합니다.

    Returns:
        True면 이 호출이 레코드를 선점 (생성 시작 책임), 이미 존재하면 False.
        동시 요청 시 중복 생성을 막습니다.
    """
    conn = _get_db()
    try:
        cur = conn.execute(
            """INSERT INTO audio_assets
               (id, user_id, class_id, material_id, section, voice, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')
               ON CONFLICT(user_id, class_id, material_id, section, voice)
               DO NOTHING""",
            (
                f"a-{uuid.uuid4().hex[:8]}",
                user_id.lower(),
                class_id,
                material_id,
                section,
                voice,
            ),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def reset_audio_asset(asset_id: str) -> bool:
    """failed(또는 파일이 사라진 ready) 에셋을 pending으로 되돌려 재생성을 선점합니다."""
    conn = _get_db()
    try:
        cur = conn.execute(
            """UPDATE audio_assets
               SET status = 'pending', duration = 0, file_path = '', error = ''
               WHERE id = ? AND status IN ('failed', 'ready')""",
            (asset_id,),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def update_audio_asset(asset_id: str, **fields):
    """오디오 에셋을 부분 업데이트합니다 (status, duration, file_path)."""
    if not fields:
        return
    set_clauses = ", ".join(f"{k} = ?" for k in fields)
    conn = _get_db()
    try:
        conn.execute(
            f"UPDATE audio_assets SET {set_clauses} WHERE id = ?",
            (*fields.values(), asset_id),
        )
        conn.commit()
    finally:
        conn.close()


# --- 학습 노트 CRUD ---


def save_study_note(
    user_email: str, class_id: str, material_name: str, content: str
) -> dict:
    """학습 노트를 저장합니다."""
    note_id = str(uuid.uuid4())[:8]
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO study_notes (id, user_email, class_id, material_name, content) VALUES (?, ?, ?, ?, ?)",
            (note_id, user_email.lower(), class_id, material_name, content),
        )
        conn.commit()
        return {"id": note_id, "material_name": material_name, "content": content}
    finally:
        conn.close()


def get_study_notes(
    user_email: str, class_id: str | None = None, material_name: str | None = None
) -> list[dict]:
    """학습 노트를 조회합니다."""
    conn = _get_db()
    try:
        query = "SELECT * FROM study_notes WHERE user_email = ?"
        params: list = [user_email.lower()]
        if class_id:
            query += " AND class_id = ?"
            params.append(class_id)
        if material_name:
            query += " AND material_name = ?"
            params.append(material_name)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_study_note(note_id: str, user_email: str) -> bool:
    """본인 소유의 학습 노트를 삭제합니다. 소유자가 아니면 아무것도 지우지 않습니다."""
    conn = _get_db()
    try:
        cur = conn.execute(
            "DELETE FROM study_notes WHERE id = ? AND user_email = ?",
            (note_id, user_email.lower()),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


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
