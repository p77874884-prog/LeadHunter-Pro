"""
scraper.py
Módulo responsável por toda a automação de navegação e extração de dados do
Google Maps. Usa a API síncrona do Playwright (mais simples de integrar com
o modelo de execução "rerun" do Streamlit do que a API assíncrona).

ATENÇÃO SOBRE SELETORES:
O Google Maps não tem uma API pública de busca e muda seu HTML/classes CSS
com frequência (as classes como 'hfpxzc' ou 'DUwDvf' são geradas/ofuscadas
e podem mudar sem aviso). Se a extração começar a retornar "N/A" para tudo,
o primeiro passo é inspecionar o HTML atual do Google Maps e atualizar os
seletores nas constantes no topo da classe.
"""

import random
import re
from typing import List, Dict, Optional, Callable
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

from config import USER_AGENTS, SCROLL_PAUSE_RANGE, MAX_SCROLL_ATTEMPTS, HEADLESS
from stealth_utils import get_stealth_script, human_delay


class GoogleMapsScraper:
    # Seletores centralizados aqui em cima: se o Google mudar o layout,
    # você só precisa atualizar estas linhas, não a lógica abaixo.
    SEL_RESULT_CARD = "a.hfpxzc"
    SEL_FEED = 'div[role="feed"]'
    SEL_NAME = "h1.DUwDvf"
    SEL_RATING = "div.F7nice span[aria-hidden='true']"
    SEL_ADDRESS_BTN = 'button[data-item-id="address"]'
    SEL_PHONE_BTN = 'button[data-item-id^="phone:tel:"]'
    SEL_WEBSITE_LINK = 'a[data-item-id="authority"]'
    # Palavras que geralmente indicam empresas fora do escopo de oficinas
    PROHIBITED_PHRASES = [
        "lava jato",
        "lava-jato",
        "auto peças",
        "autopeças",
    ]
    PROHIBITED_KEYWORDS = [
        "lava jato",
        "lava-jato",
        "auto peças",
        "autopeças",
        "peças",
        "transporte",
        "logística",
        "frete",
        "distribuidora",
        "revenda",
        "estacionamento",
        "aluguel",
        "serviço de limpeza",
        "pintura automotiva",
    ]
    SEARCH_BOX_SELECTORS = [
        "#searchboxinput",
        "input[role='combobox']",
        "input[name='q']",
        "input[aria-label*='Pesquisar']",
        "input[aria-label*='Search']",
        "input[type='search']",
    ]

    def __init__(self, headless: bool = HEADLESS):
        self.headless = headless

    def search(
        self,
        niche: str,
        city: str,
        max_results: int = 30,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Dict]:
        """
        Busca `niche` em `city` no Google Maps e retorna uma lista de dicts
        com Nome, Nota, Endereço, Telefone e Site de cada estabelecimento.

        progress_callback(atual, total, mensagem) é chamado a cada etapa
        relevante para que a UI (Streamlit) possa atualizar a barra de progresso.
        """
        query = f"{niche} em {city}"
        results: List[Dict] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    # Remove a flag que entrega a automação para alguns scripts
                    # de detecção que checam navigator.webdriver via Chromium flags.
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )

            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1366, "height": 768},
                locale="pt-BR",
            )

            # O script de stealth precisa ser injetado ANTES da página carregar,
            # por isso usamos add_init_script no contexto (não na página).
            context.add_init_script(get_stealth_script())

            page = context.new_page()

            if progress_callback:
                progress_callback(0, max_results, "Acessando resultados do Google Maps...")

            try:
                search_url = self._build_search_url(query)
                page.goto(search_url, timeout=60000)
                human_delay(1.5, 3.0)

                try:
                    page.wait_for_selector(self.SEL_FEED, timeout=30000)
                except Exception:
                    if progress_callback:
                        progress_callback(0, max_results, "Busca direta falhou, tentando fallback...")
                    page.goto("https://www.google.com/maps", timeout=60000)
                    human_delay(1.5, 3.0)
                    self._perform_search(page, query)

                page.wait_for_selector(self.SEL_FEED, timeout=30000)
                feed = page.locator(self.SEL_FEED)

                self._scroll_feed(page, feed, max_results, progress_callback)

                cards = feed.locator(self.SEL_RESULT_CARD).all()[:max_results]
                total = len(cards)

                for index, card in enumerate(cards, start=1):
                    if progress_callback:
                        progress_callback(
                            index, total, f"Extraindo estabelecimento {index}/{total}..."
                        )
                    data = self._extract_card_data(page, card)
                    if data:
                        results.append(data)
                    human_delay(*SCROLL_PAUSE_RANGE)

            except PlaywrightTimeoutError as e:
                raise RuntimeError(
                    "Tempo esgotado esperando um elemento do Google Maps. "
                    "Causas comuns: o layout mudou, a conexão está lenta, ou a "
                    "sessão foi bloqueada/recebeu CAPTCHA. "
                    f"Detalhe técnico: {e}"
                )
            finally:
                browser.close()

        return self._sanitize_results(results)[:max_results]

    # ---------- Métodos auxiliares (privados) ----------

    def _perform_search(self, page: Page, query: str) -> None:
        """Clica na caixa de busca e digita a query simulando digitação humana.

        Se não for possível localizar ou interagir com a caixa de busca
        (ex: seletor mudou, página bloqueou cliques), o método faz um
        fallback navegando diretamente para a URL de busca do Maps.
        """
        try:
            search_box = self._find_search_box(page)
            search_box.scroll_into_view_if_needed()
            search_box.click(timeout=10000)
            for char in query:
                # delay por caractere: digitação instantânea de uma string inteira
                # é um padrão claramente não-humano.
                search_box.type(char, delay=random.uniform(50, 150))
            page.keyboard.press("Enter")
            return
        except Exception:
            # Se o campo não for localizado ou se a interação falhar,
            # usamos fallback por URL.
            pass

        # --- Fallback: navegar diretamente para a página de resultados ---
        search_url = self._build_search_url(query)
        page.goto(search_url, timeout=60000)
        # pequena espera para o feed aparecer; a chamada que invoca _perform_search
        # fará o wait_for_selector mais adiante também.
        human_delay(1.0, 2.0)

    def _find_search_box(self, page: Page):
        """Tenta localizar a caixa de busca do Google Maps usando seletores conhecidos."""
        for selector in self.SEARCH_BOX_SELECTORS:
            locator = page.locator(selector).first
            if locator.count() > 0:
                return locator
        raise RuntimeError(
            "Não foi possível localizar a caixa de busca do Google Maps. "
            "O layout provavelmente mudou e o seletor precisa ser atualizado."
        )

    def _build_search_url(self, query: str) -> str:
        """Gera a URL de busca do Google Maps para uma query.

        Evita depender de um campo de busca que pode mudar de seletor.
        """
        return f"https://www.google.com/maps/search/{quote_plus(query)}"

    def _scroll_feed(
        self,
        page: Page,
        feed,
        max_results: int,
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> None:
        """
        Rola o painel de resultados (a div do feed, não a página inteira) até
        carregar `max_results` itens ou detectar o fim da lista.

        A lógica de "estagnação" (stagnant_attempts) existe porque às vezes o
        Google demora alguns ciclos para carregar mais itens mesmo sem ter
        chegado ao fim — se simplesmente parássemos no primeiro scroll sem
        novidade, cortaríamos resultados válidos.
        """
        previous_count = 0
        stagnant_attempts = 0

        for _ in range(MAX_SCROLL_ATTEMPTS):
            current_count = len(feed.locator(self.SEL_RESULT_CARD).all())

            if progress_callback:
                progress_callback(
                    min(current_count, max_results),
                    max_results,
                    f"Carregando lista... {current_count} encontrados",
                )

            if current_count >= max_results:
                break

            # Mensagem que o próprio Google mostra quando a lista acaba
            if page.locator("text=Você chegou ao final da lista").count() > 0:
                break

            # Rola o feed (não a página) até o fundo via JS
            feed.evaluate("(el) => el.scrollTo(0, el.scrollHeight)")
            human_delay(*SCROLL_PAUSE_RANGE)

            if current_count == previous_count:
                stagnant_attempts += 1
                if stagnant_attempts >= 3:
                    break
            else:
                stagnant_attempts = 0

            previous_count = current_count

    def _extract_card_data(self, page: Page, card) -> Optional[Dict]:
        """Clica em um cartão da lista para abrir o painel de detalhes e extrai os campos."""
        try:
            profile_url = card.get_attribute("href") or ""
            card.click()
            page.wait_for_selector('div[role="main"]', timeout=10000)
            human_delay(1.0, 2.0)

            name = self._safe_text(page, self.SEL_NAME)
            rating = self._safe_text(page, self.SEL_RATING)

            address = self._get_address(page)

            phone = self._safe_attr(page, self.SEL_PHONE_BTN, "aria-label")
            if phone:
                phone = phone.replace("Telefone: ", "").strip()
            if not phone:
                phone = self._parse_phone(page)

            website = self._get_website(page)
            instagram = self._get_instagram(page)
            whatsapp = self._get_whatsapp(page)
            email = self._get_email(page)

            category = self._parse_category(page)
            status = self._parse_status(page)
            google_maps_url = profile_url or page.url

            return {
                "Nome": name or "N/A",
                "Categoria": category or "N/A",
                "Nota": rating or "N/A",
                "Status": status or "N/A",
                "Endereço": address or "N/A",
                "Telefone": phone or "N/A",
                "WhatsApp": whatsapp or "N/A",
                "Email": email or "N/A",
                "Site": website or "N/A",
                "Instagram": instagram or "N/A",
                "Perfil Google Maps": google_maps_url,
            }
        except PlaywrightTimeoutError:
            # Um card individual falhar não deve derrubar a extração inteira
            return None

    def _parse_detail_lines(self, page: Page) -> List[str]:
        try:
            raw_text = page.inner_text('div[role="main"]')
            return [line.strip() for line in raw_text.splitlines() if line.strip()]
        except Exception:
            return []

    def _parse_category(self, page: Page) -> Optional[str]:
        for line in self._parse_detail_lines(page):
            if "·" in line and "Website" not in line and "Rotas" not in line:
                parts = [part.strip() for part in line.split("·")]
                if len(parts) >= 2:
                    return parts[0]
        return None

    def _get_address(self, page: Page) -> Optional[str]:
        address = self._safe_attr(page, self.SEL_ADDRESS_BTN, "aria-label")
        if address:
            address = re.sub(r"^Endereço[:]?\s*", "", address).strip()
        if not address:
            address = self._safe_text(page, self.SEL_ADDRESS_BTN)
            if address:
                address = re.sub(r"^Endereço[:]?\s*", "", address).strip()
        if not address:
            for line in self._parse_detail_lines(page):
                if line.startswith("Endereço") or any(tok in line for tok in ["Rua ", "Av.", "Alameda", "Rodovia", "Estrada", "Travessa"]):
                    candidate = re.sub(r"^Endereço[:]?\s*", "", line).strip()
                    if len(candidate) > 8:
                        return candidate
        return None

    def _get_whatsapp(self, page: Page) -> Optional[str]:
        whatsapp = self._safe_attr(page, 'a[href*="wa.me/"]', "href")
        if whatsapp:
            return whatsapp
        whatsapp = self._safe_attr(page, 'a[href*="api.whatsapp.com/send"]', "href")
        if whatsapp:
            return whatsapp
        for line in self._parse_detail_lines(page):
            if "WhatsApp" in line:
                return re.sub(r"^.*WhatsApp[:]?\s*", "", line).strip()
        return None

    def _get_instagram(self, page: Page) -> Optional[str]:
        instagram = self._safe_attr(page, 'a[href*="instagram.com"]', "href")
        if instagram:
            return instagram
        return None

    def _get_email(self, page: Page) -> Optional[str]:
        email = self._safe_attr(page, 'a[href^="mailto:"]', "href")
        if email:
            return email.replace("mailto:", "").split("?")[0].strip()
        for line in self._parse_detail_lines(page):
            match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", line)
            if match:
                return match.group(0).strip()
        return None

    def _normalize_key(self, item: Dict) -> tuple:
        name = (item.get("Nome") or "").strip().lower()
        address = (item.get("Endereço") or "").strip().lower()
        phone = (item.get("Telefone") or "").strip().lower()
        url = (item.get("Perfil Google Maps") or "").strip().lower()
        return (name, address, phone or url)

    def _is_valid_lead(self, item: Dict) -> bool:
        content = " ".join(
            [str(item.get(key, "")) for key in ["Nome", "Categoria"]]
        ).lower()
        if any(phrase in content for phrase in self.PROHIBITED_PHRASES):
            return False
        for keyword in self.PROHIBITED_KEYWORDS:
            if keyword in content and not any(term in content for term in ["oficina", "mecânica", "mecanica", "mécanica"]):
                return False
        return True

    def _sanitize_results(self, results: List[Dict]) -> List[Dict]:
        cleaned: List[Dict] = []
        seen = set()
        for item in results:
            if not self._is_valid_lead(item):
                continue
            key = self._normalize_key(item)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(item)
        return cleaned

    def _parse_status(self, page: Page) -> Optional[str]:
        for line in self._parse_detail_lines(page):
            if "Aberto" in line or "Fechado" in line:
                return line
        return None

    def _parse_phone(self, page: Page) -> Optional[str]:
        for line in self._parse_detail_lines(page):
            match = re.search(r"\(\d{2}\)\s*\d{4,5}-\d{4}", line)
            if match:
                return match.group(0)
        return None

    def _get_website(self, page: Page) -> Optional[str]:
        website = self._safe_attr(page, 'a[aria-label*="Acessar o site"]', "href")
        if website:
            return website
        website = self._safe_attr(page, self.SEL_WEBSITE_LINK, "aria-label")
        if website:
            return website.replace("Site: ", "").strip()
        return None

    def _safe_text(self, page: Page, selector: str) -> Optional[str]:
        """Tenta extrair texto de um seletor; retorna None em vez de lançar exceção."""
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                return locator.inner_text().strip()
        except Exception:
            pass
        return None

    def _safe_attr(self, page: Page, selector: str, attr: str) -> Optional[str]:
        """Mesma ideia do _safe_text, mas para um atributo HTML específico."""
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                return locator.get_attribute(attr)
        except Exception:
            pass
        return None