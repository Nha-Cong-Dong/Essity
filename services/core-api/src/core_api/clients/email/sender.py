from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str  # plain text only: no HTML, no tracking pixels


class EmailSender(Protocol):
    """Where email goes: SMTP (Mailpit locally, a transactional provider in production, T1.15)."""

    def send(self, message: EmailMessage) -> None: ...


@dataclass
class InMemoryEmailSender:
    """For tests: keeps every message instead of sending it."""

    sent: list[EmailMessage] = field(default_factory=lambda: [])

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
