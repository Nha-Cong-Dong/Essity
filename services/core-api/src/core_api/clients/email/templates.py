"""Plain-text email templates in core_api/templates/email/.

Each file starts with a `Subject: ...` line, then a blank line, then the body. Values are
filled with `string.Template` (`$link`, `$valid_for`...); a missing value raises KeyError, so an
email is never sent with a hole in it. Tone: friendly, "bạn", no signature (chosen by the
product owner).
"""

from enum import StrEnum
from importlib.resources import files
from string import Template

_SUBJECT_PREFIX = "Subject: "


class EmailTemplate(StrEnum):
    VERIFY_EMAIL = "verify_email"  # $link, $valid_for
    ACCOUNT_EXISTS = "account_exists"  # $login_link, $reset_link
    RESET_PASSWORD = "reset_password"  # $link, $valid_for


def render_email(template: EmailTemplate, **values: str) -> tuple[str, str]:
    """Return (subject, body)."""
    raw = files("core_api.templates").joinpath("email", f"{template}.txt").read_text("utf-8")
    first_line, _, body = raw.partition("\n\n")
    if not first_line.startswith(_SUBJECT_PREFIX):
        raise ValueError(f"{template}.txt must start with '{_SUBJECT_PREFIX}'")
    subject = Template(first_line.removeprefix(_SUBJECT_PREFIX)).substitute(values)
    return subject, Template(body).substitute(values)
