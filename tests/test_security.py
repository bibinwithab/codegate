import time
from pathlib import Path
import pytest

from codegate.core.models import CapabilityToken
from codegate.core.security import (
    get_or_create_secret,
    sign_token,
    verify_token,
)


def test_get_or_create_secret(tmp_path: Path):
    secret_dir = tmp_path / ".codegate"
    secret1 = get_or_create_secret(secret_dir)
    assert len(secret1) >= 32
    assert (secret_dir / ".secret").exists()

    # Re-reading should yield identical bytes
    secret2 = get_or_create_secret(secret_dir)
    assert secret1 == secret2


def test_sign_and_verify_token():
    secret = b"test_secret_32_bytes_long_123456"
    session_id = "test-session-1"
    diff_hash = "abc123def456"

    token = sign_token(session_id, diff_hash, secret)
    assert token.session_id == session_id
    assert token.diff_hash == diff_hash
    assert verify_token(token, diff_hash, secret)


def test_verify_token_tampered_diff_hash():
    secret = b"test_secret_32_bytes_long_123456"
    token = sign_token("sess-1", "original_hash", secret)

    # Different expected diff hash must fail
    assert not verify_token(token, "tampered_hash", secret)


def test_verify_token_tampered_signature():
    secret = b"test_secret_32_bytes_long_123456"
    token = sign_token("sess-1", "hash123", secret)

    tampered = CapabilityToken(
        session_id=token.session_id,
        diff_hash=token.diff_hash,
        timestamp=token.timestamp,
        signature="deadbeef" * 8,
    )
    assert not verify_token(tampered, "hash123", secret)


def test_verify_token_expired():
    secret = b"test_secret_32_bytes_long_123456"
    old_timestamp = time.time() - 3600  # 1 hour ago
    token = sign_token("sess-1", "hash123", secret, timestamp=old_timestamp)

    # With TTL 1800s, 3600s old token must fail
    assert not verify_token(token, "hash123", secret, ttl_seconds=1800)
