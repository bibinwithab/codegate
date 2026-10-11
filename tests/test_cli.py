import time
from pathlib import Path
from click.testing import CliRunner

from codevoight.cli import main
from codevoight.core.diff import compute_diff_hash
from codevoight.core.models import QuizOption, QuizQuestion, SessionStatus, StagedSession
from codevoight.db.repository import StateRepository


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "CodeVoight: Voight-Kampff Comprehension Gate" in result.output


def test_cli_status(tmp_path: Path, monkeypatch):
    tmp_path = tmp_path.resolve()
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    # Initial status without DB
    result_empty = runner.invoke(main, ["status"])
    assert result_empty.exit_code == 0
    assert "No CodeVoight database found" in result_empty.output

    # Create dummy session in .codevoight
    codevoight_dir = tmp_path / ".codevoight"
    repo = StateRepository(codevoight_dir / "state.db")
    now = time.time()
    session = StagedSession(
        session_id="sess-cli-1",
        diff_text="diff content",
        diff_hash="hash-cli-1",
        description="CLI test session",
        status=SessionStatus.PENDING_QUIZ,
        created_at=now,
        expires_at=now + 1800,
    )
    repo.create_session(session, [])

    result_with_session = runner.invoke(main, ["status"])
    assert result_with_session.exit_code == 0
    assert "sess-cli-1" in result_with_session.output
    assert "PENDING_QUIZ" in result_with_session.output


def test_cli_quiz_pass(tmp_path: Path, monkeypatch):
    tmp_path = tmp_path.resolve()
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    codevoight_dir = tmp_path / ".codevoight"
    repo = StateRepository(codevoight_dir / "state.db")
    now = time.time()
    diff_text = "--- a/x.py\n+++ b/x.py\n+def foo(): pass\n"
    diff_hash = compute_diff_hash(diff_text)

    session = StagedSession(
        session_id="sess-quiz-1",
        diff_text=diff_text,
        diff_hash=diff_hash,
        description="Add foo function",
        status=SessionStatus.PENDING_QUIZ,
        created_at=now,
        expires_at=now + 1800,
    )

    question = QuizQuestion(
        id="q1",
        prompt="What function was added?",
        options=[
            QuizOption(id="A", text="foo"),
            QuizOption(id="B", text="bar"),
            QuizOption(id="C", text="baz"),
            QuizOption(id="D", text="qux"),
        ],
        correct_option_id="A",
        explanation="Function foo was added.",
    )

    repo.create_session(session, [question])

    # Run quiz answering "A"
    result = runner.invoke(main, ["quiz", "sess-quiz-1"], input="A\n")
    assert result.exit_code == 0
    assert "[PASSED]" in result.output
    assert "[UNLOCKED]" in result.output

    # Verify session is now APPROVED with a capability token
    updated = repo.get_session("sess-quiz-1")
    assert updated.status == SessionStatus.APPROVED
    assert updated.capability_token is not None


def test_cli_quiz_fail(tmp_path: Path, monkeypatch):
    tmp_path = tmp_path.resolve()
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    codevoight_dir = tmp_path / ".codevoight"
    repo = StateRepository(codevoight_dir / "state.db")
    now = time.time()
    diff_text = "--- a/x.py\n+++ b/x.py\n+def foo(): pass\n"
    diff_hash = compute_diff_hash(diff_text)

    session = StagedSession(
        session_id="sess-quiz-2",
        diff_text=diff_text,
        diff_hash=diff_hash,
        description="Add foo function",
        status=SessionStatus.PENDING_QUIZ,
        created_at=now,
        expires_at=now + 1800,
    )

    question = QuizQuestion(
        id="q1",
        prompt="What function was added?",
        options=[
            QuizOption(id="A", text="foo"),
            QuizOption(id="B", text="bar"),
            QuizOption(id="C", text="baz"),
            QuizOption(id="D", text="qux"),
        ],
        correct_option_id="A",
        explanation="Function foo was added.",
    )

    repo.create_session(session, [question])

    # Run quiz answering "B" (incorrect)
    result = runner.invoke(main, ["quiz", "sess-quiz-2"], input="B\n")
    assert result.exit_code == 1
    assert "[FAILED]" in result.output
    assert "[LOCKED]" in result.output

    # Verify session is marked REJECTED
    updated = repo.get_session("sess-quiz-2")
    assert updated.status == SessionStatus.REJECTED
