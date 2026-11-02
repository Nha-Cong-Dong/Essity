"""T8.5 tester edges (US-06 AC5 "làm và làm lại", US-16 AC10/AC11): in a mixed review session the
card schedule (`review_log`, `memory_state`) and the practice schedule (`practice_log`,
`practice_state`) never move each other, through grading, "Chấm lại" (regrade) and "Chấm sai"
(override), and neither route family accepts the other's attempt or grade. The practice question
here is linked to the very unit of the card in the session, so a write to the wrong schedule
would land on a row the assertions watch."""

import uuid
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from test_t28_today_api import today
from test_t85_mixed_session import OVERDUE, World, ai, world  # noqa: F401 - fixtures

from clock import FROZEN_NOW
from core_api.clients.ai_client import NotGraded
from core_api.db.models import Grade, MemoryState, PracticeState, Question, Subject, UnitRevision
from core_api.domain.learning_day import day_bounds, learning_day
from core_api.repositories.question import QuestionUnitRepository
from practice_bench import Bench, schedule

_ = (ai, world)


def shared_unit_world(world: World) -> tuple[uuid.UUID, uuid.UUID, Question]:
    """A due card and a due practice question linked to the same unit."""
    q = world.practice()
    unit_id, card = world.space.question(q.subject_id, "TCP")
    world.space.scheduled(unit_id, due_in_days=-1)
    card_question = card.id
    QuestionUnitRepository(world.session, world.user.id).link(q.id, unit_id)
    world.session.flush()
    return unit_id, card_question, q


def open_card(world: World, sid: str) -> str:
    assert world.current(sid)["question"]["kind"] == "card"
    made = world.client.post(f"/v1/review-sessions/{sid}/attempts", headers=world.headers)
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def submit_card(world: World, attempt_id: str) -> dict[str, Any]:
    sent = world.client.post(
        f"/v1/attempts/{attempt_id}/submit",
        json={"answer_text": "x", "dont_remember": False},
        headers=world.headers,
    )
    assert sent.status_code == 200, sent.text
    return dict(sent.json())


def answer_practice(world: World, question_id: uuid.UUID) -> dict[str, Any]:
    opened = world.client.post(f"/v1/practice/questions/{question_id}/open", headers=world.headers)
    assert opened.status_code == 200, opened.text
    sent = world.client.post(
        f"/v1/practice/attempts/{opened.json()['attempt_id']}/submit",
        json={"answer_text": "SYN, SYN-ACK, ACK", "dont_remember": False},
        headers=world.headers,
    )
    assert sent.status_code == 200, sent.text
    return dict(sent.json())


def newest_grade(world: World, attempt_id: str) -> str:
    world.session.expire_all()
    grade = world.session.scalars(
        select(Grade).where(Grade.attempt_id == uuid.UUID(attempt_id)).order_by(Grade.seq.desc())
    ).first()
    assert grade is not None
    return str(grade.id)


def practice_rows(tables: dict[str, list[tuple[Any, ...]]]) -> tuple[Any, Any]:
    return tables["practice_log"], tables["practice_state"]


def card_rows(tables: dict[str, list[tuple[Any, ...]]]) -> tuple[Any, Any]:
    return tables["review_log"], tables["memory_state"]


