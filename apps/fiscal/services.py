import re
from datetime import timedelta
from decimal import Decimal
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.vendas.models import TipoDocumentoConsumidor

from .adapters import SefazAdapterError, carregar_adaptador_sefaz, normalizar_retorno_transmissao
from .assinaturas import assinar_xml_documento, verificar_assinatura_xml
from .validacoes import validar_xml_pre_transmissao
from .qrcode_nfce import gerar_url_qrcode_nfce
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


def _digito_verificador_chave(chave_sem_dv):
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(digito) * pesos[indice % len(pesos)] for indice, digito in enumerate(reversed(chave_sem_dv)))
    resultado = 11 - (soma % 11)
    return "0" if resultado >= 10 else str(resultado)


def _chave_acesso_documento(documento, filial, modelo, tipo_emissao):
    cnpj = _somente_digitos(filial.cnpj or filial.empresa.cnpj)
    if len(cnpj) != 14:
        raise ValidationError("CNPJ do emitente deve possuir 14 digitos para gerar a chave fiscal.")
    codigo_uf = CODIGOS_UF_IBGE.get(filial.uf)
    if not codigo_uf:
        raise ValidationError("UF do emitente invalida para gerar a chave fiscal.")
    data = timezone.localtime(documento.criado_em).strftime("%y%m")
    serie = f"{documento.serie:03d}"
    numero = f"{documento.numero:09d}"
    codigo_numerico = f"{documento.pk:08d}"[-8:]
    base = f"{codigo_uf}{data}{cnpj}{modelo}{serie}{numero}{tipo_emissao}{codigo_numerico}"
    return f"{base}{_digito_verificador_chave(base)}", codigo_numerico

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
    if "VALE_ALIMENTACAO" in tipo:
        return "10"
    if "VALE_REFEICAO" in tipo:
        return "11"
    if "CREDIARIO" in tipo or "CONVENIO" in tipo:
        return "05"
    if "PIX" in tipo:
        return "17"
    return "99"


def _documento_consumidor_nfce(venda):
    tipo = venda.documento_consumidor_tipo
    documento = _somente_digitos(venda.documento_consumidor)
    if not documento and venda.cliente and venda.cliente.cpf_cnpj:
        documento = _somente_digitos(venda.cliente.cpf_cnpj)
        tipo = TipoDocumentoConsumidor.CPF if len(documento) == 11 else TipoDocumentoConsumidor.CNPJ
    if tipo == TipoDocumentoConsumidor.NAO_IDENTIFICADO or not documento:
        return None
    if tipo == TipoDocumentoConsumidor.CPF and len(documento) == 11:
        return {"tipo": TipoDocumentoConsumidor.CPF, "documento": documento}
    if tipo == TipoDocumentoConsumidor.ESTRANGEIRO and venda.documento_consumidor:
        return {"tipo": TipoDocumentoConsumidor.ESTRANGEIRO, "documento": venda.documento_consumidor.strip()[:20]}
    if tipo == TipoDocumentoConsumidor.CNPJ or len(documento) == 14:
        raise ValidationError("NFC-e modelo 65 nao deve ser preparada para consumidor identificado por CNPJ; emita NF-e modelo 55.")
    raise ValidationError("Documento do consumidor invalido para NFC-e.")


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
    em_contingencia = documento.status == StatusDocumentoFiscal.CONTINGENCIA
    tipo_emissao = "9" if em_contingencia else "1"
    chave_acesso, codigo_numerico = _chave_acesso_documento(documento, venda.filial, "65", tipo_emissao)
    documento.chave_acesso = chave_acesso

    nfe = ET.Element(f"{{{NFE_NS}}}NFe")
    inf_nfe = ET.SubElement(nfe, f"{{{NFE_NS}}}infNFe", {"versao": "4.00", "Id": f"NFe{chave_acesso}"})

    ide = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}ide")
    _texto(ide, "cUF", CODIGOS_UF_IBGE.get(venda.filial.uf, "00"))
    _texto(ide, "cNF", codigo_numerico)
    _texto(ide, "natOp", natureza.descricao[:60])
    _texto(ide, "mod", "65")
    _texto(ide, "serie", documento.serie)
    _texto(ide, "nNF", documento.numero)
    _texto(ide, "dhEmi", data_emissao)
    _texto(ide, "tpNF", "1")
    _texto(ide, "idDest", "1")
    _texto(ide, "cMunFG", venda.filial.codigo_municipio_ibge)
    _texto(ide, "tpImp", "4")
    _texto(ide, "tpEmis", tipo_emissao)
    _texto(ide, "cDV", chave_acesso[-1])
    _texto(ide, "tpAmb", "2" if configuracao.ambiente == "HOMOLOGACAO" else "1")
    _texto(ide, "finNFe", "1")
    _texto(ide, "indFinal", "1")
    _texto(ide, "indPres", "1")
    _texto(ide, "procEmi", "0")
    _texto(ide, "verProc", "SupermercadoERP-0.1")
    if em_contingencia:
        _texto(ide, "dhCont", timezone.localtime(documento.contingencia_iniciada_em).replace(microsecond=0).isoformat())
        _texto(ide, "xJust", documento.contingencia_justificativa)

    emit = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}emit")
    _texto(emit, "CNPJ", cnpj_emitente)
    _texto(emit, "xNome", empresa.razao_social[:60])
    _texto(emit, "xFant", empresa.nome_fantasia[:60])
    _texto(emit, "IE", configuracao.inscricao_estadual)
    _texto(emit, "CRT", "1" if "SIMPLES" in configuracao.regime_tributario.upper() else "3")

    consumidor = _documento_consumidor_nfce(venda)
    if consumidor:
        dest = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}dest")
        if consumidor["tipo"] == TipoDocumentoConsumidor.CPF:
            _texto(dest, "CPF", consumidor["documento"])
        else:
            _texto(dest, "idEstrangeiro", consumidor["documento"])
        _texto(dest, "indIEDest", "9")

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

    inf_supl = ET.SubElement(nfe, f"{{{NFE_NS}}}infNFeSupl")
    _texto(inf_supl, "qrCode", gerar_url_qrcode_nfce(documento, configuracao))
    _texto(inf_supl, "urlChave", configuracao.url_consulta_nfce.strip())

    return ET.tostring(nfe, encoding="unicode", xml_declaration=True)


