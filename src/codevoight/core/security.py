from __future__ import annotations

import hmac
import hashlib
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from codevoight.core.models import CapabilityToken


DEFAULT_TTL_SECONDS = 1800.0  # 30 minutes


def get_or_create_secret(secret_dir: Path) -> bytes:
    """Retrieve or generate a 32-byte cryptographic secret stored in secret_dir/.secret."""
    secret_dir.mkdir(parents=True, exist_ok=True)
    secret_path = secret_dir / ".secret"

    if secret_path.exists():
        secret_bytes = secret_path.read_bytes().strip()
        if len(secret_bytes) >= 32:
            return secret_bytes

    new_secret = secrets.token_bytes(32)
    # Write with restricted permissions
    secret_path.write_bytes(new_secret)
    return new_secret


def sign_token(session_id: str, diff_hash: str, secret_key: bytes, timestamp: Optional[int] = None) -> CapabilityToken:
    """Generate an HMAC-SHA256 capability token for a verified session diff."""
    ts = int(timestamp) if timestamp is not None else int(time.time())
    payload = f"{session_id}:{diff_hash}:{ts}".encode("utf-8")
    sig = hmac.new(secret_key, payload, hashlib.sha256).hexdigest()
    return CapabilityToken(
        session_id=session_id,
        diff_hash=diff_hash,
        timestamp=ts,
        signature=sig,
    )


def verify_token(
    token: CapabilityToken,
    expected_diff_hash: str,
    secret_key: bytes,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
    current_time: Optional[float] = None,
) -> bool:
    """Verify validity, expiration, and cryptographic signature of a capability token."""
    now = current_time if current_time is not None else time.time()

    # Expiry check
    if now - token.timestamp > ttl_seconds or token.timestamp > now + 60.0:
        return False

    # Diff hash match check (constant time)
    if not hmac.compare_digest(token.diff_hash, expected_diff_hash):
        return False

    # Signature recomputation
    payload = f"{token.session_id}:{token.diff_hash}:{token.timestamp}".encode("utf-8")
    expected_sig = hmac.new(secret_key, payload, hashlib.sha256).hexdigest()

    return hmac.compare_digest(token.signature, expected_sig)
