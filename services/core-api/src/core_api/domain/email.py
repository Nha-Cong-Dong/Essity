"""Email addresses are compared and stored in one form (T1.3)."""


def normalize_email(email: str) -> str:
    """Trim and lowercase. Call before storing an email and before every comparison.

    `str.lower`, not `casefold`: casefold maps distinct characters together (ß -> ss), which
    could merge two real addresses. The database refuses anything not lowercase.
    """
    return email.strip().lower()
