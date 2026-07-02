import re
from decimal import Decimal
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import (
    ConfiguracaoFiscal,
    DocumentoFiscal,
    NaturezaOperacao,
    SerieFiscal,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
)

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
ET.register_namespace("", NFE_NS)

CODIGOS_UF_IBGE = {
    "RO": "11",
    "AC": "12",
    "AM": "13",
    "RR": "14",
    "PA": "15",
    "AP": "16",
    "TO": "17",
    "MA": "21",
    "PI": "22",
    "CE": "23",
    "RN": "24",
    "PB": "25",
    "PE": "26",
    "AL": "27",
    "SE": "28",
    "BA": "29",
    "MG": "31",
    "ES": "32",
    "RJ": "33",
    "SP": "35",
    "PR": "41",
    "SC": "42",
    "RS": "43",
    "MS": "50",
    "MT": "51",
    "GO": "52",
    "DF": "53",
}


def _somente_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def _valor(valor, casas=2):
    quantizador = Decimal("1." + ("0" * casas))
    return str((valor or Decimal("0")).quantize(quantizador))


def _texto(parent, tag, valor):
    elemento = ET.SubElement(parent, f"{{{NFE_NS}}}{tag}")
    elemento.text = str(valor)
    return elemento


def _codigo_pagamento(tipo):
    tipo = (tipo or "").upper()
    if "DINHEIRO" in tipo:
        return "01"
    if "CREDITO" in tipo or "CARTAO_CREDITO" in tipo:
        return "03"
    if "DEBITO" in tipo or "CARTAO_DEBITO" in tipo:
        return "04"
    if "CREDIARIO" in tipo or "CONVENIO" in tipo:
        return "05"
    if "PIX" in tipo:
        return "17"
    return "99"


def _icms_produto(imposto, produto, configuracao):
    icms = ET.SubElement(imposto, f"{{{NFE_NS}}}ICMS")
    simples = "SIMPLES" in configuracao.regime_tributario.upper()
    if simples:
        grupo = ET.SubElement(icms, f"{{{NFE_NS}}}ICMSSN102")
        _texto(grupo, "orig", produto.origem_mercadoria)
        _texto(grupo, "CSOSN", produto.csosn or "102")
    else:
        grupo = ET.SubElement(icms, f"{{{NFE_NS}}}ICMS00")
        _texto(grupo, "orig", produto.origem_mercadoria)
        _texto(grupo, "CST", produto.cst_icms or "00")
        _texto(grupo, "modBC", "3")
        _texto(grupo, "vBC", "0.00")
        _texto(grupo, "pICMS", _valor(produto.aliquota_icms or Decimal("0")))
        _texto(grupo, "vICMS", "0.00")


def pendencias_produto_fiscal(produto, regimes_tributarios=None):
    pendencias = []
    regimes = [regime.upper() for regime in (regimes_tributarios or []) if regime]
    exige_simples = not regimes or any("SIMPLES" in regime for regime in regimes)
    exige_normal = not regimes or any("SIMPLES" not in regime for regime in regimes)
    if not re.fullmatch(r"\d{8}", produto.ncm or ""):
        pendencias.append("NCM com 8 digitos")
    if produto.cest and not re.fullmatch(r"\d{7}", produto.cest):
        pendencias.append("CEST com 7 digitos")
    if not produto.origem_mercadoria:
        pendencias.append("Origem da mercadoria")
    if exige_simples and not re.fullmatch(r"\d{3}", produto.csosn or ""):
        pendencias.append("CSOSN com 3 digitos")
    if exige_normal and not re.fullmatch(r"\d{2}", produto.cst_icms or ""):
        pendencias.append("CST ICMS com 2 digitos")
    if produto.aliquota_icms is None or produto.aliquota_icms < 0:
        pendencias.append("Aliquota ICMS")
    return pendencias


