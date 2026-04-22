import argparse
import datetime
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv  # type: ignore


class NewsletterTestSender:
    """Send a rendered newsletter HTML file through an SMTP provider."""

    REQUIRED_ENV = [
        "SMTP_HOST",
        "SMTP_FROM",
    ]

    def __init__(self, html_path: Optional[str] = None, production: bool = False, confirm_production: bool = False):
        load_dotenv()

        today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        self.html_path = Path(html_path or f"data/formatted/{today_str}.html")
        self.production = production
        self.confirm_production = confirm_production

    def run(self) -> List[str]:
        self._validate_env()
        if not self.html_path.exists():
            raise FileNotFoundError(f"Input file not found: {self.html_path}")

        html = self.html_path.read_text(encoding="utf-8")
        date_label = self.html_path.stem
        recipients = self._recipients()
        messages = [self._build_message(html, date_label, recipient) for recipient in recipients]
        self._send(messages)
        return recipients

    def _validate_env(self) -> None:
        missing = [name for name in self.REQUIRED_ENV if not os.environ.get(name)]
        if missing:
            raise ValueError(f"Missing required SMTP environment variables: {', '.join(missing)}")

        if self.production and not self.confirm_production:
            raise ValueError("Production sends require --confirm-production.")

        port = os.environ.get("SMTP_PORT", "587")
        try:
            int(port)
        except ValueError as e:
            raise ValueError("SMTP_PORT must be an integer") from e

        self._recipients()

    def _recipients(self) -> List[str]:
        if self.production:
            raw_recipients = os.environ.get("NEWSLETTER_RECIPIENTS", "")
            recipients = [email.strip() for email in raw_recipients.split(",") if email.strip()]
            if not recipients:
                raise ValueError("NEWSLETTER_RECIPIENTS must include at least one recipient for production sends")
            return recipients

        recipient = os.environ.get("NEWSLETTER_TEST_RECIPIENT")
        if not recipient:
            raise ValueError("Missing required SMTP environment variables: NEWSLETTER_TEST_RECIPIENT")
        return [recipient]

    def _build_message(self, html: str, date_label: str, recipient: str) -> EmailMessage:
        sender = os.environ["SMTP_FROM"]
        default_subject = f"Nigerian Politics Brief - {date_label}" if self.production else f"Nigerian Politics Brief test - {date_label}"
        subject = os.environ.get("NEWSLETTER_TEST_SUBJECT", default_subject)

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipient
        message.set_content("This is a test send of the Nigerian Politics Brief. View in HTML mode.")
        message.add_alternative(html, subtype="html")
        return message

    def _send(self, messages: List[EmailMessage]) -> None:
        host = os.environ["SMTP_HOST"]
        port = int(os.environ.get("SMTP_PORT", "587"))
        username = os.environ.get("SMTP_USERNAME")
        password = os.environ.get("SMTP_PASSWORD")
        use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() not in {"0", "false", "no"}

        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if username or password:
                if not username or not password:
                    raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must both be set when using auth")
                smtp.login(username, password)
            for message in messages:
                smtp.send_message(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a rendered newsletter HTML file as a test email.")
    parser.add_argument(
        "html_path",
        nargs="?",
        help="Path to data/formatted/YYYY-MM-DD.html. Defaults to today's UTC output.",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Send to NEWSLETTER_RECIPIENTS instead of NEWSLETTER_TEST_RECIPIENT.",
    )
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Required with --production to confirm a real subscriber send.",
    )
    args = parser.parse_args()

    recipients = NewsletterTestSender(args.html_path, args.production, args.confirm_production).run()
    if args.production:
        print(f"Production newsletter sent to {len(recipients)} recipients.")
    else:
        print(f"Test newsletter sent to: {recipients[0]}")


if __name__ == "__main__":
    main()
