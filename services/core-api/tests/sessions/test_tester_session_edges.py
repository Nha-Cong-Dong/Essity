"""Edge cases of T4.12 added by the independent tester: window and page boundaries, the day the
learner's own clock starts, the contract limits of session.confirmed.v1, and note files across
users. Each test says when it goes red."""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from session_helpers import indexed_document, proposed, subject_of
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_confirm_session import (
    SHA,
    World,
    confirm,
    count,
    note,
    outbox,
    range_of,
)

from accounts import signed_in
from conftest import FakeAi
from core_api.db.models import KnowledgeUnit, NoteFile, Outbox, SessionRange, StudySession
from core_api.repositories.subject import SubjectRepository
from fake_storage import FakeStorage
from test_event_contracts import validator

pytestmark = pytest.mark.usefixtures("fake_storage")


@pytest.fixture
def world(db_session: Session, fake_storage: FakeStorage) -> World:
    return World(db_session, fake_storage)


def add_unit(world: World, title: str, summary: str, created: datetime) -> KnowledgeUnit:
    row = KnowledgeUnit(
        subject_id=world.subject.id,
        title=title,
        summary=summary,
        kind="concept",
        run_id=uuid.uuid4(),
        created_at=created,
    )
    row.user_id = world.user.id
    world.db.add(row)
    return row


def envelope(row: Outbox) -> dict[str, Any]:
    return {
        "event_id": str(row.id),
        "event_type": row.event_type,
        "schema_version": 1,
        "occurred_at": row.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "user_id": str(row.user_id),
        "trace_context": row.trace_context,
        "payload": row.payload,
    }


@pytest.mark.parametrize(
    ("day", "status"),
    [("2025-10-21", 200), ("2026-10-22", 200), ("2025-10-20", 422), ("2026-10-23", 422)],
    ids=["oldest-allowed", "today", "one-day-too-old", "tomorrow"],
)
def test_late_log_window_edges(client: TestClient, world: World, day: str, status: int) -> None:
    # Red when: the window for "ghi bù" is shorter than 366 days back from the learning day
    # (2026-10-22 - 366 days = 2025-10-21), longer, or an edge uses < instead of <=.
    response = confirm(client, world.headers, world.draft, studied_on=day)

    assert response.status_code == status
    assert len(outbox(world.db)) == (1 if status == 200 else 0)


def test_learning_day_follows_day_start_hour_not_utc(
    client: TestClient, world: World, set_now: Callable[[datetime], None]
) -> None:
    # 21:30 UTC on the 22nd is 04:30 on the 23rd in Ho Chi Minh City: past the 04:00 day start,
    # so the learning day is the 23rd and studying "today" (the 23rd) is not in the future.
    # Red when: `learning_day` is the UTC date, the calendar date ignoring day_start_hour, or the
    # studied day instead of the day it was logged (Q14).
    set_now(datetime(2026, 10, 22, 21, 30, tzinfo=UTC))

    response = confirm(client, world.headers, world.draft, studied_on="2026-10-23")

    assert response.status_code == 200
    assert response.json()["learning_day"] == "2026-10-23"
    assert response.json()["studied_on"] == "2026-10-23"


def test_late_log_before_day_start_keeps_both_days(
    client: TestClient, world: World, set_now: Callable[[datetime], None]
) -> None:
    # 03:59 local on the 23rd still belongs to the 22nd. Red when: the learning day flips at
    # midnight, or a late log moves `learning_day` to the studied day.
    set_now(datetime(2026, 10, 22, 20, 59, tzinfo=UTC))

    response = confirm(client, world.headers, world.draft, studied_on="2026-10-20")

    assert response.status_code == 200
    out = response.json()
    assert (out["studied_on"], out["learning_day"]) == ("2026-10-20", "2026-10-22")


def test_single_page_ranges_at_the_file_edges(client: TestClient, world: World) -> None:
    # The document has 40 pages. Red when: a range of one page (first == last), page 1 or the
    # last page is refused, or the event changes the pages.
    ranges = [range_of(world.document, 1, 1), range_of(world.document, 40, 40)]
    ranges.append(range_of(world.document, 1, 40, depth="skim"))

    response = confirm(client, world.headers, world.draft, ranges=ranges)

    assert response.status_code == 200
    [event] = outbox(world.db)
    assert [(r["first"], r["last"]) for r in event.payload["ranges"]] == [(1, 1), (40, 40), (1, 40)]