def _documento_destinatario_pedido(pedido):
    tipo = pedido.documento_cliente_tipo
    documento = _somente_digitos(pedido.documento_cliente)
    if not documento and pedido.cliente and pedido.cliente.cpf_cnpj:
        documento = _somente_digitos(pedido.cliente.cpf_cnpj)
        tipo = TipoDocumentoConsumidor.CPF if len(documento) == 11 else TipoDocumentoConsumidor.CNPJ
    if tipo == TipoDocumentoConsumidor.CPF and len(documento) == 11:
        return "CPF", documento
    if tipo == TipoDocumentoConsumidor.CNPJ and len(documento) == 14:
        return "CNPJ", documento
    if tipo == TipoDocumentoConsumidor.ESTRANGEIRO and pedido.documento_cliente:
        return "idEstrangeiro", pedido.documento_cliente.strip()[:20]
    raise ValidationError("Pedido online precisa ter CPF, CNPJ ou documento estrangeiro do destinatario para NF-e.")


def gerar_xml_nfe_pedido_online(documento):
    if not documento.pedido_online:
        raise ValidationError("Documento fiscal sem pedido online vinculado.")
    pedido = documento.pedido_online
    configuracao = pedido.filial.configuracao_fiscal
    natureza = documento.natureza_operacao
    empresa = pedido.filial.empresa
    cnpj_emitente = _somente_digitos(pedido.filial.cnpj or empresa.cnpj)
    data_emissao = timezone.localtime(documento.criado_em).replace(microsecond=0).isoformat()
    doc_tag, doc_valor = _documento_destinatario_pedido(pedido)
    chave_acesso, codigo_numerico = _chave_acesso_documento(documento, pedido.filial, "55", "1")
    documento.chave_acesso = chave_acesso

    nfe = ET.Element(f"{{{NFE_NS}}}NFe")
    inf_nfe = ET.SubElement(nfe, f"{{{NFE_NS}}}infNFe", {"versao": "4.00", "Id": f"NFe{chave_acesso}"})
    ide = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}ide")
    _texto(ide, "cUF", CODIGOS_UF_IBGE.get(pedido.filial.uf, "00"))
    _texto(ide, "cNF", codigo_numerico)
    _texto(ide, "natOp", natureza.descricao[:60])
    _texto(ide, "mod", "55")
    _texto(ide, "serie", documento.serie)
    _texto(ide, "nNF", documento.numero)
    _texto(ide, "dhEmi", data_emissao)
    _texto(ide, "tpNF", "1")
    _texto(ide, "idDest", "1")
    _texto(ide, "cMunFG", pedido.filial.codigo_municipio_ibge)
    _texto(ide, "tpImp", "1")
    _texto(ide, "tpEmis", "1")
    _texto(ide, "cDV", chave_acesso[-1])
    _texto(ide, "tpAmb", "2" if configuracao.ambiente == "HOMOLOGACAO" else "1")
    _texto(ide, "finNFe", "1")
    _texto(ide, "indFinal", "1")
    _texto(ide, "indPres", "2" if pedido.canal == "LOJA_ONLINE" else "9")
    _texto(ide, "procEmi", "0")
    _texto(ide, "verProc", "SupermercadoERP-0.1")

    emit = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}emit")
    _texto(emit, "CNPJ", cnpj_emitente)
    _texto(emit, "xNome", empresa.razao_social[:60])
    _texto(emit, "xFant", empresa.nome_fantasia[:60])
    _texto(emit, "IE", configuracao.inscricao_estadual)
    _texto(emit, "CRT", "1" if "SIMPLES" in configuracao.regime_tributario.upper() else "3")

    dest = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}dest")
    _texto(dest, doc_tag, doc_valor)
    _texto(dest, "xNome", pedido.nome_cliente[:60])
    _texto(dest, "indIEDest", "9")

    for numero, item in enumerate(pedido.itens.select_related("produto"), start=1):
        produto = item.produto
        det = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}det", {"nItem": str(numero)})
        prod = ET.SubElement(det, f"{{{NFE_NS}}}prod")
        _texto(prod, "cProd", produto.codigo_interno or produto.codigo_barras or produto.pk)
        _texto(prod, "cEAN", produto.codigo_barras or "SEM GTIN")
        _texto(prod, "xProd", produto.nome[:120])
        _texto(prod, "NCM", produto.ncm)
        _texto(prod, "CFOP", natureza.cfop)
        _texto(prod, "uCom", produto.unidade)
        _texto(prod, "qCom", _valor(item.quantidade, casas=3))
        _texto(prod, "vUnCom", _valor(item.preco_unitario, casas=2))
        _texto(prod, "vProd", _valor(item.total))
        _texto(prod, "cEANTrib", produto.codigo_barras or "SEM GTIN")
        _texto(prod, "uTrib", produto.unidade)
        _texto(prod, "qTrib", _valor(item.quantidade, casas=3))
        _texto(prod, "vUnTrib", _valor(item.preco_unitario, casas=2))
        _texto(prod, "indTot", "1")
        imposto = ET.SubElement(det, f"{{{NFE_NS}}}imposto")
        _icms_produto(imposto, produto, configuracao)

    total = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}total")
    icmstot = ET.SubElement(total, f"{{{NFE_NS}}}ICMSTot")
    _texto(icmstot, "vProd", _valor(pedido.subtotal))
    _texto(icmstot, "vDesc", _valor(pedido.desconto))
    _texto(icmstot, "vOutro", _valor(pedido.taxa_entrega))
    _texto(icmstot, "vNF", _valor(pedido.total))
    transp = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}transp")
    _texto(transp, "modFrete", "9")
    pag = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}pag")
    det_pag = ET.SubElement(pag, f"{{{NFE_NS}}}detPag")
    _texto(det_pag, "indPag", "0")
    _texto(det_pag, "tPag", _codigo_pagamento(pedido.forma_pagamento))
    _texto(det_pag, "vPag", _valor(pedido.valor_pago or pedido.total))
    inf_adic = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}infAdic")
    complemento = f"Pedido online {pedido.pk}. {pedido.endereco_entrega}".strip()
    _texto(inf_adic, "infCpl", complemento[:500] or "XML local de NF-e para pedido online.")
    return ET.tostring(nfe, encoding="unicode", xml_declaration=True)


