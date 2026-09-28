"""Tests for marketing_data/meta.py (P3).

Tests cover:
- month_windows: slices by calendar month with edge recrop
- month_windows: mid-month boundaries (2026-08-15 to 2026-09-10 → 2 windows)
- month_windows: single month (2026-09-01 to 2026-09-28 → 1 window, full)
- month_windows: start == end same day → 1 window
- load_meta_creds: prefixes act_ if missing
- load_meta_creds: does NOT double-prefix act_ if already present
- load_meta_creds: returns None if token/acct missing
- parse insight row: onsite_conversion.messaging_first_reply action → int new_msg_contacts
- fetch_meta_insights_daily: pagination stops at 50 pages (mocked requests)
- fetch_meta_reach_monthly: pagination stops at 20 pages (mocked)
- fetch_meta_window: swallows reach/metadata failures, propagates insights failure

No real network calls.
"""

import pytest
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# month_windows (pure function — no mocking needed)
# ---------------------------------------------------------------------------

def test_month_windows_mid_month_two_windows():
    """2026-08-15 to 2026-09-10 → 2 windows with correct recropped edges."""
    from marketing_data.meta import month_windows

    windows = month_windows("2026-08-15", "2026-09-10")
    assert len(windows) == 2

    w0 = windows[0]
    assert w0["ym"] == "2026-08"
    assert w0["since"] == "2026-08-15"   # recropped to provided since
    assert w0["until"] == "2026-08-31"   # end of August

    w1 = windows[1]
    assert w1["ym"] == "2026-09"
    assert w1["since"] == "2026-09-01"
    assert w1["until"] == "2026-09-10"   # recropped to provided until


def test_month_windows_full_single_month():
    """2026-09-01 to 2026-09-28 → 1 window."""
    from marketing_data.meta import month_windows

    windows = month_windows("2026-09-01", "2026-09-28")
    assert len(windows) == 1
    w = windows[0]
    assert w["ym"] == "2026-09"
    assert w["since"] == "2026-09-01"
    assert w["until"] == "2026-09-28"


def test_month_windows_same_day():
    """Single day → 1 window."""
    from marketing_data.meta import month_windows

    windows = month_windows("2026-09-15", "2026-09-15")
    assert len(windows) == 1
    assert windows[0]["since"] == "2026-09-15"
    assert windows[0]["until"] == "2026-09-15"


def test_month_windows_three_months():
    """2026-07-20 to 2026-09-05 → 3 windows."""
    from marketing_data.meta import month_windows

    windows = month_windows("2026-07-20", "2026-09-05")
    assert len(windows) == 3
    assert windows[0]["ym"] == "2026-07"
    assert windows[0]["since"] == "2026-07-20"
    assert windows[0]["until"] == "2026-07-31"
    assert windows[1]["ym"] == "2026-08"
    assert windows[1]["since"] == "2026-08-01"
    assert windows[1]["until"] == "2026-08-31"
    assert windows[2]["ym"] == "2026-09"
    assert windows[2]["since"] == "2026-09-01"
    assert windows[2]["until"] == "2026-09-05"


def test_month_windows_full_two_months():
    """2026-08-01 to 2026-09-30 → 2 windows with full-month until."""
    from marketing_data.meta import month_windows

    windows = month_windows("2026-08-01", "2026-09-30")
    assert len(windows) == 2
    assert windows[0]["since"] == "2026-08-01"
    assert windows[0]["until"] == "2026-08-31"
    assert windows[1]["since"] == "2026-09-01"
    assert windows[1]["until"] == "2026-09-30"


# ---------------------------------------------------------------------------
# load_meta_creds
# ---------------------------------------------------------------------------

def test_load_meta_creds_prefixes_act_():
    """Account ID without act_ prefix gets prefixed."""
    from marketing_data.meta import load_meta_creds

    env = {"META_ACCESS_TOKEN": "tok123", "META_AD_ACCOUNT_ID": "987654321"}
    creds = load_meta_creds(env)
    assert creds is not None
    assert creds["acct"] == "act_987654321"
    assert creds["token"] == "tok123"


def test_load_meta_creds_no_double_prefix():
    """Account ID already has act_ — no double-prefix."""
    from marketing_data.meta import load_meta_creds

    env = {"META_ACCESS_TOKEN": "tok123", "META_AD_ACCOUNT_ID": "act_987654321"}
    creds = load_meta_creds(env)
    assert creds["acct"] == "act_987654321"


