"""Pure functions for diffing day-status snapshots between runs, shared by every ticket monitor."""


def find_status_changes(previous, current):
    """Return every date whose status differs from its previous recorded status."""
    changes = []
    for date_str, status in current.items():
        prev_status = previous.get(date_str)
        if prev_status != status:
            changes.append({"date": date_str, "from": prev_status, "to": status})
    return changes


def find_newly_available(previous, current):
    """Return dates that just became "available" (weren't before, or weren't tracked)."""
    return [
        date_str
        for date_str, status in current.items()
        if status == "available" and previous.get(date_str) != "available"
    ]
