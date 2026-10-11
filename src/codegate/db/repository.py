from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator, List, Optional

from codegate.core.models import (
    QuizOption,
    QuizQuestion,
    SessionStatus,
    StagedSession,
)
from codegate.db.schema import init_db


class StateRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_init()

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_init(self) -> None:
        with self._get_connection() as conn:
            init_db(conn)

    def create_session(self, session: StagedSession, questions: List[QuizQuestion]) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sessions (
                    session_id, diff_text, diff_hash, description, status,
                    created_at, expires_at, capability_token
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.diff_text,
                    session.diff_hash,
                    session.description,
                    session.status.value,
                    session.created_at,
                    session.expires_at,
                    session.capability_token,
                ),
            )

            for q in questions:
                options_data = [opt.model_dump() for opt in q.options]
                cursor.execute(
                    """
                    INSERT INTO questions (
                        id, session_id, prompt, options_json, correct_option_id, explanation
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        q.id,
                        session.session_id,
                        q.prompt,
                        json.dumps(options_data),
                        q.correct_option_id,
                        q.explanation,
                    ),
                )
            conn.commit()

    def get_session(self, session_id: str) -> Optional[StagedSession]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return StagedSession(
                session_id=row["session_id"],
                diff_text=row["diff_text"],
                diff_hash=row["diff_hash"],
                description=row["description"],
                status=SessionStatus(row["status"]),
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                capability_token=row["capability_token"],
            )

    def get_latest_pending_session(self) -> Optional[StagedSession]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM sessions 
                WHERE status = ? AND expires_at > ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (SessionStatus.PENDING_QUIZ.value, time.time()),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return StagedSession(
                session_id=row["session_id"],
                diff_text=row["diff_text"],
                diff_hash=row["diff_hash"],
                description=row["description"],
                status=SessionStatus(row["status"]),
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                capability_token=row["capability_token"],
            )

    def get_questions_for_session(self, session_id: str) -> List[QuizQuestion]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM questions WHERE session_id = ?",
                (session_id,),
            )
            rows = cursor.fetchall()
            questions = []
            for r in rows:
                opts = [QuizOption(**opt) for opt in json.loads(r["options_json"])]
                questions.append(
                    QuizQuestion(
                        id=r["id"],
                        prompt=r["prompt"],
                        options=opts,
                        correct_option_id=r["correct_option_id"],
                        explanation=r["explanation"],
                    )
                )
            return questions

    def update_session_status(
        self, session_id: str, status: SessionStatus, token: Optional[str] = None
    ) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if token is not None:
                cursor.execute(
                    "UPDATE sessions SET status = ?, capability_token = ? WHERE session_id = ?",
                    (status.value, token, session_id),
                )
            else:
                cursor.execute(
                    "UPDATE sessions SET status = ? WHERE session_id = ?",
                    (status.value, session_id),
                )
            conn.commit()

    def find_valid_approved_session(self, diff_hash: str) -> Optional[StagedSession]:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM sessions 
                WHERE diff_hash = ? AND status = ? AND expires_at > ? AND capability_token IS NOT NULL
                ORDER BY created_at DESC LIMIT 1
                """,
                (diff_hash, SessionStatus.APPROVED.value, now),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return StagedSession(
                session_id=row["session_id"],
                diff_text=row["diff_text"],
                diff_hash=row["diff_hash"],
                description=row["description"],
                status=SessionStatus(row["status"]),
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                capability_token=row["capability_token"],
            )

    def consume_session_token(self, session_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sessions SET status = ? WHERE session_id = ? AND status = ?",
                (SessionStatus.CONSUMED.value, session_id, SessionStatus.APPROVED.value),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_sessions(self, limit: int = 20) -> List[StagedSession]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                StagedSession(
                    session_id=r["session_id"],
                    diff_text=r["diff_text"],
                    diff_hash=r["diff_hash"],
                    description=r["description"],
                    status=SessionStatus(r["status"]),
                    created_at=r["created_at"],
                    expires_at=r["expires_at"],
                    capability_token=r["capability_token"],
                )
                for r in rows
            ]
