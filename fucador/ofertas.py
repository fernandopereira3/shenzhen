"""Fuçador: incorporado de news_bot/fucador.py.

Do original mudou: Gemini e e-mail compartilhados (main.gemini, main.emails), produtos,
destinatários, canais, modelo e prompt no banco (editáveis na página).
"""

import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, quote_plus, urljoin

import requests

from main.emails import enviar_email
from main.gemini import GEMINI_MODEL, ask_gemini

# busca de cada loja: a do Gemini quase nunca devolve a página da oferta, então o link abre a busca da loja pelo modelo
BUSCA_LOJA = {
    "mercado livre": lambda q: (
        "https://lista.mercadolivre.com.br/" + quote(q.replace(" ", "-"))
    ),
    "magazine luiza": lambda q: f"https://www.magazineluiza.com.br/busca/{quote(q)}/",
    "magalu": lambda q: f"https://www.magazineluiza.com.br/busca/{quote(q)}/",
    "casas bahia": lambda q: f"https://www.casasbahia.com.br/{quote(q)}/b",
    "amazon": lambda q: "https://www.amazon.com.br/s?k=" + quote_plus(q),
    "kabum": lambda q: "https://www.kabum.com.br/busca/" + quote(q.replace(" ", "-")),
    "zoom": lambda q: "https://www.zoom.com.br/search?q=" + quote_plus(q),
    "buscapé": lambda q: "https://www.buscape.com.br/search?q=" + quote_plus(q),
}
PASTA = (
    Path(__file__).parent / "imgs"
)  # fucador_banner.png / fucador_rodape.png; o que faltar é pulado
DIAS = [
    "SEGUNDA-FEIRA",
    "TERÇA-FEIRA",
    "QUARTA-FEIRA",
    "QUINTA-FEIRA",
    "SEXTA-FEIRA",
    "SÁBADO",
    "DOMINGO",
]
MESES = [
    "JANEIRO",
    "FEVEREIRO",
    "MARÇO",
    "ABRIL",
    "MAIO",
    "JUNHO",
    "JULHO",
    "AGOSTO",
    "SETEMBRO",
    "OUTUBRO",
    "NOVEMBRO",
    "DEZEMBRO",
]
# formato comum a todos os bots: cada bot só explica no prompt o que vai em cada campo
FORMATO_JSON = (
    "Responda somente com JSON, sem comentários antes ou depois, neste formato: "
    '{"abertura": "...", "itens": [{"rotulo": "...", "titulo": "...", "destaque": "...", '
    '"texto": ["parágrafo", "..."], "fonte": "nome do site"}], "despedida": "..."}. '
    "Não escreva links (eles são adicionados depois). Destaque números importantes com **asteriscos duplos**."
)


class _Capa(HTMLParser):
    """Lê as tags og:title, og:description e og:image (a prévia que aparece no WhatsApp)."""

    def __init__(self):
        super().__init__()
        self.og = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        nome = a.get("property") or a.get("name")
        if (
            tag == "meta"
            and nome in ("og:title", "og:description", "og:image")
            and nome not in self.og
        ):
            self.og[nome] = a.get("content") or ""


def abrir_materia(url: str) -> tuple[str, str, str | None]:
    """Segue o redirecionamento do Google e devolve (link real, título + descrição, imagem de capa)."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        # 1º redirecionamento = link real; lojas que bloqueiam robô (403, captcha) mandam para outra página depois
        link = r.history[0].headers.get("location", r.url) if r.history else r.url
        leitor = _Capa()
        leitor.feed(r.text if r.ok else "")
        og = leitor.og
        imagem = og.get("og:image")
        # o endereço entra na comparação: o nome do produto/matéria costuma estar nele, mesmo se a página bloquear
        descricao = f"{og.get('og:title', '')} {og.get('og:description', '')} {link}"
        return link, descricao, imagem and urljoin(r.url, imagem)
    except requests.RequestException:
        return url, "", None


def _palavras(texto: str) -> set[str]:
    return set(re.findall(r"\w{4,}", texto.lower()))


def materia_da_linha(linha: str, materias: list[tuple[str, str, str | None]]):
    """Matéria que mais combina com a linha; None se nenhuma bater de verdade.

    Palavras presentes em mais da metade das fontes ("placa", "radeon") são ignoradas; das restantes
    precisa bater pelo menos 2, e as mais raras (marca, modelo, nome próprio) valem mais.
    """
    textos = [_palavras(m[1]) for m in materias]
    frequencia = {}
    for t in textos:
        for w in t:
            frequencia[w] = frequencia.get(w, 0) + 1
    # palavras em mais da metade das fontes não distinguem nada
    palavras = {
        w for w in _palavras(linha) if frequencia.get(w, 0) <= max(1, len(materias) / 2)
    }

    def pontos(t):
        comuns = palavras & t
        return sum(1 / frequencia[w] for w in comuns) if len(comuns) >= 2 else 0

    notas = [pontos(t) for t in textos]
    # shortcut: casamento por palavras; se ainda errar muito, pedir ao Gemini um JSON com o índice da fonte
    melhor = max(range(len(materias)), key=notas.__getitem__, default=None)
    return materias[melhor] if melhor is not None and notas[melhor] > 0 else None


def ler_json(texto: str) -> dict:
    # com google_search a API não aceita resposta só-JSON, então às vezes vem embrulhado em ```json
    return json.loads(texto[texto.find("{") : texto.rfind("}") + 1])


def _rico(texto: str) -> str:
    """Escapa o HTML e transforma **x** em negrito."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(texto))


