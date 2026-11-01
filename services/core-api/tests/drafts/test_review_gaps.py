"""T7.8 tester round (US-02b AC6, AC8-AC10, AC13, Bảo mật; review-task-1 Y1-Y6): the edges the
first tests left open. Storage is a double; the database is real."""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from draft_world import World
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_review_api import Api, count, put_context, save_body, unit

from accounts import signed_in
from core_api.db.models import (
    Anchor,
    KnowledgeUnit,
    StudyLedger,
    StudySession,
    UnitLineage,
    UnitSection,
)
from core_api.domain import unit_review
from core_api.handlers.session_result_v2 import OnSubmissionProcessed
from core_api.messaging.session_result_v2 import draft_key
from fake_storage import FakeStorage
from sessions.session_helpers import indexed_document, subject_of
from v2_rows import make_section

SHA = "ab" * 32


@pytest.fixture
def api(client: TestClient, db_session: Session, fake_storage: FakeStorage) -> Api:
    user, headers = signed_in(db_session)
    world = World(db_session, user, fake_storage)
    key = world.put([world.draft(1), world.draft(2), world.draft(3)])
    OnSubmissionProcessed(fake_storage)(db_session, world.processed(key))
    db_session.commit()
    return Api(client, world, headers)


def add(api: Api, title: str, headers: dict[str, str] | None = None, **extra: Any) -> Any:
    body = {"title": title, "content": "Tự viết", "kind": "concept"} | extra
    return api.client.post(api.base, json=body, headers=headers or api.headers)


def save(api: Api, ids: list[str]) -> Any:
    versions = {d["id"]: d["version"] for d in api.drafts()}
    body = {"units": [{"unit_id": i, "version": versions[i]} for i in ids]}
    return api.client.post(f"{api.base}/save", json=body, headers=api.headers)


# --- Y1: file_keys of another user never reach a submission (CHECK 0024 is the layer) ---------


def test_y1_security_db_refuses_another_users_file_key_on_the_draft_submission(
    api: Api, db_session: Session
) -> None:
    # Red when: CHECK file_keys_are_own_notes is dropped or stops covering UPDATE, or the pure
    # helper and the CHECK disagree on which keys are this session's own.
    w = api.world
    stranger, _ = signed_in(db_session)
    own = f"users/{w.user.id}/sessions/{w.study.id}/notes/{SHA}.jpg"
    foreign = f"users/{stranger.id}/sessions/{w.study.id}/notes/{SHA}.jpg"
    assert unit_review.file_keys_are_own([own], w.user.id, w.study.id)
    assert not unit_review.file_keys_are_own([foreign], w.user.id, w.study.id)
    w.submission.file_keys = [own]
    db_session.flush()  # the own key is accepted
    nested = db_session.begin_nested()
    w.submission.file_keys = [own, foreign]
    with pytest.raises(IntegrityError) as caught:
        db_session.flush()
    assert "file_keys_are_own_notes" in str(caught.value)
    nested.rollback()


# --- Y2: isolation and "unverified is refused" on every new endpoint ---------------------------


def test_y2_isolation_a_stranger_cannot_add_or_split_and_nothing_is_written(
    api: Api, db_session: Session
) -> None:
    # Red when: add or split finds the session/card by id alone (no user_id): a stranger writes a
    # card into someone else's session, or splits their card (500 from the double FK counts too).
    _, other = signed_in(db_session)
    before = count(db_session, KnowledgeUnit)
    assert add(api, "Kẻ lạ", headers=other).status_code == 404
    card = api.drafts()[0]
    parts: list[dict[str, Any]] = [
        {"title": "P1", "content": "x", "anchor_ids": []},
        {"title": "P2", "content": "y", "anchor_ids": []},
    ]
    split = api.client.post(
        f"/v1/drafts/{card['id']}/split", json={"parts": parts}, headers=other | {"If-Match": "1"}
    )
    assert split.status_code == 404
    assert count(db_session, KnowledgeUnit) == before
    assert {d["title"] for d in api.drafts()} == {"Thẻ 1", "Thẻ 2", "Thẻ 3"}