def test_card_regrade_and_override_in_mixed_session_leave_practice(world: World, ai: Any) -> None:
    # US-06 AC5, US-16 AC11 (T4). Red when: "Chấm lại" or "Chấm sai" of the card writes
    # practice_log or rebuilds practice_state of a practice question on the same unit.
    _, _, p = shared_unit_world(world)
    sid = world.start()["id"]
    answer_practice(world, p.id)  # riskier: first
    practice_before = practice_rows(world.tables())
    assert practice_before[0] != []  # the practice answer was graded and logged

    ai.cards.failure = NotGraded("invalid", "grade_invalid")  # not queued (T2.13)
    attempt = open_card(world, sid)
    failed = submit_card(world, attempt)
    assert failed["grading"] == "failed"
    assert world.current(sid)["ungraded"] == [attempt]
    ai.cards.failure = None
    cards_before = card_rows(world.tables())
    again = world.client.post(f"/v1/attempts/{attempt}/regrade", headers=world.headers)
    assert again.status_code == 200 and again.json()["grading"] == "graded", again.text
    after_regrade = world.tables()
    assert card_rows(after_regrade) != cards_before  # the card schedule moved
    assert practice_rows(after_regrade) == practice_before

    overridden = world.client.post(
        f"/v1/grades/{newest_grade(world, attempt)}/override",
        json={"verdict": "incorrect"},
        headers=world.headers,
    )
    assert overridden.status_code == 200, overridden.text
    after_override = world.tables()
    assert card_rows(after_override) != card_rows(after_regrade)
    assert practice_rows(after_override) == practice_before
    assert world.current(sid)["ungraded"] == []


def test_practice_regrade_and_override_in_mixed_session_leave_cards(world: World, ai: Any) -> None:
    # US-06 AC5, US-16 AC10/AC11 (T4). Red when: "Chấm lại" or "Chấm sai" of the practice question
    # writes review_log or rebuilds memory_state of the card unit it is linked to; or a pending
    # practice answer shows as a review "chấm lại" (`ungraded`), which would lead to a 404 route.
    _, _, p = shared_unit_world(world)
    sid = world.start()["id"]
    ai.verdicts = NotGraded("quota", "quota_hard_cap")
    pending = answer_practice(world, p.id)
    assert pending["grading"] == "pending"
    now = world.current(sid)
    assert now["ungraded"] == [] and now["position"] == 2  # submitted counts as answered
    attempt = open_card(world, sid)
    submit_card(world, attempt)
    cards_before = card_rows(world.tables())
    assert cards_before[0] != []

    ai.verdicts = ["correct", "correct"]
    practice_attempt = pending["attempt_id"]
    again = world.client.post(
        f"/v1/practice/attempts/{practice_attempt}/regrade", headers=world.headers
    )
    assert again.status_code == 200 and again.json()["grading"] == "graded", again.text
    after_regrade = world.tables()
    assert practice_rows(after_regrade)[0] != []
    assert card_rows(after_regrade) == cards_before

    overridden = world.client.post(
        f"/v1/practice/grades/{again.json()['result']['grade_id']}/override",
        json={"verdict": "incorrect"},
        headers=world.headers,
    )
    assert overridden.status_code == 200, overridden.text
    after_override = world.tables()
    assert practice_rows(after_override) != practice_rows(after_regrade)
    assert card_rows(after_override) == cards_before
    assert world.current(sid)["done"] is True


def test_each_route_family_refuses_the_other_schedules_attempt_and_grade(world: World) -> None:
    # US-16 AC11. Red when: a card grade can be overridden through /v1/practice (or the reverse),
    # or a regrade route grades the other kind's attempt; any of them moves a table.
    _, _, p = shared_unit_world(world)
    sid = world.start()["id"]
    practice = answer_practice(world, p.id)
    card_attempt = open_card(world, sid)
    submit_card(world, card_attempt)
    card_grade = newest_grade(world, card_attempt)
    practice_grade = practice["result"]["grade_id"]
    before = world.tables()
    calls = [
        world.client.post(
            f"/v1/practice/grades/{card_grade}/override",
            json={"verdict": "incorrect"},
            headers=world.headers,
        ),
        world.client.post(
            f"/v1/grades/{practice_grade}/override",
            json={"verdict": "incorrect"},
            headers=world.headers,
        ),
        world.client.post(f"/v1/practice/attempts/{card_attempt}/regrade", headers=world.headers),
        world.client.post(f"/v1/attempts/{practice['attempt_id']}/regrade", headers=world.headers),
    ]
    assert [c.status_code for c in calls] == [404] * 4, [c.text for c in calls]
    assert world.tables() == before


