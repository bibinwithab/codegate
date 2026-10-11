from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional, Tuple

from codegate.core.diff import compute_diff_hash
from codegate.core.models import CapabilityToken
from codegate.core.security import get_or_create_secret, verify_token
from codegate.db.repository import StateRepository
from codegate.git.runner import GitRunner


HOOK_SCRIPT = """#!/bin/sh
# CodeGate Pre-Commit Verification Hook
# Enforces human comprehension quiz verification before git commit.

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
elif command -v py >/dev/null 2>&1; then
    PYTHON=py
else
    echo "[CODEGATE] Error: Python runtime not found in PATH."
    exit 1
fi

$PYTHON -m codegate.cli verify-commit
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[CODEGATE] COMMIT BLOCKED: Staged changes require human quiz approval."
    echo "[CODEGATE] To approve, run: codegate quiz"
    echo ""
    exit 1
fi

exit 0
"""


def install_pre_commit_hook(repo_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Install the pre-commit hook into .git/hooks/pre-commit."""
    runner = GitRunner(repo_dir)
    root = runner.get_repo_root()
    if not root:
        return False, "Not inside a valid Git repository."

    hooks_dir = root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "pre-commit"

    hook_file.write_text(HOOK_SCRIPT, encoding="utf-8", newline="\n")

    # Set executable bit for unix/posix
    try:
        current_stat = os.stat(hook_file)
        os.chmod(hook_file, current_stat.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    return True, str(hook_file)


def verify_staged_commit(workspace_root: Optional[Path] = None) -> Tuple[bool, str]:
    """Verify that current staged Git changes have a valid, unexpired approval token."""
    runner = GitRunner(workspace_root)
    root = runner.get_repo_root() or (workspace_root.resolve() if workspace_root else None)
    if not root:
        return False, "Not inside a git repository."

    staged_diff = runner.get_staged_diff()
    if not staged_diff.strip():
        # Nothing staged or empty commit
        return True, "No staged diff to verify."

    diff_hash = compute_diff_hash(staged_diff)

    codegate_dir = root / ".codegate"
    db_path = codegate_dir / "state.db"
    if not db_path.exists():
        return False, "No CodeGate state found. Run 'codegate quiz' to approve staged changes."

    repo = StateRepository(db_path)
    session = repo.find_valid_approved_session(diff_hash)
    if not session or not session.capability_token:
        return False, f"Diff hash {diff_hash[:12]} has not been approved via quiz."

    # Verify cryptographic signature
    secret_key = get_or_create_secret(codegate_dir)
    try:
        token = CapabilityToken.parse(session.capability_token)
    except Exception as e:
        return False, f"Invalid token format: {e}"

    is_valid = verify_token(token, diff_hash, secret_key)
    if not is_valid:
        return False, "Token signature invalid or expired."

    return True, f"Verified capability token for session {session.session_id}."
