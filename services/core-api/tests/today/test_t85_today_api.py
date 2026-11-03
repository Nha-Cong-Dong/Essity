"""T8.5 (US-03 AC4, US-06 AC8; plan commit 4): `GET /v1/today` carries the practice questions due
in `review` and the ready never-attempted ones in `practice`; fields are only added."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_t28_today_api import Space, today

from accounts import signed_in
from clock import FROZEN_NOW
from practice_bench import Bench, schedule
from v2_rows import make_subject, make_type

V1_KEYS = {
    "learning_day",
    "state",
    "session",
    "in_progress",
    "backlog",
    "next_day",
    "subjects",
    "unfinished",
    "next_study",
    "review",
}
OVERDUE = FROZEN_NOW - timedelta(days=3)


def test_t711_fields_unchanged_and_enums_closed(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit_id, _ = space.question(space.subject())
    space.scheduled(unit_id, due_in_days=-1)
    bench = Bench(db_session, user)
    schedule(db_session, user, bench.ready(), OVERDUE)
    body: dict[str, Any] = today(client, headers)
    assert V1_KEYS <= set(body) and "practice" in body
    assert set(body["review"]) == {"items", "minutes", "next_due_day", "new_saved_today"}
    for item in body["review"]["items"]:
        assert set(item) == {
            "question_id",
            "subject_id",
            "why",
            "reason",
            "item_kind",
            "front",
            "back",
        }
        assert item["reason"]["kind"] in {"review", "new"}
    assert {i["item_kind"] for i in body["review"]["items"]} == {"card", "practice"}


def test_due_practice_is_in_review_and_session_counts_it(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    bench = Bench(db_session, user)
    due = bench.ready()
    schedule(db_session, user, due, OVERDUE)
    body = today(client, headers)
    assert body["state"] == "ready"  # a day with only practice questions due is still a day
    assert [i["question_id"] for i in body["review"]["items"]] == [str(due.id)]
    assert body["review"]["items"][0]["item_kind"] == "practice"
    assert body["session"]["question_count"] == 1
    assert body["session"]["minutes"] == body["review"]["minutes"] > 0
    assert body["practice"] is None  # nothing never attempted: the due one is not listed twice


def test_practice_part_lists_only_never_attempted_ready_questions(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    bench = Bench(db_session, user)
    kind = make_type(db_session, user, bench.subject)
    bench.ready(type_id=kind.id)
    bench.ready()
    schedule(db_session, user, bench.ready(), OVERDUE)
    bench.question()  # unlinked: in neither place
    body = today(client, headers)
    (line,) = body["practice"]["lines"]
    assert line["subject_id"] == str(bench.subject.id)
    assert line["subject_name"] == bench.subject.name
    assert line["ready_questions"] == 2
    assert line["question_types"] == 2  # the typed one and the untyped ones
    assert len(body["review"]["items"]) == 1


def test_only_never_attempted_questions_state_is_not_no_questions(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    Bench(db_session, user).ready()
    body = today(client, headers)
    assert body["state"] == "rested" and body["review"]["items"] == []
    assert body["practice"]["lines"][0]["ready_questions"] == 1


def test_no_backlog_total_in_payload(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    bench = Bench(db_session, user)
    for _ in range(40):
        schedule(db_session, user, bench.ready(), OVERDUE)
    body = today(client, headers)
    assert len(body["review"]["items"]) <= 20
    assert body["backlog"] is None  # practice questions cut by the cap are not counted anywhere
    assert set(body["session"]) == {"question_count", "minutes", "subjects"}
    assert body["session"]["question_count"] <= 20 and "backlog" not in body["review"]


def test_unverified_account_is_refused(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session, verified=False)
    assert client.get("/v1/today", headers=headers).status_code == 403


def test_today_runs_the_same_queries_for_few_or_many_practice_questions(
    client: TestClient, db_session: Session
) -> None:
    from test_t28_timing import statements_per_request

    small_user, small = signed_in(db_session)
    one = Bench(db_session, small_user)
    schedule(db_session, small_user, one.ready(), OVERDUE)
    large_user, large = signed_in(db_session)
    for _ in range(3):  # three subjects, many questions: still the same statements
        bench = Bench(db_session, large_user, make_subject(db_session, large_user, f"M{_}"))
        for _ in range(15):
            schedule(db_session, large_user, bench.ready(), OVERDUE)
        bench.ready()
    assert statements_per_request(client, db_session, small) == statements_per_request(
        client, db_session, large
    )


def test_t85_f2_practice_kept_but_not_due_is_rested(
    client: TestClient, db_session: Session
) -> None:
    """T8.5 F2: only practice questions, attempted and not due today: rested, not no_questions."""
    user, headers = signed_in(db_session)
    bench = Bench(db_session, user)
    schedule(db_session, user, bench.ready(), FROZEN_NOW + timedelta(days=5))
    body = today(client, headers)
    assert body["state"] == "rested" and body["review"]["items"] == []


def test_t85_f2_removed_practice_is_still_no_questions(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    bench = Bench(db_session, user)
    schedule(db_session, user, bench.ready(), FROZEN_NOW + timedelta(days=5), removed=FROZEN_NOW)
    assert today(client, headers)["state"] == "no_questions"
