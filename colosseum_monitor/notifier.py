"""Send monitor notifications by email via SMTP (Discord is blocked on this network)."""

import smtplib
from email.message import EmailMessage


def format_availability_message(dates, ticket_url):
    lines = [f"- {date}" for date in dates]
    return "O calendário do Coliseu abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"


def format_failure_message(consecutive_failures, error_message):
    return (
        f"O monitor do Coliseu falhou {consecutive_failures} vezes seguidas.\n"
        f"Último erro: {error_message}"
    )


def send_email_message(smtp_host, smtp_port, username, password, to_address, subject, body):
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = username
    message["To"] = to_address
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)
