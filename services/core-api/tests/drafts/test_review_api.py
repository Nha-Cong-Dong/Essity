"""T7.8 (US-02b AC6-AC9, AC12, AC14, Bảo mật): the review API over a session's draft cards.
Storage is a double; the database is real."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from draft_world import World
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import (
    Anchor,
    KnowledgeUnit,
    Outbox,
    SessionRange,
    StudyLedger,
    UnitLineage,
    UnitRevision,
)
from core_api.domain import unit_review
from core_api.handlers.session_result_v2 import OnSubmissionProcessed
from fake_storage import FakeStorage

SetNow = Callable[[datetime], None]


class Api:
    def __init__(self, client: TestClient, world: World, headers: dict[str, str]) -> None:
        self.client, self.world, self.headers = client, world, headers
        self.base = f"/v1/sessions/{world.study.id}/drafts"

    def get(self, path: str = "") -> Any:
        return self.client.get(self.base + path, headers=self.headers)

    def send(self, method: str, path: str, body: Any = None, **headers: str) -> Any:
        return self.client.request(
            method,
            path,
            json=body,
            headers=self.headers | {k.replace("_", "-"): v for k, v in headers.items()},
        )

    def drafts(self) -> list[dict[str, Any]]:
        return sorted(
            self.get().json()["drafts"], key=lambda d: d["title"]
        )  # one transaction: no order


@pytest.fixture
def api(client: TestClient, db_session: Session, fake_storage: FakeStorage) -> Api:
    user, headers = signed_in(db_session)
    world = World(db_session, user, fake_storage)
    key = world.put([world.draft(1), world.draft(2), world.draft(3)])
    OnSubmissionProcessed(fake_storage)(db_session, world.processed(key))
    db_session.commit()
    return Api(client, world, headers)


def count(db: Session, model: type, **where: Any) -> int:
    query = select(func.count()).select_from(model)
    for name, value in where.items():
        query = query.where(getattr(model, name) == value)
    return db.scalar(query) or 0


def unit(db: Session, title: str) -> KnowledgeUnit:
    return db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.title == title)).one()


def test_ac14_list_has_anchors_revisions_sections_and_submission_status(api: Api) -> None:
    # Red when: the list lacks the anchor, the AI revision, the section or the submission status.
    body = api.get().json()
    assert body["submission_status"] == "done"
    first = body["drafts"][0]
    assert first["status"] == "draft" and first["version"] == 1
    assert first["section_ids"] == [str(api.world.section.id)]
    assert first["anchors"][0]["quote_text"].startswith("Câu trích")
    assert [(r["rev"], r["origin"]) for r in first["revisions"]] == [(0, "ai")]
    assert len(body["drafts"]) == 3


def test_ac8_leave_the_screen_and_come_back_the_drafts_are_kept(api: Api) -> None:
    # Red when: drafts depend on a screen-side state: a second read gives the same cards.
    assert api.drafts() == api.drafts()


def test_ac7_edit_with_if_match_bumps_the_version(api: Api) -> None:
    card = api.drafts()[0]
    done = api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "Mới"}, if_match="1")
    assert done.status_code == 200
    assert done.json()["title"] == "Mới" and done.json()["version"] == 2
    assert [r["origin"] for r in done.json()["revisions"]] == ["ai"]  # rev 0 untouched


def test_ac7_stale_if_match_is_409_with_the_message(api: Api) -> None:
    # Red when: an edit over a newer version is accepted silently.
    card = api.drafts()[0]
    api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "A"}, if_match="1")
    stale = api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "B"}, if_match='"1"')
    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "unit_changed_elsewhere",
        "message": "thẻ đã đổi ở nơi khác",
    }


def test_ac7_missing_if_match_is_428_and_junk_is_400(api: Api) -> None:
    card = api.drafts()[0]
    assert api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "A"}).status_code == 428
    junk = api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "A"}, if_match="abc")
    assert junk.status_code == 400


def test_ac6_rerun_never_overwrites_an_edit(api: Api, fake_storage: FakeStorage) -> None:
    # Red when: a second result over the same quote rewrites the edited draft or its rev 0.
    card = api.drafts()[0]
    api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "Của tôi"}, if_match="1")
    world = api.world
    world.submission.status = "processing"
    world.submission.finished_at = None
    key = world.put([world.draft(1, title="AI khác")])
    OnSubmissionProcessed(fake_storage)(world.db, world.processed(key))
    again = api.send("GET", f"/v1/drafts/{card['id']}").json()
    assert again["title"] == "Của tôi"
    assert again["revisions"][0]["content"]["title"] == "Thẻ 1"
    assert count(world.db, KnowledgeUnit) == 3


def test_ac8_discard_then_undo_within_seven_days(api: Api, set_now: SetNow) -> None:
    card = api.drafts()[0]
    gone = api.send("DELETE", f"/v1/drafts/{card['id']}")
    assert gone.json()["status"] == "retired"
    assert len(api.drafts()) == 2
    row = api.world.db.get(KnowledgeUnit, __import__("uuid").UUID(card["id"]))
    assert row is not None and row.retired_at is not None
    assert api.send("POST", f"/v1/drafts/{card['id']}/undo").json()["status"] == "draft"
    api.world.db.refresh(row)
    assert row.retired_at is None  # restored in the same change
    assert len(api.drafts()) == 3


def test_ac8_undo_after_seven_days_is_410(api: Api, set_now: SetNow) -> None:
    card = api.drafts()[0]
    api.send("DELETE", f"/v1/drafts/{card['id']}")
    set_now(datetime.now(UTC) + timedelta(days=8))
    assert api.send("POST", f"/v1/drafts/{card['id']}/undo").status_code == 410


def test_ac8_old_retired_row_without_retired_at_is_not_undoable(api: Api) -> None:
    # Red when: a retired card from before 0027 (retired_at NULL) can be brought back.
    row = unit(api.world.db, "Thẻ 1")
    row.status = "retired"
    api.world.db.flush()
    assert api.send("POST", f"/v1/drafts/{row.id}/undo").status_code == 409


def test_ac6_add_a_card_by_hand_has_a_user_rev0_and_no_anchor(api: Api) -> None:
    made = api.client.post(
        api.base,
        json={"title": "Của tôi", "content": "Tự viết", "kind": "formula"},
        headers=api.headers,
    )
    assert made.status_code == 201
    body = made.json()
    assert body["anchors"] == [] and [(r["rev"], r["origin"]) for r in body["revisions"]] == [
        (0, "user")
    ]
    assert len(api.drafts()) == 4


def test_ac6_merge_is_deterministic_and_keeps_anchors_and_lineage(api: Api) -> None:
    ids = [d["id"] for d in api.drafts()]
    merged = api.client.post(f"{api.base}/merge", json={"unit_ids": ids[:2]}, headers=api.headers)
    assert merged.status_code == 200
    body = merged.json()
    assert sorted(body["content"].split("\n\n")) == ["Nội dung 1.", "Nội dung 2."]
    assert len(body["anchors"]) == 2
    assert len(api.drafts()) == 2
    assert count(api.world.db, UnitLineage) == 1


def test_ac6_merge_refuses_a_saved_card_and_a_stranger(api: Api, db_session: Session) -> None:
    ids = [d["id"] for d in api.drafts()]
    row = unit(db_session, "Thẻ 2")
    row.status = "canonical"
    db_session.flush()
    refused = api.client.post(f"{api.base}/merge", json={"unit_ids": ids[:2]}, headers=api.headers)
    assert refused.status_code == 409
    _, other = signed_in(db_session)
    stranger = api.client.post(f"{api.base}/merge", json={"unit_ids": ids[:2]}, headers=other)
    assert stranger.status_code == 404


def test_ac6_split_moves_anchors_and_retires_the_original(api: Api) -> None:
    ids = [d["id"] for d in api.drafts()]
    merged = api.client.post(
        f"{api.base}/merge", json={"unit_ids": ids[:2]}, headers=api.headers
    ).json()
    a, b = (x["id"] for x in merged["anchors"])
    parts = [
        {"title": "P1", "content": "x", "anchor_ids": [a]},
        {"title": "P2", "content": "y", "anchor_ids": [b]},
    ]
    done = api.send(
        "POST",
        f"/v1/drafts/{merged['id']}/split",
        {"parts": parts},
        if_match=str(merged["version"]),
    )
    assert done.status_code == 200
    assert [len(d["anchors"]) for d in done.json()["drafts"]] == [1, 1]
    assert {d["title"] for d in api.drafts()} == {"P1", "P2", "Thẻ 3"}
    assert count(api.world.db, Anchor) == 3
    bad = api.send("POST", f"/v1/drafts/{ids[2]}/split", {"parts": parts}, if_match="1")
    assert bad.status_code == 422


def test_isolation_another_users_drafts_are_404(api: Api, db_session: Session) -> None:
    _, other = signed_in(db_session)
    card = api.drafts()[0]["id"]
    for method, path, body in [
        ("GET", api.base, None),
        ("GET", f"/v1/drafts/{card}", None),
        ("PATCH", f"/v1/drafts/{card}", {"title": "x"}),
        ("DELETE", f"/v1/drafts/{card}", None),
        ("POST", f"/v1/drafts/{card}/undo", None),
    ]:
        response = api.client.request(method, path, json=body, headers=other | {"If-Match": "1"})
        assert response.status_code == 404, (method, path)
    saved = api.client.post(
        f"{api.base}/save", json={"units": [{"unit_id": card, "version": 1}]}, headers=other
    )
    assert saved.status_code == 404


def test_unverified_cannot_review(client: TestClient, db_session: Session, api: Api) -> None:
    _, headers = signed_in(db_session, verified=False)
    assert client.get(api.base, headers=headers).status_code == 403


# --- Save ----------------------------------------------------------------------------------------


def save_body(api: Api, versions: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "units": [
            {"unit_id": d["id"], "version": (versions or {}).get(d["id"], d["version"])}
            for d in api.drafts()
        ]
    }


def put_context(api: Api, mentions: list[dict[str, Any]]) -> None:
    w = api.world
    key = f"users/{w.user.id}/sessions/{w.study.id}/context/{w.submission.id}.json"
    w.storage.write(
        key, json.dumps({"version": 1, "mentions": mentions}).encode(), content_type="x"
    )


def test_ac9_save_writes_everything_in_one_transaction(api: Api) -> None:
    w = api.world
    put_context(
        api,
        [
            {
                "document_id": str(w.document.id),
                "section_id": None,
                "first_page": 3,
                "last_page": 9,
            },
            {
                "document_id": str(w.document.id),
                "section_id": None,
                "first_page": None,
                "last_page": None,
            },
        ],
    )
    body = save_body(api)
    done = api.client.post(f"{api.base}/save", json=body, headers=api.headers)
    assert done.status_code == 200 and len(done.json()["saved"]) == 3
    db = w.db
    units = list(db.scalars(select(KnowledgeUnit)))
    assert {u.status for u in units} == {"canonical"} and all(u.saved_at for u in units)
    assert (
        sorted((r.rev, r.origin) for r in db.scalars(select(UnitRevision)))
        == [(0, "ai")] * 3 + [(1, "user")] * 3
    )
    ledger = db.scalars(select(StudyLedger)).one()
    assert ledger.units_saved == 3 and ledger.section_id == w.section.id
    ranges = list(db.scalars(select(SessionRange)))
    assert [(r.start_page, r.end_page) for r in ranges] == [(3, 9)]
    events = list(db.scalars(select(Outbox).where(Outbox.event_type == "unit.saved.v1")))
    assert len(events) == 3 and {e.payload["unit_rev"] for e in events} == {1}


def test_ac9_rev0_stays_the_ai_original_after_an_edit(api: Api) -> None:
    card = api.drafts()[0]
    api.send("PATCH", f"/v1/drafts/{card['id']}", {"content": "Sửa rồi"}, if_match="1")
    api.client.post(f"{api.base}/save", json=save_body(api), headers=api.headers)
    revs = {
        r.rev: r
        for r in api.world.db.scalars(
            select(UnitRevision).where(UnitRevision.unit_id == __import__("uuid").UUID(card["id"]))
        )
    }
    assert revs[0].origin == "ai" and revs[0].content["content"] == "Nội dung 1."
    assert revs[1].origin == "user" and revs[1].content["content"] == "Sửa rồi"


def test_ac9_save_covers_only_the_listed_and_not_the_retired(api: Api) -> None:
    ids = [d["id"] for d in api.drafts()]
    api.send("DELETE", f"/v1/drafts/{ids[0]}")
    body = {"units": [{"unit_id": ids[1], "version": 1}]}
    done = api.client.post(f"{api.base}/save", json=body, headers=api.headers)
    assert done.json()["saved"] == [ids[1]]
    status = {u.title: u.status for u in api.world.db.scalars(select(KnowledgeUnit))}
    assert status == {"Thẻ 1": "retired", "Thẻ 2": "canonical", "Thẻ 3": "draft"}


def test_ac9_stale_version_is_409_and_nothing_is_saved(api: Api) -> None:
    card = api.drafts()[1]
    api.send("PATCH", f"/v1/drafts/{card['id']}", {"title": "Đổi"}, if_match="1")
    stale = api.client.post(
        f"{api.base}/save",
        json={
            "units": [
                {"unit_id": api.drafts()[0]["id"], "version": 1},
                {"unit_id": card["id"], "version": 1},
            ]
        },
        headers=api.headers,
    )
    assert stale.status_code == 409
    api.world.db.rollback()  # what the request's own session does on an exception: nothing wrote
    assert count(api.world.db, KnowledgeUnit, status="canonical") == 0
    assert count(api.world.db, Outbox, event_type="unit.saved.v1") == 0


def test_ac9_a_second_save_saves_nothing(api: Api) -> None:
    body = save_body(api)
    api.client.post(f"{api.base}/save", json=body, headers=api.headers)
    again = api.client.post(f"{api.base}/save", json=body, headers=api.headers)
    assert again.status_code == 200 and again.json()["saved"] == []
    assert api.world.db.scalar(select(func.sum(StudyLedger.units_saved))) == 3
    assert count(api.world.db, Outbox, event_type="unit.saved.v1") == 3


def test_ac9_failure_midway_leaves_no_half_save(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    # Red when: Save commits per card or per table: after the second card's outbox fails, the
    # rollback must take the first card, its revision and the ledger with it.
    real = unit_review._enqueue_unit_saved  # pyright: ignore[reportPrivateUsage]
    calls: list[int] = []

    def failing(*args: Any, **kwargs: Any) -> None:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("outbox down")
        real(*args, **kwargs)

    monkeypatch.setattr(unit_review, "_enqueue_unit_saved", failing)
    body = save_body(api)
    with pytest.raises(RuntimeError):
        api.client.post(f"{api.base}/save", json=body, headers=api.headers)
    api.world.db.rollback()
    db = api.world.db
    assert count(db, KnowledgeUnit, status="draft") == 3
    assert count(db, UnitRevision, rev=1) == 0
    assert count(db, StudyLedger) == 0
    assert count(db, Outbox, event_type="unit.saved.v1") == 0


@pytest.mark.parametrize(("hh", "mm", "same_day"), [(3, 59, True), (4, 0, False)])
def test_ac12_saved_learning_day_boundary(
    api: Api, set_now: SetNow, hh: int, mm: int, same_day: bool
) -> None:
    # 2026-11-01 03:59 / 04:00 in the user's zone (Asia/Ho_Chi_Minh = UTC+7, day starts 04:00).
    set_now(datetime(2026, 10, 31, hh, mm, tzinfo=UTC) - timedelta(hours=7) + timedelta(days=1))
    api.client.post(f"{api.base}/save", json=save_body(api), headers=api.headers)
    row = api.world.db.scalars(select(KnowledgeUnit)).first()
    assert row is not None and row.saved_learning_day is not None
    assert (row.saved_learning_day.day == 31) is same_day
    assert not unit_review.in_review(row.saved_learning_day, row.saved_learning_day)


def test_save_with_a_context_naming_a_foreign_document_skips_the_range(api: Api) -> None:
    put_context(
        api,
        [{"document_id": "0" * 8 + "-0000-4000-8000-" + "0" * 12, "first_page": 1, "last_page": 2}],
    )
    api.client.post(f"{api.base}/save", json=save_body(api), headers=api.headers)
    assert count(api.world.db, SessionRange) == 0
