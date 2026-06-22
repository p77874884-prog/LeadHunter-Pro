"""
stealth_utils.py
Funções para reduzir a 'fingerprint' de automação do navegador e simular
comportamento humano (delays aleatórios entre ações).
"""

import random
import time


def human_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """Pausa a execução por um tempo aleatório, simulando tempo de reação humano."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def get_stealth_script() -> str:
    """
    Retorna um trecho de JavaScript que é injetado em TODA página nova através de
    `context.add_init_script()`. Isso roda antes de qualquer script da própria
    página, então conseguimos sobrescrever propriedades do navigator antes que
    os scripts de detecção do site as leiam.

    Importante: isso reduz os sinais mais óbvios de automação, mas não torna
    o scraper indetectável. Sistemas anti-bot mais sofisticados (como os do
    Google) combinam dezenas de sinais — fingerprint de canvas, timing de
    eventos, comportamento do mouse, etc.
    """
    return """
    // 1. O sinal clássico nº 1 de automação: navigator.webdriver === true.
    //    Playwright/Selenium definem isso por padrão; removemos a propriedade.
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });

    // 2. Navegadores reais sempre reportam alguns plugins instalados.
    //    Um navegador automatizado "limpo" reporta uma lista vazia, o que é suspeito.
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5]
    });

    // 3. Define idiomas como um navegador real configurado em pt-BR reportaria.
    Object.defineProperty(navigator, 'languages', {
        get: () => ['pt-BR', 'pt', 'en-US', 'en']
    });

    // 4. O objeto window.chrome normalmente existe no Chrome real e contém
    //    metadados internos. Em contextos automatizados ele costuma faltar.
    window.chrome = { runtime: {} };

    // 5. Alguns scripts de detecção testam o comportamento da API de Permissions.
    //    Aqui garantimos que ela responda de forma consistente com um navegador real.
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );
    """