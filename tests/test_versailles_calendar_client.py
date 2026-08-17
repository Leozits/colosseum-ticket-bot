from unittest.mock import patch, Mock
from versailles_monitor.calendar_client import fetch_month_html, parse_month_days


def test_parse_month_days_maps_open_to_available_and_others_to_unavailable():
    html = (
        '<div id="agenda--calendar--date-2026-10-14" class="agenda--calendar-slot open theme--jardins_musicaux">'
        '<span>14</span></div>'
        '<div id="agenda--calendar--date-2026-10-19" class="agenda--calendar-slot closed">'
        '<span>19</span></div>'
        '<div id="agenda--calendar--date-2026-09-01" class="agenda--calendar-slot disabled">'
        '<span>01</span></div>'
    )
    assert parse_month_days(html) == {
        "2026-10-14": "available",
        "2026-10-19": "unavailable",
        "2026-09-01": "unavailable",
    }


def test_parse_month_days_returns_empty_dict_for_no_matches():
    assert parse_month_days("<div>nothing here</div>") == {}


@patch("versailles_monitor.calendar_client.httpx.post")
def test_fetch_month_html_posts_month_and_year_and_returns_markup(mock_post):
    mock_post.return_value = Mock(status_code=200, json=lambda: {"#markup": "<div>ok</div>"})

    result = fetch_month_html(2026, 10)

    mock_post.assert_called_once_with(
        "https://ticket.chateauversailles.fr/en/api/calendar",
        data={"month": 10, "year": 2026},
        timeout=15,
    )
    assert result == "<div>ok</div>"


@patch("versailles_monitor.calendar_client.httpx.post")
def test_fetch_month_html_raises_on_http_error(mock_post):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("500 error")
    mock_post.return_value = mock_response

    import pytest
    with pytest.raises(Exception):
        fetch_month_html(2026, 10)
