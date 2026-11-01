from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text


@pytest.fixture(autouse=True)
def _no_review_rows_left(request: pytest.FixtureRequest) -> Iterator[None]:
    """The migration tests downgrade below the revision that allows `generate_questions`: rows
    the endpoint tests wrote must not outlive them."""
    yield
    if "engine" in request.fixturenames:
        engine: Engine = request.getfixturevalue("engine")
        with engine.begin() as connection:
            for table in ("llm_call", "pipeline_run"):
                connection.execute(
                    text(f"DELETE FROM {table} WHERE task = 'generate_questions'")  # noqa: S608
                )