def salvar_xml_documento(documento):
    documento.xml_conteudo = gerar_xml_nfe_pedido_online(documento) if documento.tipo_documento == TipoDocumentoFiscal.NFE else gerar_xml_nfce(documento)
    documento.xml_gerado_em = timezone.now()
    documento.save(update_fields=["chave_acesso", "xml_conteudo", "xml_gerado_em", "atualizado_em"])
    return documento.xml_conteudo


def pendencias_preparacao_fiscal(venda, configuracao, natureza):
    erros = []
    if not configuracao.inscricao_estadual.strip():
        erros.append("Informe a inscricao estadual da filial.")
    if not configuracao.regime_tributario.strip():
        erros.append("Informe o regime tributario da filial.")
    if not configuracao.url_qrcode_nfce.strip() or not configuracao.url_consulta_nfce.strip():
        erros.append("Informe as URLs oficiais do QR Code e da consulta NFC-e para a UF e o ambiente.")
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


def pendencias_preparacao_nfe_pedido(pedido, configuracao, natureza):
    erros = []
    if not configuracao.inscricao_estadual.strip():
        erros.append("Informe a inscricao estadual da filial.")
    if not configuracao.regime_tributario.strip():
        erros.append("Informe o regime tributario da filial.")
    if not pedido.filial.uf or pedido.filial.uf not in CODIGOS_UF_IBGE:
        erros.append("Informe a UF da filial para emissao fiscal.")
    if not re.fullmatch(r"\d{7}", pedido.filial.codigo_municipio_ibge or ""):
        erros.append("Informe o codigo IBGE do municipio da filial com 7 digitos.")
    if not configuracao.certificado_configurado:
        erros.append("Envie o certificado A1 da filial.")
    elif configuracao.certificado_status == "vencido":
        erros.append("O certificado A1 da filial esta vencido.")
    if not natureza:
        erros.append("Cadastre uma natureza de operacao NF-e ativa.")
    elif not re.fullmatch(r"[1-7]\d{3}", natureza.cfop.strip()):
        erros.append("A natureza de operacao deve possuir CFOP valido com 4 digitos.")
    try:
        _documento_destinatario_pedido(pedido)
    except ValidationError as exc:
        erros.extend(exc.messages)
    itens = list(pedido.itens.select_related("produto"))
    if not itens:
        erros.append("O pedido online nao possui itens para emissao fiscal.")
    simples_nacional = "SIMPLES" in configuracao.regime_tributario.upper()
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


