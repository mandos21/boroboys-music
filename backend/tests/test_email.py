from __future__ import annotations

import smtplib

import pytest

from app.core.config import Settings
from app.services import email


class FakeSMTP:
    instances: list[FakeSMTP] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.sent_message = None
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: object) -> None:
        self.sent_message = message


@pytest.fixture(autouse=True)
def _reset_fake_smtp() -> None:
    FakeSMTP.instances = []


def test_send_email_uses_tls_and_login_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="user",
        smtp_password="secret",
        smtp_from_address="rounds@example.com",
        smtp_use_tls=True,
    )

    email.send_email(settings, "member@example.com", "Subject", "Body")

    assert len(FakeSMTP.instances) == 1
    client = FakeSMTP.instances[0]
    assert client.host == "smtp.example.com"
    assert client.started_tls is True
    assert client.login_args == ("user", "secret")
    assert client.sent_message["To"] == "member@example.com"
    assert client.sent_message["From"] == "rounds@example.com"
    assert client.sent_message["Subject"] == "Subject"


def test_send_email_skips_login_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_from_address="rounds@example.com",
        smtp_use_tls=False,
    )

    email.send_email(settings, "member@example.com", "Subject", "Body")

    client = FakeSMTP.instances[0]
    assert client.started_tls is False
    assert client.login_args is None


def test_send_email_requires_smtp_configuration() -> None:
    with pytest.raises(email.EmailError):
        email.send_email(Settings(smtp_host=None), "member@example.com", "Subject", "Body")


def test_send_email_wraps_smtp_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class ExplodingSMTP(FakeSMTP):
        def send_message(self, message: object) -> None:
            raise smtplib.SMTPException("rejected")

    monkeypatch.setattr(email.smtplib, "SMTP", ExplodingSMTP)
    settings = Settings(smtp_host="smtp.example.com", smtp_from_address="rounds@example.com")

    with pytest.raises(email.EmailError):
        email.send_email(settings, "member@example.com", "Subject", "Body")
