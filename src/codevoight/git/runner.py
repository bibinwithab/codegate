from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from codevoight.core.diff import normalize_text


class GitRunner:
    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = repo_path or Path.cwd()

    def _run(self, args: List[str]) -> Tuple[int, str, str]:
        cmd = ["git"] + args
        proc = subprocess.run(
            cmd,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr

    def is_git_repo(self) -> bool:
        code, stdout, _ = self._run(["rev-parse", "--is-inside-work-tree"])
        return code == 0 and "true" in stdout.strip().lower()

    def get_repo_root(self) -> Optional[Path]:
        code, stdout, _ = self._run(["rev-parse", "--show-toplevel"])
        if code == 0 and stdout.strip():
            return Path(stdout.strip()).resolve()
        return None

    def get_staged_diff(self) -> str:
        """Get git diff of cached/staged files normalized."""
        code, stdout, _ = self._run(["diff", "--cached"])
        if code == 0:
            return normalize_text(stdout)
        return ""

    def get_working_diff(self) -> str:
        """Get git diff against HEAD."""
        code, stdout, _ = self._run(["diff", "HEAD"])
        if code == 0:
            return normalize_text(stdout)
        return ""

    def stage_files(self, paths: List[str]) -> bool:
        code, _, _ = self._run(["add"] + paths)
        return code == 0

    def commit(self, message: str) -> Tuple[bool, str]:
        code, stdout, stderr = self._run(["commit", "-m", message])
        output = stdout if code == 0 else f"{stderr}\n{stdout}".strip()
        return code == 0, output
