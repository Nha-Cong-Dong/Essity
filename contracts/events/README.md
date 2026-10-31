# Event contracts

JSON Schemas (draft 2020-12) for the events `core-api` and `ai-service` exchange over Redis Streams
(ADR-0006, ARCHITECTURE §7.3).

## Files

- `envelope.schema.json`: the fields every event carries: `event_id`, `event_type`,
  `schema_version` (1), `occurred_at` (UTC, ends in `Z`), `user_id`, `trace_context` (W3C
  `traceparent`/`tracestate`, empty object when there was no span) and `payload`.
- `<event>.v1.schema.json`: one per event. References the envelope, fixes `event_type` and closes
  `payload`.
- `examples/<event>.v1.json`: a valid event. `examples/<event>.v1.invalid-<reason>.json`: one the
  schema must reject.

Every object is closed (`additionalProperties: false`). Payloads carry identifiers and object keys
only (claim-check): never an answer, a note, a description, a secret or the material the AI works
from. The one exception is `session.confirmed.v1`, which lists the subject's existing units
(`unit_id`, `title`, `summary`) so `ai-service` can merge duplicates without calling back.

Each service keeps its own models and checks them against these files in its tests. Nothing here
is imported by code (ADR-0003). A breaking change is a new `v2` schema, run side by side until
every consumer has moved.

## On the wire

| Stream | Written by | Read by (consumer group) | Events |
|---|---|---|---|
| `events.core` | `core-relay` (from the `outbox` table) | `ai-service` | `document.uploaded`, `session.confirmed`, `submission.created`, `grade.requested`, `user.deleted` |
| `events.ai` | `ai-service` | `core-api` | `document.indexed`, `document.failed`, `session.progress`, `session.processed`, `session.failed`, `submission.processed`, `submission.failed`, `grade.completed` |
| `events.dead` | consumers, after the last failed delivery | people, by hand | any |

- Each stream entry has exactly one field, `envelope`, whose value is the event as JSON text.
- `events.core` and `events.ai` are trimmed with `MAXLEN ~ 100000`. `events.dead` is never trimmed.
- Delivery is at least once: consumers record `event_id` and skip an event they have already
  handled. Order is not guaranteed.
- An entry in `events.dead` has the fields `envelope` (the original text), `stream`, `entry_id`
  (its id in that stream), `reason` and `deliveries`. Never an exception message. `envelope` is
  empty when the entry had no such field. `reason` is one of:
  - `invalid_envelope`: not text, not JSON, or not an event of the contract;
  - `unknown_type`: well-formed, but its `event_type` is not in the contract;
  - `no_handler`: a known type this consumer has no handler for yet (replayable once there is one);
  - `user_mismatch`: an object key in the payload is not under `users/<user_id>/` of the envelope
    (F2);
  - `max_deliveries`: delivered more than 5 times without a recorded failure (its handling kills
    the consumer, or its acknowledgement keeps failing) and not found in `processed_event`;
  - otherwise the class name of the exception the handler raised on its 5th delivery.

## Delivery semantics

- A handler that fails leaves its entry pending; it is delivered again after a backoff (5, 15, 45,
  then 60 s: `XCLAIM IDLE` set to `60 s - backoff`, never below 0) and goes to `events.dead` on
  its 5th delivery.
- A handler may raise `Deferred` (`ai-service`) to put its event back for later without counting a
  failure: the consumer `XCLAIM`s the entry with `RETRYCOUNT` set to the count before this
  delivery, so it never reaches the dead letter by waiting.
- A lost connection (Redis `ConnectionError`/`TimeoutError`, a database connection invalidated, or
  SQLSTATE empty, class `08`, or `57P01`-`57P03`) is handled the same way, not counted as a failed
  delivery. A statement timeout, a deadlock, a full disk or a row too large is an ordinary failure.
- Before an entry is dead-lettered for too many deliveries, `processed_event` is checked: an
  event already handled is only acknowledged. If that check itself fails for a reason other than
  a lost connection, the entry goes to `events.dead` as `max_deliveries`.
- Logs, spans and `reason` carry ids, counts and exception class names only; a round that fails
  logs the class name, not the traceback (an SQLAlchemy error holds the statement and its
  parameters).
- `python -m core_api.messaging.dead_letter purge --user <uuid>` (core-api) and
  `python -m ai_service.messaging.dead_letter purge --user <uuid>` (ai-service) delete every
  `events.dead` entry that mentions the user, in any case and anywhere in the envelope (T6.3).

## Derived files

`../files/` holds the schemas of files ai-service writes to object storage and core-api reads:
`toc.v1.schema.json` (`toc.json`, T4.9). Same rules as above: closed objects, an example and
`invalid-*` examples; each service checks its side in its tests (writer: ai-service, reader:
core-api).
