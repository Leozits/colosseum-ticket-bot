"""Pure functions for computing ticket availability from the site's calendar API response."""


def parse_slots(response_json):
    """Validate and extract the slot list from a calendars_month API response.

    Raises ValueError if the response doesn't have the expected shape.
    """
    if not isinstance(response_json, dict) or response_json.get("success") is not True:
        raise ValueError(f"Unexpected calendar response shape: {response_json!r}")
    data = response_json.get("data")
    if not isinstance(data, list):
        raise ValueError(f"Unexpected calendar response shape: {response_json!r}")
    return data


def capacity_by_date(slots, target_dates):
    """Sum remaining capacity per date, for the given list of target date strings (YYYY-MM-DD).

    Dates in target_dates with no matching slots are included with capacity 0.
    """
    totals = {date_str: 0 for date_str in target_dates}
    for slot in slots:
        slot_date = slot["startDateTime"][:10]
        if slot_date in totals:
            totals[slot_date] += slot["capacity"]
    return totals


def find_newly_available(previous, current):
    """Return the dates that went from 0 (or unknown) capacity to >0 capacity."""
    newly_available = []
    for date_str, capacity in current.items():
        if capacity > 0 and previous.get(date_str, 0) == 0:
            newly_available.append(date_str)
    return newly_available
