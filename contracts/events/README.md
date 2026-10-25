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
| `events.core` | `core-relay` (from the `outbox` table) | `ai-service` | `document.uploaded`, `session.confirmed`, `grade.requested`, `user.deleted` |
| `events.ai` | `ai-service` | `core-api` | `document.indexed`, `document.failed`, `session.progress`, `session.processed`, `session.failed`, `grade.completed` |
| `events.dead` | consumers, after the last failed delivery | people, by hand | any |

- Each stream entry has exactly one field, `envelope`, whose value is the event as JSON text.
- `events.core` and `events.ai` are trimmed with `MAXLEN ~ 100000`. `events.dead` is never trimmed.
- Delivery is at least once: consumers record `event_id` and skip an event they have already
  handled. Order is not guaranteed.
- An entry in `events.dead` has the fields `envelope` (the original text), `stream`, `entry_id`
  (its id in that stream), `reason` (exception class name, `invalid_envelope`, `unknown_type`, or
  `max_deliveries` when deliveries died with their consumer) and `deliveries`. Never an exception
  message. `envelope` is empty when the entry had no such field.