WRITES: list[tuple[str, str, Any]] = [
    ("GET", "{base}", None),
    ("POST", "{base}", {"title": "x", "content": "y", "kind": "concept"}),
    ("POST", "{base}/merge", {"unit_ids": ["{card}", "{card2}"]}),
    ("POST", "{base}/save", {"units": [{"unit_id": "{card}", "version": 1}]}),
    ("GET", "/v1/drafts/{card}", None),
    ("PATCH", "/v1/drafts/{card}", {"title": "x"}),
    ("DELETE", "/v1/drafts/{card}", None),
    ("POST", "/v1/drafts/{card}/undo", None),
    (
        "POST",
        "/v1/drafts/{card}/split",
        {"parts": [{"title": "a", "content": "b"}, {"title": "c", "content": "d"}]},
    ),
]


@pytest.mark.parametrize(("method", "path", "body"), WRITES, ids=[f"{m} {p}" for m, p, _ in WRITES])
def test_y2_unverified_is_refused_on_every_endpoint(
    api: Api, db_session: Session, method: str, path: str, body: Any
) -> None:
    # Red when: one route drops the router-level verified_user dependency.
    _, headers = signed_in(db_session, verified=False)
    cards = [d["id"] for d in api.drafts()]
    fill = {"base": api.base, "card": cards[0], "card2": cards[1]}
    raw = json.dumps(body).replace("{card}", cards[0]).replace("{card2}", cards[1])
    response = api.client.request(
        method, path.format(**fill), json=json.loads(raw), headers=headers | {"If-Match": "1"}
    )
    assert response.status_code == 403, response.text
    assert count(db_session, KnowledgeUnit, status="draft") == 3


def test_add_with_a_strangers_section_links_no_section(
    api: Api, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Red when: add() trusts the section_id of the body (no user/subject filter): the card is
    # linked to another user's outline section (or the double FK turns it into a 500).
    bob, _ = signed_in(db_session)
    doc = indexed_document(
        db_session, fake_storage, bob, subject_of(db_session, bob), sha="cd" * 32
    )
    foreign = make_section(db_session, bob, doc)
    made = add(api, "Của tôi", section_id=str(foreign.id))
    assert made.status_code == 201 and made.json()["section_ids"] == []
    own = add(api, "Có mục", section_id=str(api.world.section.id))
    assert own.json()["section_ids"] == [str(api.world.section.id)]


def test_save_refuses_a_card_of_another_session_of_the_same_user(
    api: Api, db_session: Session
) -> None:
    # Red when: Save locks the listed cards by id and user only, not by the session in the path:
    # a card of session B gets saved (and counted in the ledger) through session A.
    w = api.world
    other = StudySession(
        user_id=w.user.id,
        subject_id=w.subject.id,
        description_raw="buổi khác",
        extraction="proposed",
        status="draft",
    )
    db_session.add(other)
    db_session.flush()
    card = api.drafts()[0]
    response = api.client.post(
        f"/v1/sessions/{other.id}/drafts/save",
        json={"units": [{"unit_id": card["id"], "version": card["version"]}]},
        headers=api.headers,
    )
    assert response.status_code == 404
    db_session.rollback()
    assert count(db_session, KnowledgeUnit, status="canonical") == 0


# --- Y3: logs never hold what the learner or the AI wrote (ADR-0013) ---------------------------


def _record_text(record: logging.LogRecord) -> str:
    return record.getMessage() + " " + " ".join(str(v) for v in record.__dict__.values())


def test_y3_logs_hold_no_title_quote_content_or_key(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, caplog: Any
) -> None:
    # Red when: a log line (message or extra) carries a card title, content, a quote, the result
    # key, or the text of an unreadable context file.
    caplog.set_level(logging.DEBUG)
    user, headers = signed_in(db_session)
    w = World(db_session, user, fake_storage)
    key = w.put([w.draft(1), w.draft(2)])
    OnSubmissionProcessed(fake_storage)(db_session, w.processed(key))
    bad = w.put([w.draft(1)]).replace("result-", "result-0")  # refused key path logs too
    OnSubmissionProcessed(fake_storage)(db_session, w.processed(bad))
    api = Api(client, w, headers)
    card = api.drafts()[0]
    api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "Bí mật tiêu đề"}, if_match="1")
    ctx = f"users/{w.user.id}/sessions/{w.study.id}/context/{w.submission.id}.json"
    w.storage.write(ctx, "{Câu trích hỏng".encode(), content_type="x")
    done = api.client.post(f"{api.base}/save", json=save_body(api), headers=api.headers)
    assert done.status_code == 200
    assert any("context unreadable" in r.getMessage() for r in caplog.records)
    secrets = ["Thẻ 1", "Thẻ 2", "Câu trích", "Nội dung", "Bí mật tiêu đề", key, "result-"]
    for record in caplog.records:
        if not record.name.startswith("core_api"):
            continue
        text = _record_text(record)
        for secret in secrets:
            assert secret not in text, (record.name, record.getMessage(), secret)


