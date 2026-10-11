from __future__ import annotations

import difflib
import hashlib
from typing import List, Optional

from codevoight.core.models import StagedFile


def normalize_text(text: Optional[str]) -> str:
    """Normalize line endings to LF and strip trailing empty lines."""
    if text is None:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized


def generate_file_diff(file_path: str, old_content: Optional[str], new_content: str) -> str:
    """Generate a unified diff string for a single file."""
    norm_old = normalize_text(old_content).splitlines(keepends=True)
    norm_new = normalize_text(new_content).splitlines(keepends=True)

    from_file = f"a/{file_path}" if old_content is not None else "/dev/null"
    to_file = f"b/{file_path}"

    diff_lines = list(
        difflib.unified_diff(
            norm_old,
            norm_new,
            fromfile=from_file,
            tofile=to_file,
            lineterm="\n",
        )
    )
    return "".join(diff_lines)


def generate_diff(files: List[StagedFile]) -> str:
    """Generate combined unified diff across multiple staged files."""
    chunks = []
    for f in sorted(files, key=lambda x: x.file_path):
        d = generate_file_diff(f.file_path, f.old_content, f.new_content)
        if d:
            chunks.append(d)
    return "\n".join(chunks)


def compute_diff_hash(diff_text: str) -> str:
    """Compute deterministic SHA-256 hash of normalized unified diff."""
    norm = normalize_text(diff_text).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
