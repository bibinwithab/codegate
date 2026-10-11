import subprocess
import time
from pathlib import Path

from codevoight.core.diff import compute_diff_hash
from codevoight.core.models import SessionStatus, StagedSession
from codevoight.core.security import get_or_create_secret, sign_token
from codevoight.db.repository import StateRepository
from codevoight.git.hook import install_pre_commit_hook, verify_staged_commit
from codevoight.git.runner import GitRunner


def init_git_repo(path: Path) -> GitRunner:
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), check=True, capture_output=True)
    return GitRunner(path)


def test_hook_installation_and_verification(tmp_path: Path):
    tmp_path = tmp_path.resolve()
    runner = init_git_repo(tmp_path)

    # 1. Test hook script installation
    success, hook_path = install_pre_commit_hook(tmp_path)
    assert success is True
    assert Path(hook_path).exists()
    assert "CodeVoight Pre-Commit Verification Hook" in Path(hook_path).read_text(encoding="utf-8")

    # 2. Stage a file in git
    test_file = tmp_path / "hello.py"
    test_file.write_text("print('hello world')\n", encoding="utf-8")
    runner.stage_files(["hello.py"])

    # Without approval in .codevoight/state.db, verify_staged_commit MUST fail
    valid, msg = verify_staged_commit(tmp_path)
    assert valid is False
    assert "has not been approved" in msg or "No CodeVoight state found" in msg

    # 3. Simulate passing the quiz and signing token
    staged_diff = runner.get_staged_diff()
    diff_hash = compute_diff_hash(staged_diff)

    codevoight_dir = tmp_path / ".codevoight"
    secret_key = get_or_create_secret(codevoight_dir)
    token = sign_token("sess-test-1", diff_hash, secret_key)

    repo = StateRepository(codevoight_dir / "state.db")
    now = time.time()
    session = StagedSession(
        session_id="sess-test-1",
        diff_text=staged_diff,
        diff_hash=diff_hash,
        description="Add hello.py",
        status=SessionStatus.APPROVED,
        created_at=now,
        expires_at=now + 1800,
        capability_token=token.serialize(),
    )
    repo.create_session(session, [])

    # Now verify_staged_commit MUST pass!
    valid_after, msg_after = verify_staged_commit(tmp_path)
    assert valid_after is True
    assert "Verified capability token" in msg_after