# --- Y4: pending_ai keeps manual work open (AC10) ----------------------------------------------


def test_y4_ac10_pending_ai_still_allows_add_and_edit(api: Api, db_session: Session) -> None:
    # Red when: a gate on the submission status blocks add/edit while the AI quota is spent, or
    # the list stops reporting pending_ai to the screen.
    w = api.world
    w.submission.status = "pending_ai"
    w.submission.finished_at = None
    db_session.flush()
    made = add(api, "Tay khi chờ AI")
    assert made.status_code == 201
    card = api.drafts()[0]
    edited = api.send("PATCH", f"/v1/drafts/{card['id']}", {"content": "Sửa khi chờ"}, if_match="1")
    assert edited.status_code == 200 and edited.json()["content"] == "Sửa khi chờ"
    listed = api.get().json()
    assert listed["submission_status"] == "pending_ai" and len(listed["drafts"]) == 4


# --- Y5: the ledger adds up (AC9) --------------------------------------------------------------


def test_y5_ac9_two_saves_same_section_same_day_add_up(api: Api) -> None:
    # Red when: the ledger upsert overwrites (units_saved = excluded) instead of adding.
    ids = [d["id"] for d in api.drafts()]
    assert save(api, [ids[0]]).json()["saved"] == [ids[0]]
    assert save(api, [ids[1]]).json()["saved"] == [ids[1]]
    rows = list(api.world.db.scalars(select(StudyLedger)))
    assert [(r.section_id, r.units_saved) for r in rows] == [(api.world.section.id, 2)]


def test_y5_ac9_ledger_without_section_is_one_row_that_adds_up(api: Api) -> None:
    # Red when: NULL sections are distinct in the ledger key (two rows) or the upsert overwrites.
    a = add(api, "Không mục A").json()
    b = add(api, "Không mục B").json()
    save(api, [a["id"]])
    save(api, [b["id"]])
    rows = list(api.world.db.scalars(select(StudyLedger).where(StudyLedger.section_id.is_(None))))
    assert [r.units_saved for r in rows] == [2]


def test_ac9_one_save_over_two_sections_writes_one_row_each(api: Api) -> None:
    # Red when: the per-section count is lumped into the first card's section.
    a = add(api, "Mục hai", section_id=str(api.world.section2.id)).json()
    ids = [d["id"] for d in api.drafts() if d["title"] in {"Thẻ 1", "Thẻ 2"}] + [a["id"]]
    save(api, ids)
    rows = {r.section_id: r.units_saved for r in api.world.db.scalars(select(StudyLedger))}
    assert rows == {api.world.section.id: 2, api.world.section2.id: 1}


def test_ac12_saves_on_two_learning_days_are_two_ledger_rows(api: Api, set_now: Any) -> None:
    # Red when: the ledger key ignores the learning day (day 2 adds into day 1's row).
    ids = [d["id"] for d in api.drafts()]
    set_now(datetime(2026, 11, 1, 5, 0, tzinfo=UTC))
    save(api, [ids[0]])
    set_now(datetime(2026, 11, 2, 5, 0, tzinfo=UTC))
    save(api, [ids[1]])
    rows = sorted(
        (r.learning_day, r.units_saved) for r in api.world.db.scalars(select(StudyLedger))
    )
    assert [n for _, n in rows] == [1, 1] and rows[0][0] < rows[1][0]


# --- Y6: split leaves the uncovered anchors on the merged original -----------------------------


