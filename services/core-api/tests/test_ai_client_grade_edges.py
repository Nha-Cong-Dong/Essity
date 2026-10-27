"""T2.13 retry table edges found by mutating the code (tester, 26/10)."""

import httpx2
import pytest

from core_api.clients.ai_client import NotGraded
from test_ai_client_grade import PAYLOAD, client_answering


# Plan 🟠2 ("413; 422 → invalid, no retry"). Red when: a 413 or 422 without one of ai-service's
# codes (a proxy's body limit, FastAPI's own validation list) is read as "unavailable": the
# screen would offer "Chấm lại" for a request that can never pass.
@pytest.mark.parametrize(
    "answer",
    [
        httpx2.Response(413, text="Request Entity Too Large"),
        httpx2.Response(422, json={"detail": [{"loc": ["body"], "msg": "x"}]}),
    ],
)
def test_t213_a_bare_413_or_422_is_invalid_without_retry(answer: httpx2.Response) -> None:
    client, seen = client_answering(answer)
    outcome = client.grade(PAYLOAD)
    assert isinstance(outcome, NotGraded)
    assert (len(seen), outcome.failure) == (1, "invalid")
