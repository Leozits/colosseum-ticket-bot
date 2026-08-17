"""Generic senders for WhatsApp (CallMeBot) and email, shared by every ticket monitor.

CallMeBot's free tier confirms "Message queued" even on messages that never
actually get delivered, so email is kept as a backup channel rather than a
straight replacement.
"""

import smtplib
from email.message import EmailMessage

import requests

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


def send_whatsapp_message(phone, api_key, text):
    response = requests.get(
        CALLMEBOT_URL,
        params={"phone": phone, "text": text, "apikey": api_key},
        timeout=15,
    )
    response.raise_for_status()
    if "Message queued" not in response.text:
        raise RuntimeError(f"CallMeBot did not confirm the message: {response.text!r}")


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
