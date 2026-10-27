"""T2.13 retry deadline edge found by mutating the code (tester round 2, 28/10)."""

import httpx2

from core_api.clients.ai_client import GRADE_MIN_RETRY_SECONDS, GRADE_TOTAL_SECONDS, Graded
from test_ai_client_grade import OK, PAYLOAD, TIMEOUT, client_answering


# Plan 🟡7 ("còn dưới 3 s thì bỏ retry"). Red when: the retry is skipped with exactly 3 s left
# (`<=` instead of `<`), so an answer that would come in time is reported "unavailable".
def test_t213_retry_still_runs_with_exactly_three_seconds_left() -> None:
    times = iter([0.0, GRADE_TOTAL_SECONDS - GRADE_MIN_RETRY_SECONDS]).__next__
    client, seen = client_answering(TIMEOUT, httpx2.Response(200, json=OK))
    assert isinstance(client.grade(PAYLOAD, clock=times), Graded)
    assert len(seen) == 2
    assert seen[1].extensions["timeout"]["read"] == GRADE_MIN_RETRY_SECONDS
