"""Send monitor notifications to a Discord channel via webhook."""

import requests


def format_availability_message(dates, capacities, ticket_url):
    lines = [f"- {date}: {capacities[date]} vagas" for date in dates]
    return "🎟️ Disponibilidade aberta no Coliseu!\n" + "\n".join(lines) + f"\n{ticket_url}"


def format_failure_message(consecutive_failures, error_message):
    return (
        f"⚠️ O monitor do Coliseu falhou {consecutive_failures} vezes seguidas.\n"
        f"Último erro: {error_message}"
    )


def send_discord_message(webhook_url, content):
    response = requests.post(webhook_url, json={"content": content}, timeout=10)
    response.raise_for_status()