def test_summary_cut_counts_characters_at_the_edge(client: TestClient, world: World) -> None:
    # Red when: a 2000-character summary is cut, a 2001-character one is not, or the cut counts
    # bytes / UTF-16 units (an emoji is one character in the contract's maxLength).
    base = datetime(2026, 10, 1, tzinfo=UTC)
    exact = add_unit(world, "Đúng 2000", "ế" * 2000, base)
    over = add_unit(world, "2001", "😀" * 2001, base + timedelta(hours=1))
    world.db.flush()

    assert confirm(client, world.headers, world.draft).status_code == 200

    [row] = outbox(world.db)
    sent = {u["unit_id"]: u["summary"] for u in row.payload["existing_units"]}
    assert sent[str(exact.id)] == "ế" * 2000
    assert sent[str(over.id)] == "😀" * 2000
    validator("session.confirmed.v1").validate(envelope(row))


def test_existing_units_capped_at_500_newest_first(client: TestClient, world: World) -> None:
    # A subject with more units than the contract's maxItems (500). Red when: confirm sends all of
    # them (the event is refused and the learner cannot confirm), sends fewer than 500, or drops
    # the newest instead of the oldest.
    base = datetime(2026, 1, 1, tzinfo=UTC)
    units = [
        add_unit(world, f"Đơn vị {n}", "tóm tắt", base + timedelta(minutes=n)) for n in range(501)
    ]
    world.db.flush()

    response = confirm(client, world.headers, world.draft)

    assert response.status_code == 200
    [row] = outbox(world.db)
    sent = [u["unit_id"] for u in row.payload["existing_units"]]
    assert len(sent) == 500
    assert sent[0] == str(units[-1].id)
    assert str(units[0].id) not in sent


def test_full_card_at_the_limits_matches_the_contract(client: TestClient, world: World) -> None:
    # Six ranges and twenty notes of every type: the most a card holds. Red when: a limit is
    # tighter than the contract's, a note's key does not take the extension of its type, or the
    # row written to the outbox does not validate against contracts/events (ADR-0006).
    mimes = ["image/jpeg", "image/png", "application/pdf", "text/plain", "text/markdown"]
    ext = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}
    ext |= {"text/plain": "txt", "text/markdown": "md"}
    notes: list[dict[str, Any]] = []
    for n in range(20):
        sha, mime = f"{n:02x}" * 32, mimes[n % 5]
        key = f"users/{world.user.id}/sessions/{world.draft.id}/notes/{sha}.{ext[mime]}"
        world.storage.put(key, b"y" * (n + 1), None)
        notes.append({"sha256": sha, "mime": mime, "size_bytes": n + 1})
    ranges = [range_of(world.document, 5 * n + 1, 5 * n + 3) for n in range(6)]

    response = confirm(client, world.headers, world.draft, ranges=ranges, notes=notes)

    assert response.status_code == 200
    assert count(world.db, NoteFile) == 20
    [row] = outbox(world.db)
    keys = [n["object_key"] for n in row.payload["notes"]]
    assert {k.rsplit(".", 1)[1] for k in keys} == {"jpg", "png", "pdf", "txt", "md"}
    validator("session.confirmed.v1").validate(envelope(row))


def test_a_note_stored_under_another_type_is_not_found(client: TestClient, world: World) -> None:
    # The file is in the store as .jpg; the card says it is a PDF. Red when: the key the server
    # checks does not follow the declared type (a note row would point at a file that is not
    # there, and ai-service would read the wrong thing).
    key = f"users/{world.user.id}/sessions/{world.draft.id}/notes/{SHA}.jpg"
    world.storage.put(key, b"x" * 10, None)

    response = confirm(client, world.headers, world.draft, notes=[note(mime="application/pdf")])

    assert response.status_code == 409
    assert response.json()["detail"] == "upload_incomplete"
    assert outbox(world.db) == []


def test_another_users_note_file_cannot_be_claimed(client: TestClient, world: World) -> None:
    # B uploaded a note with this hash under B's own prefix. A confirms a card naming that hash.
    # Red when: the server finds the file anywhere but A's own session prefix (A could make
    # ai-service read B's notes into A's units).
    other, _ = signed_in(world.db)
    other_subject = subject_of(world.db, other)
    other_draft = StudySession(
        subject_id=other_subject.id, description_raw="của B", extraction="proposed"
    )
    other_draft.user_id = other.id
    world.db.add(other_draft)
    world.db.flush()
    world.storage.put(
        f"users/{other.id}/sessions/{other_draft.id}/notes/{SHA}.jpg", b"x" * 10, None
    )
    world.storage.put(
        f"users/{other.id}/sessions/{world.draft.id}/notes/{SHA}.jpg", b"x" * 10, None
    )

    response = confirm(client, world.headers, world.draft, notes=[note()])

    assert response.status_code == 409
    assert count(world.db, NoteFile) == 0


