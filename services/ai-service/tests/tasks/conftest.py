from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session


@pytest.fixture
def session() -> Iterator[Session]:
    # The indexer never touches the database; a session bound to nothing proves it.
    with Session() as session:
        yield session
