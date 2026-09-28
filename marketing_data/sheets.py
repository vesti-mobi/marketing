"""marketing_data/sheets.py — porta fiel de functions/api/_sheets.js.

Lê uma aba do Google Sheets usando a Sheets API v4 via google-api-python-client.
Auth: GCP_SA_KEY (JSON inline ou base64) tem prioridade sobre
      GOOGLE_APPLICATION_CREDENTIALS (caminho para arquivo).
Devolve matriz de strings (str(c or '')), igual ao JS.
"""

import json
import base64

from google.oauth2 import service_account
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _parse_service_account(v: str) -> dict:
    """Aceita JSON puro ou base64 — igual ao parseServiceAccount() do JS."""
    s = v.strip()
    if s.startswith("{"):
        return json.loads(s)
    return json.loads(base64.b64decode(s).decode("utf-8"))


def get_google_credentials(env):
    """Seleciona credenciais Google a partir das variáveis de ambiente.

    Preferência: GCP_SA_KEY (inline) → GOOGLE_APPLICATION_CREDENTIALS (arquivo).
    Lança ValueError se nenhuma das duas estiver configurada.
    """
    sa_key = env.get("GCP_SA_KEY")
    if sa_key:
        sa_info = _parse_service_account(sa_key)
        return service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=_SCOPES,
        )

    creds_file = env.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_file:
        return service_account.Credentials.from_service_account_file(
            creds_file,
            scopes=_SCOPES,
        )

    raise ValueError(
        "Credenciais Google não configuradas: defina GCP_SA_KEY (JSON inline) "
        "ou GOOGLE_APPLICATION_CREDENTIALS (caminho para arquivo de SA)."
    )


def read_sheet_rows(env, *, tab: str, rng: str = "A:K") -> list[list[str]]:
    """Lê '{tab}!{rng}' do SHEET_ID e devolve uma matriz de strings.

    Equivalente a readSheetRows() do _sheets.js, mas usando as libs Python
    (google-auth + googleapiclient) em vez de JWT manual via WebCrypto.

    Args:
        env: dict/Mapping com variáveis de ambiente.
             Deve conter SHEET_ID e credenciais (GCP_SA_KEY ou GOOGLE_APPLICATION_CREDENTIALS).
        tab: nome da aba (ex: "LeadsV2").
        rng: range de colunas (default "A:K").

    Returns:
        Lista de listas de strings. Células None ou ausentes viram ''.
    """
    sheet_id = env["SHEET_ID"]  # levanta KeyError se ausente — igual ao JS

    creds = get_google_credentials(env)
    service = build("sheets", "v4", credentials=creds)

    range_notation = f"{tab}!{rng}"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=range_notation)
        .execute()
    )

    values = result.get("values") or []
    # Coerce cada célula para string, None → '' (igual ao .map(c => String(c == null ? '' : c)) do JS)
    return [[str(c or "") for c in row] for row in values]