def test_an_opened_but_unsent_practice_attempt_does_not_answer_the_step(world: World) -> None:
    # Session steps count a practice question answered only by a submitted attempt. Red when:
    # the `status == "submitted"` filter of `session_steps` is dropped (a draft would skip it).
    world.card()
    p = world.practice()
    sid = world.start()["id"]
    opened = world.client.post(f"/v1/practice/questions/{p.id}/open", headers=world.headers)
    assert opened.status_code == 200, opened.text
    now = world.current(sid)
    assert (now["position"], now["total"]) == (1, 2)
    assert now["question"]["id"] == str(p.id)
    shown = today(world.client, world.headers)["in_progress"]
    assert shown is not None and shown["position"] == 1


def test_a_removed_practice_question_never_sets_next_day(world: World) -> None:
    # Red when: `stop` or `/v1/today` take the due date of a question taken out of practice as
    # the next review day (the `not c.removed` filters).
    _, card_question = world.card()
    q = world.bench.ready()
    schedule(world.session, world.user, q, FROZEN_NOW + timedelta(days=1), removed=FROZEN_NOW)
    sid = world.start()["id"]
    attempt = open_card(world, sid)
    submit_card(world, attempt)
    stopped = world.client.post(f"/v1/review-sessions/{sid}/stop", headers=world.headers)
    assert stopped.status_code == 200, stopped.text
    tomorrow = (FROZEN_NOW + timedelta(days=1)).date()
    world.session.expire_all()
    tz = ZoneInfo(world.user.timezone)
    card_days = {
        learning_day(row.due, tz, world.user.day_start_hour)
        for row in world.session.scalars(select(MemoryState))
    }
    assert stopped.json()["next_day"] == str(min(card_days))
    assert tomorrow not in card_days  # so a wrong answer would differ
    assert card_question is not None


def test_only_a_removed_practice_question_left_gives_no_next_day(world: World) -> None:
    # Red when: compose_mixed's next_day (nothing due today) counts a removed practice question.
    q = world.bench.ready()
    schedule(world.session, world.user, q, FROZEN_NOW + timedelta(days=2), removed=FROZEN_NOW)
    body = today(world.client, world.headers)
    assert body["session"] is None and body["next_day"] is None
    assert body["practice"] is None  # attempted once: never back in Luyện tập either
    state = world.session.scalars(select(PracticeState)).one()
    assert state.removed_at is not None and OVERDUE < state.due


def test_a_question_due_exactly_at_the_learning_day_end_waits_for_tomorrow(world: World) -> None:
    # US-06 AC9 (ranh ngày học: `due < end`, as the cards and `PracticeStateRepository.due_on`).
    # Red when: compose_mixed counts a question due exactly at the end of today as due today.
    tz = ZoneInfo(world.user.timezone)
    day = learning_day(FROZEN_NOW, tz, world.user.day_start_hour)
    end = day_bounds(day, tz, world.user.day_start_hour)[1]
    at_end, before_end = world.bench.ready(), world.bench.ready()
    schedule(world.session, world.user, at_end, end)
    schedule(world.session, world.user, before_end, end - timedelta(microseconds=1))
    items = today(world.client, world.headers)["review"]["items"]
    assert [i["question_id"] for i in items] == [str(before_end.id)]


def test_a_kept_generated_question_is_a_practice_step_too(world: World) -> None:
    # US-06 AC8: bank and kept generated questions are both practice. Red when: `is_practice`
    # treats only `bank` as practice, so a generated question in the session is shown as a card
    # (kind "card", unit ids to skip) and graded through the review attempt route.
    world.card()
    q = world.bench.ready(source="generated", run_id=uuid.uuid4(), kept_at=FROZEN_NOW)
    schedule(world.session, world.user, q, OVERDUE)
    sid = world.start()["id"]
    assert world.current(sid)["total"] == 2
    now = world.current(sid)
    if now["question"]["id"] != str(q.id):  # the card came first: answer it to reach q
        attempt = open_card(world, sid)
        submit_card(world, attempt)
        now = world.current(sid)
    assert now["question"]["id"] == str(q.id)
    assert now["question"]["kind"] == "practice" and now["question"]["unit_ids"] == []
    refused = world.client.post(f"/v1/review-sessions/{sid}/attempts", headers=world.headers)
    assert refused.status_code == 409 and refused.json()["detail"] == "practice_question"