def gerar_xml_nfce(documento):
    if not documento.venda:
        raise ValidationError("Documento fiscal sem venda vinculada.")
    venda = documento.venda
    configuracao = venda.filial.configuracao_fiscal
    natureza = documento.natureza_operacao
    empresa = venda.filial.empresa
    cnpj_emitente = _somente_digitos(venda.filial.cnpj or empresa.cnpj)
    data_emissao = timezone.localtime(documento.criado_em).replace(microsecond=0).isoformat()

    nfe = ET.Element(f"{{{NFE_NS}}}NFe")
    inf_nfe = ET.SubElement(nfe, f"{{{NFE_NS}}}infNFe", {"versao": "4.00", "Id": f"NFeLOCAL{documento.pk:044d}"})

    ide = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}ide")
    _texto(ide, "cUF", CODIGOS_UF_IBGE.get(venda.filial.uf, "00"))
    _texto(ide, "cNF", f"{documento.pk:08d}"[-8:])
    _texto(ide, "natOp", natureza.descricao[:60])
    _texto(ide, "mod", "65")
    _texto(ide, "serie", documento.serie)
    _texto(ide, "nNF", documento.numero)
    _texto(ide, "dhEmi", data_emissao)
    _texto(ide, "tpNF", "1")
    _texto(ide, "idDest", "1")
    _texto(ide, "cMunFG", venda.filial.codigo_municipio_ibge)
    _texto(ide, "tpImp", "4")
    _texto(ide, "tpEmis", "1")
    _texto(ide, "cDV", "0")
    _texto(ide, "tpAmb", "2" if configuracao.ambiente == "HOMOLOGACAO" else "1")
    _texto(ide, "finNFe", "1")
    _texto(ide, "indFinal", "1")
    _texto(ide, "indPres", "1")
    _texto(ide, "procEmi", "0")
    _texto(ide, "verProc", "SupermercadoERP-0.1")

    emit = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}emit")
    _texto(emit, "CNPJ", cnpj_emitente)
    _texto(emit, "xNome", empresa.razao_social[:60])
    _texto(emit, "xFant", empresa.nome_fantasia[:60])
    _texto(emit, "IE", configuracao.inscricao_estadual)
    _texto(emit, "CRT", "1" if "SIMPLES" in configuracao.regime_tributario.upper() else "3")

    for numero, item in enumerate(venda.itens.select_related("produto"), start=1):
        produto = item.produto
        det = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}det", {"nItem": str(numero)})
        prod = ET.SubElement(det, f"{{{NFE_NS}}}prod")
        _texto(prod, "cProd", produto.codigo_interno or produto.codigo_barras or produto.pk)
        _texto(prod, "cEAN", produto.codigo_barras or "SEM GTIN")
        _texto(prod, "xProd", produto.nome[:120])
        _texto(prod, "NCM", produto.ncm)
        if produto.cest:
            _texto(prod, "CEST", produto.cest)
        _texto(prod, "CFOP", natureza.cfop)
        _texto(prod, "uCom", produto.unidade)
        _texto(prod, "qCom", _valor(item.quantidade, casas=3))
        _texto(prod, "vUnCom", _valor(item.preco_unitario_venda, casas=2))
        _texto(prod, "vProd", _valor(item.total + item.desconto))
        _texto(prod, "cEANTrib", produto.codigo_barras or "SEM GTIN")
        _texto(prod, "uTrib", produto.unidade)
        _texto(prod, "qTrib", _valor(item.quantidade, casas=3))
        _texto(prod, "vUnTrib", _valor(item.preco_unitario_venda, casas=2))
        if item.desconto:
            _texto(prod, "vDesc", _valor(item.desconto))
        _texto(prod, "indTot", "1")
        imposto = ET.SubElement(det, f"{{{NFE_NS}}}imposto")
        _icms_produto(imposto, produto, configuracao)

    total = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}total")
    icmstot = ET.SubElement(total, f"{{{NFE_NS}}}ICMSTot")
    _texto(icmstot, "vBC", "0.00")
    _texto(icmstot, "vICMS", "0.00")
    _texto(icmstot, "vICMSDeson", "0.00")
    _texto(icmstot, "vFCP", "0.00")
    _texto(icmstot, "vBCST", "0.00")
    _texto(icmstot, "vST", "0.00")
    _texto(icmstot, "vFCPST", "0.00")
    _texto(icmstot, "vFCPSTRet", "0.00")
    _texto(icmstot, "vProd", _valor(venda.total_bruto))
    _texto(icmstot, "vFrete", "0.00")
    _texto(icmstot, "vSeg", "0.00")
    _texto(icmstot, "vDesc", _valor(venda.desconto))
    _texto(icmstot, "vII", "0.00")
    _texto(icmstot, "vIPI", "0.00")
    _texto(icmstot, "vIPIDevol", "0.00")
    _texto(icmstot, "vPIS", "0.00")
    _texto(icmstot, "vCOFINS", "0.00")
    _texto(icmstot, "vOutro", "0.00")
    _texto(icmstot, "vNF", _valor(venda.total_liquido))

    transp = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}transp")
    _texto(transp, "modFrete", "9")

    pag = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}pag")
    for pagamento in venda.pagamentos.select_related("forma_pagamento"):
        det_pag = ET.SubElement(pag, f"{{{NFE_NS}}}detPag")
        _texto(det_pag, "indPag", "0")
        _texto(det_pag, "tPag", _codigo_pagamento(pagamento.forma_pagamento.tipo))
        _texto(det_pag, "vPag", _valor(pagamento.valor))

    inf_adic = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}infAdic")
    _texto(inf_adic, "infCpl", "XML local de preparacao. Assinatura e transmissao SEFAZ pendentes.")

    return ET.tostring(nfe, encoding="unicode", xml_declaration=True)


def salvar_xml_documento(documento):
    documento.xml_conteudo = gerar_xml_nfce(documento)
    documento.xml_gerado_em = timezone.now()
    documento.save(update_fields=["xml_conteudo", "xml_gerado_em", "atualizado_em"])
    return documento.xml_conteudo


