"""Site-specific WhatsApp/email message wording for the Louvre monitor."""


def format_availability_message(dates, ticket_url):
    lines = [f"- {date}" for date in dates]
    return "O calendário do Louvre abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"


def format_failure_message(consecutive_failures, error_message):
    return (
        f"O monitor do Louvre falhou {consecutive_failures} vezes seguidas.\n"
        f"Último erro: {error_message}"
    )