def test_y6_split_uncovered_anchor_stays_on_the_merged_original(api: Api) -> None:
    # Red when: an anchor no part named is moved, deleted, or the original is left a draft (it
    # would show twice). Decision 01/11: parts need not cover every anchor (lineage keeps it).
    ids = [d["id"] for d in api.drafts()]
    merged = api.client.post(
        f"{api.base}/merge", json={"unit_ids": ids[:2]}, headers=api.headers
    ).json()
    a, b = (x["id"] for x in merged["anchors"])
    parts: list[dict[str, Any]] = [
        {"title": "P1", "content": "x", "anchor_ids": [a]},
        {"title": "P2", "content": "y", "anchor_ids": []},
    ]
    done = api.send(
        "POST",
        f"/v1/drafts/{merged['id']}/split",
        {"parts": parts},
        if_match=str(merged["version"]),
    )
    assert done.status_code == 200
    db = api.world.db
    left = db.get(Anchor, uuid.UUID(b))
    assert left is not None and str(left.unit_id) == merged["id"]
    original = db.get(KnowledgeUnit, uuid.UUID(merged["id"]))
    assert original is not None and original.status == "merged"
    assert {d["title"] for d in api.drafts()} == {"P1", "P2", "Thẻ 3"}
    assert count(db, UnitLineage, old_unit_id=uuid.UUID(merged["id"])) == 2
    new_sections = db.scalars(
        select(UnitSection.section_id)
        .join(KnowledgeUnit, KnowledgeUnit.id == UnitSection.unit_id)
        .where(KnowledgeUnit.title == "P2")
    )
    assert list(new_sections) == [api.world.section.id]  # sections copied to each part


def test_split_with_a_stale_version_is_409_and_writes_nothing(api: Api) -> None:
    # Red when: split skips the If-Match check (two tabs: one edits, the other splits the old text).
    card = api.drafts()[0]
    api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "Đổi"}, if_match="1")
    parts = [{"title": "P1", "content": "x"}, {"title": "P2", "content": "y"}]
    stale = api.send("POST", f"/v1/drafts/{card['id']}/split", {"parts": parts}, if_match="1")
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "unit_changed_elsewhere"
    assert count(api.world.db, KnowledgeUnit) == 3


# --- edges: discard / undo / edit on non-drafts, undo boundary ---------------------------------


def test_ac8_undo_on_the_seventh_day_works_and_a_second_later_is_410(
    api: Api, set_now: Any
) -> None:
    # Red when: the window is < instead of <=, or counted from another instant than retired_at.
    t0 = datetime(2026, 11, 1, 5, 0, tzinfo=UTC)
    ids = [d["id"] for d in api.drafts()]
    set_now(t0)
    api.send("DELETE", f"/v1/drafts/{ids[0]}")
    api.send("DELETE", f"/v1/drafts/{ids[1]}")
    set_now(t0 + timedelta(days=7))
    assert api.send("POST", f"/v1/drafts/{ids[0]}/undo").status_code == 200
    set_now(t0 + timedelta(days=7, seconds=1))
    assert api.send("POST", f"/v1/drafts/{ids[1]}/undo").status_code == 410


def test_saved_card_cannot_be_edited_discarded_or_undone_as_a_draft(api: Api) -> None:
    # Red when: edit/discard/undo skip the status check: a canonical card is rewritten in place
    # (no new revision) or retired through the draft routes.
    card = api.drafts()[0]
    save(api, [card["id"]])
    row = unit(api.world.db, "Thẻ 1")
    v = str(row.version)
    assert (
        api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "x"}, if_match=v).status_code == 409
    )
    assert api.send("DELETE", f"/v1/drafts/{card['id']}").status_code == 409
    assert api.send("POST", f"/v1/drafts/{card['id']}/undo").status_code == 409
    api.world.db.refresh(row)
    assert row.status == "canonical" and row.title == "Thẻ 1"


def test_discard_then_save_the_retired_card_is_refused(api: Api) -> None:
    # Red when: Save turns a retired card canonical (the learner threw it away).
    card = api.drafts()[0]
    api.send("DELETE", f"/v1/drafts/{card['id']}")
    response = api.client.post(
        f"{api.base}/save",
        json={"units": [{"unit_id": card["id"], "version": 2}]},
        headers=api.headers,
    )
    assert response.status_code == 409
    api.world.db.rollback()
    assert count(api.world.db, KnowledgeUnit, status="canonical") == 0


