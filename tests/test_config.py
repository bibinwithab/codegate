import os
from pathlib import Path

from codegate.core.config import get_passing_score, get_token_ttl, load_dotenv


def test_load_dotenv(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comment line\n"
        "CODEGATE_TOKEN_TTL=900\n"
        "CODEGATE_PASSING_SCORE=0.8\n"
        "CUSTOM_KEY=\"custom_value\"\n",
        encoding="utf-8",
    )

    # Clean existing env
    monkeypatch.delenv("CODEGATE_TOKEN_TTL", raising=False)
    monkeypatch.delenv("CODEGATE_PASSING_SCORE", raising=False)
    monkeypatch.delenv("CUSTOM_KEY", raising=False)

    load_dotenv(env_file)

    assert os.getenv("CODEGATE_TOKEN_TTL") == "900"
    assert os.getenv("CODEGATE_PASSING_SCORE") == "0.8"
    assert os.getenv("CUSTOM_KEY") == "custom_value"

    assert get_token_ttl() == 900.0
    assert get_passing_score() == 0.8


def test_default_config_fallbacks(monkeypatch):
    monkeypatch.delenv("CODEGATE_TOKEN_TTL", raising=False)
    monkeypatch.delenv("CODEGATE_PASSING_SCORE", raising=False)

    assert get_token_ttl() == 1800.0
    assert get_passing_score() == 1.0
