"""T1.4: background jobs. Runs on the real test PostgreSQL, with real commits and workers.

Jobs must be committed for a worker to see them, so these tests do not use `db_session`; the
`clean_jobs` fixture empties the job tables around each test instead.
"""

import io
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.db.session import DbSession
from core_api.jobs.app import MAX_ATTEMPTS, libpq_conninfo
from core_api.jobs.handler import UnknownJobKind, job_handler
from core_api.jobs.queue import enqueue_job
from core_api.jobs.worker import run, run_workers
from core_api.logging import configure_logging
from core_api.telemetry import configure_tracing

EMAIL = "someone@example.com"

_lock = threading.Lock()
handled: list[dict[str, Any]] = []
failed: list[dict[str, Any]] = []


@job_handler("test_record")
def record(payload: dict[str, Any]) -> None:
    with _lock:
        handled.append(payload)


@job_handler("test_slow_record")
def slow_record(payload: dict[str, Any]) -> None:
    time.sleep(0.01)  # long enough for the two workers to overlap
    record(payload)


@job_handler("test_fail")
def fail(payload: dict[str, Any]) -> None:
    with _lock:
        failed.append(payload)
    raise RuntimeError(f"cannot reach {payload['email']}")  # the message must not be logged


@pytest.fixture(autouse=True)
def clean_jobs(engine: Engine) -> Iterator[None]:
    def clean() -> None:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM procrastinate_jobs"))
            connection.execute(text("DELETE FROM procrastinate_workers"))
        handled.clear()
        failed.clear()

    clean()
    yield
    clean()


@pytest.fixture
def work(test_database_url: str) -> Callable[..., None]:
    """Run workers until no job is due, then return."""
    conninfo = libpq_conninfo(test_database_url)

    def work(count: int = 1) -> None:
        run(
            run_workers(
                conninfo, count, wait=False, install_signal_handlers=False, listen_notify=False
            )
        )

    return work


def enqueue_committed(engine: Engine, kind: str, payload: dict[str, Any]) -> None:
    with Session(engine) as session:
        enqueue_job(session, kind, payload)
        session.commit()


def jobs(engine: Engine) -> list[dict[str, Any]]:
    """Every job, with `due_in` = seconds from now until it may run."""
    query = text(
        "SELECT id, task_name, status::text, attempts, args, "
        "extract(epoch FROM scheduled_at - now())::float AS due_in "
        "FROM procrastinate_jobs ORDER BY id"
    )
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


# --- Enqueueing ------------------------------------------------------------------------------


def test_job_exists_only_once_the_transaction_commits(engine: Engine) -> None:
    with Session(engine) as session:
        enqueue_job(session, "test_record", {"n": 1})
        assert jobs(engine) == []  # written in the session's transaction, not beside it
        session.commit()
    [job] = jobs(engine)
    assert (job["task_name"], job["status"], job["args"]) == (
        "test_record",
        "todo",
        {"payload": {"n": 1}},
    )


def test_route_that_fails_after_enqueueing_leaves_no_job(engine: Engine) -> None:
    app = FastAPI()

    @app.post("/ok")
    def ok(session: DbSession) -> None:
        enqueue_job(session, "test_record", {"route": "ok"})

    @app.post("/fail")
    def fail_route(session: DbSession) -> None:
        enqueue_job(session, "test_record", {"route": "fail"})
        raise HTTPException(status_code=409)

    client = TestClient(app)
    assert client.post("/fail").status_code == 409
    assert jobs(engine) == []
    assert client.post("/ok").status_code == 200
    assert [job["args"] for job in jobs(engine)] == [{"payload": {"route": "ok"}}]


def test_unknown_kind_is_refused_at_enqueue_time(engine: Engine) -> None:
    with Session(engine) as session, pytest.raises(UnknownJobKind):
        enqueue_job(session, "no_such_job", {})


def test_payload_must_be_json(engine: Engine) -> None:
    with Session(engine) as session, pytest.raises(TypeError):
        enqueue_job(session, "test_record", {"when": object()})


def test_a_kind_cannot_be_registered_twice() -> None:
    with pytest.raises(ValueError, match="already registered"):
        job_handler("test_record")(record)


# --- Running ---------------------------------------------------------------------------------


def test_worker_runs_the_handler_once_with_the_payload(
    engine: Engine, work: Callable[..., None]
) -> None:
    payload = {"email": EMAIL, "count": 2, "tags": ["a", "b"], "nested": {"ok": True}}
    enqueue_committed(engine, "test_record", payload)
    work()
    assert handled == [payload]
    assert [job["status"] for job in jobs(engine)] == ["succeeded"]


def test_failing_job_is_retried_with_growing_delays_then_kept_as_failed(
    engine: Engine, work: Callable[..., None]
) -> None:
    enqueue_committed(engine, "test_fail", {"email": EMAIL})
    delays: list[float] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        work()
        assert len(failed) == attempt
        [job] = jobs(engine)
        if attempt < MAX_ATTEMPTS:
            assert job["status"] == "todo"
            delays.append(job["due_in"])
            with engine.begin() as connection:  # fast-forward to the retry
                connection.execute(text("UPDATE procrastinate_jobs SET scheduled_at = now()"))
    assert delays == pytest.approx([10, 30, 90, 270], abs=3)
    assert delays == sorted(delays)
    [job] = jobs(engine)
    assert (job["status"], job["attempts"]) == ("failed", MAX_ATTEMPTS)
    work()
    assert len(failed) == MAX_ATTEMPTS  # no sixth attempt


def test_two_workers_handle_each_job_exactly_once(
    engine: Engine, work: Callable[..., None]
) -> None:
    count = 40
    with Session(engine) as session:
        for n in range(count):
            enqueue_job(session, "test_slow_record", {"n": n})
        session.commit()
    work(count=2)
    assert sorted(payload["n"] for payload in handled) == list(range(count))
    assert {job["status"] for job in jobs(engine)} == {"succeeded"}


# --- Logging ---------------------------------------------------------------------------------


@pytest.fixture
def log_output() -> Iterator[Callable[[], str]]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("core-worker", "DEBUG", stream=buffer)
    configure_tracing("core-worker")  # as worker.main does; a no-op if already installed
    yield buffer.getvalue
    root.handlers, root.level = saved


def test_payload_never_reaches_the_logs(
    engine: Engine, work: Callable[..., None], log_output: Callable[[], str]
) -> None:
    enqueue_committed(engine, "test_record", {"email": EMAIL})
    enqueue_committed(engine, "test_fail", {"email": EMAIL})
    work()
    assert handled == [{"email": EMAIL}]
    assert len(failed) == 1

    output = log_output()
    assert EMAIL not in output
    assert "someone" not in output
    lines = [json.loads(line) for line in output.splitlines()]
    assert any(line["logger"].startswith("procrastinate") for line in lines)  # were checked
    done = next(line for line in lines if line["message"] == "job done")
    assert done["job_kind"] == "test_record"
    assert done["outcome"] == "success"
    assert done["attempt"] == 1
    assert isinstance(done["job_id"], int)
    assert done["duration_ms"] >= 0
    error = next(line for line in lines if line["message"] == "job failed")
    assert (error["job_kind"], error["outcome"], error["error_type"]) == (
        "test_fail",
        "error",
        "RuntimeError",
    )
    assert "trace_id" in error
