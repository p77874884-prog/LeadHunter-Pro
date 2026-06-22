"""
config.py
Configurações centrais do LeadHunter Pro.
Mantenha aqui tudo que você queira ajustar sem precisar mexer na lógica do scraper.
"""

import os

# Lista de User-Agents reais para rotação a cada execução.
# Por quê: usar sempre o mesmo UA é um sinal forte de automação para sistemas
# anti-bot. Atualize esta lista de tempos em tempos com versões recentes de
# navegadores (UAs muito antigos também levantam suspeita).
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Intervalo (em segundos) de espera aleatória entre ações do scraper.
# Por quê: ações em intervalos fixos (ex: sempre 1.0s) são fáceis de detectar
# estatisticamente. Um range aleatório simula a variação natural humana.
SCROLL_PAUSE_RANGE = (1.2, 3.0)

# Quantas vezes o scraper tenta rolar a lista de resultados antes de desistir.
# O Google Maps carrega resultados em lotes; isso evita loop infinito caso
# a lista pare de crescer por algum motivo.
MAX_SCROLL_ATTEMPTS = 40

# headless=False mostra o navegador na tela — útil durante desenvolvimento
# para ver o que está acontecendo e ajustar seletores quebrados.
# headless=True é mais seguro para servidores sem interface gráfica.
HEADLESS = os.environ.get("HEADLESS", "true").strip().lower() in ("1", "true", "yes")

# Caminho para o arquivo JSON da conta de serviço do Google Sheets.
# Defina a variável de ambiente GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
# ou ajuste este valor diretamente para uso local.
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = os.environ.get(
    "GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", ""
)
