import logging
import smtplib
import ssl
from email.message import EmailMessage as MimeMessage

from core_api.clients.email.sender import EmailMessage
from core_api.config import Settings

_log = logging.getLogger("core_api.email")


class SmtpEmailSender:
    """Sends over SMTP. Locally that is Mailpit (no TLS, no login), web UI on :8025."""

    def __init__(
        self,
        host: str,
        port: int,
        from_address: str,
        *,
        username: str | None = None,
        password: str | None = None,
        starttls: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.from_address = from_address
        self.username = username
        self.password = password
        self.starttls = starttls
        self.timeout = timeout

    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self.from_address
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text, charset="utf-8")
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
            if self.starttls:
                # A verifying context: smtplib's default checks neither the certificate nor the
                # host name (review f617e23). Port 465 (TLS from the start) is not supported.
                smtp.starttls(context=ssl.create_default_context())
            if self.username is not None and self.password is not None:
                smtp.login(self.username, self.password)
            smtp.send_message(mime)
        # `email` is masked by the log formatter; the body (links with tokens) is never logged.
        _log.info("email sent", extra={"email": message.to})


def smtp_sender_from_settings(settings: Settings) -> SmtpEmailSender:
    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        from_address=settings.email_from,
        username=settings.smtp_username,
        password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
        starttls=settings.smtp_starttls,
    )
