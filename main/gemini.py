"""Gemini compartilhado pelos bots (News e Fuçador): pergunta com busca do Google e lista de modelos."""
import os

import requests
from django.core.cache import cache

GEMINI_MODEL = "gemini-3.8-flash"  # padrão; cada bot pode trocar na página (aba Gemini)
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"


def ask_gemini(prompt: str, modelo: str = GEMINI_MODEL) -> tuple[str, list[str]]:
    """Devolve (texto, links das páginas que a busca do Google usou)."""
    resp = requests.post(
        f"{GEMINI_API}/{modelo}:generateContent",
        headers={"x-goog-api-key": GEMINI_KEY},
        # google_search: sem isso o modelo inventa em vez de buscar as notícias/ofertas de hoje
        json={"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]},
        timeout=180,  # com busca (uma por site, no Fuçador) passa fácil de 60s
    )
    resp.raise_for_status()
    candidato = resp.json()["candidates"][0]
    texto = "".join(p.get("text", "") for p in candidato["content"]["parts"])
    # os links escritos no texto são inventados; os reais vêm só nos metadados da busca
    chunks = candidato.get("groundingMetadata", {}).get("groundingChunks", [])
    return texto, list(dict.fromkeys(c["web"]["uri"] for c in chunks if "web" in c))


# modelos da lista que não geram texto ou não usam a busca do Google (sem busca não há dado real)
_FORA_DA_LISTA = ("tts", "image", "banana", "lyria", "robotics", "computer-use", "transcribe",
                  "customtools", "embedding", "antigravity", "deep-research")


def listar_modelos() -> list[tuple[str, str]]:
    """[(id, nome)] dos modelos Gemini de texto disponíveis na chave."""
    r = requests.get(GEMINI_API, params={"pageSize": 1000},
                     headers={"x-goog-api-key": GEMINI_KEY}, timeout=10)
    r.raise_for_status()
    modelos = []
    for m in r.json().get("models", []):
        id_ = m["name"].removeprefix("models/")
        if (id_.startswith("gemini-") and "generateContent" in m.get("supportedGenerationMethods", [])
                and not any(t in id_ for t in _FORA_DA_LISTA)):
            modelos.append((id_, m.get("displayName", id_)))
    return sorted(modelos, reverse=True)


def modelos_em_cache() -> list[tuple[str, str]]:
    """listar_modelos() guardado por 1h; se a API falhar, lista vazia (a página deixa digitar)."""
    modelos = cache.get("gemini_modelos")
    if modelos is None:
        try:
            modelos = listar_modelos()
        except Exception as erro:
            print(f"Não deu pra listar os modelos do Gemini: {erro!r}")
            return []
        cache.set("gemini_modelos", modelos, 3600)
    return modelos
