"""Site-specific WhatsApp/email message wording for the Louvre monitor."""


def format_availability_message(dates, ticket_url):
    lines = [f"- {date}" for date in dates]
    return "O calendário do Louvre abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"
