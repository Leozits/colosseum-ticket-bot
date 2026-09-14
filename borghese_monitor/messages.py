"""Site-specific email message wording for the Galleria Borghese monitor."""


def format_availability_message(dates, ticket_url):
    lines = [f"- {date}" for date in dates]
    return "O calendário da Galleria Borghese abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"
