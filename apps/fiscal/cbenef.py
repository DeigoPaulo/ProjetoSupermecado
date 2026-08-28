"""Catálogo versionado de códigos de benefício fiscal (cBenef)."""

import hashlib
import re
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

from django.db import models
from django.utils import timezone


CODIGO_CBENEF_GO_RE = re.compile(r"^GO\d{6}$")
CODIGOS_ESPECIAIS_GO = {"SEM CBENEF"}
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def sha256_arquivo(caminho):
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _texto_celula(celula):
    partes = [no.text or "" for no in celula.findall(f".//{{{WORD_NS}}}t")]
    return " ".join(" ".join(partes).split())


def ler_catalogo_cbenef_go_docx(caminho):
    """Lê a tabela consolidada publicada em DOCX pela Economia de Goiás."""
    try:
        with zipfile.ZipFile(caminho) as pacote:
            xml = pacote.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ValueError("Arquivo não é um DOCX válido com word/document.xml.") from exc

    raiz = ET.fromstring(xml)
    cabecalho = None
    itens = {}
    duplicados = []
    for linha in raiz.findall(f".//{{{WORD_NS}}}tr"):
        celulas = [_texto_celula(celula) for celula in linha.findall(f"./{{{WORD_NS}}}tc")]
        if not celulas:
            continue
        if celulas[0].upper() == "CÓDIGO" and any(valor.upper() == "CST 20" for valor in celulas):
            cabecalho = [valor.upper() for valor in celulas]
            continue
        codigo = celulas[0].strip().upper()
        if not (CODIGO_CBENEF_GO_RE.fullmatch(codigo) or codigo in CODIGOS_ESPECIAIS_GO):
            continue
        if not cabecalho or len(celulas) < len(cabecalho):
            raise ValueError(f"Linha {codigo} não corresponde ao cabeçalho consolidado da tabela.")
        csts = []
        for indice, titulo in enumerate(cabecalho):
            match = re.fullmatch(r"CST (\d{2})", titulo)
            if match and celulas[indice].strip().upper() == "SIM":
                csts.append(match.group(1))
        if not csts:
            raise ValueError(f"Código {codigo} não possui CST compatível marcado na tabela oficial.")
        if codigo in itens:
            duplicados.append(codigo)
        itens[codigo] = {
            "codigo": codigo,
            "csts": sorted(set(csts)),
            "dispositivo_legal": celulas[-3].strip(),
            "descricao": celulas[-2].strip(),
            "observacao": celulas[-1].strip(),
        }
    if not itens:
        raise ValueError("Nenhum código cBenef de Goiás foi encontrado no arquivo.")
    return list(itens.values()), sorted(set(duplicados))


def catalogo_cbenef_vigente(uf, data_referencia=None):
    from .models import CatalogoBeneficioFiscal

    data_referencia = data_referencia or timezone.localdate()
    if isinstance(data_referencia, str):
        data_referencia = date.fromisoformat(data_referencia)
    return (
        CatalogoBeneficioFiscal.objects.filter(
            uf=(uf or "").strip().upper(), ativo=True, vigencia_inicio__lte=data_referencia
        )
        .filter(models.Q(vigencia_fim__isnull=True) | models.Q(vigencia_fim__gte=data_referencia))
        .order_by("-vigencia_inicio", "-importado_em")
        .first()
    )


def codigos_cbenef_go_validos(cst=None, data_referencia=None):
    catalogo = catalogo_cbenef_vigente("GO", data_referencia)
    if not catalogo:
        return set()
    registros = catalogo.itens.values_list("codigo", "csts")
    if not cst:
        return {codigo for codigo, _csts in registros}
    cst = str(cst)
    return {codigo for codigo, csts in registros if cst in csts}


def validar_cbenef_go(codigo, cst, data_referencia=None):
    """Retorna uma pendência segura ou ``None`` para código/CST vigente."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return None
    if not (CODIGO_CBENEF_GO_RE.fullmatch(codigo) or codigo in CODIGOS_ESPECIAIS_GO):
        return "cBenef de Goiás no formato GO + 6 dígitos ou literal oficial SEM CBENEF"
    catalogo = catalogo_cbenef_vigente("GO", data_referencia)
    if not catalogo:
        return "Catálogo oficial cBenef de Goiás não instalado para a data da operação"
    item = catalogo.itens.filter(codigo=codigo).first()
    if not item:
        return f"cBenef {codigo} não consta no catálogo oficial de Goiás vigente"
    cst = (cst or "").strip()
    if cst and cst not in item.csts:
        return f"cBenef {codigo} incompatível com CST ICMS {cst} no catálogo oficial de Goiás"
    return None