def validar_preparacao_nfe_pedido(pedido, configuracao, natureza):
    erros = pendencias_preparacao_nfe_pedido(pedido, configuracao, natureza)
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
    _documento_consumidor_nfce(venda)

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



@transaction.atomic
def preparar_documento_pedido_online(pedido, usuario, natureza_operacao=None, ip=None):
    documento_existente = pedido.documentos_fiscais.exclude(status=StatusDocumentoFiscal.CANCELADO).first()
    if documento_existente:
        raise ValidationError(f"O pedido online {pedido.id} ja possui documento fiscal em andamento.")
    try:
        configuracao = pedido.filial.configuracao_fiscal
    except ConfiguracaoFiscal.DoesNotExist as exc:
        raise ValidationError("Configure os dados fiscais da filial antes de preparar a NF-e.") from exc
    if not configuracao.ativo:
        raise ValidationError("A configuracao fiscal da filial esta inativa.")
    serie = (
        SerieFiscal.objects.select_for_update()
        .filter(filial=pedido.filial, tipo_documento=TipoDocumentoFiscal.NFE, ativo=True)
        .order_by("serie")
        .first()
    )
    if not serie:
        raise ValidationError("Cadastre uma serie NF-e ativa para a filial.")
    natureza = natureza_operacao or NaturezaOperacao.objects.filter(tipo_documento=TipoDocumentoFiscal.NFE, ativo=True).first()
    validar_preparacao_nfe_pedido(pedido, configuracao, natureza)
    numero = serie.proximo_numero
    documento = DocumentoFiscal.objects.create(
        filial=pedido.filial,
        pedido_online=pedido,
        natureza_operacao=natureza,
        tipo_documento=TipoDocumentoFiscal.NFE,
        ambiente=configuracao.ambiente,
        serie=serie.serie,
        numero=numero,
        status=StatusDocumentoFiscal.PRONTO,
        valor_total=pedido.total,
        usuario=usuario,
        mensagem_retorno="NF-e de pedido online preparada localmente. Transmissao SEFAZ pendente de integracao fiscal.",
    )
    salvar_xml_documento(documento)
    serie.proximo_numero = numero + 1
    serie.save(update_fields=["proximo_numero"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="PREPARA_NFE_PEDIDO_ONLINE",
        descricao=f"NF-e {documento.id} preparada para pedido online {pedido.id}.",
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.id),
        ip=ip,
    )
    return documento



