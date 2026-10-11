import subprocess
import time
from pathlib import Path
import pytest

from codevoight.core.diff import compute_diff_hash
from codevoight.core.models import SessionStatus
from codevoight.core.security import get_or_create_secret, sign_token
from codevoight.db.repository import StateRepository
from codevoight.git.runner import GitRunner
from codevoight.server import create_server


def init_git_repo(path: Path) -> GitRunner:
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), check=True, capture_output=True)
    return GitRunner(path)


@pytest.mark.asyncio
async def test_mcp_server_flow(tmp_path: Path):
    tmp_path = tmp_path.resolve()
    runner = init_git_repo(tmp_path)
    server = create_server(tmp_path)

    # 1. Call stage_code_change tool
    stage_res = await server.call_tool(
        "stage_code_change",
        {
            "files": [{"file_path": "lib/calc.py", "content": "def add(a, b):\n    return a + b\n"}],
            "description": "Add math addition utility",
        },
    )
    assert not stage_res.is_error
    text_out = stage_res.content[0].text
    assert "[CODEVOIGHT: CHANGES STAGED]" in text_out
    assert "Session ID :" in text_out

    # Extract session id from output
    import re
    match = re.search(r"Session ID\s*:\s*([a-zA-Z0-9_\-]+)", text_out)
    assert match is not None
    session_id = match.group(1)

    # 2. Check gate status -> PENDING_QUIZ, can_commit is False
    status_res = await server.call_tool("get_gate_status", {"session_id": session_id})
    import json
    status_data = json.loads(status_res.content[0].text)
    assert status_data["status"] == "PENDING_QUIZ"
    assert status_data["can_commit"] is False

    # 3. Attempt to commit directly via MCP -> MUST BE REJECTED
    commit_attempt = await server.call_tool(
        "commit_staged",
        {"session_id": session_id, "commit_message": "feat: add calc utility"},
    )
    commit_text = commit_attempt.content[0].text
    assert "[ACCESS DENIED]" in commit_text
    assert "must run 'codevoight quiz" in commit_text

    # 4. Simulate developer passing quiz via CLI / StateRepository
    codevoight_dir = tmp_path / ".codevoight"
    repo = StateRepository(codevoight_dir / "state.db")
    session = repo.get_session(session_id)
    assert session is not None

    secret_key = get_or_create_secret(codevoight_dir)
    token = sign_token(session_id, session.diff_hash, secret_key)
    repo.update_session_status(session_id, SessionStatus.APPROVED, token.serialize())

    # Gate status should now report can_commit: True
    status_after = await server.call_tool("get_gate_status", {"session_id": session_id})
    status_after_data = json.loads(status_after.content[0].text)
    assert status_after_data["status"] == "APPROVED"
    assert status_after_data["can_commit"] is True

    # 5. Commit staged changes now -> MUST SUCCEED
    commit_success = await server.call_tool(
        "commit_staged",
        {"session_id": session_id, "commit_message": "feat: add calc utility"},
    )
    success_text = commit_success.content[0].text
    assert "[COMMIT SUCCESSFUL]" in success_text

    # Check git log in the repo
    code, stdout, _ = runner._run(["log", "-n", "1", "--oneline"])
    assert code == 0
    assert "feat: add calc utility" in stdout
