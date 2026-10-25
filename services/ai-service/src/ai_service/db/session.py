"""Sessions for the audit tables.

There is no session per request here: `pipeline_run` and `llm_call` rows are each committed in
a transaction of their own as soon as they are known (🟠4), so an error later in the request
never rolls back the record of a call that was made and paid for.
"""

from collections.abc import Callable
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from ai_service.db.engine import get_engine

SessionFactory = Callable[[], Session]


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)
