from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

import click

from codevoight.core.diff import compute_diff_hash, normalize_text
from codevoight.core.models import (
    QuizSubmission,
    SessionStatus,
    StagedSession,
)
from codevoight.core.security import get_or_create_secret, sign_token
from codevoight.db.repository import StateRepository
from codevoight.generators.deterministic import (
    DeterministicQuizEvaluator,
    DeterministicQuizGenerator,
)
from codevoight.git.hook import install_pre_commit_hook, verify_staged_commit
from codevoight.git.runner import GitRunner


def get_repo_and_db_paths() -> tuple[Path, Path]:
    runner = GitRunner()
    root = (runner.get_repo_root() or Path.cwd()).resolve()
    codevoight_dir = root / ".codevoight"
    if not codevoight_dir.exists():
        if (root / ".quizgate").exists():
            codevoight_dir = root / ".quizgate"
        elif (root / ".codegate").exists():
            codevoight_dir = root / ".codegate"
    db_path = codevoight_dir / "state.db"
    return codevoight_dir, db_path


@click.group()
def main() -> None:
    """CodeVoight: Voight-Kampff Comprehension Gate for AI Commits."""
    pass


@main.command("quiz")
@click.argument("session_id", required=False)
def run_quiz(session_id: Optional[str] = None) -> None:
    """Take comprehension quiz for a staged change to unlock git commit."""
    codevoight_dir, db_path = get_repo_and_db_paths()
    repo = StateRepository(db_path)

    session = None
    if session_id:
        session = repo.get_session(session_id)
        if not session:
            click.echo(f"[ERROR] Session '{session_id}' not found.", err=True)
            sys.exit(1)
    else:
        session = repo.get_latest_pending_session()
        if not session:
            click.echo("[INFO] No pending quiz sessions found.", err=True)
            click.echo("Stage code changes via MCP or 'codevoight stage' first.")
            sys.exit(0)

    click.echo("=" * 60)
    click.echo(f"CODEVOIGHT COMPREHENSION QUIZ")
    click.echo(f"Session ID : {session.session_id}")
    click.echo(f"Diff Hash  : {session.diff_hash[:16]}...")
    if session.description:
        click.echo(f"Description: {session.description}")
    click.echo("=" * 60)

    # Show Diff Summary
    click.echo("\n--- STAGED DIFF PREVIEW ---")
    diff_lines = session.diff_text.strip().splitlines()
    for line in diff_lines[:30]:
        click.echo(line)
    if len(diff_lines) > 30:
        click.echo(f"... ({len(diff_lines) - 30} more lines omitted) ...")
    click.echo("---------------------------\n")

    questions = repo.get_questions_for_session(session.session_id)
    if not questions:
        click.echo("[WARNING] No questions found for this session. Generating on the fly...")
        gen = DeterministicQuizGenerator()
        questions = gen.generate_quiz(session.diff_text, session.description)

    answers = {}
    for idx, q in enumerate(questions, 1):
        click.echo(f"\n[Question {idx}/{len(questions)}] {q.prompt}")
        for opt in q.options:
            click.echo(f"  [{opt.id}] {opt.text}")

        valid_ids = [opt.id.upper() for opt in q.options]
        chosen = ""
        while chosen not in valid_ids:
            chosen = click.prompt("Your answer", type=str).strip().upper()
        answers[q.id] = chosen

    # Evaluate
    submission = QuizSubmission(session_id=session.session_id, answers=answers)
    evaluator = DeterministicQuizEvaluator(passing_score=1.0)
    result = evaluator.evaluate(submission, questions)

    click.echo("\n" + "=" * 60)
    if result.passed:
        secret_key = get_or_create_secret(codevoight_dir)
        token = sign_token(session.session_id, session.diff_hash, secret_key)
        repo.update_session_status(session.session_id, SessionStatus.APPROVED, token.serialize())

        click.echo(f"[PASSED] Score: {int(result.score * 100)}% ({result.correct}/{result.total})")
        click.echo(f"[UNLOCKED] Capability token generated for diff hash {session.diff_hash[:16]}.")
        click.echo("You may now proceed with 'git commit' or call the MCP commit tool.")
    else:
        repo.update_session_status(session.session_id, SessionStatus.REJECTED)
        click.echo(f"[FAILED] Score: {int(result.score * 100)}% ({result.correct}/{result.total})")
        click.echo("[LOCKED] Commit permission DENIED. Review the following feedback:")
        for fb in result.feedback:
            click.echo(f"  * {fb}")
        click.echo("\nReview the diff and run 'codevoight quiz' to try again.")
        sys.exit(1)
    click.echo("=" * 60)


