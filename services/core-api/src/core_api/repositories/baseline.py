"""The user's baseline (US-11). Each write is one statement, so two requests at once cannot both
succeed or end in a database error: the session commits only after the response is decided
(db.session), and an IntegrityError there would reach the user as a 500."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from core_api.db.models import Baseline
from core_api.domain.baseline import EDIT_WINDOW
from core_api.repositories.base import UserScopedRepository


class BaselineRepository(UserScopedRepository[Baseline]):
    model = Baseline

    def get_mine(self) -> Baseline | None:
        return self.session.scalars(self._select()).one_or_none()

    def create(
        self,
        *,
        gpa_before: Decimal,
        prior_ready_days: int,
        prior_days_unknown: bool,
        is_late: bool,
        now: datetime,
    ) -> Baseline | None:
        """The new baseline, or None if this user already has one (entered once, PLAN T1.17)."""
        query = (
            insert(Baseline)
            .values(
                user_id=self.user_id,
                gpa_before=gpa_before,
                prior_ready_days=prior_ready_days,
                prior_days_unknown=prior_days_unknown,
                entered_at=now,
                is_late=is_late,
            )
            .on_conflict_do_nothing(index_elements=[Baseline.user_id])
            .returning(Baseline)
        )
        return self.session.scalars(query).one_or_none()

    def replace(
        self, *, gpa_before: Decimal, prior_ready_days: int, prior_days_unknown: bool, now: datetime
    ) -> Baseline | None:
        """The edited baseline, or None if there is none or it is locked (AC5). `entered_at` and
        `is_late` stay: editing must not reopen the window or clear the late mark."""
        query = (
            update(Baseline)
            .where(Baseline.user_id == self.user_id, Baseline.entered_at > now - EDIT_WINDOW)
            .values(
                gpa_before=gpa_before,
                prior_ready_days=prior_ready_days,
                prior_days_unknown=prior_days_unknown,
            )
            .returning(Baseline)
            .execution_options(synchronize_session="fetch")
        )
        return self.session.scalars(query).one_or_none()
