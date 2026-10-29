"""POST /v1/subjects/{id}/sessions (T4.12, US-02 AC3-AC5, AC7, AC11): the sentence is saved
first, then the card; whatever the AI does, the learner gets a card or the manual form."""

import json
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from session_helpers import COMMON, indexed_document, proposed, subject_of
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from conftest import FakeAi
from core_api.db.models import Outbox, SessionRange, StudySession
from fake_storage import FakeStorage

SENTENCE = "hôm qua tôi học chương 3 từ trang 2 đến 8"
pytestmark = pytest.mark.usefixtures("fake_storage", "fake_ai")


def post(
    client: TestClient, headers: dict[str, str], subject_id: uuid.UUID, text: str = SENTENCE
) -> Any:
    return client.post(
        f"/v1/subjects/{subject_id}/sessions", json={"description": text}, headers=headers
    )


def rows(db: Session) -> list[StudySession]:
    return list(db.scalars(select(StudySession)))


def test_proposed_card_and_draft_saved(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    fake_ai.answer = proposed(document)

    response = post(client, headers, subject.id)

    assert response.status_code == 201
    card = response.json()
    assert card["card"] == "proposed"
    assert card["status"] == "draft"
    assert card["studied_on"] == "2026-10-22"
    assert card["ranges"][0]["short_name"] == "Chương 3"
    assert (card["ranges"][0]["start_page"], card["ranges"][0]["end_page"]) == (3, 9)
    [draft] = rows(db_session)
    assert draft.description_raw == SENTENCE
    assert draft.status == "draft"
    assert draft.extraction == "proposed"
    assert str(draft.id) == card["session_id"]
    assert db_session.scalar(select(func.count()).select_from(SessionRange)) == 0
    assert db_session.scalar(select(func.count()).select_from(Outbox)) == 0


def test_the_request_to_ai_carries_the_documents(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject, pages=10)
    fake_ai.answer = proposed(document, range={"end_page": 9})

    post(client, headers, subject.id)

    [request] = fake_ai.requests
    sent = json.loads(request.content)
    assert sent["description"] == SENTENCE
    assert sent["user_id"] == str(user.id)
    assert sent["today"] == "2026-10-22"
    [doc] = sent["documents"]
    assert doc["document_id"] == str(document.id)
    assert doc["page_count"] == 10
    assert doc["toc"] == [{"title": "Chương 3", "level": 0, "page": 3}]
    assert doc["page_labels"] == [str(i) for i in range(10)]
    assert doc["last_end_page"] is None
    assert request.extensions["timeout"]["read"] <= 5.0


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (httpx2.ReadTimeout("slow"), "failed"),
        (httpx2.ConnectError("down"), "failed"),
        (httpx2.Response(500, text="boom"), "failed"),
        (httpx2.Response(200, json={"status": "proposed"}), "failed"),
        (httpx2.Response(503, json={"code": "quota_hard_cap"}), "quota"),
        (httpx2.Response(503, json={"code": "grading_disabled"}), "disabled"),
    ],
)
def test_manual_card_when_ai_fails_and_description_is_kept(
    client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    fake_ai: FakeAi,
    answer: httpx2.Response | Exception,
    reason: str,
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    fake_ai.answer = answer

    response = post(client, headers, subject.id)

    assert response.status_code == 201
    card = response.json()
    assert card["card"] == "manual"
    assert card["manual_reason"] == reason
    assert card["documents"] == [
        {"document_id": str(document.id), "short_name": "Chương 3", "page_count": 40}
    ]
    [draft] = rows(db_session)
    assert draft.description_raw == SENTENCE
    assert draft.extraction == reason


def test_no_indexed_document_is_manual_without_asking_ai(
    client: TestClient, db_session: Session, fake_ai: FakeAi
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)

    card = post(client, headers, subject.id).json()

    assert card["card"] == "manual"
    assert card["manual_reason"] is None
    assert card["documents"] == []
    assert fake_ai.requests == []
    assert rows(db_session)[0].extraction == "no_documents"


def test_clarify_and_note_only_have_no_ranges(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    run = str(uuid.uuid4())
    fake_ai.answer = httpx2.Response(
        200,
        json=COMMON
        | {
            "status": "clarify",
            "run_id": run,
            "question": "Chương 4 của tài liệu nào?",
            "reason": "ambiguous_document",
            "candidate_document_ids": [str(document.id), str(uuid.uuid4())],
        },
    )
    clarify = post(client, headers, subject.id).json()
    fake_ai.answer = httpx2.Response(
        200, json=COMMON | {"status": "note_only", "run_id": run, "studied_on": "2026-10-21"}
    )
    note = post(client, headers, subject.id).json()

    assert clarify["card"] == "clarify"
    assert clarify["question"] == "Chương 4 của tài liệu nào?"
    assert clarify["candidate_document_ids"] == [str(document.id)]
    assert clarify["ranges"] == []
    assert note["card"] == "note_only"
    assert note["studied_on"] == "2026-10-21"
    assert note["ranges"] == []
    assert db_session.scalar(select(func.count()).select_from(SessionRange)) == 0


@pytest.mark.parametrize(
    "range_",
    [
        {"document_id": str(uuid.uuid4())},  # a document ai-service made up
        {"start_page": 30, "end_page": 41},  # beyond the file
        {"start_page": 9, "end_page": 3},  # upside down
    ],
)
def test_an_answer_that_does_not_fit_the_documents_is_manual(
    client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    fake_ai: FakeAi,
    range_: dict[str, object],
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    fake_ai.answer = proposed(document, range=range_)

    card = post(client, headers, subject.id).json()

    assert card["card"] == "manual"
    assert card["manual_reason"] == "failed"
    assert card["ranges"] == []


@pytest.mark.parametrize("studied_on", ["2026-10-23", "2025-01-01"])
def test_a_date_outside_the_window_is_dropped(
    client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    fake_ai: FakeAi,
    studied_on: str,
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    fake_ai.answer = proposed(document, studied_on=studied_on)

    assert post(client, headers, subject.id).json()["studied_on"] is None


def test_the_total_budget_cuts_reading_and_asking(
    client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    fake_ai: FakeAi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    fake_ai.answer = proposed(document)
    ticks = [0.0]

    def monotonic() -> float:
        # Reading the files used up the budget.
        value = ticks[0]
        ticks[0] = 4.9
        return value

    monkeypatch.setattr("core_api.api.sessions.monotonic", monotonic)

    card = post(client, headers, subject.id).json()

    assert card["card"] == "manual"
    assert fake_ai.requests == []
    assert rows(db_session)[0].description_raw == SENTENCE


def test_the_ai_timeout_is_what_is_left_of_the_budget(
    client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    fake_ai: FakeAi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    fake_ai.answer = proposed(document)
    ticks = [0.0]

    def monotonic() -> float:
        value = ticks[0]
        ticks[0] = 2.0
        return value

    monkeypatch.setattr("core_api.api.sessions.monotonic", monotonic)

    post(client, headers, subject.id)

    assert fake_ai.requests[0].extensions["timeout"]["read"] == pytest.approx(2.5)


def test_last_end_page_comes_from_confirmed_sessions(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    done = StudySession(
        subject_id=subject.id,
        description_raw="trước",
        status="confirmed",
        extraction="proposed",
        studied_on=date(2026, 10, 20),
        learning_day=date(2026, 10, 20),
        confirmed_at=db_session.scalar(select(func.now())),
    )
    done.user_id = user.id
    db_session.add(done)
    db_session.flush()
    for position, end in enumerate((12, 17)):
        db_session.add(
            SessionRange(
                user_id=user.id,
                session_id=done.id,
                document_id=document.id,
                start_page=1,
                end_page=end,
                depth="deep",
                position=position,
            )
        )
    db_session.flush()
    fake_ai.answer = proposed(document)

    post(client, headers, subject.id)

    assert json.loads(fake_ai.requests[0].content)["documents"][0]["last_end_page"] == 17


def test_unverified_account_cannot_create_a_session(
    client: TestClient, db_session: Session, fake_ai: FakeAi
) -> None:
    user, headers = signed_in(db_session, verified=False)
    subject = subject_of(db_session, user)

    response = post(client, headers, subject.id)

    assert response.status_code == 403
    assert rows(db_session) == []
    assert fake_ai.requests == []


def test_another_users_subject_is_404_and_nothing_is_saved(
    client: TestClient, db_session: Session, fake_ai: FakeAi
) -> None:
    owner, _ = signed_in(db_session)
    _, headers = signed_in(db_session)
    subject = subject_of(db_session, owner)

    response = post(client, headers, subject.id)

    assert response.status_code == 404
    assert response.json()["detail"] == "subject_not_found"
    assert rows(db_session) == []
    assert fake_ai.requests == []


@pytest.mark.parametrize("text", ["", "   ", "x" * 2001])
def test_a_bad_sentence_is_422(client: TestClient, db_session: Session, text: str) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)

    assert post(client, headers, subject.id, text).status_code == 422
    assert rows(db_session) == []


def test_a_toc_file_that_cannot_be_read_leaves_the_document_out(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    fake_storage.objects[document.toc_key or ""] = (b"not json", None)

    card = post(client, headers, subject.id).json()

    assert card["card"] == "manual"
    assert fake_ai.requests == []
    assert card["documents"][0]["document_id"] == str(document.id)


def test_log_has_no_description(
    client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    fake_ai: FakeAi,
    log_output: Callable[[], str],
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    indexed_document(db_session, fake_storage, user, subject)
    fake_ai.answer = httpx2.Response(500, text=SENTENCE)

    post(client, headers, subject.id)

    assert SENTENCE not in log_output()
