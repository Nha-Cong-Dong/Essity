"""`@job_handler`: declare the function that runs one kind of job."""

import logging
import time
from collections.abc import Callable
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import StatusCode
from procrastinate import JobContext

from core_api.jobs.app import RETRY, app

Payload = dict[str, Any]
Handler = Callable[[Payload], None]

_handlers: dict[str, Handler] = {}
_periodic: set[str] = set()
_log = logging.getLogger("core_api.jobs")
_tracer = trace.get_tracer("core_api.jobs")


class UnknownJobKind(LookupError):
    """No handler is registered for this kind of job."""


def job_handler(kind: str) -> Callable[[Handler], Handler]:
    """Register the decorated function to run jobs of `kind` in the worker.

    The handler is synchronous and receives the payload given to `enqueue_job`, as a dict.

    Delivery is at least once: the same job can run twice, for instance when the worker stops
    after the handler has finished but before the job was marked done, or when a shutdown
    releases a job whose handler then completes anyway. Make handlers idempotent, or make a
    repeat harmless.

    A handler that raises is retried after 10 s, 30 s, 90 s and 270 s (five attempts in all,
    see `app.RETRY`); after the last one the job stays in the table as `failed`. Neither the
    payload nor the exception message is logged.
    """

    def register(handler: Handler) -> Handler:
        if kind in _handlers:
            raise ValueError(f"job kind {kind!r} is already registered")

        def run(context: JobContext, payload: Payload) -> None:
            _run(kind, handler, context, payload)

        app.task(name=kind, pass_context=True, retry=RETRY)(run)
        _handlers[kind] = handler
        return handler

    return register


def periodic_job(kind: str, cron: str) -> Callable[[Handler], Handler]:
    """Run the decorated function on a schedule (`cron`, UTC), like a `job_handler` job.

    It receives an empty payload. Procrastinate defers one job per scheduled time, even with
    several workers, and only for a time missed by less than 10 minutes, so a worker that was
    down does not catch up on a backlog. The kind is not enqueueable: `enqueue_job` refuses it.
    """

    def register(handler: Handler) -> Handler:
        if kind in _handlers or kind in _periodic:
            raise ValueError(f"job kind {kind!r} is already registered")

        def run(context: JobContext, timestamp: int) -> None:
            _run(kind, handler, context, {})

        task = app.task(name=kind, pass_context=True, retry=RETRY)(run)
        app.periodic(cron=cron, periodic_id=kind)(task)
        _periodic.add(kind)
        return handler

    return register


def check_kind(kind: str) -> None:
    if kind not in _handlers:
        raise UnknownJobKind(kind)


def _run(kind: str, handler: Handler, context: JobContext, payload: Payload) -> None:
    job = context.job
    fields: dict[str, Any] = {"job_kind": kind, "job_id": job.id, "attempt": job.attempts + 1}
    # No automatic exception recording: its event and status carry the exception message.
    with _tracer.start_as_current_span(
        f"job {kind}",
        attributes={"job.kind": kind, "job.id": job.id or 0, "job.attempt": fields["attempt"]},
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        started = time.perf_counter()
        try:
            handler(payload)
        except Exception as exc:
            span.set_status(StatusCode.ERROR)
            span.set_attribute("error.type", type(exc).__name__)
            _log.exception(
                "job failed", extra={**fields, "outcome": "error", "duration_ms": _ms(started)}
            )
            raise
        _log.info("job done", extra={**fields, "outcome": "success", "duration_ms": _ms(started)})


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
