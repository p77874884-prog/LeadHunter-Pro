import os
import random
import re
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote_plus

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


SEARCH_PHRASES = [
    "Distribuidora de autopeças em Goiânia",
    "Atacado de peças automotivas Goiânia",
    "Motopeças atacado Goiânia",
    "Distribuidora de peças para oficinas Goiânia",
]

WHATSAPP_PANEL_WIDTH = 450
WHATSAPP_PANEL_HEIGHT = 800
WHATSAPP_PANEL_POSITION = (1400, 100)
WHATSAPP_USER_DATA_DIR = os.path.join(os.getcwd(), "dados_whatsapp")


def _safe_log(message: str, status_callback: Optional[Callable[[str, Optional[float]], None]] = None, progress: Optional[float] = None) -> None:
    if status_callback:
        status_callback(message, progress)


def _clean_numeric_score(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("55") and len(digits) > 10:
        return digits
    if len(digits) >= 10:
        return digits
    return ""


def _find_email(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0).strip() if match else None


def _find_phone(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"(\+?\d[\d\s().-]{8,}\d)", text)
    if match:
        number = re.sub(r"\D", "", match.group(1))
        return number if len(number) >= 10 else None
    return None


def _create_chrome_options(user_data_dir: str, width: int, height: int, x: int, y: int) -> Options:
    options = Options()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument(f"--window-position={x},{y}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def _extract_city_from_address(address: str) -> str:
    if not address:
        return ""
    hints = [part.strip() for part in re.split(r"[,\-]", address) if part.strip()]
    if hints:
        return hints[0]
    return ""


def build_buyer_search_queries(leads_df: pd.DataFrame, max_queries: int = 6) -> List[str]:
    queries: List[str] = []
    if leads_df.empty:
        return SEARCH_PHRASES[:max_queries]

    city = ""
    if "Endereço" in leads_df.columns:
        city = _extract_city_from_address(str(leads_df.iloc[0].get("Endereço", "")))

    categories = []
    if "Categoria" in leads_df.columns:
        raw_categories = leads_df["Categoria"].dropna()
        for cat in raw_categories:
            if isinstance(cat, list):
                categories.extend([str(item).strip() for item in cat if item])
            else:
                categories.append(str(cat).strip())
        categories = [re.sub(r"\s+", " ", cat) for cat in categories if cat]

    if city:
        queries.append(f"compradores de serviços automotivos em {city}")
        queries.append(f"atacado de autopeças em {city}")
        queries.append(f"fornecedores para oficinas automotivas em {city}")

    unique_categories = []
    for category in categories:
        if category and category not in unique_categories:
            unique_categories.append(category)

    for category in unique_categories[:3]:
        cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", category).strip()
        if cleaned:
            queries.append(f"compradores de {cleaned} em {city or 'Brasil'}")

    for phrase in SEARCH_PHRASES:
        if phrase not in queries:
            queries.append(phrase)

    return queries[:max_queries]


def find_buyers_for_leads(
    leads_df: pd.DataFrame,
    max_buyers: int = 50,
    status_callback: Optional[Callable[[str, Optional[float]], None]] = None,
) -> List[Dict[str, str]]:
    queries = build_buyer_search_queries(leads_df, max_queries=8)
    _safe_log("🔎 Encontrando compradores qualificados para seus leads...", status_callback, 0.0)
    _safe_log(f"🔧 Consultando Google com {len(queries)} pesquisas estratégicas.", status_callback, 0.05)
    buyers = search_buyers_from_google(queries, max_results=max_buyers, status_callback=status_callback)
    _safe_log(f"✅ Encontramos {len(buyers)} compradores para prospecção.", status_callback, 1.0)
    return buyers


def _wait_for_whatsapp_ready(driver: webdriver.Chrome, timeout: int = 60) -> bool:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return True
    except TimeoutException:
        return False


def open_whatsapp_panel(
    status_callback: Optional[Callable[[str, Optional[float]], None]] = None,
    user_data_dir: Optional[str] = None,
) -> Optional[webdriver.Chrome]:
    user_data_dir = user_data_dir or WHATSAPP_USER_DATA_DIR
    os.makedirs(user_data_dir, exist_ok=True)

    _safe_log("☑️ Iniciando painel lateral do WhatsApp Web...", status_callback)
    options = _create_chrome_options(
        user_data_dir,
        WHATSAPP_PANEL_WIDTH,
        WHATSAPP_PANEL_HEIGHT,
        WHATSAPP_PANEL_POSITION[0],
        WHATSAPP_PANEL_POSITION[1],
    )

    try:
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
        driver.get("https://web.whatsapp.com/")
        if _wait_for_whatsapp_ready(driver, timeout=40):
            _safe_log("📱 WhatsApp Web aberto no painel lateral. Verifique o canto direito da tela.", status_callback)
            return driver
    except WebDriverException as exc:
        _safe_log(f"⚠️ Falha ao abrir WhatsApp Web: {exc}", status_callback)
    return None


def _extract_google_results(driver: webdriver.Chrome, limit: int = 25) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    items = driver.find_elements(By.CSS_SELECTOR, "div.g")
    if not items:
        items = driver.find_elements(By.CSS_SELECTOR, "div[data-header-feature]")

    for item in items[:limit]:
        try:
            title_elem = item.find_element(By.TAG_NAME, "h3")
            link_elem = item.find_element(By.CSS_SELECTOR, "a")
            snippet_elem = item.find_element(By.CSS_SELECTOR, "span.aCOpRe")
            title = title_elem.text.strip()
            link = link_elem.get_attribute("href")
            snippet = snippet_elem.text.strip()
            results.append({
                "Nome": title or "N/A",
                "Site": link or "N/A",
                "Email": _find_email(snippet) or "N/A",
                "Telefone": _normalize_phone(_find_phone(snippet) or "") or "N/A",
                "Resumo": snippet,
            })
        except Exception:
            continue
    return results


def search_buyers_from_google(
    queries: List[str],
    max_results: int = 100,
    status_callback: Optional[Callable[[str, Optional[float]], None]] = None,
) -> List[Dict[str, str]]:
    _safe_log("🔎 Preparando busca automática de potenciais compradores...", status_callback)
    options = _create_chrome_options(
        WHATSAPP_USER_DATA_DIR,
        1200,
        900,
        100,
        100,
    )
    buyers: List[Dict[str, str]] = []

    try:
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    except WebDriverException as exc:
        _safe_log(f"⚠️ Não foi possível iniciar o navegador para busca: {exc}", status_callback)
        return buyers

    try:
        for index, query in enumerate(queries, start=1):
            _safe_log(f"🔍 Buscando compradores: {query}", status_callback, index / len(queries))
            driver.get(f"https://www.google.com/search?q={quote_plus(query)}")
            time.sleep(random.uniform(2.5, 4.5))
            buyers += _extract_google_results(driver, limit=20)
            if len(buyers) >= max_results:
                break
        unique_buyers: List[Dict[str, str]] = []
        seen = set()
        for buyer in buyers:
            key = (buyer["Nome"].lower(), buyer["Site"].lower())
            if key not in seen:
                seen.add(key)
                unique_buyers.append(buyer)
            if len(unique_buyers) >= max_results:
                break
        _safe_log(f"✅ Buyer list criada: {len(unique_buyers)} empresas qualificadas.", status_callback)
        return unique_buyers
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def compose_sample_message(leads: List[Dict[str, Any]]) -> str:
    sample_lines = []
    for lead in leads:
        sample_lines.append(
            f"• {lead.get('Nome', 'Empresa')} — {lead.get('Endereço', 'Endereço não informado')}"
        )
    sample_text = "\n".join(sample_lines)
    return (
        "Olá, tudo bem?\n\n"
        "Aqui é um especialista de inteligência de mercado B2B, e eu trouxe uma amostra gratuita com "
        f"{len(leads)} contatos de oficinas e parceiros automotivos altamente qualificados.\n\n"
        "Amostra grátis: \n"
        f"{sample_text}\n\n"
        "Este material é ideal para testar o envio de propostas e descobrir rapidamente oportunidades de compra no segmento automotivo em Goiânia."
    )


def compose_email_html(leads: List[Dict[str, Any]], buyer_name: str) -> str:
    rows = "".join(
        f"<tr><td>{lead.get('Nome', 'N/A')}</td><td>{lead.get('Endereço', 'N/A')}</td><td>{lead.get('Telefone', 'N/A')}</td></tr>"
        for lead in leads
    )
    return f"""
    <html>
        <body style='font-family: Arial, sans-serif; color: #202124;'>
            <div style='max-width: 720px; margin: auto; padding: 24px; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0;'>
                <h2 style='color: #0f172a;'>Olá {buyer_name},</h2>
                <p>Sou consultor de inteligência de mercado B2B e preparei uma lista grátis de 5 contatos-chave para você testar logo.</p>
                <p><strong>Confira a amostra gratuita abaixo:</strong></p>
                <table style='width:100%; border-collapse: collapse;'>
                    <thead>
                        <tr style='background: #0f172a; color: #f8fafc;'>
                            <th style='padding: 10px; text-align:left;'>Empresa</th>
                            <th style='padding: 10px; text-align:left;'>Endereço</th>
                            <th style='padding: 10px; text-align:left;'>Telefone</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
                <p>Se quiser, eu posso enviar agora esta lista para o seu time de vendas e montar uma sequência de abordagem completa.</p>
                <p style='color: #0f172a; font-weight: bold;'>Vamos conversar?</p>
            </div>
        </body>
    </html>
    """


def send_email(
    smtp_server: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    recipient: str,
    subject: str,
    html_body: str,
    status_callback: Optional[Callable[[str, Optional[float]], None]] = None,
) -> bool:
    _safe_log(f"✉️ Enviando e-mail para {recipient}...", status_callback)
    try:
        message = EmailMessage()
        message["From"] = smtp_username
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content("Este e-mail requer um cliente que suporte HTML.")
        message.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
        _safe_log(f"✅ E-mail enviado para {recipient}.", status_callback)
        return True
    except Exception as exc:
        _safe_log(f"⚠️ Falha ao enviar e-mail para {recipient}: {exc}", status_callback)
        return False


def send_whatsapp_message(
    driver: webdriver.Chrome,
    phone: str,
    message: str,
    status_callback: Optional[Callable[[str, Optional[float]], None]] = None,
) -> bool:
    normalized_phone = _normalize_phone(phone)
    if not normalized_phone:
        _safe_log(f"⚠️ Número inválido para WhatsApp: {phone}", status_callback)
        return False

    url = f"https://web.whatsapp.com/send?phone={normalized_phone}&text={quote_plus(message)}"
    _safe_log(f"📲 Preparando chat do WhatsApp para {normalized_phone}...", status_callback)
    try:
        driver.get(url)
        WebDriverWait(driver, 40).until(
            EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true']"))
        )
        send_button = WebDriverWait(driver, 40).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[@data-testid='compose-btn-send'] | //span[@data-icon='send']/..")
            )
        )
        send_button.click()
        _safe_log(f"✅ WhatsApp disparado para {normalized_phone}.", status_callback)
        return True
    except Exception as exc:
        _safe_log(f"⚠️ Não foi possível enviar WhatsApp para {normalized_phone}: {exc}", status_callback)
        return False


