"""Delivery of payment reminders over SMTP (Mailpit in dev).

Uses the stdlib ``smtplib``/``email`` so core needs no extra dependency. SMTP
failures are logged but never raised - the audit trail is the source of truth
and a reminder that fails to send must not 500 the request that generated it.

Empty ``host`` selects a log-only transport (dev/test default), matching the
ai-agent and identity email blocks.
"""

from __future__ import annotations

import asyncio
import smtplib
import structlog
from email.message import EmailMessage

from core.core.config import settings
from core.domain.entities import ReminderDraft

logger = structlog.get_logger("core.finance.reminder_email")

DEFAULT_TO = "reminders@skyrict.dev"


async def send_reminder_email(*, reminder: ReminderDraft) -> None:
    """Deliver a drafted reminder to the configured SMTP relay (Mailpit).

    The invoice has no customer email on the finance side (customers live in
    CRM and only names are exposed), so the recipient is a fixed dev address.
    """
    host = getattr(settings, "EMAIL_SMTP_HOST", "").strip()
    if not host:
        logger.info(
            "reminder_email.log_only",
            invoice=reminder.invoice_number,
            to=DEFAULT_TO,
            subject=reminder.subject,
        )
        return

    message = EmailMessage()
    message["From"] = getattr(settings, "EMAIL_FROM_ADDR", "Skyrict <no-reply@skyrict.dev>")
    message["To"] = DEFAULT_TO
    message["Subject"] = reminder.subject
    message.set_content(reminder.body)

    def _blocking() -> None:
        with smtplib.SMTP(host, settings.EMAIL_SMTP_PORT, timeout=10) as client:
            client.ehlo()
            client.send_message(message)

    try:
        await asyncio.to_thread(_blocking)
    except (OSError, smtplib.SMTPException) as exc:
        logger.exception(
            "reminder_email.delivery_failed",
            invoice=reminder.invoice_number,
            smtp_host=host,
            smtp_port=settings.EMAIL_SMTP_PORT,
            error=str(exc),
        )
        return
    logger.info("reminder_email.delivered", invoice=reminder.invoice_number, to=DEFAULT_TO)
