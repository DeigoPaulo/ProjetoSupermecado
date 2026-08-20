"""Monitor de publicações fiscais oficiais.

O componente apenas detecta mudanças e cria alertas. Ele nunca baixa, instala ou
ativa schemas, notas técnicas ou código do adaptador automaticamente.
"""

import hashlib
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from lxml import html

from apps.auditoria.models import LogAuditoria

from .models import (
    AlertaAtualizacaoFiscal,
    FonteAtualizacaoFiscal,
    StatusAlertaAtualizacaoFiscal,
    StatusFonteAtualizacaoFiscal,
)

CONTRATO_MONITOR = "fiscal_update_monitor_v1"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ALLOWED_HOSTS = {
    "www.nfe.fazenda.gov.br",
    "nfe.fazenda.gov.br",
    "goias.gov.br",
    "www.goias.gov.br",
}
DEFAULT_SOURCES = (
    {
        "codigo": "portal-nfe-notas-tecnicas",
        "nome": "Portal Nacional NF-e - Notas técnicas",
        "url": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=6WfrpZYE4Ik=",
    },
    {
        "codigo": "portal-nfe-schemas",
        "nome": "Portal Nacional NF-e - Schemas XML",
        "url": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=",
    },
    {
        "codigo": "sefaz-go-documentos-fiscais",
        "nome": "Secretaria da Economia de Goiás - Documentos fiscais",
        "url": "https://goias.gov.br/economia/documentos-fiscais/",
    },
)
RELEVANT_PATTERN = re.compile(
    r"(?:nota\s+t[eé]cnica|informe\s+t[eé]cnico|schema|esquema\s+xml|"
    r"pacote\s+de\s+libera[cç][aã]o|manual\s+de\s+orienta[cç][aã]o|"
    r"[uú]ltima\s+atualiza[cç][aã]o|nf-?e|nfc-?e|ibs/?cbs)",
    re.IGNORECASE,
)


class MonitorAtualizacaoFiscalError(Exception):
    pass


def fontes_configuradas():
    fontes = getattr(settings, "FISCAL_UPDATE_MONITOR_SOURCES", None) or DEFAULT_SOURCES
    normalizadas = []
    codigos = set()
    for item in fontes:
        codigo = str(item.get("codigo") or "").strip().lower()
        nome = str(item.get("nome") or "").strip()
        url = str(item.get("url") or "").strip()
        if not codigo or not nome or not url or codigo in codigos:
            raise MonitorAtualizacaoFiscalError("Fonte fiscal inválida ou duplicada.")
        _validar_url_oficial(url)
        codigos.add(codigo)
        normalizadas.append({"codigo": codigo, "nome": nome[:160], "url": url[:500]})
    return tuple(normalizadas)


