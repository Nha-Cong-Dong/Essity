"""The FSRS scheduler with a user's ACTIVE parameters (T5.9b): every retrievability the app shows
or ranks by must come from the same curve that set the due dates (`record_grade`, `rebuild`)."""

import uuid

from sqlalchemy.orm import Session

from core_api.db.models import User
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler
from core_api.domain.scheduling.params import active_parameters

_DEFAULT = FsrsScheduler()


def scheduler_for(user: User) -> FsrsScheduler:
    """The user's scheduler; the shared defaults one when they have no fitted version."""
    parameters = active_parameters(user.fsrs_params, user.fsrs_params_version)
    return _DEFAULT if parameters is None else FsrsScheduler(parameters)


def scheduler_for_id(session: Session, user_id: uuid.UUID) -> FsrsScheduler:
    user = session.get(User, user_id)
    assert user is not None
    return scheduler_for(user)
