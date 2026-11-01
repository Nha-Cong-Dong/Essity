from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(autouse=True)
def _no_practice_rows_left(request: pytest.FixtureRequest) -> Iterator[None]:
    """The migration tests downgrade below the revision that allows these tasks: rows the endpoint
    tests wrote must not outlive them."""
    yield
    if "engine" in request.fixturenames:
        engine: Engine = request.getfixturevalue("engine")
        with engine.begin() as connection:
            for table in ("llm_call", "pipeline_run"):
                connection.execute(
                    text(f"DELETE FROM {table} WHERE task IN ('grade_practice', 'draft_answer')")  # noqa: S608
                )


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