def _validar_url_oficial(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise MonitorAtualizacaoFiscalError(
            "O monitor fiscal aceita somente URLs HTTPS de fontes oficiais autorizadas."
        )


def _normalizar_texto(valor):
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def _fingerprint(valor):
    return hashlib.sha256(valor.casefold().encode("utf-8")).hexdigest()


def extrair_itens_relevantes(conteudo):
    try:
        documento = html.fromstring(conteudo)
    except (ValueError, TypeError) as exc:
        raise MonitorAtualizacaoFiscalError("A fonte oficial retornou HTML inválido.") from exc
    for elemento in documento.xpath("//script|//style|//noscript"):
        elemento.drop_tree()
    candidatos = []
    for elemento in documento.xpath("//a|//h1|//h2|//h3|//h4|//li|//p"):
        texto = _normalizar_texto(" ".join(elemento.itertext()))
        if 12 <= len(texto) <= 500 and RELEVANT_PATTERN.search(texto):
            candidatos.append(texto)
    unicos = {}
    for titulo in candidatos:
        unicos.setdefault(_fingerprint(titulo), titulo)
    if not unicos:
        titulo = _normalizar_texto(documento.xpath("string(//title)")) or "Conteúdo da fonte oficial"
        unicos[_fingerprint(titulo)] = titulo[:500]
    return [
        {"fingerprint": fingerprint, "titulo": titulo}
        for fingerprint, titulo in sorted(unicos.items(), key=lambda item: item[1].casefold())
    ][:500]


def _conteudo_sha256(itens):
    serializado = "\n".join(item["fingerprint"] for item in itens)
    return hashlib.sha256(serializado.encode("ascii")).hexdigest()


def buscar_fonte_http(fonte, estado):
    _validar_url_oficial(fonte["url"])
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "Deigo-Varejo-Monitor-Fiscal/1.0",
    }
    if estado.etag:
        headers["If-None-Match"] = estado.etag
    if estado.ultima_modificacao_http:
        headers["If-Modified-Since"] = estado.ultima_modificacao_http
    request = Request(fonte["url"], headers=headers, method="GET")
    try:
        with urlopen(
            request,
            timeout=max(2, int(getattr(settings, "FISCAL_UPDATE_MONITOR_TIMEOUT_SECONDS", 20))),
            context=ssl.create_default_context(),
        ) as response:
            final_url = response.geturl()
            _validar_url_oficial(final_url)
            tipo = (response.headers.get("Content-Type") or "").lower()
            if "text/html" not in tipo and "application/xhtml+xml" not in tipo:
                raise MonitorAtualizacaoFiscalError("A fonte oficial não retornou uma página HTML.")
            conteudo = response.read(MAX_RESPONSE_BYTES + 1)
            if len(conteudo) > MAX_RESPONSE_BYTES:
                raise MonitorAtualizacaoFiscalError("A resposta da fonte oficial excedeu 2 MB.")
            return {
                "status": int(getattr(response, "status", 200)),
                "conteudo": conteudo,
                "etag": response.headers.get("ETag", "")[:255],
                "ultima_modificacao": response.headers.get("Last-Modified", "")[:255],
                "url_final": final_url,
            }
    except HTTPError as exc:
        if exc.code == 304:
            return {"status": 304, "conteudo": b"", "etag": estado.etag, "ultima_modificacao": estado.ultima_modificacao_http, "url_final": fonte["url"]}
        raise MonitorAtualizacaoFiscalError(f"A fonte oficial respondeu HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
        raise MonitorAtualizacaoFiscalError("Não foi possível consultar a fonte fiscal oficial.") from exc


def _registrar_falha(estado, mensagem):
    estado.status = StatusFonteAtualizacaoFiscal.ERRO
    estado.ultima_consulta_em = timezone.now()
    estado.ultima_mensagem = str(mensagem)[:2000]
    estado.save(update_fields=["status", "ultima_consulta_em", "ultima_mensagem", "atualizado_em"])


def monitorar_atualizacoes_fiscais(*, fetcher=None, fontes=None, forcar=False):
    habilitado = bool(getattr(settings, "FISCAL_UPDATE_MONITOR_ENABLED", False))
    if not habilitado and not forcar:
        return {
            "contrato": CONTRATO_MONITOR,
            "habilitado": False,
            "consultadas": 0,
            "alteradas": 0,
            "alertas_criados": 0,
            "falhas": [],
        }
    fetcher = fetcher or buscar_fonte_http
    fontes = tuple(fontes or fontes_configuradas())
    resumo = {
        "contrato": CONTRATO_MONITOR,
        "habilitado": habilitado,
        "consultadas": 0,
        "alteradas": 0,
        "alertas_criados": 0,
        "falhas": [],
    }
    for fonte in fontes:
        _validar_url_oficial(fonte["url"])
        estado, _ = FonteAtualizacaoFiscal.objects.update_or_create(
            codigo=fonte["codigo"],
            defaults={"nome": fonte["nome"], "url": fonte["url"]},
        )
        try:
            resposta = fetcher(fonte, estado)
            resumo["consultadas"] += 1
            if int(resposta.get("status", 0)) == 304:
                estado.status = StatusFonteAtualizacaoFiscal.OK
                estado.ultima_consulta_em = timezone.now()
                estado.ultima_mensagem = "Fonte sem alteração desde a última consulta."
                estado.save(update_fields=["status", "ultima_consulta_em", "ultima_mensagem", "atualizado_em"])
                continue
            _validar_url_oficial(resposta.get("url_final") or fonte["url"])
            itens = extrair_itens_relevantes(resposta.get("conteudo") or b"")
            novo_hash = _conteudo_sha256(itens)
            primeira_consulta = not estado.conteudo_sha256
            alterada = bool(estado.conteudo_sha256 and estado.conteudo_sha256 != novo_hash)
            anteriores = {
                item.get("fingerprint")
                for item in (estado.itens_snapshot or [])
                if isinstance(item, dict)
            }
            novos = [item for item in itens if item["fingerprint"] not in anteriores]
            criados = 0
            with transaction.atomic():
                estado = FonteAtualizacaoFiscal.objects.select_for_update().get(pk=estado.pk)
                if alterada:
                    for item in novos[:50]:
                        _, criado = AlertaAtualizacaoFiscal.objects.get_or_create(
                            fonte=estado,
                            fingerprint=item["fingerprint"],
                            defaults={
                                "titulo": item["titulo"],
                                "url_referencia": resposta.get("url_final") or fonte["url"],
                            },
                        )
                        criados += int(criado)
                    if not novos:
                        fingerprint = _fingerprint(f"{fonte['codigo']}:{novo_hash}")
                        _, criado = AlertaAtualizacaoFiscal.objects.get_or_create(
                            fonte=estado,
                            fingerprint=fingerprint,
                            defaults={
                                "titulo": "A fonte oficial teve conteúdo fiscal relevante alterado.",
                                "url_referencia": resposta.get("url_final") or fonte["url"],
                            },
                        )
                        criados += int(criado)
                agora = timezone.now()
                estado.status = StatusFonteAtualizacaoFiscal.OK
                estado.etag = str(resposta.get("etag") or "")[:255]
                estado.ultima_modificacao_http = str(resposta.get("ultima_modificacao") or "")[:255]
                estado.conteudo_sha256 = novo_hash
                estado.itens_snapshot = itens
                estado.ultima_consulta_em = agora
                if alterada:
                    estado.ultima_alteracao_em = agora
                estado.ultima_mensagem = (
                    "Baseline oficial registrado; nenhum alerta foi criado."
                    if primeira_consulta
                    else f"Consulta concluída; {criados} atualização(ões) nova(s)."
                )
                estado.save()
            if alterada:
                resumo["alteradas"] += 1
            resumo["alertas_criados"] += criados
            if criados:
                LogAuditoria.objects.create(
                    modulo="fiscal",
                    acao="ATUALIZACOES_FISCAIS_DETECTADAS",
                    descricao=f"{criados} atualização(ões) detectada(s) em {fonte['nome']}.",
                    objeto_tipo="FonteAtualizacaoFiscal",
                    objeto_id=str(estado.pk),
                )
        except (MonitorAtualizacaoFiscalError, ValueError, TypeError) as exc:
            _registrar_falha(estado, exc)
            resumo["falhas"].append({"fonte": fonte["codigo"], "mensagem": str(exc)})
    return resumo


def resumo_monitor_atualizacoes():
    return {
        "contrato": CONTRATO_MONITOR,
        "habilitado": bool(getattr(settings, "FISCAL_UPDATE_MONITOR_ENABLED", False)),
        "fontes": FonteAtualizacaoFiscal.objects.count(),
        "fontes_com_erro": FonteAtualizacaoFiscal.objects.filter(status=StatusFonteAtualizacaoFiscal.ERRO).count(),
        "alertas_novos": AlertaAtualizacaoFiscal.objects.filter(status=StatusAlertaAtualizacaoFiscal.NOVO).count(),
        "ultima_consulta_em": FonteAtualizacaoFiscal.objects.order_by("-ultima_consulta_em").values_list("ultima_consulta_em", flat=True).first(),
    }