def test_two_users_drafts_do_not_mix(client: TestClient, world: World) -> None:
    # B confirms B's own draft naming A's document id; then A confirms A's. Red when: B's
    # document check accepts A's document, or one user's confirm touches the other's draft.
    other, other_headers = signed_in(world.db)
    other_subject = subject_of(world.db, other)
    other_draft = StudySession(
        subject_id=other_subject.id, description_raw="của B", extraction="proposed"
    )
    other_draft.user_id = other.id
    world.db.add(other_draft)
    world.db.flush()

    refused = confirm(client, other_headers, other_draft, ranges=[range_of(world.document)])
    mine = confirm(client, world.headers, world.draft, ranges=[range_of(world.document)])

    assert refused.status_code == 404
    assert refused.json()["detail"] == "document_not_found"
    assert mine.status_code == 200
    rows = world.db.execute(select(StudySession.user_id, StudySession.status)).tuples()
    statuses = {user_id: status for user_id, status in rows}
    assert statuses == {world.user.id: "confirmed", other.id: "draft"}
    assert [r.user_id for r in outbox(world.db)] == [world.user.id]


def test_create_on_a_deleted_subject_is_404_and_saves_nothing(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    # Red when: a sentence is saved (and the AI asked) for a subject the learner deleted.
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    indexed_document(db_session, fake_storage, user, subject)
    SubjectRepository(db_session, user.id).soft_delete(subject.id, datetime.now(UTC))

    response = client.post(
        f"/v1/subjects/{subject.id}/sessions", json={"description": "học"}, headers=headers
    )

    assert response.status_code == 404
    assert db_session.scalar(select(StudySession.id)) is None
    assert fake_ai.requests == []


def test_a_sentence_of_exactly_2000_characters_is_kept_whole(
    client: TestClient, db_session: Session, fake_ai: FakeAi
) -> None:
    # Red when: the API limit and the column's CHECK disagree at the edge (a 2000-character
    # sentence refused, cut, or a 500 from the database).
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    text = "ổ" * 2000

    response = client.post(
        f"/v1/subjects/{subject.id}/sessions", json={"description": text}, headers=headers
    )

    assert response.status_code == 201
    assert db_session.scalar(select(StudySession.description_raw)) == text


def test_more_than_twenty_notes_is_422_not_500(client: TestClient, world: World) -> None:
    # Red when: the request takes more notes than the contract's maxItems (20): the event is then
    # refused inside the transaction and the learner gets a 500 instead of a clear 422.
    notes = [note(f"{n:02x}" * 32) for n in range(21)]

    response = confirm(client, world.headers, world.draft, notes=notes)

    assert response.status_code == 422
    assert outbox(world.db) == []


def test_a_failed_document_with_a_page_count_is_not_indexed(
    client: TestClient, world: World
) -> None:
    # ai-service may know the page count of a file it then refused (too_large). Red when: confirm
    # accepts a range on any document that has a page count, indexed or not.
    document = world.document
    document.status = "failed"
    document.failure_reason = "too_large"
    document.toc_key = document.page_labels_key = None
    document.page_text_key = document.thumbnails_prefix = None
    document.run_id = None
    world.db.flush()

    response = confirm(client, world.headers, world.draft, ranges=[range_of(document)])

    assert response.status_code == 409
    assert response.json()["detail"] == "not_indexed"
    assert count(world.db, SessionRange) == 0


def test_an_answer_with_seven_ranges_is_manual(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    # Red when: the card proposes more ranges than confirm (and session.confirmed.v1) accept: the
    # learner would get a card that cannot be confirmed as shown.
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject)
    answer = proposed(document)
    body = json.loads(answer.content)
    body["ranges"] = [body["ranges"][0] | {"start_page": n, "end_page": n} for n in range(1, 8)]
    fake_ai.answer = httpx2.Response(200, json=body)

    card = client.post(
        f"/v1/subjects/{subject.id}/sessions", json={"description": "học"}, headers=headers
    ).json()

    assert card["card"] == "manual"
    assert card["ranges"] == []


def test_last_end_page_beyond_the_file_is_not_sent(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    # A past range ends past today's page count (a row written before a change of file). Red
    # when: core sends `last_end_page > page_count` and ai-service refuses the whole request.
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject, pages=10)
    done = StudySession(
        subject_id=subject.id,
        description_raw="trước",
        status="confirmed",
        extraction="proposed",
        studied_on=date(2026, 10, 20),
        learning_day=date(2026, 10, 20),
        confirmed_at=datetime(2026, 10, 20, tzinfo=UTC),
    )
    done.user_id = user.id
    db_session.add(done)
    db_session.flush()
    db_session.add(
        SessionRange(
            user_id=user.id,
            session_id=done.id,
            document_id=document.id,
            start_page=1,
            end_page=12,
            depth="deep",
            position=0,
        )
    )
    db_session.flush()
    fake_ai.answer = proposed(document, range={"end_page": 9})

    client.post(f"/v1/subjects/{subject.id}/sessions", json={"description": "học"}, headers=headers)

    assert json.loads(fake_ai.requests[0].content)["documents"][0]["last_end_page"] is None
