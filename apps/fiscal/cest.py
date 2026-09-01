"""Catálogo versionado do Código Especificador da Substituição Tributária (CEST)."""

import re
import unicodedata
from datetime import date
from pathlib import Path

from django.utils import timezone
from lxml import html


FONTE_CEST_OFICIAL = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"
ATO_CEST = "Convênio ICMS 142/18 consolidado"
_CABECALHO = ["ITEM", "CEST", "NCM/SH", "DESCRIÇÃO"]


def _texto(elemento):
    return " ".join(elemento.xpath("string(.)").split())


def _sem_acentos(valor):
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", valor or "")
        if not unicodedata.combining(caractere)
    )


def _prefixos_ncm(valor):
    valor = " ".join((valor or "").split())
    if not valor:
        return []
    capitulos = "CAPITULO" in _sem_acentos(valor).upper()
    prefixos = []
    for token in re.findall(r"\d+(?:\.\d+)*", valor):
        codigo = re.sub(r"\D", "", token)
        if capitulos:
            if len(codigo) != 2:
                raise ValueError(f"Referência de capítulo NCM inválida: {valor!r}.")
        elif len(codigo) not in {4, 5, 6, 7, 8}:
            raise ValueError(f"Referência NCM/SH inválida: {valor!r}.")
        if codigo not in prefixos:
            prefixos.append(codigo)
    if not prefixos:
        raise ValueError(f"Referência NCM/SH não reconhecida: {valor!r}.")
    return prefixos


def ler_catalogo_cest_html(caminho, referencia_em):
    """Extrai a redação vigente dos anexos CEST da página consolidada do CONFAZ."""
    caminho = Path(caminho)
    try:
        referencia_em = date.fromisoformat(str(referencia_em))
    except ValueError as exc:
        raise ValueError("Referência CEST deve usar AAAA-MM-DD.") from exc
    try:
        parser = html.HTMLParser(encoding="utf-8", no_network=True, recover=True)
        raiz = html.fromstring(caminho.read_bytes(), parser=parser)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Arquivo não é um HTML CEST válido em UTF-8.") from exc

    segmentos = {}
    for tabela in raiz.xpath("//table"):
        linhas = tabela.xpath(".//tr")
        if not linhas:
            continue
        for tr in linhas[1:]:
            celulas = [_texto(no) for no in tr.xpath("./th|./td")]
            if len(celulas) == 3 and re.fullmatch(r"\d{2}", celulas[2]):
                segmentos[celulas[2]] = celulas[1]
        if segmentos:
            break
    if not segmentos:
        raise ValueError("HTML CEST sem a tabela oficial de segmentos.")

    vistos = set()
    itens = []
    quantidade_linhas_origem = 0
    tabelas_anexos = 0
    for tabela in raiz.xpath("//table"):
        linhas = tabela.xpath(".//tr")
        if not linhas:
            continue
        cabecalho = [_texto(no).upper() for no in linhas[0].xpath("./th|./td")]
        if cabecalho != _CABECALHO:
            continue
        tabelas_anexos += 1
        for tr in linhas[1:]:
            celulas = [_texto(no) for no in tr.xpath("./th|./td")]
            if len(celulas) != 4 or not re.fullmatch(r"\d{2}\.\d{3}\.\d{2}", celulas[1]):
                continue
            quantidade_linhas_origem += 1
            codigo_formatado = celulas[1]
            codigo = re.sub(r"\D", "", codigo_formatado)
            if codigo in vistos:
                continue
            vistos.add(codigo)
            descricao = celulas[3].strip()
            if descricao.upper() == "REVOGADO":
                continue
            if not descricao:
                raise ValueError(f"CEST {codigo_formatado} sem descrição.")
            segmento_codigo = codigo[:2]
            segmento_nome = segmentos.get(segmento_codigo)
            if not segmento_nome:
                raise ValueError(f"CEST {codigo_formatado} usa segmento não catalogado.")
            itens.append(
                {
                    "codigo": codigo,
                    "codigo_formatado": codigo_formatado,
                    "item": celulas[0],
                    "segmento_codigo": segmento_codigo,
                    "segmento_nome": segmento_nome,
                    "ncm_sh_original": celulas[2],
                    "ncm_prefixos": _prefixos_ncm(celulas[2]),
                    "descricao": descricao,
                }
            )
    if not tabelas_anexos or not itens:
        raise ValueError("Nenhum anexo CEST vigente foi encontrado no HTML oficial.")
    return {
        "referencia_em": referencia_em,
        "ato": ATO_CEST,
        "itens": itens,
        "quantidade_linhas_origem": quantidade_linhas_origem,
        "quantidade_tabelas_origem": tabelas_anexos,
    }


def catalogo_cest_vigente(data_referencia=None):
    from .models import CatalogoCEST

    data_referencia = data_referencia or timezone.localdate()
    if isinstance(data_referencia, str):
        data_referencia = date.fromisoformat(data_referencia)
    return (
        CatalogoCEST.objects.filter(ativo=True, referencia_em__lte=data_referencia)
        .order_by("-referencia_em", "-importado_em")
        .first()
    )


def queryset_codigos_cest_vigentes(data_referencia=None):
    catalogo = catalogo_cest_vigente(data_referencia)
    if not catalogo:
        return None
    return catalogo.itens.values("codigo")


def validar_cest(codigo, ncm=None, data_referencia=None):
    """Valida existência e compatibilidade objetiva; descrição exige análise fiscal."""
    codigo = re.sub(r"\D", "", str(codigo or ""))
    if not codigo:
        return None
    if not re.fullmatch(r"\d{7}", codigo):
        return "CEST com 7 dígitos"
    catalogo = catalogo_cest_vigente(data_referencia)
    if not catalogo:
        return None
    item = catalogo.itens.filter(codigo=codigo).first()
    if not item:
        return f"CEST {codigo} não consta no catálogo oficial vigente"
    ncm = re.sub(r"\D", "", str(ncm or ""))
    if ncm and re.fullmatch(r"\d{8}", ncm) and item.ncm_prefixos:
        if not any(ncm.startswith(prefixo) for prefixo in item.ncm_prefixos):
            return f"CEST {codigo} não é compatível com a NCM {ncm} no catálogo oficial"
    return None