"""
app.py
Painel principal do LeadHunter Pro.
Execute com: streamlit run app.py
"""

import os
from datetime import datetime
from io import BytesIO
from typing import Optional

import pandas as pd
import streamlit as st
from openpyxl.styles import Alignment, Font, PatternFill

from scraper import GoogleMapsScraper


def clean_leads_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    df = df.fillna("")
    df["Nome"] = df["Nome"].astype(str).str.title().str.strip()
    df["Categoria"] = df["Categoria"].astype(str).str.title().str.strip()
    df["Endereço"] = df["Endereço"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    df["Telefone"] = df["Telefone"].astype(str).str.replace(r"\D", "", regex=True)
    df["WhatsApp"] = df["WhatsApp"].astype(str).str.replace(r"\D", "", regex=True)
    df["Email"] = df["Email"].astype(str).str.lower().str.strip()
    df["Site"] = df["Site"].astype(str).str.strip()
    df["Instagram"] = df["Instagram"].astype(str).str.strip()
    df["Nota"] = df["Nota"].astype(str).str.replace(r"[^0-9.,]", "", regex=True).str.strip()
    df["Status"] = df["Status"].astype(str).str.title().str.strip()

    df["Nome_norm"] = df["Nome"].str.lower().str.strip()
    df["Endereço_norm"] = df["Endereço"].str.lower().str.strip()
    df["Telefone_norm"] = df["Telefone"].str.replace(r"\D", "", regex=True)
    df["Email_norm"] = df["Email"].str.lower().str.strip()

    phone_rows = df[df["Telefone_norm"].astype(bool)].drop_duplicates(subset=["Telefone_norm"], keep="first")
    no_phone_rows = df[~df["Telefone_norm"].astype(bool)].drop_duplicates(subset=["Nome_norm", "Endereço_norm"], keep="first")
    df = pd.concat([phone_rows, no_phone_rows]).sort_index().reset_index(drop=True)

    df = df.drop(columns=["Nome_norm", "Endereço_norm", "Telefone_norm", "Email_norm"])

    ordered_columns = [
        "Nome",
        "Categoria",
        "Status",
        "Nota",
        "Endereço",
        "Telefone",
        "WhatsApp",
        "Email",
        "Site",
        "Instagram",
        "Perfil Google Maps",
    ]
    ordered_columns = [col for col in ordered_columns if col in df.columns]
    df = df[ordered_columns]

    return df


def generate_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Leads")
        workbook = writer.book
        worksheet = writer.sheets["Leads"]

        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(fill_type="solid", fgColor="1F2937")
        for cell in worksheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for column_cells in worksheet.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter
            for cell in column_cells:
                value = str(cell.value or "")
                max_length = max(max_length, len(value))
            worksheet.column_dimensions[column_letter].width = min(max_length + 4, 50)

        worksheet.freeze_panes = worksheet["A2"]

    buffer.seek(0)
    return buffer.getvalue()


st.set_page_config(page_title="LeadHunter Pro", page_icon="🚀", layout="wide")

st.markdown(
    """
    <style>
    .page-background { background: linear-gradient(180deg, #0F172A 0%, #111827 100%); color: #f8fafc; }
    .main-title { font-size: 3rem; font-weight: 800; letter-spacing: -0.04em; color: #F59E0B; margin-bottom: 0; }
    .subtitle { color: #d1d5db; font-size: 1.1rem; margin-top: 0.35rem; margin-bottom: 1.75rem; }
    .section-title { color: #FBBF24; font-size: 1.4rem; margin-bottom: 0.8rem; font-weight: 700; }
    .metric-card { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 24px; padding: 24px; }
    .metric-label { color: #cbd5e1; font-size: 0.95rem; margin-bottom: 0.35rem; }
    .metric-value { color: #f8fafc; font-size: 2.3rem; font-weight: 800; }
    .button-gold button { background: linear-gradient(135deg, #FBBF24, #F59E0B); color: #0f172a !important; border: none !important; }
    .button-gold button:hover { opacity: 0.95; }
    .panel-box { background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(245, 158, 11, 0.2); border-radius: 24px; padding: 24px; }
    .log-box { background: rgba(30, 41, 59, 0.95); border: 1px solid rgba(96, 165, 250, 0.15); border-radius: 18px; padding: 18px; color: #e2e8f0; font-family: monospace; font-size: 0.92rem; max-height: 420px; overflow-y: auto; }
    .whatsapp-card { background: linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(30, 41, 59, 0.98)); border: 1px solid rgba(34, 197, 94, 0.2); border-radius: 20px; padding: 20px; }
    .highlight { color: #FBBF24; }
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stTextArea>div>div>textarea { background: #0f172a !important; color: #f8fafc !important; }
    .stSelectbox>div>div>div>span { color: #f8fafc !important; }
    .streamlit-expanderHeader { color: #f8fafc !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-title">LeadHunter Pro - Inteligência de Mercado B2B</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Plataforma premium para capturar e qualificar leads e gerar planilhas limpas, prontas para venda.</div>', unsafe_allow_html=True)

if "leads_df" not in st.session_state:
    st.session_state.leads_df = pd.DataFrame()

with st.form("search_form"):
    st.markdown('<div class="section-title">1. Extração de Leads</div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        niche = st.text_input("Nicho / Tipo de negócio", placeholder="Ex: Oficinas automotivas")
    with col2:
        city = st.text_input("Cidade / Região", placeholder="Ex: Goiânia, GO")
    with col3:
        max_results = st.number_input(
            "Máx. de leads",
            min_value=5,
            max_value=200,
            value=30,
            step=5,
            help="O número real de leads retornados é limitado a este valor após limpeza e deduplicação.",
        )

    headless_mode = st.checkbox(
        "Rodar em segundo plano (headless)",
        value=False,
        help="Ative para executar sem exibir a janela do navegador do scraper.",
    )

    submitted = st.form_submit_button("🚀 Extrair Leads", use_container_width=True)

if submitted:
    if not niche or not city:
        st.error("Preencha o nicho e a cidade antes de iniciar a extração.")
    else:
        if "progress_bar" not in st.session_state:
            st.session_state.progress_bar = st.progress(0.0)
        progress_bar = st.session_state.progress_bar
        status_text = st.empty()

        def update_progress(current: int, total: int, message: str) -> None:
            pct = min(current / total, 1.0) if total else 0.0
            progress_bar.progress(pct)
            status_text.markdown(f"**{message}**")

        scraper = GoogleMapsScraper(headless=headless_mode)
        try:
            results = scraper.search(
                niche=niche,
                city=city,
                max_results=int(max_results),
                progress_callback=update_progress,
            )
            cleaned_df = clean_leads_dataframe(pd.DataFrame(results))
            st.session_state.leads_df = cleaned_df
            st.success(f"Extração concluída: {len(cleaned_df)} leads únicos prontos para prospecção.")
        except Exception as e:
            st.error(f"Erro durante a extração: {e}")

if not st.session_state.leads_df.empty:
    st.markdown('<div class="section-title">2. Planilha Pronta para Compartilhar</div>', unsafe_allow_html=True)

    st.dataframe(st.session_state.leads_df.fillna("Não informado"), use_container_width=True)

    st.download_button(
        "⬇️ Compartilhar / Baixar Planilha Limpa (CSV)",
        data=st.session_state.leads_df.to_csv(index=False).encode("utf-8"),
        file_name="leads_limpos.csv",
        mime="text/csv",
        use_container_width=True,
    )

    try:
        excel_data = generate_excel_bytes(st.session_state.leads_df)
        st.download_button(
            "⬇️ Compartilhar / Baixar Planilha Top (Excel)",
            data=excel_data,
            file_name="leads_limpos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except ModuleNotFoundError:
        st.warning(
            "O módulo openpyxl não está instalado. Instale-o com `pip install openpyxl` para baixar o arquivo Excel.",
        )
        st.caption("O download CSV ainda está disponível.")

    st.markdown('<div class="panel-box" style="margin-top: 1rem;"><h4 style="color:#F59E0B; margin-bottom:0.75rem;">Observação</h4><p>O robô extrai leads, limpa e salva apenas a planilha final. Telefones duplicados são removidos automaticamente.</p></div>', unsafe_allow_html=True)
