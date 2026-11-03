"""Contact phone numbers (US-12 D4): Vietnamese mobile numbers, stored as `+84...`.

Contact only: not unique, not a login key, never verified (no SMS provider, budget).
"""

import re

_SEPARATORS = re.compile(r"[ .\-()]")
_VN_MOBILE = re.compile(r"(?:0|\+?84)([35789]\d{8})")


class PhoneInvalidError(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    match = _VN_MOBILE.fullmatch(_SEPARATORS.sub("", raw.strip()))
    if match is None:
        raise PhoneInvalidError("phone_invalid")
    return f"+84{match.group(1)}"
