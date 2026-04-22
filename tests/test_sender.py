import sys

import pytest  # type: ignore

from agents import sender as sender_module
from agents.sender import NewsletterTestSender


@pytest.fixture(autouse=True)
def disable_real_dotenv(monkeypatch):
    monkeypatch.setattr(sender_module, "load_dotenv", lambda: None)


def clear_smtp_env(monkeypatch):
    for name in [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_FROM",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_USE_TLS",
        "NEWSLETTER_TEST_RECIPIENT",
        "NEWSLETTER_RECIPIENTS",
        "NEWSLETTER_TEST_SUBJECT",
    ]:
        monkeypatch.delenv(name, raising=False)


def set_minimal_smtp_env(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "brief@example.com")
    monkeypatch.setenv("NEWSLETTER_TEST_RECIPIENT", "reader@example.com")


def write_html(tmp_path):
    html_path = tmp_path / "data" / "formatted" / "2026-04-22.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text("<html><body><h1>Brief</h1></body></html>", encoding="utf-8")
    return html_path


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.sent_message = None
        self.sent_messages = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent_message = message
        self.sent_messages.append(message)


def test_sender_sends_html_message(tmp_path, monkeypatch):
    clear_smtp_env(monkeypatch)
    set_minimal_smtp_env(monkeypatch)
    html_path = write_html(tmp_path)
    FakeSMTP.instances = []
    monkeypatch.setattr(sender_module.smtplib, "SMTP", FakeSMTP)

    recipients = NewsletterTestSender(str(html_path)).run()

    smtp = FakeSMTP.instances[0]
    assert recipients == ["reader@example.com"]
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.timeout == 30
    assert smtp.started_tls is True
    assert smtp.login_args is None
    assert smtp.sent_message["Subject"] == "Nigerian Politics Brief test - 2026-04-22"
    assert smtp.sent_message["From"] == "brief@example.com"
    assert smtp.sent_message["To"] == "reader@example.com"
    assert "<h1>Brief</h1>" in smtp.sent_message.get_body(preferencelist=("html",)).get_content()


def test_sender_loads_dotenv_before_reading_config(tmp_path, monkeypatch):
    clear_smtp_env(monkeypatch)
    html_path = write_html(tmp_path)
    FakeSMTP.instances = []
    monkeypatch.setattr(sender_module.smtplib, "SMTP", FakeSMTP)

    def fake_load_dotenv():
        monkeypatch.setenv("SMTP_HOST", "smtp.env.example.com")
        monkeypatch.setenv("SMTP_FROM", "env-brief@example.com")
        monkeypatch.setenv("NEWSLETTER_TEST_RECIPIENT", "env-reader@example.com")

    monkeypatch.setattr(sender_module, "load_dotenv", fake_load_dotenv)

    recipients = NewsletterTestSender(str(html_path)).run()

    smtp = FakeSMTP.instances[0]
    assert recipients == ["env-reader@example.com"]
    assert smtp.host == "smtp.env.example.com"
    assert smtp.sent_message["From"] == "env-brief@example.com"
    assert smtp.sent_message["To"] == "env-reader@example.com"


def test_sender_uses_optional_auth_and_custom_port(tmp_path, monkeypatch):
    clear_smtp_env(monkeypatch)
    set_minimal_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USERNAME", "api-user")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    html_path = write_html(tmp_path)
    FakeSMTP.instances = []
    monkeypatch.setattr(sender_module.smtplib, "SMTP", FakeSMTP)

    NewsletterTestSender(str(html_path)).run()

    smtp = FakeSMTP.instances[0]
    assert smtp.port == 2525
    assert smtp.started_tls is False
    assert smtp.login_args == ("api-user", "secret")


def test_sender_missing_env_raises_clear_error(tmp_path, monkeypatch):
    clear_smtp_env(monkeypatch)
    html_path = write_html(tmp_path)

    with pytest.raises(ValueError, match="SMTP_HOST, SMTP_FROM"):
        NewsletterTestSender(str(html_path)).run()


def test_sender_missing_html_raises_file_not_found(tmp_path, monkeypatch):
    clear_smtp_env(monkeypatch)
    set_minimal_smtp_env(monkeypatch)

    with pytest.raises(FileNotFoundError, match="missing.html"):
        NewsletterTestSender(str(tmp_path / "missing.html")).run()


def test_sender_requires_complete_auth_pair(tmp_path, monkeypatch):
    clear_smtp_env(monkeypatch)
    set_minimal_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_USERNAME", "api-user")
    html_path = write_html(tmp_path)
    FakeSMTP.instances = []
    monkeypatch.setattr(sender_module.smtplib, "SMTP", FakeSMTP)

    with pytest.raises(ValueError, match="SMTP_USERNAME and SMTP_PASSWORD"):
        NewsletterTestSender(str(html_path)).run()


def test_production_send_requires_confirmation(tmp_path, monkeypatch):
    clear_smtp_env(monkeypatch)
    set_minimal_smtp_env(monkeypatch)
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "subscriber@example.com")
    html_path = write_html(tmp_path)

    with pytest.raises(ValueError, match="--confirm-production"):
        NewsletterTestSender(str(html_path), production=True).run()


def test_production_send_requires_recipients(tmp_path, monkeypatch):
    clear_smtp_env(monkeypatch)
    set_minimal_smtp_env(monkeypatch)
    html_path = write_html(tmp_path)

    with pytest.raises(ValueError, match="NEWSLETTER_RECIPIENTS"):
        NewsletterTestSender(str(html_path), production=True, confirm_production=True).run()


def test_production_send_sends_one_private_email_per_recipient(tmp_path, monkeypatch):
    clear_smtp_env(monkeypatch)
    set_minimal_smtp_env(monkeypatch)
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", " first@example.com, second@example.com ,, third@example.com ")
    html_path = write_html(tmp_path)
    FakeSMTP.instances = []
    monkeypatch.setattr(sender_module.smtplib, "SMTP", FakeSMTP)

    recipients = NewsletterTestSender(str(html_path), production=True, confirm_production=True).run()

    smtp = FakeSMTP.instances[0]
    sent_messages = smtp.sent_messages
    assert recipients == ["first@example.com", "second@example.com", "third@example.com"]
    assert [message["To"] for message in sent_messages] == recipients
    assert [message["Subject"] for message in sent_messages] == ["Nigerian Politics Brief - 2026-04-22"] * 3
    assert all("Bcc" not in message for message in sent_messages)
    assert all("first@example.com, second@example.com" not in message.as_string() for message in sent_messages)


def test_main_prints_production_count(tmp_path, monkeypatch, capsys):
    clear_smtp_env(monkeypatch)
    set_minimal_smtp_env(monkeypatch)
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "first@example.com,second@example.com")
    html_path = write_html(tmp_path)
    FakeSMTP.instances = []
    monkeypatch.setattr(sender_module.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(sys, "argv", ["sender", str(html_path), "--production", "--confirm-production"])

    sender_module.main()

    assert "Production newsletter sent to 2 recipients." in capsys.readouterr().out


def test_main_prints_test_recipient(tmp_path, monkeypatch, capsys):
    clear_smtp_env(monkeypatch)
    set_minimal_smtp_env(monkeypatch)
    html_path = write_html(tmp_path)
    FakeSMTP.instances = []
    monkeypatch.setattr(sender_module.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(sys, "argv", ["sender", str(html_path)])

    sender_module.main()

    assert "Test newsletter sent to: reader@example.com" in capsys.readouterr().out
