"""Regression test: the student verification email is actually sent.

Run: python tests/test_student_verification_email.py   (or pytest)

send_verification_email() used MIMEMultipart, MIMEText and smtplib without
importing them. Its `except Exception` turned the NameError into
`return False`, so no verification email could go out even with SMTP set up.

smtplib.SMTP is replaced by a recorder and the host is a .invalid name:
nothing leaves the machine.
"""
import email
import os
import smtplib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402


class FakeSMTP:
    """Records what would have been sent."""
    sent = []

    def __init__(self, host, port):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def sendmail(self, from_addr, to_addrs, msg):
        FakeSMTP.sent.append((from_addr, to_addrs, msg))


def test_verification_email_goes_to_the_student_with_the_token_link():
    saved = (smtplib.SMTP, main.SMTP_HOST, main.SMTP_USER, main.SMTP_PASS, main.SMTP_FROM)
    smtplib.SMTP = FakeSMTP
    main.SMTP_HOST, main.SMTP_USER, main.SMTP_PASS, main.SMTP_FROM = (
        "smtp.invalid", "user", "pass", "noreply@example.com")
    FakeSMTP.sent.clear()
    try:
        ok = main.send_verification_email("student@example.edu", "tok-123", "https://app.example.com")
    finally:
        smtplib.SMTP, main.SMTP_HOST, main.SMTP_USER, main.SMTP_PASS, main.SMTP_FROM = saved

    assert ok is True, "send_verification_email returned False"
    assert len(FakeSMTP.sent) == 1, FakeSMTP.sent
    from_addr, to_addrs, raw = FakeSMTP.sent[0]
    assert to_addrs == "student@example.edu", to_addrs
    msg = email.message_from_string(raw)
    assert msg["To"] == "student@example.edu", msg["To"]
    html = next(p for p in msg.walk() if p.get_content_type() == "text/html")
    body = html.get_payload(decode=True).decode(html.get_content_charset())
    assert "https://app.example.com/verify-student?token=tok-123" in body, body[:300]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", str(e)[:160])
    sys.exit(1 if failed else 0)