def test_load_meta_creds_missing_token_returns_none():
    """Missing META_ACCESS_TOKEN → returns None."""
    from marketing_data.meta import load_meta_creds

    env = {"META_AD_ACCOUNT_ID": "123"}
    assert load_meta_creds(env) is None


def test_load_meta_creds_missing_acct_returns_none():
    """Missing META_AD_ACCOUNT_ID → returns None."""
    from marketing_data.meta import load_meta_creds

    env = {"META_ACCESS_TOKEN": "tok"}
    assert load_meta_creds(env) is None


def test_load_meta_creds_both_missing_returns_none():
    from marketing_data.meta import load_meta_creds

    assert load_meta_creds({}) is None


# ---------------------------------------------------------------------------
# Insight row parsing (messaging_first_reply → int)
# ---------------------------------------------------------------------------

def _make_requests_mock(pages_data):
    """pages_data: list of dicts that requests.get().json() returns in sequence."""
    responses = []
    for page in pages_data:
        mock_resp = MagicMock()
        mock_resp.json.return_value = page
        responses.append(mock_resp)
    mock_get = MagicMock(side_effect=responses)
    return mock_get


def test_parse_insight_messaging_first_reply():
    """onsite_conversion.messaging_first_reply action → new_msg_contacts as int."""
    from marketing_data.meta import fetch_meta_insights_daily

    creds = {"token": "tok", "acct": "act_123"}

    page1 = {
        "data": [
            {
                "ad_name": "Ad Alpha",
                "date_start": "2026-09-01",
                "spend": "12.50",
                "impressions": "1000",
                "reach": "800",
                "actions": [
                    {"action_type": "link_click", "value": "50"},
                    {"action_type": "onsite_conversion.messaging_first_reply", "value": "7"},
                ],
            }
        ],
        # no paging.next → single page
    }

    with patch("marketing_data.meta.requests.get", _make_requests_mock([page1])):
        result = fetch_meta_insights_daily(creds, "2026-09-01", "2026-09-30")

    assert result["spend"]["Ad Alpha"]["2026-09-01"] == 12.50
    assert result["impressions"]["Ad Alpha"]["2026-09-01"] == 1000
    assert result["reach"]["Ad Alpha"]["2026-09-01"] == 800
    assert result["new_msg_contacts"]["Ad Alpha"]["2026-09-01"] == 7


def test_parse_insight_no_messaging_action():
    """Missing messaging_first_reply → new_msg_contacts is 0."""
    from marketing_data.meta import fetch_meta_insights_daily

    creds = {"token": "tok", "acct": "act_123"}

    page1 = {
        "data": [
            {
                "ad_name": "Ad Beta",
                "date_start": "2026-09-02",
                "spend": "5.00",
                "impressions": "200",
                "reach": "150",
                "actions": [
                    {"action_type": "link_click", "value": "10"},
                ],
            }
        ],
    }

    with patch("marketing_data.meta.requests.get", _make_requests_mock([page1])):
        result = fetch_meta_insights_daily(creds, "2026-09-01", "2026-09-30")

    assert result["new_msg_contacts"]["Ad Beta"]["2026-09-02"] == 0


def test_parse_insight_missing_ad_name_skipped():
    """Rows without ad_name or date_start are skipped."""
    from marketing_data.meta import fetch_meta_insights_daily

    creds = {"token": "tok", "acct": "act_123"}

    page1 = {
        "data": [
            {"date_start": "2026-09-01", "spend": "5.00"},  # no ad_name
            {"ad_name": "Ad C", "spend": "3.00"},            # no date_start
        ],
    }

    with patch("marketing_data.meta.requests.get", _make_requests_mock([page1])):
        result = fetch_meta_insights_daily(creds, "2026-09-01", "2026-09-30")

    assert result["spend"] == {}


# ---------------------------------------------------------------------------
# Pagination guard: insights daily stops at 50 pages
# ---------------------------------------------------------------------------

