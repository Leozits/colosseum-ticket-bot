"""Colosseum-specific WhatsApp/email message wording.

Sending itself (WhatsApp via CallMeBot, email via SMTP) lives in
monitor_common.notifier, shared by every ticket monitor in this repo.
"""


def format_availability_message(dates, slots_by_date, ticket_url):
    lines = []
    for date in dates:
        available_times = sorted(
            t for t, status in slots_by_date.get(date, {}).items() if status == "available"
        )
        if available_times:
            lines.append(f"- {date}: {', '.join(available_times)}")
        else:
            lines.append(f"- {date}")
    return "O calendário do Coliseu abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"
