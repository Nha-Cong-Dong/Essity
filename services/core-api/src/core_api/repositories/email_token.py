"""One-time email tokens (ADR-0014, ADR-0019). Not scoped to a user: whoever clicks a link is
not signed in, so the token itself is how the user is found (see tests/test_repository_rule.py).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core_api.db.models import EmailToken, User
from core_api.domain.auth.tokens import TOKEN_TTL, TokenPurpose, hash_token, new_token


class EmailTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def issue(self, user_id: uuid.UUID, purpose: TokenPurpose, now: datetime | None = None) -> str:
        """Store a new token's hash; return the raw token, for the link only."""
        issued = now or datetime.now(UTC)
        raw, token_hash = new_token()
        self.session.add(
            EmailToken(
                user_id=user_id,
                purpose=purpose,
                token_hash=token_hash,
                created_at=issued,
                expires_at=issued + TOKEN_TTL[purpose],
            )
        )
        return raw

    def consume(
        self, raw: str, purpose: TokenPurpose, now: datetime | None = None
    ) -> uuid.UUID | None:
        """Use the token once and return its user; None if it is unknown, used, expired or for
        another purpose (one answer for all, so a caller cannot tell which).

        Every other unused token of the same purpose for that user ends too: once an email is
        verified, no older link works (ADR-0019).
        """
        at = now or datetime.now(UTC)
        token_hash = hash_token(raw)
        owner = self.session.scalar(
            select(EmailToken.user_id).where(EmailToken.token_hash == token_hash)
        )
        if owner is None:
            return None
        # Lock the user's row before reading the token for real: every consume for one user then
        # runs one at a time. Two clicks on one link: the second waits, then finds it used. Two
        # links clicked at once cannot deadlock on each other's token rows.
        self.session.execute(select(User.id).where(User.id == owner).with_for_update())
        token = self.session.scalars(
            select(EmailToken).where(
                EmailToken.token_hash == token_hash,
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
                EmailToken.expires_at > at,
            )
        ).one_or_none()
        if token is None:
            return None
        self.session.execute(
            update(EmailToken)
            .where(
                EmailToken.user_id == token.user_id,
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
            )
            .values(used_at=at)
        )
        return token.user_id