def get_top_leads(leads_df: pd.DataFrame, count: int = 5) -> List[Dict[str, Any]]:
    if leads_df.empty:
        return []
    leads = leads_df.copy()
    leads["Nota_num"] = leads["Nota"].apply(_clean_numeric_score)
    leads = leads.sort_values(by="Nota_num", ascending=False)
    return leads.head(count).to_dict(orient="records")


def run_sales_prospector(
    leads_df: pd.DataFrame,
    smtp_server: Optional[str] = None,
    smtp_port: int = 587,
    smtp_username: Optional[str] = None,
    smtp_password: Optional[str] = None,
    whatsapp_user_data_dir: Optional[str] = None,
    max_buyers: int = 100,
    status_callback: Optional[Callable[[str, Optional[float]], None]] = None,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "buyers_found": 0,
        "emails_sent": 0,
        "whatsapp_sent": 0,
        "sample_leads": [],
        "buyers": [],
    }

    _safe_log("🤖 Iniciando o Prospector de Vendas Inteligente...", status_callback)
    sample_leads = get_top_leads(leads_df, count=5)
    summary["sample_leads"] = sample_leads
    _safe_log(f"✨ {len(sample_leads)} leads de amostra selecionados para kit grátis.", status_callback)

    buyers = search_buyers_from_google(SEARCH_PHRASES, max_results=max_buyers, status_callback=status_callback)
    summary["buyers"] = buyers
    summary["buyers_found"] = len(buyers)

    if smtp_server and smtp_username and smtp_password:
        email_recipients = [buyer for buyer in buyers if buyer.get("Email") and buyer["Email"] != "N/A"]
        subject = "Amostra grátis de 5 contatos para sua operação automotiva"

        for buyer in email_recipients[:5]:
            html_body = compose_email_html(sample_leads, buyer.get("Nome", "Parceiro"))
            if send_email(
                smtp_server,
                smtp_port,
                smtp_username,
                smtp_password,
                buyer["Email"],
                subject,
                html_body,
                status_callback,
            ):
                summary["emails_sent"] += 1
    else:
        _safe_log("⚠️ Configurações de SMTP não fornecidas. O envio de e-mail não será executado.", status_callback)

    whatsapp_driver = open_whatsapp_panel(status_callback, whatsapp_user_data_dir)
    if whatsapp_driver is not None:
        whatsapp_targets = [buyer for buyer in buyers if buyer.get("Telefone") and buyer["Telefone"] != "N/A"]
        for index, buyer in enumerate(whatsapp_targets[:5], start=1):
            message = compose_sample_message(sample_leads)
            if send_whatsapp_message(whatsapp_driver, buyer["Telefone"], message, status_callback):
                summary["whatsapp_sent"] += 1
            delay = random.randint(60, 120)
            _safe_log(f"⏱️ Aguardando {delay} segundos antes do próximo disparo...", status_callback)
            time.sleep(delay)
    else:
        _safe_log("⚠️ O painel do WhatsApp não foi iniciado. Os disparos via WhatsApp foram ignorados.", status_callback)

    _safe_log(
        f"✅ Prospector finalizado: {summary['buyers_found']} compradores encontrados, {summary['emails_sent']} e-mails enviados, {summary['whatsapp_sent']} WhatsApps disparados.",
        status_callback,
        1.0,
    )
    return summary