ROTULO = (
    "font-size:12px;letter-spacing:2px;color:#888;margin:36px 0 6px;font-weight:bold"
)
TITULO = "font-size:24px;line-height:1.25;margin:0 0 16px;padding-bottom:10px;border-bottom:3px solid #111"
FOTO = "width:100%;height:auto;display:block;margin:0 0 16px;border-radius:4px"


def montar_html(edicao: dict, fontes: list[str], pngs: dict) -> str:
    """Página no estilo newsletter: data, abertura, um bloco por item e rodapé. pngs = {cid: bytes}."""
    materias = [abrir_materia(u) for u in fontes]
    hoje = datetime.now()
    e = html.escape
    p = []
    if "capa" in pngs:
        p.append(
            f'<img src="cid:capa" alt="" width="600" style="{FOTO};border-radius:0">'
        )
    p.append(
        f'<p style="font-size:12px;letter-spacing:2px;color:#888;margin:16px 0 0">'
        f"{DIAS[hoje.weekday()]}, {hoje.day} DE {MESES[hoje.month - 1]} DE {hoje.year}</p>"
    )
    p.append(f'<h1 style="font-size:36px;margin:4px 0 16px">{hoje:%d/%m/%Y}</h1>')
    if edicao.get("abertura"):
        p.append(
            f'<p style="font-style:italic;color:#444">{_rico(edicao["abertura"])}</p>'
        )
    for item in edicao.get("itens", []):
        texto = item.get("texto") or []
        materia = materia_da_linha(
            f"{item.get('titulo', '')} {item.get('destaque', '')} {' '.join(texto)}",
            materias,
        )
        link, _, imagem = materia or (None, None, None)
        if not link:  # sem fonte: busca do modelo na loja da oferta; loja desconhecida vai para o Google Shopping
            modelo = re.sub(r"[^\w\s.,/-]", "", item.get("titulo", "")).strip()
            loja = item.get("fonte", "").lower()
            busca = BUSCA_LOJA.get(loja) or (
                lambda q: (
                    "https://www.google.com/search?tbm=shop&q="
                    + quote_plus(f"{q} {loja}")
                )
            )
            link = busca(modelo)
        p.append(f'<p style="{ROTULO}">{e(item.get("rotulo", "").upper())}</p>')
        p.append(f'<h2 style="{TITULO}">{e(item.get("titulo", ""))}</h2>')
        if imagem:
            p.append(f'<img src="{e(imagem)}" alt="" width="600" style="{FOTO}">')
        if item.get("destaque"):
            p.append(f"<p><b>{_rico(item['destaque'])}</b></p>")
        p += [f"<p>{_rico(t)}</p>" for t in texto]
        fonte = e(item.get("fonte", ""))
        p.append(
            f'<p><a href="{e(link)}" style="color:#111;font-weight:bold">Ver oferta na {fonte or "loja"} →</a></p>'
            if link
            else f'<p style="color:#888">Fonte: {fonte}</p>'
            if fonte
            else ""
        )
    if edicao.get("despedida"):
        p.append(f'<p style="margin-top:40px">{_rico(edicao["despedida"])}</p>')
    if "rodape" in pngs:
        p.append(
            f'<img src="cid:rodape" alt="" width="600" style="{FOTO};border-radius:0;margin-top:24px">'
        )
    return (
        '<html><body style="margin:0;background:#f2f2f2">'
        '<div style="max-width:600px;margin:0 auto;background:#fff;padding:24px;'
        'font-family:Helvetica,Arial,sans-serif;font-size:16px;line-height:1.6;color:#111">'
        + "\n".join(p)
        + "</div></body></html>"
    )


