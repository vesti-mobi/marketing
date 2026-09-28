"""Tests for marketing_data/sheets.py (P2).

Tests cover:
- get_google_credentials: inline GCP_SA_KEY JSON → uses from_service_account_info
- get_google_credentials: only GOOGLE_APPLICATION_CREDENTIALS file path → uses from_service_account_file
- get_google_credentials: neither env var → raises clear ValueError
- read_sheet_rows cell coercion: None → '', non-string → str, already string unchanged
- read_sheet_rows: calls the sheets API with correct tab+range notation

No real network calls — Credentials and googleapiclient.discovery.build are mocked.
"""

import json
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# get_google_credentials
# ---------------------------------------------------------------------------

def test_get_google_credentials_inline_json():
    """GCP_SA_KEY with inline JSON → calls from_service_account_info."""
    from marketing_data.sheets import get_google_credentials

    fake_sa = {
        "type": "service_account",
        "project_id": "proj",
        "private_key_id": "kid",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "test@proj.iam.gserviceaccount.com",
        "client_id": "123",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    env = {"GCP_SA_KEY": json.dumps(fake_sa)}

    with patch("marketing_data.sheets.service_account.Credentials.from_service_account_info") as mock_fsi:
        mock_fsi.return_value = MagicMock()
        creds = get_google_credentials(env)
        mock_fsi.assert_called_once()
        call_args = mock_fsi.call_args
        # First positional arg should be the parsed dict
        assert call_args[0][0]["client_email"] == "test@proj.iam.gserviceaccount.com"
        assert creds is mock_fsi.return_value


def test_get_google_credentials_file_path():
    """Only GOOGLE_APPLICATION_CREDENTIALS → calls from_service_account_file."""
    from marketing_data.sheets import get_google_credentials

    env = {"GOOGLE_APPLICATION_CREDENTIALS": "/path/to/sa.json"}

    with patch("marketing_data.sheets.service_account.Credentials.from_service_account_file") as mock_fsf:
        mock_fsf.return_value = MagicMock()
        creds = get_google_credentials(env)
        mock_fsf.assert_called_once_with(
            "/path/to/sa.json",
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        assert creds is mock_fsf.return_value


def test_get_google_credentials_neither_raises():
    """No credentials configured → raises ValueError with clear message."""
    from marketing_data.sheets import get_google_credentials

    env = {}
    with pytest.raises(ValueError, match="GCP_SA_KEY"):
        get_google_credentials(env)


def test_get_google_credentials_prefers_inline_over_file():
    """When both env vars present, GCP_SA_KEY (inline) takes priority."""
    from marketing_data.sheets import get_google_credentials

    fake_sa = {
        "type": "service_account",
        "client_email": "a@b.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    env = {
        "GCP_SA_KEY": json.dumps(fake_sa),
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/sa.json",
    }

    with patch("marketing_data.sheets.service_account.Credentials.from_service_account_info") as mock_fsi, \
         patch("marketing_data.sheets.service_account.Credentials.from_service_account_file") as mock_fsf:
        mock_fsi.return_value = MagicMock()
        get_google_credentials(env)
        mock_fsi.assert_called_once()
        mock_fsf.assert_not_called()


# ---------------------------------------------------------------------------
# Cell coercion (pure logic tested via read_sheet_rows with mocked client)
# ---------------------------------------------------------------------------

def _make_sheets_mock(values_response):
    """Build a mock googleapiclient discovery client that returns values_response."""
    mock_service = MagicMock()
    mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
        "values": values_response
    }
    return mock_service


def test_read_sheet_rows_cell_coercion():
    """Cells are coerced to str: None→'', int→'1', float→'1.5', str unchanged."""
    from marketing_data.sheets import read_sheet_rows

    raw_rows = [
        ["Header", None, 1, 1.5, "text"],
    ]

    fake_sa = {"type": "service_account", "client_email": "a@b.com",
               "token_uri": "https://oauth2.googleapis.com/token"}
    env = {
        "GCP_SA_KEY": json.dumps(fake_sa),
        "SHEET_ID": "sheet123",
    }

    with patch("marketing_data.sheets.service_account.Credentials.from_service_account_info") as mock_fsi, \
         patch("marketing_data.sheets.build") as mock_build:
        mock_fsi.return_value = MagicMock()
        mock_build.return_value = _make_sheets_mock(raw_rows)

        rows = read_sheet_rows(env, tab="LeadsV2", rng="A:K")

    assert rows == [["Header", "", "1", "1.5", "text"]]


def test_read_sheet_rows_empty_sheet():
    """Empty sheet returns empty list."""
    from marketing_data.sheets import read_sheet_rows

    fake_sa = {"type": "service_account", "client_email": "a@b.com",
               "token_uri": "https://oauth2.googleapis.com/token"}
    env = {
        "GCP_SA_KEY": json.dumps(fake_sa),
        "SHEET_ID": "sheet123",
    }

    with patch("marketing_data.sheets.service_account.Credentials.from_service_account_info") as mock_fsi, \
         patch("marketing_data.sheets.build") as mock_build:
        mock_fsi.return_value = MagicMock()
        mock_build.return_value = _make_sheets_mock([])

        rows = read_sheet_rows(env, tab="LeadsV2", rng="A:K")

    assert rows == []


def test_read_sheet_rows_uses_correct_range():
    """read_sheet_rows passes '{tab}!{rng}' to the Sheets API."""
    from marketing_data.sheets import read_sheet_rows

    fake_sa = {"type": "service_account", "client_email": "a@b.com",
               "token_uri": "https://oauth2.googleapis.com/token"}
    env = {
        "GCP_SA_KEY": json.dumps(fake_sa),
        "SHEET_ID": "mysheetid",
    }

    with patch("marketing_data.sheets.service_account.Credentials.from_service_account_info") as mock_fsi, \
         patch("marketing_data.sheets.build") as mock_build:
        mock_fsi.return_value = MagicMock()
        mock_service = MagicMock()
        mock_execute = mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute
        mock_execute.return_value = {"values": []}
        mock_build.return_value = mock_service

        read_sheet_rows(env, tab="LeadsV2", rng="A:K")

        get_call = mock_service.spreadsheets.return_value.values.return_value.get
        get_call.assert_called_once()
        call_kwargs = get_call.call_args[1]
        assert call_kwargs["spreadsheetId"] == "mysheetid"
        assert call_kwargs["range"] == "LeadsV2!A:K"


def test_read_sheet_rows_missing_sheet_id_raises():
    """Missing SHEET_ID in env raises ValueError."""
    from marketing_data.sheets import read_sheet_rows

    env = {"GCP_SA_KEY": json.dumps({"type": "service_account", "client_email": "a@b.com"})}
    with pytest.raises((ValueError, KeyError)):
        read_sheet_rows(env, tab="LeadsV2", rng="A:K")
