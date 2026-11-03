"""T8.7b (US-16): the practice result lists every rubric point, and "Gỡ khỏi luyện tập" can be
undone. Reuses the T8.4 fakes; nothing here calls a model."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t84_practice_api import RUBRIC, FakeAi, Learner

from accounts import signed_in
from core_api.api.ping import get_ai_client
from core_api.db.models import PracticeState, Question
from core_api.main import app


@pytest.fixture
def ai() -> Iterator[FakeAi]:
    fake = FakeAi()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


@pytest.fixture
def learner(client: TestClient, db_session: Session, ai: FakeAi) -> Learner:
    return Learner(client, db_session)


def units(body: dict[str, Any]) -> list[tuple[str, bool]]:
    return [(u["text"], u["met"]) for u in body["result"]["units"]]


def test_us16_every_rubric_point_is_listed_in_rubric_order(learner: Learner, ai: FakeAi) -> None:
    # Red when: units are missing, reordered, or a met point is shown as not met.
    ai.verdicts = ["correct", "incorrect"]
    body = learner.submit(learner.open(learner.question())["attempt_id"])
    assert units(body) == [(RUBRIC[0], True), (RUBRIC[1], False)]
    assert body["result"]["missing"] == [RUBRIC[1]]


def test_us16_all_met_and_partial_points(learner: Learner, ai: FakeAi) -> None:
    body = learner.submit(learner.open(learner.question())["attempt_id"])
    assert units(body) == [(RUBRIC[0], True), (RUBRIC[1], True)]
    ai.verdicts = ["partial", "correct"]
    again = learner.submit(learner.open(learner.question())["attempt_id"])
    assert units(again) == [(RUBRIC[0], False), (RUBRIC[1], True)]  # partial = not fully met


def test_us16_forgotten_answer_meets_no_point(learner: Learner) -> None:
    attempt = learner.open(learner.question())["attempt_id"]
    body = learner.submit(attempt, text="", dont_remember=True)
    assert body["result"]["overall"] == "forgot"
    assert units(body) == [(RUBRIC[0], False), (RUBRIC[1], False)]


def test_us16_read_again_keeps_the_units(learner: Learner) -> None:
    attempt = learner.open(learner.question())["attempt_id"]
    learner.submit(attempt)
    seen = learner.client.get(f"/v1/practice/attempts/{attempt}", headers=learner.headers).json()
    assert len(seen["result"]["units"]) == 2


def test_us16_restore_undoes_removal(learner: Learner, db_session: Session) -> None:
    # Red when: restore leaves the question retired or its schedule stopped.
    question = learner.question()
    learner.submit(learner.open(question)["attempt_id"])
    path = f"/v1/practice/questions/{question}"
    assert learner.client.post(f"{path}/worthless", headers=learner.headers).status_code == 204
    assert learner.client.post(f"{path}/restore", headers=learner.headers).status_code == 204
    assert db_session.get(Question, question).status == "active"  # type: ignore[union-attr]
    assert db_session.scalars(select(PracticeState.removed_at)).one() is None
    assert learner.client.post(f"{path}/restore", headers=learner.headers).status_code == 204


def test_us16_restore_of_another_users_question_is_404(
    learner: Learner, client: TestClient, db_session: Session
) -> None:
    question = learner.question()
    _, bob = signed_in(db_session)
    response = client.post(f"/v1/practice/questions/{question}/restore", headers=bob)
    assert response.status_code == 404


def _post(learner: Learner, question: object, verb: str) -> int:
    path = f"/v1/practice/questions/{question}/{verb}"
    return learner.client.post(path, headers=learner.headers).status_code


def test_us16_restore_leaves_a_rejected_question_retired(
    learner: Learner, db_session: Session
) -> None:
    # Review F1. Red when: restore revives a question the learner rejected ("Không giữ").
    question = learner.question()
    row = db_session.get(Question, question)
    assert row is not None
    row.status, row.quality_status = "retired", "rejected"
    db_session.flush()
    assert _post(learner, question, "restore") == 204
    db_session.refresh(row)
    assert row.status == "retired"


def test_us16_restore_with_a_twin_active_question_is_not_a_500(
    learner: Learner, db_session: Session
) -> None:
    # Review F1. Red when: restoring over an active question of the same content is a 500.
    first = learner.question()
    assert _post(learner, first, "worthless") == 204
    original = db_session.get(Question, first)
    assert original is not None
    twin = learner.question()
    twin_row = db_session.get(Question, twin)
    assert twin_row is not None
    twin_row.content_hash = original.content_hash
    db_session.flush()
    assert _post(learner, first, "restore") == 409
    db_session.refresh(original)
    assert original.status == "retired"


def test_us16_restore_is_refused_for_an_unverified_account(
    client: TestClient, db_session: Session
) -> None:
    import uuid

    _, headers = signed_in(db_session, verified=False)
    path = f"/v1/practice/questions/{uuid.uuid4()}/restore"
    assert client.post(path, headers=headers).status_code == 403


def test_us16_restore_of_a_question_still_in_practice_writes_no_log(
    learner: Learner, db_session: Session
) -> None:
    from core_api.db.models import PracticeRemovalLog

    question = learner.question()
    before = len(db_session.scalars(select(PracticeRemovalLog)).all())
    assert _post(learner, question, "restore") == 204
    assert len(db_session.scalars(select(PracticeRemovalLog)).all()) == before