def montar_texto(edicao: dict, negrito: str = "") -> str:
    """Versão texto para quem não abre HTML; `negrito="*"` vira negrito no WhatsApp."""
    linhas = [edicao.get("abertura", "")]
    for i in edicao.get("itens", []):
        linhas += [
            "",
            f"{i.get('rotulo', '')} | {i.get('titulo', '')}",
            i.get("destaque", ""),
            *(i.get("texto") or []),
            f"Fonte: {i.get('fonte', '')}",
        ]
    linhas += ["", edicao.get("despedida", "")]
    return "\n".join(linhas).replace("**", negrito)


def enviar_whatsapp(assunto: str, edicao: dict, para: list[tuple[str, str]]) -> None:
    """Manda a versão texto pelo CallMeBot; cada (telefone, apikey) recebe uma mensagem."""
    print("🏷️ Enviando WhatsApp...")
    texto = f"*{assunto}*\n\n{montar_texto(edicao, negrito='*')}"
    for fone, chave in para:
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": fone, "text": texto, "apikey": chave},
            timeout=60,
        )
        r.raise_for_status()  # shortcut: o CallMeBot às vezes responde 200 com erro no corpo; ver r.text se não chegar


# {hoje} vira a data e {produto} o produto pesquisado. Editável na página (aba Gemini); este é o padrão.
PROMPT_PADRAO = (
    "Hoje é {hoje} (a data está correta; não a questione). Encontre ofertas à venda no Brasil de: {produto}. "
    "Faça as buscas direto nestes sites, uma por site, usando o operador site: (ex.: site:zoom.com.br {produto}): zoom.com.br, buscape.com.br, magazineluiza.com.br, casasbahia.com.br, amazon.com.br, mercadolivre.com.br, kabum.com.br. "
    "Não use o Google Shopping. "
    "Liste até 5 ofertas, do menor para o maior preço, um item por oferta: "
    "rotulo = nome da loja que vende (nunca a marca do produto); "
    "titulo = nome completo do produto (marca, modelo e versão) com um emoji; "
    "destaque = o preço no formato 'R$ 1.234,56', só o que aparece na busca; "
    "se não aparecer, escreva só 'preço não informado' (sem R$); não invente preços; "
    "texto = uma frase sobre a oferta; fonte = o mesmo nome da loja do rotulo (ex.: Mercado Livre, não o endereço do site). "
    "Prefira ofertas com preço visível. "
    "Inclua apenas produtos que correspondem ao que foi pedido (mesmo modelo e capacidade). "
    "abertura = saudação curta, informe que pode haver divergências nos preços; despedida = qual parece o melhor custo-benefício e por quê, "
    "assinada pelo 'Fuçador'. Tom leve."
)


def ofertas_prompt(produto: str, texto: str | None = None) -> str:
    # replace e não format: chaves digitadas no prompt editado não quebram nada
    return (
        (texto or PROMPT_PADRAO)
        .replace("{hoje}", datetime.now().strftime("%d/%m/%Y"))
        .replace("{produto}", produto)
    )


def imagens(
    capa: str = "fucador_banner.png", rodape: str = "fucador_rodape.png"
) -> dict:
    return {
        cid: (PASTA / nome).read_bytes()
        for cid, nome in {"capa": capa, "rodape": rodape}.items()
        if (PASTA / nome).exists()
    }


def enviar_produto(
    produto: str,
    emails: list[str],
    whatsapps: list[tuple[str, str]],
    prompt: str | None = None,
    modelo: str | None = None,
) -> None:
    """Procura ofertas do produto e manda por e-mail e/ou WhatsApp (era o produto()/enviar() do original).
    Canal sem destinatário é pulado."""
    print(f"🏷️ Fuçador: buscando ofertas de {produto}...")
    resposta, fontes = ask_gemini(
        f"{ofertas_prompt(produto, prompt)} {FORMATO_JSON}", modelo or GEMINI_MODEL
    )
    edicao = ler_json(resposta)
    assunto = f"Fuçador: {produto}"
    if emails:
        print("🏷️ Montando e-mail...")
        pngs = imagens()
        enviar_email(
            assunto,
            montar_texto(edicao),
            montar_html(edicao, fontes, pngs),
            emails,
            pngs,
        )
    if whatsapps:
        enviar_whatsapp(assunto, edicao, whatsapps)
    print(f"🏷️ Enviado: {len(emails)} e-mail(s), {len(whatsapps)} WhatsApp(s)")