def pendencias_preparacao_fiscal(venda, configuracao, natureza):
    erros = []
    if not configuracao.inscricao_estadual.strip():
        erros.append("Informe a inscricao estadual da filial.")
    if not configuracao.regime_tributario.strip():
        erros.append("Informe o regime tributario da filial.")
    if not configuracao.csc_id.strip() or not configuracao.csc_token.strip():
        erros.append("Informe o ID e o token CSC da NFC-e.")
    if not venda.filial.uf or venda.filial.uf not in CODIGOS_UF_IBGE:
        erros.append("Informe a UF da filial para emissao fiscal.")
    if not re.fullmatch(r"\d{7}", venda.filial.codigo_municipio_ibge or ""):
        erros.append("Informe o codigo IBGE do municipio da filial com 7 digitos.")
    if not configuracao.certificado_configurado:
        erros.append("Envie o certificado A1 da filial.")
    elif configuracao.certificado_status == "vencido":
        erros.append("O certificado A1 da filial esta vencido.")
    if not natureza:
        erros.append("Cadastre uma natureza de operacao NFC-e ativa.")
    elif not re.fullmatch(r"[1-7]\d{3}", natureza.cfop.strip()):
        erros.append("A natureza de operacao deve possuir CFOP valido com 4 digitos.")

    simples_nacional = "SIMPLES" in configuracao.regime_tributario.upper()
    itens = list(venda.itens.select_related("produto"))
    if not itens:
        erros.append("A venda nao possui itens para emissao fiscal.")
    for item in itens:
        produto = item.produto
        prefixo = f"Produto {produto.nome}:"
        if not re.fullmatch(r"\d{8}", produto.ncm or ""):
            erros.append(f"{prefixo} informe NCM com 8 digitos.")
        if not produto.origem_mercadoria:
            erros.append(f"{prefixo} informe a origem da mercadoria.")
        if simples_nacional:
            if not re.fullmatch(r"\d{3}", produto.csosn or ""):
                erros.append(f"{prefixo} informe CSOSN com 3 digitos para o Simples Nacional.")
        elif not re.fullmatch(r"\d{2}", produto.cst_icms or ""):
            erros.append(f"{prefixo} informe CST ICMS com 2 digitos.")
        if produto.aliquota_icms is None or produto.aliquota_icms < 0:
            erros.append(f"{prefixo} informe a aliquota de ICMS, inclusive quando for zero.")
    return erros


def validar_preparacao_fiscal(venda, configuracao, natureza):
    erros = pendencias_preparacao_fiscal(venda, configuracao, natureza)
    if erros:
        raise ValidationError(erros)


@transaction.atomic
def preparar_documento_venda(venda, usuario, natureza_operacao=None, ip=None):
    documento_existente = venda.documentos_fiscais.exclude(status=StatusDocumentoFiscal.CANCELADO).first()
    if documento_existente:
        raise ValidationError(f"A venda {venda.id} ja possui documento fiscal em andamento.")

    try:
        configuracao = venda.filial.configuracao_fiscal
    except ConfiguracaoFiscal.DoesNotExist as exc:
        raise ValidationError("Configure os dados fiscais da filial antes de preparar a NFC-e.") from exc
    if not configuracao.ativo:
        raise ValidationError("A configuracao fiscal da filial esta inativa.")

    serie = (
        SerieFiscal.objects.select_for_update()
        .filter(filial=venda.filial, tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True)
        .order_by("serie")
        .first()
    )
    if not serie:
        raise ValidationError("Cadastre uma serie NFC-e ativa para a filial.")

    natureza = natureza_operacao or NaturezaOperacao.objects.filter(tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True).first()
    validar_preparacao_fiscal(venda, configuracao, natureza)
    numero = serie.proximo_numero
    documento = DocumentoFiscal.objects.create(
        filial=venda.filial,
        venda=venda,
        natureza_operacao=natureza,
        tipo_documento=TipoDocumentoFiscal.NFCE,
        ambiente=configuracao.ambiente,
        serie=serie.serie,
        numero=numero,
        status=StatusDocumentoFiscal.PRONTO,
        valor_total=venda.total_liquido,
        usuario=usuario,
        mensagem_retorno="Documento preparado localmente. Transmissao SEFAZ pendente de integracao fiscal.",
    )
    salvar_xml_documento(documento)
    serie.proximo_numero = numero + 1
    serie.save(update_fields=["proximo_numero"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="PREPARA_DOCUMENTO",
        descricao=f"Documento fiscal {documento.id} preparado para venda {venda.id}.",
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.id),
        ip=ip,
    )
    return documento


def cancelar_documento(documento, usuario, motivo, ip=None):
    if documento.status not in {StatusDocumentoFiscal.PRONTO, StatusDocumentoFiscal.REJEITADO}:
        raise ValidationError("Somente documentos prontos ou rejeitados podem ser cancelados nesta etapa.")
    if not motivo.strip():
        raise ValidationError("Informe o motivo do cancelamento.")
    documento.status = StatusDocumentoFiscal.CANCELADO
    documento.motivo_cancelamento = motivo.strip()
    documento.save(update_fields=["status", "motivo_cancelamento", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="CANCELA_DOCUMENTO",
        descricao=f"Documento fiscal {documento.id} cancelado. Motivo: {motivo.strip()}",
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.id),
        ip=ip,
    )
    return documento
