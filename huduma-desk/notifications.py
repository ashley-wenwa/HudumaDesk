"""Email notifications. Sends through SMTP when MAIL_SERVER is set, otherwise logs the message."""
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("huduma.mail")


def send_status_update(to_email, name, request_id, category, status, note):
    """Tell a citizen their request changed. Never raises: a mail failure must not break the admin action."""
    lines = [f"Hello {name},", "",
             f"Your {category.lower()} request (#{request_id}) is now: {status}."]
    if note:
        lines += ["", f"Note from the team: {note}"]
    body = "\n".join(lines)
    subject = f"Request #{request_id} is now {status}"

    host = os.environ.get("MAIL_SERVER")
    if not host:
        log.info("MAIL_SERVER not set, email not sent. To: %s | %s\n%s", to_email, subject, body)
        return False

    message = EmailMessage()
    message["From"] = os.environ.get("MAIL_FROM", "no-reply@huduma.local")
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.environ.get("MAIL_PORT", "587")), timeout=10) as smtp:
            smtp.starttls()
            if os.environ.get("MAIL_USERNAME"):
                smtp.login(os.environ["MAIL_USERNAME"], os.environ.get("MAIL_PASSWORD", ""))
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        log.exception("Could not send status email to %s", to_email)
        return False
