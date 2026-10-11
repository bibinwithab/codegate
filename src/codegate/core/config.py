from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def load_dotenv(env_path: Optional[Path] = None) -> None:
    """Load key-value pairs from .env into os.environ without overriding existing keys."""
    target = env_path or (Path.cwd() / ".env")
    if not target.exists():
        return

    try:
        content = target.read_text(encoding="utf-8")
    except Exception:
        return

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = val


def get_token_ttl() -> float:
    """Return capability token TTL in seconds (default: 1800.0)."""
    val = os.getenv("CODEGATE_TOKEN_TTL")
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return 1800.0


def get_passing_score() -> float:
    """Return required quiz passing score between 0.0 and 1.0 (default: 1.0)."""
    val = os.getenv("CODEGATE_PASSING_SCORE")
    if val:
        try:
            score = float(val)
            if 0.0 <= score <= 1.0:
                return score
        except ValueError:
            pass
    return 1.0
