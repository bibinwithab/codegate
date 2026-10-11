from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore

from codegate.core.diff import compute_diff_hash, normalize_text
from codegate.core.models import CapabilityToken, SessionStatus, StagedSession
from codegate.core.security import get_or_create_secret, verify_token
from codegate.db.repository import StateRepository
from codegate.generators.deterministic import DeterministicQuizGenerator
from codegate.git.runner import GitRunner


def create_server(workspace_root: Optional[Path] = None) -> MCPServer:
    root = (workspace_root or GitRunner().get_repo_root() or Path.cwd()).resolve()
    codegate_dir = root / ".codegate"
    db_path = codegate_dir / "state.db"

    repo = StateRepository(db_path)
    git_runner = GitRunner(root)
    generator = DeterministicQuizGenerator()

    server = MCPServer(
        name="codegate",
        instructions="CodeGate intercepts and verifies code changes before Git commits.",
    )

    @server.tool()
    def stage_code_change(files: List[Dict[str, str]], description: str = "") -> str:
        """Stage one or more file changes into the workspace and register a human comprehension quiz.

        Args:
            files: List of file dictionaries with keys 'file_path' and 'content'.
            description: Short summary of what this change accomplishes.
        """
        if not files:
            return "[ERROR] No files provided to stage."

        staged_paths = []
        for f in files:
            rel_path = f.get("file_path")
            content = f.get("content")
            if not rel_path or content is None:
                continue

            target_file = root / rel_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content, encoding="utf-8")
            staged_paths.append(rel_path)

        if not staged_paths:
            return "[ERROR] No valid file paths provided."

        git_runner.stage_files(staged_paths)
        staged_diff = git_runner.get_staged_diff()
        if not staged_diff.strip():
            return "[WARNING] Changes were written to disk, but no git diff was produced."

        diff_hash = compute_diff_hash(staged_diff)
        session_id = str(uuid.uuid4())[:8]

        questions = generator.generate_quiz(staged_diff, description)

        now = time.time()
        session = StagedSession(
            session_id=session_id,
            diff_text=staged_diff,
            diff_hash=diff_hash,
            description=description,
            status=SessionStatus.PENDING_QUIZ,
            created_at=now,
            expires_at=now + 1800.0,
        )

        repo.create_session(session, questions)

        return (
            f"[CODEGATE: CHANGES STAGED]\n"
            f"Session ID : {session_id}\n"
            f"Diff Hash  : {diff_hash[:16]}...\n"
            f"Files      : {', '.join(staged_paths)}\n"
            f"Questions  : {len(questions)} generated\n\n"
            f"ACTION REQUIRED:\n"
            f"Tell the developer: 'Please run \"codegate quiz {session_id}\" in your terminal "
            f"to verify your understanding and unlock the commit gate.'"
        )

    @server.tool()
    def get_gate_status(session_id: str = "") -> str:
        """Check the authorization status of a CodeGate staging session.

        Args:
            session_id: Optional session identifier. If omitted, checks latest pending or current staged diff.
        """
        if session_id:
            session = repo.get_session(session_id)
        else:
            session = repo.get_latest_pending_session()
            if not session:
                staged_diff = git_runner.get_staged_diff()
                if staged_diff:
                    d_hash = compute_diff_hash(staged_diff)
                    session = repo.find_valid_approved_session(d_hash)

        if not session:
            return json.dumps({
                "status": "NOT_FOUND",
                "can_commit": False,
                "message": "No active or pending staging session found."
            }, indent=2)

        now = time.time()
        is_expired = now > session.expires_at
        status_val = "EXPIRED" if is_expired else session.status.value
        can_commit = (status_val == SessionStatus.APPROVED.value) and not is_expired

        return json.dumps({
            "session_id": session.session_id,
            "status": status_val,
            "diff_hash": session.diff_hash,
            "can_commit": can_commit,
            "expires_in_seconds": max(0, int(session.expires_at - now)),
        }, indent=2)

    @server.tool()
    def commit_staged(session_id: str, commit_message: str) -> str:
        """Commit staged changes to Git if and only if the human developer has passed the comprehension quiz.

        Args:
            session_id: The session ID of the approved staging session.
            commit_message: The commit message for git commit.
        """
        session = repo.get_session(session_id)
        if not session:
            return f"[ACCESS DENIED] Staging session '{session_id}' not found."

        if session.status != SessionStatus.APPROVED:
            return (
                f"[ACCESS DENIED] Session '{session_id}' status is '{session.status.value}'. "
                f"The human developer must run 'codegate quiz {session_id}' to pass verification before committing."
            )

        if not session.capability_token:
            return "[ACCESS DENIED] No capability token found for this session."

        secret_key = get_or_create_secret(codegate_dir)
        try:
            token = CapabilityToken.parse(session.capability_token)
        except Exception as e:
            return f"[ACCESS DENIED] Corrupted capability token: {e}"

        current_staged_diff = git_runner.get_staged_diff()
        if not current_staged_diff:
            return "[ACCESS DENIED] Working tree has no staged git changes to commit."

        current_diff_hash = compute_diff_hash(current_staged_diff)

        # Constant time cryptographic verification
        if not verify_token(token, current_diff_hash, secret_key):
            return (
                "[ACCESS DENIED] Capability token invalid, expired, or staged git diff modified after quiz! "
                "You must re-stage and pass a new quiz."
            )

        # Execute commit
        success, output = git_runner.commit(commit_message)
        if not success:
            return f"[COMMIT FAILED] Git error:\n{output}"

        # Consume token to prevent replay
        repo.consume_session_token(session_id)

        return f"[COMMIT SUCCESSFUL] CodeGate gate passed!\n{output}"

    return server


def main() -> None:
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
