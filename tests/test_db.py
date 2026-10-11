import time
from pathlib import Path

from codevoight.core.models import (
    QuizOption,
    QuizQuestion,
    SessionStatus,
    StagedSession,
)
from codevoight.db.repository import StateRepository


def test_repository_crud(tmp_path: Path):
    db_path = tmp_path / "state.db"
    repo = StateRepository(db_path)

    now = time.time()
    session = StagedSession(
        session_id="sess-100",
        diff_text="--- a/x.py\n+++ b/x.py\n",
        diff_hash="hash-100",
        description="Fix bug in x.py",
        status=SessionStatus.PENDING_QUIZ,
        created_at=now,
        expires_at=now + 1800,
    )

    questions = [
        QuizQuestion(
            id="q1",
            prompt="What is changed?",
            options=[QuizOption(id="A", text="x.py"), QuizOption(id="B", text="y.py")],
            correct_option_id="A",
            explanation="x.py is modified",
        )
    ]

    repo.create_session(session, questions)

    # Retrieval
    retrieved = repo.get_session("sess-100")
    assert retrieved is not None
    assert retrieved.session_id == "sess-100"
    assert retrieved.status == SessionStatus.PENDING_QUIZ

    retrieved_questions = repo.get_questions_for_session("sess-100")
    assert len(retrieved_questions) == 1
    assert retrieved_questions[0].prompt == "What is changed?"
    assert retrieved_questions[0].correct_option_id == "A"

    # Status update & token assignment
    repo.update_session_status("sess-100", SessionStatus.APPROVED, "dummy-token-abc")
    approved = repo.get_session("sess-100")
    assert approved.status == SessionStatus.APPROVED
    assert approved.capability_token == "dummy-token-abc"

    # Find valid approved session
    found = repo.find_valid_approved_session("hash-100")
    assert found is not None
    assert found.session_id == "sess-100"

    # Consume token
    consumed = repo.consume_session_token("sess-100")
    assert consumed is True
    assert repo.get_session("sess-100").status == SessionStatus.CONSUMED
