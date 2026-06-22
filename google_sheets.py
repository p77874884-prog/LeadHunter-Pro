import os
from datetime import datetime
from typing import Optional

import pandas as pd


def export_df_to_google_sheet(
    df: pd.DataFrame,
    spreadsheet_name: str,
    worksheet_name: str = "Leads",
    credentials_path: Optional[str] = None,
) -> str:
    """Exporta um DataFrame para um Google Sheet e retorna a URL da planilha."""
    if df.empty:
        raise ValueError("DataFrame está vazio; não há dados para exportar.")

    if not credentials_path:
        credentials_path = os.environ.get("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", "")

    if not credentials_path:
        raise ValueError(
            "Caminho para credenciais do Google Sheets não configurado. "
            "Defina a variável de ambiente GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE."
        )

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Arquivo de credenciais não encontrado em: {credentials_path}"
        )

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        raise ImportError(
            "A biblioteca gspread/google-auth não está instalada. "
            "Use: pip install gspread google-auth"
        ) from e

    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scope)
    client = gspread.authorize(creds)

    spreadsheet_title = spreadsheet_name.strip() or f"LeadHunter Pro Export {datetime.now():%Y-%m-%d %H:%M}"
    try:
        spreadsheet = client.open(spreadsheet_title)
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(spreadsheet_title)

    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        worksheet.clear()
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=str(max(1000, len(df) + 5)),
            cols=str(len(df.columns) + 5),
        )

    values = [list(df.columns)] + df.fillna("").astype(str).values.tolist()
    worksheet.update(values)

    try:
        spreadsheet.share(None, perm_type="anyone", role="writer")
    except Exception:
        # Caso a conta de serviço não tenha permissão para alterar compartilhamento,
        # deixamos a planilha criada, mas o link pode ficar restrito.
        pass

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"
