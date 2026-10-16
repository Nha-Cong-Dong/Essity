"""T1.7: one-time tokens for email links (verify email, reset password)."""

import re

from core_api.domain.auth.tokens import hash_token, new_token


def test_token_is_32_random_bytes_url_safe() -> None:
    raw, _ = new_token()
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", raw)  # 32 bytes in unpadded base64url


def test_only_the_hash_is_meant_for_the_database() -> None:
    raw, digest = new_token()
    assert re.fullmatch(r"[0-9a-f]{64}", digest)  # SHA-256
    assert digest == hash_token(raw)
    assert raw not in digest


def test_tokens_do_not_repeat() -> None:
    assert len({new_token()[0] for _ in range(1000)}) == 1000
