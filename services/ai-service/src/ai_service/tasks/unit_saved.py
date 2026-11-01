"""`unit.saved.v1` (T7.8b, US-02b AC9): core saved a card.

This task only receives it. The work that follows a Save, review questions (T7.9) and edge
proposals (T9.9), adds its own step here; until then the event is acknowledged on purpose, with
one log line of ids, so it never reaches the dead letter stream. Nothing is read or written.
"""

import logging

from sqlalchemy.orm import Session

from ai_service.messaging.envelope import Event, UnitSavedEvent

_log = logging.getLogger("ai_service.tasks")


class OnUnitSaved:
    def __call__(self, session: Session, event: Event) -> None:
        if not isinstance(event, UnitSavedEvent):
            raise TypeError("OnUnitSaved handles unit.saved.v1 only")
        _log.info(
            "unit saved received",
            extra={
                "event_id": str(event.event_id),
                "unit_id": str(event.payload.unit_id),
                "unit_rev": event.payload.unit_rev,
            },
        )
