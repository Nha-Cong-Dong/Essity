"""T8.5 tester (review T3, US-03 AC2): `GET /v1/today` stays under 300 ms with ~500 questions now
that the practice questions are read too: 250 scheduled cards plus 250 ready bank questions, half
of them due on their own practice schedule. Rows go in by bulk insert, as `test_t28_timing`."""

import os
import statistics
import time
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, text
from sqlalchemy.orm import Session
from test_t28_timing import analyze, bulk_subject, statements_per_request

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import PracticeState, Question, QuestionSection
from practice_bench import Bench

pytestmark = [pytest.mark.timing, pytest.mark.usefixtures("analyze_allowed")]


def bulk_practice(session: Session, bench: Bench, count: int) -> None:
    """`count` ready bank questions on one studied section; every second one scheduled, due."""
    section = bench.section("Chương 1")
    bench.card(section)
    user, subject = bench.user, bench.subject
    ids = [uuid.uuid4() for _ in range(count)]
    session.execute(
        insert(Question),
        [
            {
                "id": q,
                "user_id": user.id,
                "subject_id": subject.id,
                "level": 1,
                "prompt": f"Câu luyện tập {n}?",
                "reference_answer": "Đáp án",
                "status": "active",
                "content_hash": uuid.uuid4().hex * 2,
                "run_id": None,
                "source": "bank",
                "bank_document_id": bench.bank.id,
                "bank_ord": n + 1,
            }
            for n, q in enumerate(ids)
        ],
    )
    session.execute(
        insert(QuestionSection),
        [
            {
                "id": uuid.uuid4(),
                "user_id": user.id,
                "subject_id": subject.id,
                "question_id": q,
                "section_id": section.id,
            }
            for q in ids
        ],
    )
    session.execute(
        insert(PracticeState),
        [
            {
                "id": uuid.uuid4(),
                "user_id": user.id,
                "question_id": q,
                "phase": "review",
                "step": None,
                "stability": 10.0,
                "difficulty": 5.0,
                "due": FROZEN_NOW - timedelta(days=1),
                "last_review": FROZEN_NOW - timedelta(days=11),
            }
            for q in ids[::2]
        ],
    )
    session.flush()
    session.execute(text("ANALYZE practice_state, question_section, doc_section, unit_section"))


# US-03 AC2 (review T3). Red when: the practice reads go one question or one subject at a time
# (N+1), or `ready_ids` / `practice_candidates` scan without an index at this size.
def test_us03_ac2_today_with_250_cards_and_250_practice_under_300ms(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    bulk_subject(db_session, user, "Mạng máy tính", 250, scheduled=True)
    bulk_practice(db_session, Bench(db_session, user), 250)
    analyze(db_session)
    body = client.get("/v1/today", headers=headers)  # warm up
    assert body.status_code == 200
    kinds = {i["item_kind"] for i in body.json()["review"]["items"]}
    assert kinds == {"card", "practice"}  # both kinds really read and mixed
    assert body.json()["practice"]["lines"][0]["ready_questions"] == 125
    # The real guard, independent of machine load: the queries do not grow with the account.
    small_user, small = signed_in(db_session)
    bulk_subject(db_session, small_user, "Mạng nhỏ", 10, scheduled=True)
    bulk_practice(db_session, Bench(db_session, small_user), 10)
    assert statements_per_request(client, db_session, headers) == statements_per_request(
        client, db_session, small
    )
    timings: list[float] = []
    for _ in range(7):
        started = time.perf_counter()
        response = client.get("/v1/today", headers=headers)
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200
    best = min(timings)  # fastest of seven, as test_t28_timing
    print(
        f"GET /v1/today with 250 cards + 250 practice: best {best * 1000:.0f} ms, "
        f"median {statistics.median(timings) * 1000:.0f} ms"
    )
    # Wall clock: 300 ms where the machine is quiet (CI); a loose 1.5 s elsewhere, where a lane
    # shares a low-RAM box with other test runs. The statement count above catches N+1.
    assert best < (0.3 if os.environ.get("CI") else 1.5)
