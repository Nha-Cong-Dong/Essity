"""T1.7: password rules (NIST SP 800-63B) and argon2id hashing."""

import pytest

from core_api.domain.auth.passwords import (
    MAX_LENGTH,
    MIN_LENGTH,
    PasswordProblem,
    PasswordRejectedError,
    dummy_verify,
    hash_password,
    needs_rehash,
    validate_password,
    verify_password,
)


def problem(password: str, email: str | None = None) -> PasswordProblem | None:
    try:
        validate_password(password, email=email)
    except PasswordRejectedError as exc:
        return exc.problem
    return None


# --- Rules -----------------------------------------------------------------------------------


def test_length_bounds() -> None:
    assert (MIN_LENGTH, MAX_LENGTH) == (8, 128)
    assert problem("x7#kQ2m") == PasswordProblem.TOO_SHORT
    assert problem("x7#kQ2mz") is None
    assert problem("y" * 120 + "x7#kQ2mz") is None  # 128
    assert problem("y" * 121 + "x7#kQ2mz") == PasswordProblem.TOO_LONG


def test_length_counts_characters_not_bytes() -> None:
    # 8 Vietnamese characters are 8, even though several take 2-3 bytes in UTF-8.
    assert problem("mậtkhẩuồ") is None
    assert problem("mậtkhẩu") == PasswordProblem.TOO_SHORT


@pytest.mark.parametrize("common", ["password1", "PASSWORD123", "iloveyou", "QwertyUiop"])
def test_common_passwords_are_refused_whatever_the_case(common: str) -> None:
    assert problem(common) == PasswordProblem.COMMON


@pytest.mark.parametrize(
    "fine",
    [
        "con mèo ngủ trên mái nhà",  # spaces and diacritics are allowed
        "correcthorsebatterystaple-essity",
        "abcdefghijxyz",  # no forced digits, capitals or symbols (NIST)
    ],
)
def test_no_composition_rules(fine: str) -> None:
    assert problem(fine) is None


def test_password_equal_to_the_email_is_refused() -> None:
    assert problem("Alice.Nguyen@example.com", email="alice.nguyen@example.com") == (
        PasswordProblem.SAME_AS_EMAIL
    )
    assert problem("alice.nguyen", email="alice.nguyen@example.com") == (
        PasswordProblem.SAME_AS_EMAIL
    )


# --- Hashing ---------------------------------------------------------------------------------


def test_hash_is_argon2id_and_verifies() -> None:
    hashed = hash_password("con mèo ngủ trên mái nhà")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "con mèo ngủ trên mái nhà")
    assert not verify_password(hashed, "con mèo ngủ trên mái nha")


def test_same_password_gets_a_different_salt() -> None:
    assert hash_password("x7#kQ2mz") != hash_password("x7#kQ2mz")


def test_unicode_is_normalized_before_hashing() -> None:
    # "ệ" typed as one code point or as e + two combining marks is the same password.
    composed = "mật khẩu Việt"
    decomposed = "mật khẩu Việt"
    assert composed != decomposed
    assert verify_password(hash_password(composed), decomposed)


def test_garbage_hash_does_not_verify_or_crash() -> None:
    assert not verify_password("not-a-hash", "x7#kQ2mz")


def test_fresh_hash_does_not_need_rehash() -> None:
    assert not needs_rehash(hash_password("x7#kQ2mz"))


def test_dummy_verify_always_fails() -> None:
    # Used when the email is unknown, so a login takes as long as for a real account (T1.8).
    assert dummy_verify("anything") is False
