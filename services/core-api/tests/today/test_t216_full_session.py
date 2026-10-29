"""T2.16 "Xong khi": a whole review session at the routes, with the fake grader (local and test
store it as practice, R41 layer 2), on the material `seed-demo` gives (plan D-10). The screen's
path: current, open, a draft, submit (one "Không nhớ"), and so on to done, then stop."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.cli import run
from core_api.db.models import ReviewLog
from grader_stub import Stub


# Red when: one step of the session breaks (a draft, a submit, a grade, the end), a grade is not
# shown as practice, or the session does not end as completed with every answer graded.
def test_t216_a_whole_session_with_the_fake_grader(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    stub.provider = "fake"
    user, headers = signed_in(db_session)
    assert run(db_session, ["seed-demo", "--user-email", user.email], environment="test") == 0
    started = client.post("/v1/review-sessions", json={}, headers=headers)
    assert started.status_code == 201, started.text
    session_id = started.json()["id"]
    total = started.json()["total"]
    assert total == 2  # the demo's level-2 question waits for a Correct at level 1 (T5.2)

    for position in range(1, total + 1):
        current = client.get(f"/v1/review-sessions/{session_id}/current", headers=headers).json()
        assert (current["done"], current["position"], current["total"]) == (False, position, total)
        assert current["ungraded"] == []
        attempt = client.post(f"/v1/review-sessions/{session_id}/attempts", headers=headers)
        attempt_id = attempt.json()["id"]
        forgot = position == 2
        body = {"answer_text": "" if forgot else "Một câu trả lời", "dont_remember": False}
        saved = client.put(f"/v1/attempts/{attempt_id}/draft", json=body, headers=headers)
        assert saved.status_code == 204
        body["dont_remember"] = forgot
        graded = client.post(f"/v1/attempts/{attempt_id}/submit", json=body, headers=headers).json()
        assert (graded["status"], graded["grading"]) == ("submitted", "graded")
        result = graded["result"]
        assert result["reference_answer"] and result["sources"]
        if forgot:
            assert result["overall"] == "forgot" and result["practice"] is False  # system grade
        else:
            assert result["practice"] is True

    done = client.get(f"/v1/review-sessions/{session_id}/current", headers=headers).json()
    assert done == {"done": True, "ungraded": []}
    stopped = client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers).json()
    assert (stopped["answered"], stopped["total"], stopped["correct"]) == (2, 2, 1)
    logs = db_session.scalar(
        select(func.count()).select_from(ReviewLog).where(ReviewLog.user_id == user.id)
    )
    assert logs == 2  # one per unit of each answered question; the level-2 one waits (T5.2)
    assert len(stub.calls) == 1  # "Không nhớ" never calls the AI (US-04 AC2)
