"""Send monitor notifications via WhatsApp (CallMeBot)."""

import requests

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


def format_availability_message(dates, ticket_url):
    lines = [f"- {date}" for date in dates]
    return "O calendário do Coliseu abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"


def format_failure_message(consecutive_failures, error_message):
    return (
        f"O monitor do Coliseu falhou {consecutive_failures} vezes seguidas.\n"
        f"Último erro: {error_message}"
    )


def send_whatsapp_message(phone, api_key, text):
    response = requests.get(
        CALLMEBOT_URL,
        params={"phone": phone, "text": text, "apikey": api_key},
        timeout=15,
    )
    response.raise_for_status()
    if "Message queued" not in response.text:
        raise RuntimeError(f"CallMeBot did not confirm the message: {response.text!r}")
