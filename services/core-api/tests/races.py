"""Helpers for tests that race two real connections: run one side in a thread, wait until it
waits on a row lock, then let the other side commit."""

import threading
import time
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

SECONDS_TO_WAIT = 5.0


def in_thread(work: Callable[[], object]) -> tuple[threading.Thread, list[object]]:
    """Run `work` in a thread; its result or its exception lands in the returned list."""
    outcome: list[object] = []

    def run() -> None:
        try:
            outcome.append(work())
        except BaseException as error:  # noqa: BLE001 - handed back to the test thread
            outcome.append(error)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcome


def wait_for_lock(engine: Engine, pid: int, outcome: list[object]) -> None:
    """Until backend `pid` waits on a lock. Fail if it never does, or if the thread behind it
    finished first (with the result or the error it finished with)."""
    deadline = time.monotonic() + SECONDS_TO_WAIT
    with engine.connect() as watcher:
        while time.monotonic() < deadline:
            if outcome:
                pytest.fail(f"backend {pid} finished before waiting on a lock: {outcome!r}")
            waiting = watcher.execute(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"), {"pid": pid}
            ).scalar_one_or_none()
            if waiting == "Lock":
                return
            watcher.rollback()
            time.sleep(0.05)
    pytest.fail(f"backend {pid} never waited on a lock")


def finished(thread: threading.Thread, outcome: list[object]) -> object:
    """The thread's one result or error, once it is done."""
    thread.join(SECONDS_TO_WAIT * 3)
    assert not thread.is_alive(), "the thread is still waiting"
    [result] = outcome
    return result