def test_today_next_day_comes_from_the_practice_schedule_too(world: World) -> None:
    # US-03 (nothing due today: the next day). Red when: `/v1/today` answers the cards' next day
    # only, so a user whose only schedule is a practice question sees no next day.
    q = world.bench.ready()
    later = FROZEN_NOW + timedelta(days=3)
    schedule(world.session, world.user, q, later)
    tz = ZoneInfo(world.user.timezone)
    body = today(world.client, world.headers)
    assert body["session"] is None
    assert body["next_day"] == str(learning_day(later, tz, world.user.day_start_hour))


def test_stop_of_a_practice_only_session_gives_the_practice_next_day(world: World) -> None:
    # Red when: `stop` leaves the practice schedule out of `next_day` (null after a session of
    # practice questions only, though the questions are scheduled for a later day).
    q = world.practice()
    sid = world.start()["id"]
    answer_practice(world, q.id)
    stopped = world.client.post(f"/v1/review-sessions/{sid}/stop", headers=world.headers)
    assert stopped.status_code == 200, stopped.text
    world.session.expire_all()
    state = world.session.scalars(select(PracticeState)).one()
    tz = ZoneInfo(world.user.timezone)
    expected = learning_day(state.due, tz, world.user.day_start_hour)
    assert expected > learning_day(FROZEN_NOW, tz, world.user.day_start_hour)
    assert stopped.json()["next_day"] == str(expected)


def test_practice_lines_are_in_subject_name_order(world: World) -> None:
    # Review T5 (stable Luyện tập lines). Red when: the lines follow the query's row order (here
    # the creation order), so the part reorders between two loads of Today.
    late = Bench(
        world.session, world.user, world.session.get(Subject, world.space.subject("Xác suất"))
    )
    early = Bench(
        world.session, world.user, world.session.get(Subject, world.space.subject("Giải tích"))
    )
    for bench in (late, early, late):
        bench.ready()
    lines = today(world.client, world.headers)["practice"]["lines"]
    assert [(ln["subject_name"], ln["ready_questions"]) for ln in lines] == [
        ("Giải tích", 1),
        ("Xác suất", 2),
    ]


def test_a_due_practice_question_never_enqueues_a_lazy_job_for_its_card(world: World) -> None:
    # T7.11 lazy job (US-02b AC11) is for the cards of today's review only. Red when: Today hands
    # the practice entries to `enqueue_lazy_questions`, so a due practice question linked to a card
    # whose review question is stale (and not due today) queues a regeneration of that card.
    from test_t711_api import _jobs, canonical  # pyright: ignore[reportPrivateUsage]

    unit_id, card_question = world.space.question(world.bench.subject.id, "TCP")
    canonical(world.session, unit_id)
    card_question.source, card_question.unit_rev = "review_auto", 1
    for rev in range(3):  # newest revision 2 > 1: the card's question is stale
        world.session.add(
            UnitRevision(user_id=world.user.id, unit_id=unit_id, rev=rev, origin="ai", content={})
        )
    world.space.scheduled(unit_id, due_in_days=9)  # the card is not in today's review
    q = world.bench.ready()
    schedule(world.session, world.user, q, OVERDUE)
    QuestionUnitRepository(world.session, world.user.id).link(q.id, unit_id)
    world.session.flush()
    items = today(world.client, world.headers)["review"]["items"]
    assert [(i["question_id"], i["item_kind"]) for i in items] == [(str(q.id), "practice")]
    assert _jobs(world.session, unit_id) == []
