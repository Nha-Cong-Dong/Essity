"""T1.23 (part 1): pure rules for usernames (D2)."""

import pytest

from core_api.domain.auth.username import (
    RESERVED,
    UsernameProblem,
    UsernameRejectedError,
    normalize_username,
    username_from_email,
    validate_username,
)


@pytest.mark.parametrize("name", ["abc", "a.b", "a_b", "nguyen.van_a9", "a" + "b" * 19])
def test_d2_good_usernames_pass(name: str) -> None:
    assert validate_username(name) == name


@pytest.mark.parametrize(
    "name",
    ["ab", "a" * 21, "1abc", "12345", "_abc", ".abc", "a@b", "a..b", "Ab c", "abc\n", "ABC", "tên"],
)
def test_d2_bad_shapes_are_refused(name: str) -> None:
    # Red when: a length, first-character, all-digit, "@", "..", space, newline or non-ASCII rule
    # is missing (a trailing "\n" is why validation uses fullmatch, not `$`).
    with pytest.raises(UsernameRejectedError) as raised:
        validate_username(name)
    assert raised.value.problem is UsernameProblem.INVALID


@pytest.mark.parametrize("name", sorted(n for n in RESERVED if len(n) >= 3))
def test_d2_reserved_names_are_refused(name: str) -> None:
    with pytest.raises(UsernameRejectedError) as raised:
        validate_username(name)
    assert raised.value.problem is UsernameProblem.RESERVED


def test_d2_reserved_list_has_the_named_ones() -> None:
    assert {"admin", "root", "support", "essity", "api", "me", "help", "staff"} <= RESERVED


def test_d2_normalize_strips_and_lowers() -> None:
    assert normalize_username("  Bob.Smith ") == "bob.smith"


@pytest.mark.parametrize(
    ("email", "taken", "expected"),
    [
        ("A.B@x.vn", [], "a.b"),
        ("9lives@x.vn", [], "lives"),
        ("ab@x.vn", [], "ab_"),
        ("a..b@x.vn", [], "a.b"),
        ("x+tag@x.vn", [], "xtag"),
        ("a" * 40 + "@x.vn", [], "a" * 20),
        ("admin@x.vn", [], "admin_2"),
        ("bob@a.vn", ["bob"], "bob_2"),
        ("bob@a.vn", ["bob", "bob_2"], "bob_3"),
        ("@x.vn", [], "user"),
        ("a" * 20 + "@x.vn", ["a" * 20], "a" * 18 + "_2"),
    ],
)
def test_d6_username_from_email(email: str, taken: list[str], expected: str) -> None:
    # Red when: the backfill/auto-name leaves an illegal character, a bad first character, a
    # short or long name, a reserved name or a clash.
    result = username_from_email(email, taken)
    assert result == expected
    assert validate_username(result) == result