def tentar_preparar_documento_pos_venda(venda, usuario, ip=None):
    documento_existente = venda.documentos_fiscais.exclude(status=StatusDocumentoFiscal.CANCELADO).first()
    if documento_existente:
        return documento_existente
    try:
        return preparar_documento_venda(venda, usuario, ip=ip)
    except ValidationError as exc:
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="PREPARA_DOCUMENTO_PENDENTE",
            descricao=f"Venda {venda.id} finalizada sem NFC-e preparada automaticamente: {'; '.join(exc.messages)}",
            objeto_tipo="Venda",
            objeto_id=str(venda.id),
            ip=ip,
        )
        return None


@transaction.atomic
def ativar_contingencia_offline(documento, usuario, justificativa, ip=None):
    documento = DocumentoFiscal.objects.select_for_update().select_related("filial").get(pk=documento.pk)
    if documento.tipo_documento != TipoDocumentoFiscal.NFCE:
        raise ValidationError("Contingencia offline nesta etapa e exclusiva para NFC-e modelo 65.")
    if documento.status != StatusDocumentoFiscal.PRONTO:
        raise ValidationError("Somente documento pronto pode entrar em contingencia offline.")
    try:
        configuracao = documento.filial.configuracao_fiscal
    except ConfiguracaoFiscal.DoesNotExist as exc:
        raise ValidationError("Configure os dados fiscais da filial antes de usar contingencia.") from exc
    if not configuracao.ativo or not configuracao.permite_contingencia_offline:
        raise ValidationError("Contingencia offline nao esta autorizada na configuracao fiscal desta filial.")
    justificativa = (justificativa or "").strip()
    if not 15 <= len(justificativa) <= 256:
        raise ValidationError("A justificativa da contingencia deve ter entre 15 e 256 caracteres.")

    agora = timezone.now()
    documento.status = StatusDocumentoFiscal.CONTINGENCIA
    documento.contingencia_iniciada_em = agora
    documento.contingencia_justificativa = justificativa
    documento.transmissao_limite_em = agora + timedelta(hours=24)
    documento.mensagem_retorno = (
        "NFC-e emitida em contingencia offline, ainda sem autorizacao da SEFAZ. "
        "Transmitir assim que a comunicacao for restabelecida."
    )
    documento.save(
        update_fields=[
            "status",
            "contingencia_iniciada_em",
            "contingencia_justificativa",
            "transmissao_limite_em",
            "mensagem_retorno",
            "atualizado_em",
        ]
    )
    salvar_xml_documento(documento)
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="ATIVA_CONTINGENCIA_OFFLINE",
        descricao=(
            f"Documento fiscal {documento.id} entrou em contingencia offline. "
            f"Prazo de transmissao: {timezone.localtime(documento.transmissao_limite_em):%d/%m/%Y %H:%M}. "
            f"Justificativa: {justificativa}"
        ),
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.id),
        ip=ip,
    )
    return documento



@transaction.atomic
def transmitir_documento_simulado(documento, usuario, ip=None):
    documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
    status_origem = documento.status
    if status_origem not in {StatusDocumentoFiscal.PRONTO, StatusDocumentoFiscal.CONTINGENCIA}:
        raise ValidationError("Somente documentos prontos podem ser transmitidos.")
    if documento.ambiente != "HOMOLOGACAO":
        raise ValidationError("Transmissao simulada permitida somente em homologacao. Em producao, configure o adaptador SEFAZ oficial.")
    if not documento.xml_conteudo:
        salvar_xml_documento(documento)

    if len(documento.chave_acesso) != 44 or not documento.chave_acesso.isdigit():
        raise ValidationError("Documento sem chave de acesso fiscal valida.")
    documento.protocolo = f"HOM{timezone.now():%Y%m%d%H%M%S}{documento.pk:06d}"
    documento.status = StatusDocumentoFiscal.EMITIDO
    documento.tentativas_transmissao += 1
    documento.ultima_tentativa_em = timezone.now()
    documento.mensagem_retorno = "Transmissao simulada em homologacao. Substituir pelo adaptador oficial da SEFAZ em producao."
    documento.save(update_fields=["chave_acesso", "protocolo", "status", "tentativas_transmissao", "ultima_tentativa_em", "mensagem_retorno", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="TRANSMISSAO_SIMULADA",
        descricao=f"Documento fiscal {documento.id} transmitido em homologacao simulada. Protocolo: {documento.protocolo}.",
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.id),
        ip=ip,
    )
    return documento