def test_insights_daily_pagination_stops_at_50():
    """Pagination stops at 50 pages even if paging.next keeps appearing."""
    from marketing_data.meta import fetch_meta_insights_daily

    creds = {"token": "tok", "acct": "act_123"}

    # Build 60 pages each with a paging.next
    pages = []
    for i in range(60):
        pages.append({
            "data": [{"ad_name": f"Ad{i}", "date_start": "2026-09-01",
                      "spend": "1.00", "impressions": "10", "reach": "8", "actions": []}],
            "paging": {"next": f"https://graph.facebook.com/page{i+1}"},
        })

    with patch("marketing_data.meta.requests.get", _make_requests_mock(pages)):
        result = fetch_meta_insights_daily(creds, "2026-09-01", "2026-09-30")

    # JS guard e `pages > 50` -> busca ate a 51a pagina (paridade com _meta.js)
    assert len(result["spend"]) == 51


# ---------------------------------------------------------------------------
# Pagination guard: reach monthly stops at 20 pages
# ---------------------------------------------------------------------------

def test_reach_monthly_pagination_stops_at_20():
    """fetchMetaReachMonthly stops at 20 pages per window."""
    from marketing_data.meta import fetch_meta_reach_monthly

    creds = {"token": "tok", "acct": "act_123"}

    # 30 pages for a single-month window
    pages = []
    for i in range(30):
        pages.append({
            "data": [{"ad_name": f"Ad{i}", "reach": "100"}],
            "paging": {"next": f"https://graph.facebook.com/reach{i+1}"},
        })

    with patch("marketing_data.meta.requests.get", _make_requests_mock(pages)):
        result = fetch_meta_reach_monthly(creds, "2026-09-01", "2026-09-30")

    assert len(result) == 21


# ---------------------------------------------------------------------------
# fetch_meta_window: swallows reach/metadata failures; propagates insights fail
# ---------------------------------------------------------------------------

def test_fetch_meta_window_swallows_reach_failure():
    """Reach monthly failure is swallowed; result still has spend_daily etc."""
    from marketing_data.meta import fetch_meta_window

    env = {"META_ACCESS_TOKEN": "tok", "META_AD_ACCOUNT_ID": "act_123"}

    mock_insights_result = {
        "spend": {"Ad A": {"2026-09-01": 10.0}},
        "impressions": {"Ad A": {"2026-09-01": 100}},
        "reach": {"Ad A": {"2026-09-01": 80}},
        "new_msg_contacts": {},
    }

    with patch("marketing_data.meta.fetch_meta_insights_daily", return_value=mock_insights_result), \
         patch("marketing_data.meta.fetch_meta_reach_monthly", side_effect=Exception("reach fail")), \
         patch("marketing_data.meta.fetch_meta_ads_metadata", return_value={"thumbs": {}, "adCampaign": {}, "adAdset": {}, "campaigns": []}):
        result = fetch_meta_window(env, {"since": "2026-09-01", "until": "2026-09-28"})

    assert "spend_daily" in result
    assert "reach_monthly" not in result   # swallowed


def test_fetch_meta_window_swallows_metadata_failure():
    """Metadata failure is swallowed; result still has spend_daily etc."""
    from marketing_data.meta import fetch_meta_window

    env = {"META_ACCESS_TOKEN": "tok", "META_AD_ACCOUNT_ID": "act_123"}

    mock_insights_result = {
        "spend": {}, "impressions": {}, "reach": {}, "new_msg_contacts": {},
    }

    with patch("marketing_data.meta.fetch_meta_insights_daily", return_value=mock_insights_result), \
         patch("marketing_data.meta.fetch_meta_reach_monthly", return_value={}), \
         patch("marketing_data.meta.fetch_meta_ads_metadata", side_effect=Exception("meta fail")):
        result = fetch_meta_window(env, {"since": "2026-09-01", "until": "2026-09-28"})

    assert "spend_daily" in result
    assert "thumbnails" not in result   # swallowed


def test_fetch_meta_window_propagates_insights_failure():
    """Insights daily failure IS propagated (raises)."""
    from marketing_data.meta import fetch_meta_window

    env = {"META_ACCESS_TOKEN": "tok", "META_AD_ACCOUNT_ID": "act_123"}

    with patch("marketing_data.meta.fetch_meta_insights_daily", side_effect=Exception("API fail")):
        with pytest.raises(Exception, match="API fail"):
            fetch_meta_window(env, {"since": "2026-09-01", "until": "2026-09-28"})


def test_fetch_meta_window_missing_creds_raises():
    """Missing Meta credentials raises."""
    from marketing_data.meta import fetch_meta_window

    env = {}
    with pytest.raises(Exception, match="[Cc]redenciais"):
        fetch_meta_window(env, {"since": "2026-09-01", "until": "2026-09-28"})
