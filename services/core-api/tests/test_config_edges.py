"""R04 (T1.21) edge cases of the production rules: other spellings of "this machine", and values
that are empty rather than missing.

Written by the Tester (feature-tester, 23/10). Each test says which change to config.py turns it
red.
"""

import pytest
from pydantic import ValidationError

from core_api.config import Settings
from test_config import PRODUCTION, settings


@pytest.mark.parametrize(
    "host",
    [
        "LOCALHOST",  # upper case
        "localhost.",  # the root dot: still localhost
        "api.localhost",  # RFC 6761: every *.localhost is loopback
        "[::1]",  # as it appears in a URL
        "0:0:0:0:0:0:0:1",  # ::1 written out
        "::",  # IPv6 "any": binds and connects to this machine
        "0.0.0.0",
        "127.255.255.254",
        "::ffff:127.0.0.1",  # IPv4 loopback inside IPv6
    ],
)
def test_r04_every_spelling_of_this_machine_is_refused_as_smtp_host(host: str) -> None:
    # Red when: `_is_loopback` loses its lower(), rstrip("."), ".localhost" suffix, "[]" strip,
    # or `is_unspecified` (the last one is the 0.0.0.0 and :: spellings only).
    with pytest.raises(ValidationError, match="smtp_host"):
        settings(**{**PRODUCTION, "smtp_host": host})


@pytest.mark.parametrize(
    "host", ["smtp.essity.example", "10.0.0.5", "localhost.essity.example", "mailpit"]
)
def test_r04_a_real_host_is_accepted_as_smtp_host(host: str) -> None:
    # Red when: the check becomes a substring test ("localhost" in host) or refuses private IPs
    # (Compose service names and 10.x addresses are how the services reach each other).
    assert settings(**{**PRODUCTION, "smtp_host": host}).smtp_host == host


@pytest.mark.parametrize(
    "url",
    [
        "https://[::1]:3000/",
        "https://LOCALHOST./login",
        "https://app.localhost/",
        "https://0.0.0.0/",
    ],
)
def test_r04_web_base_url_spellings_of_this_machine_are_refused(url: str) -> None:
    # Red when: the URL's host is compared as written (no `urlsplit(...).hostname` clean-up in
    # front of `_is_loopback`) or `_is_loopback` misses a spelling.
    with pytest.raises(ValidationError, match="web_base_url"):
        settings(**{**PRODUCTION, "web_base_url": url})


@pytest.mark.parametrize("field", ["smtp_host", "ai_service_url"])
def test_r04_outside_dev_an_empty_value_is_refused(field: str) -> None:
    # Red when: an empty value passes the production rules. Compose and shells pass an unset
    # variable as "" (see web_token): an empty smtp_host would start fine and fail on the first
    # email, an empty ai_service_url on the first call.
    with pytest.raises(ValidationError, match=field):
        settings(**{**PRODUCTION, field: ""})


def test_r04_the_test_environment_keeps_the_local_defaults() -> None:
    # Red when: "test" leaves DEV_ENVIRONMENTS (the whole suite runs on it).
    test = settings(environment="test")
    assert (test.smtp_host, test.web_base_url) == ("127.0.0.1", "http://localhost:3000")


def test_r04_staging_with_everything_set_is_accepted() -> None:
    # Red when: a rule refuses a complete staging setup (the rules must not be production-only
    # by name), or `Environment` loses "staging".
    assert settings(**{**PRODUCTION, "environment": "staging"}).environment == "staging"


def test_r04_staging_needs_starttls_too() -> None:
    # Red when: DEV_ENVIRONMENTS gains "staging", or the STARTTLS rule checks == "production".
    with pytest.raises(ValidationError, match="smtp_starttls"):
        settings(**{**PRODUCTION, "environment": "staging", "smtp_starttls": "false"})


def test_r04_environment_is_case_sensitive() -> None:
    # Red when: "Local" or "LOCAL" is accepted as local (a typo must not switch the rules off).
    with pytest.raises(ValidationError, match="environment"):
        settings(environment="Local")


def test_r04_settings_class_is_what_the_app_reads() -> None:
    # Red when: `Settings` stops requiring `environment` from the process environment: a
    # variable set to a valid value is read, not defaulted.
    assert Settings.model_fields["environment"].is_required()