def test_save_context_with_inverted_or_zero_pages_writes_no_range(api: Api) -> None:
    # Red when: a range with first > last or page 0 from the (untrusted) context file is stored.
    doc = str(api.world.document.id)
    put_context(
        api,
        [
            {"document_id": doc, "first_page": 9, "last_page": 3},
            {"document_id": doc, "first_page": 0, "last_page": 2},
            {"document_id": doc, "first_page": "1", "last_page": 2},
            {"document_id": doc, "first_page": True, "last_page": 2},
        ],
    )
    assert (
        api.client.post(f"{api.base}/save", json=save_body(api), headers=api.headers).status_code
        == 200
    )
    from core_api.db.models import SessionRange

    assert count(api.world.db, SessionRange) == 0


# --- second round: edges the mutation run left uncovered ---------------------------------------


def _world(db: Session) -> World:
    user, _ = signed_in(db)
    return World(db, user, FakeStorage())


def _units_of(db: Session, w: World) -> int:
    return count(db, KnowledgeUnit, user_id=w.user.id)


def test_security_result_file_of_another_session_with_matching_keys_is_refused(
    db_session: Session,
) -> None:
    # Red when: the file's study_session_id is not compared with the locked session (its draft
    # keys here are consistent with the other session, so the schema alone does not refuse it).
    w = _world(db_session)
    other = uuid.uuid4()
    d = w.draft(1)
    d["draft_key"] = draft_key(other, d["quote_hash"])
    body = w.body([d]) | {"study_session_id": str(other)}
    w.storage.write(w.key(), json.dumps(body).encode(), content_type="x")
    OnSubmissionProcessed(w.storage)(db_session, w.processed(w.key()))
    assert _units_of(db_session, w) == 0
    assert w.submission.status == "failed"


def test_security_event_pairing_a_session_with_another_sessions_submission_is_ignored(
    db_session: Session,
) -> None:
    # Red when: the consumer does not check that the submission belongs to the locked session:
    # drafts land in session A and session B's submission is marked done.
    a = _world(db_session)
    b = World(db_session, a.user, a.storage)
    a.submission = b.submission  # the event names session A but B's submission
    key = a.put([a.draft(1)])
    OnSubmissionProcessed(a.storage)(db_session, a.processed(key))
    assert _units_of(db_session, a) == 0
    assert b.submission.status == "processing"


def test_ac13_a_result_after_done_adds_no_new_card(db_session: Session) -> None:
    # Red when: a done submission is processed again: a later file with a new draft adds a card.
    w = _world(db_session)
    OnSubmissionProcessed(w.storage)(db_session, w.processed(w.put([w.draft(1)])))
    assert w.submission.status == "done"
    finished = w.submission.finished_at
    OnSubmissionProcessed(w.storage)(db_session, w.processed(w.put([w.draft(1), w.draft(5)])))
    assert _units_of(db_session, w) == 1 and w.submission.finished_at == finished


def test_isolation_merge_with_a_strangers_card_in_the_list_is_404(
    api: Api, db_session: Session
) -> None:
    # Red when: merge drops the ids it could not lock and merges the rest (a stranger's id is
    # silently ignored instead of refusing the whole request).
    bob = World(db_session, signed_in(db_session)[0], FakeStorage())
    OnSubmissionProcessed(bob.storage)(db_session, bob.processed(bob.put([bob.draft(1)])))
    theirs = db_session.scalars(
        select(KnowledgeUnit.id).where(KnowledgeUnit.user_id == bob.user.id)
    ).one()
    mine = [d["id"] for d in api.drafts()][:2]
    response = api.client.post(
        f"{api.base}/merge", json={"unit_ids": [*mine, str(theirs)]}, headers=api.headers
    )
    assert response.status_code == 404
    assert len(api.drafts()) == 3 and count(db_session, UnitLineage) == 0


def test_ac9_the_same_range_mentioned_twice_or_saved_twice_is_one_row(api: Api) -> None:
    # Red when: Save writes a range already in the session again (from a repeated mention or a
    # second Save of other cards).
    from core_api.db.models import SessionRange

    doc = str(api.world.document.id)
    mention = {"document_id": doc, "first_page": 3, "last_page": 9}
    put_context(api, [mention, mention])
    ids = [d["id"] for d in api.drafts()]
    save(api, [ids[0]])
    save(api, [ids[1]])
    assert count(api.world.db, SessionRange) == 1