@main.command("status")
def show_status() -> None:
    """View active and recent CodeVoight staging sessions."""
    _, db_path = get_repo_and_db_paths()
    if not db_path.exists():
        click.echo("[INFO] No CodeVoight database found in current repository.")
        return

    repo = StateRepository(db_path)
    sessions = repo.list_sessions(limit=10)
    if not sessions:
        click.echo("[INFO] No staging sessions found.")
        return

    click.echo(f"{'SESSION ID':<12} {'STATUS':<15} {'EXPIRES IN':<12} {'DIFF HASH':<16} {'DESCRIPTION'}")
    click.echo("-" * 75)
    now = time.time()
    for s in sessions:
        remaining = max(0, int(s.expires_at - now))
        rem_str = f"{remaining}s" if remaining > 0 else "EXPIRED"
        click.echo(f"{s.session_id[:10]:<12} {s.status.value:<15} {rem_str:<12} {s.diff_hash[:14]:<16} {s.description[:20]}")


@main.command("hook")
@click.argument("action", type=click.Choice(["install", "verify"]))
def manage_hook(action: str) -> None:
    """Install or test the Git pre-commit verification hook."""
    if action == "install":
        success, msg = install_pre_commit_hook()
        if success:
            click.echo(f"[SUCCESS] CodeVoight pre-commit hook installed to: {msg}")
        else:
            click.echo(f"[ERROR] Failed to install hook: {msg}", err=True)
            sys.exit(1)
    elif action == "verify":
        success, msg = verify_staged_commit()
        if success:
            click.echo(f"[SUCCESS] {msg}")
        else:
            click.echo(f"[DENIED] {msg}", err=True)
            sys.exit(1)


@main.command("verify-commit", hidden=True)
def run_verify_commit() -> None:
    """Internal entrypoint invoked directly by .git/hooks/pre-commit."""
    success, msg = verify_staged_commit()
    if not success:
        click.echo(f"[CODEVOIGHT] {msg}", err=True)
        sys.exit(1)
    sys.exit(0)


@main.command("stage")
@click.argument("files", nargs=-1, required=True)
@click.option("--description", "-m", default="Manual CLI staging", help="Description of staged change")
def stage_from_cli(files: tuple[str, ...], description: str) -> None:
    """Stage files and create a comprehension quiz session."""
    runner = GitRunner()
    if not runner.is_git_repo():
        click.echo("[ERROR] Not in a git repository.", err=True)
        sys.exit(1)

    runner.stage_files(list(files))
    staged_diff = runner.get_staged_diff()
    if not staged_diff.strip():
        click.echo("[WARNING] No staged changes found for specified files.")
        return

    import uuid
    codevoight_dir, db_path = get_repo_and_db_paths()
    repo = StateRepository(db_path)
    diff_hash = compute_diff_hash(staged_diff)

    gen = DeterministicQuizGenerator()
    questions = gen.generate_quiz(staged_diff, description)

    now = time.time()
    session = StagedSession(
        session_id=str(uuid.uuid4())[:8],
        diff_text=staged_diff,
        diff_hash=diff_hash,
        description=description,
        status=SessionStatus.PENDING_QUIZ,
        created_at=now,
        expires_at=now + 1800.0,
    )

    repo.create_session(session, questions)
    click.echo(f"[SUCCESS] Staged session created: {session.session_id}")
    click.echo(f"Run 'codevoight quiz {session.session_id}' to take the quiz and unlock commit.")


if __name__ == "__main__":
    main()