def transmitir_documento_sefaz(documento, usuario, ip=None):
    with transaction.atomic():
        documento = (
            DocumentoFiscal.objects.select_for_update()
            .select_related("filial__empresa")
            .get(pk=documento.pk)
        )
        status_origem = documento.status
        if status_origem not in {StatusDocumentoFiscal.PRONTO, StatusDocumentoFiscal.CONTINGENCIA}:
            raise ValidationError("Somente documentos prontos ou em contingencia podem ser transmitidos.")
        if not documento.xml_conteudo:
            salvar_xml_documento(documento)
        documento.tentativas_transmissao += 1
        documento.ultima_tentativa_em = timezone.now()
        documento.save(update_fields=["tentativas_transmissao", "ultima_tentativa_em", "atualizado_em"])
        idempotency_key = (
            f"fiscal:{documento.pk}:{documento.numero or 0}:"
            f"{documento.xml_gerado_em.isoformat() if documento.xml_gerado_em else 'sem-xml'}"
        )

    try:
        adapter = carregar_adaptador_sefaz()
        if not bool(getattr(adapter, "assina_xml", False)):
            assinar_xml_documento(documento)
            verificar_assinatura_xml(documento.xml_conteudo)
        validar_xml_pre_transmissao(documento, adapter)
        retorno = adapter.transmitir(
            documento=documento,
            xml=documento.xml_conteudo,
            idempotency_key=idempotency_key,
            ambiente=documento.ambiente,
        )
        resultado = normalizar_retorno_transmissao(retorno)
        if resultado.status == "AUTORIZADO" and resultado.chave_acesso != documento.chave_acesso:
            raise SefazAdapterError("A SEFAZ autorizou uma chave diferente do documento transmitido.")
    except Exception as exc:
        mensagem = (
            str(exc)
            if isinstance(exc, (SefazAdapterError, ValidationError))
            else "Falha na comunicacao com o adaptador SEFAZ."
        )
        DocumentoFiscal.objects.filter(pk=documento.pk).update(
            mensagem_retorno=mensagem,
            atualizado_em=timezone.now(),
        )
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="TRANSMISSAO_SEFAZ_FALHA",
            descricao=f"Falha ao transmitir documento fiscal {documento.id}: {mensagem}",
            objeto_tipo="DocumentoFiscal",
            objeto_id=str(documento.id),
            ip=ip,
        )
        raise ValidationError(mensagem) from exc

    with transaction.atomic():
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        if documento.status == StatusDocumentoFiscal.EMITIDO:
            return documento

        documento.mensagem_retorno = resultado.mensagem
        if resultado.status == "AUTORIZADO":
            documento.status = StatusDocumentoFiscal.EMITIDO
            documento.chave_acesso = resultado.chave_acesso
            documento.protocolo = resultado.protocolo
        elif resultado.status == "REJEITADO":
            documento.status = StatusDocumentoFiscal.REJEITADO
        else:
            documento.status = status_origem
        documento.save(
            update_fields=[
                "status",
                "chave_acesso",
                "protocolo",
                "mensagem_retorno",
                "atualizado_em",
            ]
        )

    acao = {
        "AUTORIZADO": "TRANSMISSAO_SEFAZ_AUTORIZADA",
        "REJEITADO": "TRANSMISSAO_SEFAZ_REJEITADA",
        "PENDENTE": "TRANSMISSAO_SEFAZ_PENDENTE",
    }[resultado.status]
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao=acao,
        descricao=(
            f"Transmissao SEFAZ do documento fiscal {documento.id}: {resultado.status}. "
            f"Protocolo: {resultado.protocolo or '-'}."
        ),
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
