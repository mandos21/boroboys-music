"""Plain-text email delivery for reminders and publication notices.

Sending is synchronous SMTP from inside a Procrastinate task, never on the
request path. An unconfigured deployment is expected, not an error: every
caller checks `Settings.smtp_is_configured` first and skips quietly.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import Settings

LOGGER = logging.getLogger(__name__)


class EmailError(Exception):
    pass


def send_email(settings: Settings, to_address: str, subject: str, body: str) -> None:
    if settings.smtp_host is None or settings.smtp_from_address is None:
        raise EmailError("SMTP is not configured")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_address
    message["To"] = to_address
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15.0) as client:
            if settings.smtp_use_tls:
                client.starttls()
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            client.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        raise EmailError(f"could not send email to {to_address}") from error
