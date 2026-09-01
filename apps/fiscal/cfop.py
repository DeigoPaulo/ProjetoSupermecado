"""Catálogo versionado do Código Fiscal de Operações e Prestações (CFOP)."""

import re
from datetime import date
from pathlib import Path

from django.utils import timezone
from lxml import html


FONTE_CFOP_OFICIAL = "https://www.confaz.fazenda.gov.br/legislacao/ajustes/2001/AJ_007_01"
ATO_CFOP = "Ajuste SINIEF 07/01 consolidado"
_PADRAO_LINHA = re.compile(r"^([1-7])\.?([0-9]{3})\s*[-–—]\s*(.+)$")


def _texto(elemento):
    return " ".join(elemento.xpath("string(.)").split())


def _metadados_codigo(codigo):
    primeiro = codigo[0]
    if primeiro in "123":
        direcao = "ENTRADA"
    elif primeiro in "567":
        direcao = "SAIDA"
    else:
        raise ValueError(f"CFOP {codigo} possui direção inválida.")
    alcance = {
        "1": "INTERNA",
        "2": "INTERESTADUAL",
        "3": "EXTERIOR",
        "5": "INTERNA",
        "6": "INTERESTADUAL",
        "7": "EXTERIOR",
    }[primeiro]
    return direcao, alcance


def ler_catalogo_cfop_html(caminho, referencia_em):
    """Extrai códigos utilizáveis e notas explicativas da página oficial consolidada."""
    caminho = Path(caminho)
    try:
        referencia_em = date.fromisoformat(str(referencia_em))
    except ValueError as exc:
        raise ValueError("Referência CFOP deve usar AAAA-MM-DD.") from exc
    try:
        parser = html.HTMLParser(encoding="utf-8", no_network=True, recover=True)
        raiz = html.fromstring(caminho.read_bytes(), parser=parser)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Arquivo não é um HTML CFOP válido em UTF-8.") from exc
    conteudo = raiz.xpath('//*[@id="content-core"]')
    raiz = conteudo[0] if conteudo else raiz
    textos = [
        _texto(no)
        for no in raiz.xpath(".//p|.//h1|.//h2|.//h3")
        if _texto(no)
    ]

    posicoes = []
    for indice, texto in enumerate(textos):
        correspondencia = _PADRAO_LINHA.match(texto)
        if correspondencia:
            codigo = correspondencia.group(1) + correspondencia.group(2)
            posicoes.append((indice, codigo, correspondencia.group(3).strip()))
    if not posicoes:
        raise ValueError("HTML CFOP sem a tabela oficial de códigos.")

    itens = []
    vistos = set()
    quantidade_agrupadores = 0
    for indice_posicao, (indice_texto, codigo, titulo) in enumerate(posicoes):
        if codigo in vistos:
            raise ValueError(f"HTML CFOP contém código duplicado: {codigo}.")
        vistos.add(codigo)
        if codigo.endswith(("00", "50")):
            quantidade_agrupadores += 1
            continue
        if titulo.upper() == "REVOGADO":
            continue
        proximo_indice = (
            posicoes[indice_posicao + 1][0]
            if indice_posicao + 1 < len(posicoes)
            else len(textos)
        )
        explicacoes = [
            texto
            for texto in textos[indice_texto + 1 : proximo_indice]
            if texto.lower().startswith("classificam-se")
        ]
        if len(explicacoes) != 1:
            raise ValueError(
                f"CFOP {codigo} deve possuir exatamente uma nota explicativa oficial; "
                f"encontradas {len(explicacoes)}."
            )
        direcao, alcance = _metadados_codigo(codigo)
        itens.append(
            {
                "codigo": codigo,
                "codigo_formatado": f"{codigo[0]}.{codigo[1:]}",
                "titulo": titulo,
                "nota_explicativa": explicacoes[0],
                "direcao": direcao,
                "alcance": alcance,
            }
        )
    if not itens:
        raise ValueError("Nenhum CFOP utilizável foi encontrado no HTML oficial.")
    return {
        "referencia_em": referencia_em,
        "ato": ATO_CFOP,
        "itens": itens,
        "quantidade_linhas_origem": len(posicoes),
        "quantidade_agrupadores": quantidade_agrupadores,
    }


def catalogo_cfop_vigente(data_referencia=None):
    from .models import CatalogoCFOP

    data_referencia = data_referencia or timezone.localdate()
    if isinstance(data_referencia, str):
        data_referencia = date.fromisoformat(data_referencia)
    return (
        CatalogoCFOP.objects.filter(ativo=True, referencia_em__lte=data_referencia)
        .order_by("-referencia_em", "-importado_em")
        .first()
    )


def validar_cfop(codigo, *, direcao=None, alcance=None, modelo=None, data_referencia=None):
    codigo = re.sub(r"\D", "", str(codigo or ""))
    if not re.fullmatch(r"[1-7]\d{3}", codigo):
        return "CFOP válido com 4 dígitos"
    if codigo.endswith(("00", "50")):
        return f"CFOP {codigo} é agrupador e não pode ser usado na operação"
    catalogo = catalogo_cfop_vigente(data_referencia)
    if not catalogo:
        return None
    item = catalogo.itens.filter(codigo=codigo).first()
    if not item:
        return f"CFOP {codigo} não consta no catálogo oficial vigente"
    if direcao and item.direcao != str(direcao).upper():
        direcao_esperada = {"ENTRADA": "entrada", "SAIDA": "saída"}.get(
            str(direcao).upper(), str(direcao).lower()
        )
        return f"CFOP {codigo} é de {item.get_direcao_display().lower()}, não de {direcao_esperada}"
    if alcance and item.alcance != str(alcance).upper():
        return f"CFOP {codigo} possui alcance {item.get_alcance_display().lower()}"
    modelo = str(modelo or "").upper().replace("-", "")
    if modelo in {"65", "NFCE"} and (item.direcao != "SAIDA" or item.alcance != "INTERNA"):
        return f"NFC-e exige CFOP de saída interna; {codigo} é {item.get_direcao_display().lower()} {item.get_alcance_display().lower()}"
    if modelo in {"55", "NFE"} and item.direcao != "SAIDA":
        return f"NF-e emitida pelo ERP exige CFOP de saída; {codigo} é de {item.get_direcao_display().lower()}"
    return None