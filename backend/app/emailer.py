"""
Sending emails.

Like storage.py for photos, this is the ONLY file that knows HOW emails are sent.
The rest of the app just calls send_email(...).

  EMAIL_BACKEND=console  (default, your laptop)
      Prints the email in the Terminal where the server runs. Nothing is really sent,
      so you can test with fake addresses like rahul@test.com.

  EMAIL_BACKEND=brevo  (the live site)
      Really sends, through Brevo's free plan. Needs BREVO_API_KEY, and EMAIL_FROM must be
      a sender you've verified in Brevo (your Gmail works - no website domain needed).
"""
import logging
import re
from dataclasses import dataclass

import httpx

from .config import BREVO_API_KEY, EMAIL_BACKEND, EMAIL_FROM

log = logging.getLogger("uvicorn.error")  # shows up in the same Terminal as the server logs


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str


# The console backend also keeps the last emails in memory so the tests can read the codes.
OUTBOX: list[SentEmail] = []


def send_email(to: str, subject: str, body: str) -> None:
    if EMAIL_BACKEND == "console":
        OUTBOX.append(SentEmail(to, subject, body))
        del OUTBOX[:-50]  # keep only the last 50
        log.info(
            "\n" + "=" * 60 + f"\nEMAIL (not really sent - console mode)\nFrom: {EMAIL_FROM}\nTo: {to}\n"
            f"Subject: {subject}\n\n{body}\n" + "=" * 60
        )
        return
    if EMAIL_BACKEND == "brevo":
        _send_brevo(to, subject, body)
        return
    raise RuntimeError(f"Unknown EMAIL_BACKEND: {EMAIL_BACKEND!r}")


def _parse_from(value: str) -> dict:
    """'Book Exchange <me@gmail.com>' -> {'name': 'Book Exchange', 'email': 'me@gmail.com'}"""
    m = re.match(r"\s*(.*?)\s*<([^>]+)>\s*$", value)
    return {"name": m.group(1) or "Book Exchange", "email": m.group(2)} if m else {"email": value.strip()}


def _send_brevo(to: str, subject: str, body: str) -> None:
    if not BREVO_API_KEY:
        raise RuntimeError("EMAIL_BACKEND=brevo but BREVO_API_KEY is not set.")
    r = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": BREVO_API_KEY, "accept": "application/json"},
        json={
            "sender": _parse_from(EMAIL_FROM),
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        },
        timeout=15,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"Brevo refused the email ({r.status_code}): {r.text[:300]}")


# ---------- the actual emails ----------
def send_verification_code(to: str, name: str, code: str, minutes: int) -> None:
    send_email(
        to,
        f"{code} is your Book Exchange verification code",
        f"Hi {name},\n\nYour verification code is: {code}\n\n"
        f"It expires in {minutes} minutes. If you didn't sign up, you can ignore this email.\n\n"
        "We will never ask you to share this code with anyone.",
    )


def send_reset_code(to: str, name: str, code: str, minutes: int) -> None:
    send_email(
        to,
        f"{code} is your Book Exchange password reset code",
        f"Hi {name},\n\nSomeone (hopefully you) asked to reset your password.\n"
        f"Your reset code is: {code}\n\nIt expires in {minutes} minutes. "
        "If this wasn't you, ignore this email - your password stays the same.\n\n"
        "We will never ask you to share this code with anyone.",
    )
