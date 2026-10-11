from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional, Tuple

from codevoight.core.diff import compute_diff_hash
from codevoight.core.models import CapabilityToken
from codevoight.core.security import get_or_create_secret, verify_token
from codevoight.db.repository import StateRepository
from codevoight.git.runner import GitRunner


HOOK_SCRIPT = """#!/bin/sh
# CodeVoight Pre-Commit Verification Hook
# Enforces human comprehension quiz verification before git commit.

if [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v py >/dev/null 2>&1; then
    PYTHON=py
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "[CODEVOIGHT] Error: Python runtime not found in PATH."
    exit 1
fi

$PYTHON -m codevoight.cli verify-commit
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[CODEVOIGHT] COMMIT BLOCKED: Staged changes require human comprehension approval."
    echo "[CODEVOIGHT] To approve, run: codevoight quiz"
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

    codevoight_dir = root / ".codevoight"
    if not codevoight_dir.exists():
        if (root / ".quizgate").exists():
            codevoight_dir = root / ".quizgate"
        elif (root / ".codegate").exists():
            codevoight_dir = root / ".codegate"

    db_path = codevoight_dir / "state.db"
    if not db_path.exists():
        return False, "No CodeVoight state found. Run 'codevoight quiz' to approve staged changes."

    repo = StateRepository(db_path)
    session = repo.find_valid_approved_session(diff_hash)
    if not session or not session.capability_token:
        return False, f"Diff hash {diff_hash[:12]} has not been approved via quiz."

    # Verify cryptographic signature
    secret_key = get_or_create_secret(codevoight_dir)
    try:
        token = CapabilityToken.parse(session.capability_token)
    except Exception as e:
        return False, f"Invalid token format: {e}"

    is_valid = verify_token(token, diff_hash, secret_key)
    if not is_valid:
        return False, "Token signature invalid or expired."

    return True, f"Verified capability token for session {session.session_id}."
