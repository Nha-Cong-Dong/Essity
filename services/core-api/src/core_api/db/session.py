"""One database session per request."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from core_api.db.engine import get_engine


def get_session() -> Iterator[Session]:
    """Commit when the route returns, roll back when it raises.

    Do not depend on this directly: use `DbSession`, which runs the commit before the
    response is sent.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise


# scope="function": the code after `yield` (the commit) runs when the route returns, before
# the response is sent. With the default scope a failed commit would still answer 200 for
# data that was never saved. Routes are `def`, not `async def` (ADR-0005): FastAPI runs them,
# and their blocking database calls, in its threadpool.
DbSession = Annotated[Session, Depends(get_session, scope="function")]
