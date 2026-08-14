import re
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from xml.etree import ElementTree as ET

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.vendas.models import TipoDocumentoConsumidor

from .adapters import (
    SefazAdapterError,
    carregar_adaptador_sefaz,
    normalizar_retorno_cancelamento,
    normalizar_retorno_consulta,
    normalizar_retorno_inutilizacao,
    normalizar_retorno_transmissao,
)
from .assinaturas import assinar_xml_documento, verificar_assinatura_xml
from .validacoes import validar_xml_pre_transmissao
from .qrcode_nfce import gerar_url_qrcode_nfce
from .perfis_uf import pendencias_endpoints_nfce, pendencias_produto_por_uf
from .models import (
    AmbienteFiscal,
    CodigoRegimeTributario,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    InutilizacaoNumeracaoFiscal,
    ModoTransicaoIbsCbs,
    NaturezaOperacao,
    SerieFiscal,
    StatusDocumentoFiscal,
    StatusInutilizacaoFiscal,
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
        raise ValidationError("UF do emitente inválida para gerar a chave fiscal.")
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


def _crt_configuracao(configuracao):
    return str(configuracao.crt or "").strip()


def _usa_csosn(configuracao):
    return _crt_configuracao(configuracao) in {
        CodigoRegimeTributario.SIMPLES_NACIONAL,
        CodigoRegimeTributario.MEI,
    }


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
        raise ValidationError("NFC-e modelo 65 não deve ser preparada para consumidor identificado por CNPJ; emita NF-e modelo 55.")
    raise ValidationError("Documento do consumidor inválido para NFC-e.")


CENTAVO = Decimal("0.01")


def _moeda(valor):
    return Decimal(valor or 0).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _ratear_desconto(itens, desconto_total, obter_valor_bruto):
    itens = list(itens)
    valores_brutos = [_moeda(obter_valor_bruto(item)) for item in itens]
    total_bruto = sum(valores_brutos, Decimal("0.00"))
    desconto_total = min(_moeda(desconto_total), total_bruto)
    restante = desconto_total
    resultado = []
    for indice, (item, valor_bruto) in enumerate(zip(itens, valores_brutos)):
        if indice == len(itens) - 1:
            desconto_item = restante
        elif total_bruto:
            desconto_item = _moeda(desconto_total * valor_bruto / total_bruto)
            desconto_item = min(desconto_item, restante, valor_bruto)
        else:
            desconto_item = Decimal("0.00")
        restante -= desconto_item
        resultado.append((item, valor_bruto, desconto_item, valor_bruto - desconto_item))
    return resultado


def _calcular_icms_produto(produto, valor_operacao):
    valor_operacao = _moeda(valor_operacao)
    reducao = Decimal(produto.reducao_base_icms or 0)
    base = _moeda(valor_operacao * (Decimal("100") - reducao) / Decimal("100"))
    aliquota = Decimal(produto.aliquota_icms or 0)
    valor_icms = _moeda(base * aliquota / Decimal("100"))
    aliquota_fcp = Decimal(produto.aliquota_fcp or 0)
    valor_fcp = _moeda(base * aliquota_fcp / Decimal("100"))
    return {
        "base": base,
        "aliquota": aliquota,
        "valor_icms": valor_icms,
        "reducao": reducao,
        "aliquota_fcp": aliquota_fcp,
        "valor_fcp": valor_fcp,
    }


CSOSN_ICMS_SUPORTADOS = {"102", "103", "300", "400"}
CST_ICMS_TRIBUTADOS_SUPORTADOS = {"00", "20"}
CST_ICMS_NAO_TRIBUTADOS_SUPORTADOS = {"40", "41", "50"}
CST_ICMS_SUPORTADOS = CST_ICMS_TRIBUTADOS_SUPORTADOS | CST_ICMS_NAO_TRIBUTADOS_SUPORTADOS


def capacidade_tributaria_fiscal(configuracoes=None):
    configuracoes = list(configuracoes or [])
    preparacao_ibs_cbs = [
        configuracao
        for configuracao in configuracoes
        if configuracao.modo_transicao_ibs_cbs != ModoTransicaoIbsCbs.LEGADO
    ]
    return {
        "contrato": "fiscal_tax_capability_v1",
        "ibs_cbs": {
            "cadastro_produto_disponivel": True,
            "campos": ["CST IBS/CBS", "cClassTrib"],
            "filiais_em_preparacao": len(preparacao_ibs_cbs),
            "emissao_xml_habilitada": False,
            "modo_seguro": "legado ou preparação controlada",
            "bloqueio": (
                "O emissor continua usando ICMS, PIS e COFINS até que o grupo IBS/CBS do XML "
                "seja implementado com schema oficial, adaptador e homologação da SEFAZ."
            ),
        },
        "regime_normal": {
            "cst_suportados": sorted(CST_ICMS_SUPORTADOS),
            "grupos_xml": {
                "00": "ICMS00",
                "20": "ICMS20",
                "40": "ICMS40",
                "41": "ICMS40",
                "50": "ICMS40",
            },
            "tributados": sorted(CST_ICMS_TRIBUTADOS_SUPORTADOS),
            "nao_tributados": sorted(CST_ICMS_NAO_TRIBUTADOS_SUPORTADOS),
        },
        "simples_nacional": {
            "csosn_suportados": sorted(CSOSN_ICMS_SUPORTADOS),
            "grupo_xml": "ICMSSN102",
        },
        "politica_bloqueio": (
            "CST ou CSOSN fora desta matriz permanece bloqueado ate que todos os "
            "campos e calculos do respectivo grupo XML estejam implementados."
        ),
    }


def _icms_produto(imposto, produto, configuracao, valor_operacao):
    icms = ET.SubElement(imposto, f"{{{NFE_NS}}}ICMS")
    if _usa_csosn(configuracao):
        if produto.csosn not in CSOSN_ICMS_SUPORTADOS:
            raise ValidationError(
                f"CSOSN {produto.csosn or '-'} ainda nao e suportado pelo emissor fiscal local."
            )
        grupo = ET.SubElement(icms, f"{{{NFE_NS}}}ICMSSN102")
        _texto(grupo, "orig", produto.origem_mercadoria)
        _texto(grupo, "CSOSN", produto.csosn)
        return {"base": Decimal("0.00"), "valor_icms": Decimal("0.00"), "valor_fcp": Decimal("0.00")}

    if produto.cst_icms not in CST_ICMS_SUPORTADOS:
        raise ValidationError(
            f"CST ICMS {produto.cst_icms or '-'} ainda nao e suportado pelo emissor fiscal local."
        )
    if produto.cst_icms in CST_ICMS_NAO_TRIBUTADOS_SUPORTADOS:
        grupo = ET.SubElement(icms, f"{{{NFE_NS}}}ICMS40")
        _texto(grupo, "orig", produto.origem_mercadoria)
        _texto(grupo, "CST", produto.cst_icms)
        return {"base": Decimal("0.00"), "valor_icms": Decimal("0.00"), "valor_fcp": Decimal("0.00")}

    calculo = _calcular_icms_produto(produto, valor_operacao)
    nome_grupo = "ICMS20" if produto.cst_icms == "20" else "ICMS00"
    grupo = ET.SubElement(icms, f"{{{NFE_NS}}}{nome_grupo}")
    _texto(grupo, "orig", produto.origem_mercadoria)
    _texto(grupo, "CST", produto.cst_icms)
    _texto(grupo, "modBC", "3")
    if produto.cst_icms == "20":
        _texto(grupo, "pRedBC", _valor(calculo["reducao"]))
    _texto(grupo, "vBC", _valor(calculo["base"]))
    _texto(grupo, "pICMS", _valor(calculo["aliquota"]))
    _texto(grupo, "vICMS", _valor(calculo["valor_icms"]))
    if calculo["aliquota_fcp"] > 0:
        _texto(grupo, "vBCFCP", _valor(calculo["base"]))
        _texto(grupo, "pFCP", _valor(calculo["aliquota_fcp"]))
        _texto(grupo, "vFCP", _valor(calculo["valor_fcp"]))
    return calculo


CST_CONTRIBUICAO_ALIQUOTA = {"01", "02"}
CST_CONTRIBUICAO_NAO_TRIBUTADA = {"04", "05", "06", "07", "08", "09"}
CST_CONTRIBUICAO_OUTRAS = {"49", "99"}
CST_IPI_NAO_TRIBUTADO = {"01", "02", "03", "04", "05", "51", "52", "53", "54", "55"}
CST_IPI_TRIBUTADO = {"00", "49", "50", "99"}


def filtro_pendencias_produto_fiscal(regimes_tributarios=None, ufs=None, crts=None, exigir_ibs_cbs=False):
    regimes = [regime.upper() for regime in (regimes_tributarios or []) if regime]
    crts_validos = {str(crt) for crt in (crts or []) if crt}
    if crts_validos:
        exige_simples = bool(
            crts_validos
            & {CodigoRegimeTributario.SIMPLES_NACIONAL, CodigoRegimeTributario.MEI}
        )
        exige_normal = bool(
            crts_validos
            & {
                CodigoRegimeTributario.SIMPLES_EXCESSO_SUBLIMITE,
                CodigoRegimeTributario.REGIME_NORMAL,
            }
        )
    else:
        exige_simples = not regimes or any("SIMPLES" in regime for regime in regimes)
        exige_normal = not regimes or any("SIMPLES" not in regime for regime in regimes)

    pendente = (
        ~Q(ncm__regex=r"^\d{8}$")
        | (~Q(cest="") & ~Q(cest__regex=r"^\d{7}$"))
        | Q(origem_mercadoria="")
    )
    if exige_simples:
        pendente |= ~Q(csosn__in=sorted(CSOSN_ICMS_SUPORTADOS))
    if exige_normal:
        pendente |= ~Q(cst_icms__in=sorted(CST_ICMS_SUPORTADOS))
        pendente |= Q(cst_icms="20") & (
            Q(reducao_base_icms__isnull=True) | Q(reducao_base_icms__lte=0)
        )
        pendente |= Q(reducao_base_icms__gt=0) & ~Q(cst_icms="20")
    pendente |= Q(aliquota_icms__isnull=True) | Q(aliquota_icms__lt=0)

    csts_contribuicao = (
        CST_CONTRIBUICAO_ALIQUOTA
        | CST_CONTRIBUICAO_NAO_TRIBUTADA
        | CST_CONTRIBUICAO_OUTRAS
    )
    for campo_cst, campo_aliquota in (
        ("cst_pis", "aliquota_pis"),
        ("cst_cofins", "aliquota_cofins"),
    ):
        pendente |= ~Q(**{f"{campo_cst}__in": sorted(csts_contribuicao)})
        pendente |= Q(**{f"{campo_cst}__in": sorted(CST_CONTRIBUICAO_ALIQUOTA)}) & (
            Q(**{f"{campo_aliquota}__isnull": True})
            | Q(**{f"{campo_aliquota}__lte": 0})
        )

    if exigir_ibs_cbs:
        pendente |= ~Q(cst_ibs_cbs__regex=r"^\d{3}$")
        pendente |= ~Q(classificacao_tributaria_ibs_cbs__regex=r"^\d{6}$")

    csts_ipi = CST_IPI_NAO_TRIBUTADO | CST_IPI_TRIBUTADO
    pendente |= ~Q(cst_ipi="") & ~Q(cst_ipi__in=sorted(csts_ipi))
    pendente |= Q(cst_ipi__in=sorted(CST_IPI_TRIBUTADO)) & (
        Q(aliquota_ipi__isnull=True) | Q(aliquota_ipi__lte=0)
    )
    pendente |= ~Q(cst_ipi="") & ~Q(codigo_enquadramento_ipi__regex=r"^\d{3}$")
    pendente |= Q(cst_ipi="") & ~Q(codigo_enquadramento_ipi="")

    ufs_validas = {(uf or "").strip().upper() for uf in (ufs or []) if uf}
    if "GO" in ufs_validas:
        pendente |= Q(reducao_base_icms__gt=0, codigo_beneficio_fiscal="")
        pendente |= ~Q(codigo_beneficio_fiscal="") & ~Q(
            codigo_beneficio_fiscal__regex=r"^GO\d{6}$"
        )
    return pendente


def _pendencias_ibs_cbs_produto(produto, exigido=False):
    if not exigido:
        return []
    pendencias = []
    if not re.fullmatch(r"\d{3}", produto.cst_ibs_cbs or ""):
        pendencias.append("CST IBS/CBS com 3 dígitos")
    if not re.fullmatch(r"\d{6}", produto.classificacao_tributaria_ibs_cbs or ""):
        pendencias.append("cClassTrib IBS/CBS com 6 dígitos")
    return pendencias


def _pendencias_emissao_ibs_cbs(configuracao):
    if configuracao.modo_transicao_ibs_cbs != ModoTransicaoIbsCbs.EMISSAO_HOMOLOGADA:
        return []
    return [
        "Emissão XML IBS/CBS bloqueada: instale o schema oficial, implemente o grupo XML vigente "
        "e homologue o adaptador SEFAZ antes de ativar esta modalidade."
    ]


def _pendencias_contribuicoes_produto(produto):
    pendencias = []
    codigos_contribuicao = (
        CST_CONTRIBUICAO_ALIQUOTA
        | CST_CONTRIBUICAO_NAO_TRIBUTADA
        | CST_CONTRIBUICAO_OUTRAS
    )
    for nome, cst, aliquota in [
        ("PIS", produto.cst_pis, produto.aliquota_pis),
        ("COFINS", produto.cst_cofins, produto.aliquota_cofins),
    ]:
        if cst not in codigos_contribuicao:
            pendencias.append(f"CST {nome} ausente ou ainda nao suportado")
        elif cst in CST_CONTRIBUICAO_ALIQUOTA and (aliquota is None or aliquota <= 0):
            pendencias.append(f"Aliquota {nome} obrigatoria para CST {cst}")
    if produto.cst_ipi:
        if produto.cst_ipi not in CST_IPI_NAO_TRIBUTADO | CST_IPI_TRIBUTADO:
            pendencias.append("CST IPI ainda nao suportado pelo emissor fiscal local")
        elif produto.cst_ipi in CST_IPI_TRIBUTADO and (
            produto.aliquota_ipi is None or produto.aliquota_ipi <= 0
        ):
            pendencias.append(f"Aliquota IPI obrigatoria para CST {produto.cst_ipi}")
        if not re.fullmatch(r"\d{3}", produto.codigo_enquadramento_ipi or ""):
            pendencias.append("Codigo de enquadramento IPI (cEnq) com 3 digitos")
    elif produto.codigo_enquadramento_ipi:
        pendencias.append("Informe CST IPI para utilizar o codigo de enquadramento")
    return pendencias

def _contribuicao_produto(imposto, *, nome, cst, aliquota, valor_operacao):
    if cst in CST_CONTRIBUICAO_ALIQUOTA:
        grupo = ET.SubElement(imposto, f"{{{NFE_NS}}}{nome}Aliq")
        base = _moeda(valor_operacao)
        percentual = Decimal(aliquota or 0)
        valor = _moeda(base * percentual / Decimal("100"))
        _texto(grupo, "CST", cst)
        _texto(grupo, "vBC", _valor(base))
        _texto(grupo, f"p{nome}", _valor(percentual, casas=4))
        _texto(grupo, f"v{nome}", _valor(valor))
        return valor
    if cst in CST_CONTRIBUICAO_NAO_TRIBUTADA:
        grupo = ET.SubElement(imposto, f"{{{NFE_NS}}}{nome}NT")
        _texto(grupo, "CST", cst)
        return Decimal("0.00")
    if cst in CST_CONTRIBUICAO_OUTRAS:
        grupo = ET.SubElement(imposto, f"{{{NFE_NS}}}{nome}Outr")
        base = _moeda(valor_operacao)
        percentual = Decimal(aliquota or 0)
        valor = _moeda(base * percentual / Decimal("100"))
        _texto(grupo, "CST", cst)
        _texto(grupo, "vBC", _valor(base))
        _texto(grupo, f"p{nome}", _valor(percentual, casas=4))
        _texto(grupo, f"v{nome}", _valor(valor))
        return valor
    raise ValidationError(f"CST {nome} {cst or '-'} ainda nao e suportado pelo emissor fiscal local.")


def _composicao_item_ipi(produto, natureza, valor_bruto, desconto):
    valor_bruto = _moeda(valor_bruto)
    desconto = _moeda(desconto)
    valor_liquido = _moeda(valor_bruto - desconto)
    if produto.cst_ipi not in CST_IPI_TRIBUTADO:
        return {
            "valor_produto": valor_bruto,
            "desconto": desconto,
            "base_ipi": valor_liquido,
            "valor_ipi": Decimal("0.00"),
            "base_icms": valor_liquido,
            "base_pis_cofins": valor_liquido,
        }
    if not natureza or not natureza.ipi_incluso_preco:
        raise ValidationError(
            "IPI tributado exige confirmar na natureza da operacao que o imposto esta incluido no preco."
        )
    aliquota = Decimal(produto.aliquota_ipi or 0)
    if aliquota <= 0:
        raise ValidationError(f"Aliquota IPI obrigatoria para CST {produto.cst_ipi}.")
    fator = Decimal("1") + aliquota / Decimal("100")
    valor_produto = _moeda(valor_bruto / fator)
    desconto_sem_ipi = _moeda(desconto / fator)
    base_ipi = _moeda(valor_produto - desconto_sem_ipi)
    valor_ipi = _moeda(valor_liquido - base_ipi)
    return {
        "valor_produto": valor_produto,
        "desconto": desconto_sem_ipi,
        "base_ipi": base_ipi,
        "valor_ipi": valor_ipi,
        "base_icms": valor_liquido if natureza.ipi_compoe_base_icms else base_ipi,
        "base_pis_cofins": valor_liquido if natureza.ipi_compoe_base_pis_cofins else base_ipi,
    }


def _ipi_produto(imposto, produto, base_ipi, valor_ipi):
    if not produto.cst_ipi:
        return Decimal("0.00")
    ipi = ET.SubElement(imposto, f"{{{NFE_NS}}}IPI")
    _texto(ipi, "cEnq", produto.codigo_enquadramento_ipi)
    if produto.cst_ipi in CST_IPI_NAO_TRIBUTADO:
        grupo = ET.SubElement(ipi, f"{{{NFE_NS}}}IPINT")
        _texto(grupo, "CST", produto.cst_ipi)
        return Decimal("0.00")
    if produto.cst_ipi not in CST_IPI_TRIBUTADO:
        raise ValidationError(f"CST IPI {produto.cst_ipi} ainda nao e suportado.")
    grupo = ET.SubElement(ipi, f"{{{NFE_NS}}}IPITrib")
    _texto(grupo, "CST", produto.cst_ipi)
    _texto(grupo, "vBC", _valor(base_ipi))
    _texto(grupo, "pIPI", _valor(produto.aliquota_ipi, casas=4))
    _texto(grupo, "vIPI", _valor(valor_ipi))
    return valor_ipi


def _pis_cofins_produto(imposto, produto, valor_operacao):
    valor_pis = _contribuicao_produto(
        imposto,
        nome="PIS",
        cst=produto.cst_pis,
        aliquota=produto.aliquota_pis,
        valor_operacao=valor_operacao,
    )
    valor_cofins = _contribuicao_produto(
        imposto,
        nome="COFINS",
        cst=produto.cst_cofins,
        aliquota=produto.aliquota_cofins,
        valor_operacao=valor_operacao,
    )
    return valor_pis, valor_cofins

def _adicionar_totais_icms(inf_nfe, *, base_icms, valor_icms, valor_fcp, valor_ipi, valor_pis, valor_cofins, valor_produtos, desconto, outros, total_nota):
    total = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}total")
    icmstot = ET.SubElement(total, f"{{{NFE_NS}}}ICMSTot")
    _texto(icmstot, "vBC", _valor(base_icms))
    _texto(icmstot, "vICMS", _valor(valor_icms))
    _texto(icmstot, "vICMSDeson", "0.00")
    _texto(icmstot, "vFCP", _valor(valor_fcp))
    _texto(icmstot, "vBCST", "0.00")
    _texto(icmstot, "vST", "0.00")
    _texto(icmstot, "vFCPST", "0.00")
    _texto(icmstot, "vFCPSTRet", "0.00")
    _texto(icmstot, "vProd", _valor(valor_produtos))
    _texto(icmstot, "vFrete", "0.00")
    _texto(icmstot, "vSeg", "0.00")
    _texto(icmstot, "vDesc", _valor(desconto))
    _texto(icmstot, "vII", "0.00")
    _texto(icmstot, "vIPI", _valor(valor_ipi))
    _texto(icmstot, "vIPIDevol", "0.00")
    _texto(icmstot, "vPIS", _valor(valor_pis))
    _texto(icmstot, "vCOFINS", _valor(valor_cofins))
    _texto(icmstot, "vOutro", _valor(outros))
    _texto(icmstot, "vNF", _valor(total_nota))

def pendencias_produto_fiscal(produto, regimes_tributarios=None, ufs=None, crts=None, exigir_ibs_cbs=False):
    pendencias = []
    regimes = [regime.upper() for regime in (regimes_tributarios or []) if regime]
    crts = {str(crt) for crt in (crts or []) if crt}
    if crts:
        exige_simples = bool(crts & {CodigoRegimeTributario.SIMPLES_NACIONAL, CodigoRegimeTributario.MEI})
        exige_normal = bool(crts & {CodigoRegimeTributario.SIMPLES_EXCESSO_SUBLIMITE, CodigoRegimeTributario.REGIME_NORMAL})
    else:
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
    elif exige_simples and produto.csosn not in CSOSN_ICMS_SUPORTADOS:
        pendencias.append("CSOSN ainda nao suportado pelo emissor fiscal local")
    if exige_normal and not re.fullmatch(r"\d{2}", produto.cst_icms or ""):
        pendencias.append("CST ICMS com 2 digitos")
    elif exige_normal and produto.cst_icms not in CST_ICMS_SUPORTADOS:
        pendencias.append("CST ICMS ainda nao suportado pelo emissor fiscal local")
    elif exige_normal and produto.cst_icms == "20" and not (produto.reducao_base_icms and produto.reducao_base_icms > 0):
        pendencias.append("CST 20 exige percentual de reducao da base do ICMS")
    elif exige_normal and produto.cst_icms != "20" and produto.reducao_base_icms and produto.reducao_base_icms > 0:
        pendencias.append("Reducao de base exige CST ICMS compativel, como 20")
    if produto.aliquota_icms is None or produto.aliquota_icms < 0:
        pendencias.append("Aliquota ICMS")
    pendencias.extend(_pendencias_contribuicoes_produto(produto))
    pendencias.extend(_pendencias_ibs_cbs_produto(produto, exigir_ibs_cbs))
    pendencias.extend(pendencias_produto_por_uf(produto, ufs))
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
    _texto(emit, "CRT", _crt_configuracao(configuracao))

    consumidor = _documento_consumidor_nfce(venda)
    if consumidor:
        dest = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}dest")
        if consumidor["tipo"] == TipoDocumentoConsumidor.CPF:
            _texto(dest, "CPF", consumidor["documento"])
        else:
            _texto(dest, "idEstrangeiro", consumidor["documento"])
        _texto(dest, "indIEDest", "9")

    itens_rateados = _ratear_desconto(
        venda.itens.select_related("produto"),
        venda.desconto,
        lambda item: item.quantidade * item.preco_unitario_venda,
    )
    base_icms_total = Decimal("0.00")
    valor_icms_total = Decimal("0.00")
    valor_fcp_total = Decimal("0.00")
    valor_ipi_total = Decimal("0.00")
    valor_pis_total = Decimal("0.00")
    valor_cofins_total = Decimal("0.00")
    valor_produtos_total = Decimal("0.00")
    desconto_total = Decimal("0.00")
    for numero, (item, valor_bruto, desconto_item, valor_liquido) in enumerate(itens_rateados, start=1):
        produto = item.produto
        composicao_ipi = _composicao_item_ipi(produto, natureza, valor_bruto, desconto_item)
        valor_unitario_fiscal = composicao_ipi["valor_produto"] / item.quantidade
        det = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}det", {"nItem": str(numero)})
        prod = ET.SubElement(det, f"{{{NFE_NS}}}prod")
        _texto(prod, "cProd", produto.codigo_interno or produto.codigo_barras or produto.pk)
        _texto(prod, "cEAN", produto.codigo_barras or "SEM GTIN")
        _texto(prod, "xProd", produto.nome[:120])
        _texto(prod, "NCM", produto.ncm)
        if produto.cest:
            _texto(prod, "CEST", produto.cest)
        if produto.codigo_beneficio_fiscal:
            _texto(prod, "cBenef", produto.codigo_beneficio_fiscal)
        _texto(prod, "CFOP", natureza.cfop)
        _texto(prod, "uCom", produto.unidade)
        _texto(prod, "qCom", _valor(item.quantidade, casas=3))
        _texto(prod, "vUnCom", _valor(valor_unitario_fiscal, casas=10))
        _texto(prod, "vProd", _valor(composicao_ipi["valor_produto"]))
        _texto(prod, "cEANTrib", produto.codigo_barras or "SEM GTIN")
        _texto(prod, "uTrib", produto.unidade)
        _texto(prod, "qTrib", _valor(item.quantidade, casas=3))
        _texto(prod, "vUnTrib", _valor(valor_unitario_fiscal, casas=10))
        if composicao_ipi["desconto"]:
            _texto(prod, "vDesc", _valor(composicao_ipi["desconto"]))
        _texto(prod, "indTot", "1")
        imposto = ET.SubElement(det, f"{{{NFE_NS}}}imposto")
        calculo_icms = _icms_produto(imposto, produto, configuracao, composicao_ipi["base_icms"])
        base_icms_total += calculo_icms["base"]
        valor_icms_total += calculo_icms["valor_icms"]
        valor_fcp_total += calculo_icms["valor_fcp"]
        valor_ipi_total += _ipi_produto(
            imposto, produto, composicao_ipi["base_ipi"], composicao_ipi["valor_ipi"]
        )
        valor_pis, valor_cofins = _pis_cofins_produto(
            imposto, produto, composicao_ipi["base_pis_cofins"]
        )
        valor_pis_total += valor_pis
        valor_cofins_total += valor_cofins
        valor_produtos_total += composicao_ipi["valor_produto"]
        desconto_total += composicao_ipi["desconto"]

    _adicionar_totais_icms(
        inf_nfe,
        base_icms=base_icms_total,
        valor_icms=valor_icms_total,
        valor_fcp=valor_fcp_total,
        valor_ipi=valor_ipi_total,
        valor_pis=valor_pis_total,
        valor_cofins=valor_cofins_total,
        valor_produtos=valor_produtos_total,
        desconto=desconto_total,
        outros=Decimal("0.00"),
        total_nota=venda.total_liquido,
    )
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
    _texto(emit, "CRT", _crt_configuracao(configuracao))

    dest = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}dest")
    _texto(dest, doc_tag, doc_valor)
    _texto(dest, "xNome", pedido.nome_cliente[:60])
    _texto(dest, "indIEDest", "9")

    itens_rateados = _ratear_desconto(
        pedido.itens.select_related("produto"),
        pedido.desconto,
        lambda item: item.quantidade * item.preco_unitario,
    )
    base_icms_total = Decimal("0.00")
    valor_icms_total = Decimal("0.00")
    valor_fcp_total = Decimal("0.00")
    valor_ipi_total = Decimal("0.00")
    valor_pis_total = Decimal("0.00")
    valor_cofins_total = Decimal("0.00")
    valor_produtos_total = Decimal("0.00")
    desconto_total = Decimal("0.00")
    for numero, (item, valor_bruto, desconto_item, valor_liquido) in enumerate(itens_rateados, start=1):
        produto = item.produto
        composicao_ipi = _composicao_item_ipi(produto, natureza, valor_bruto, desconto_item)
        valor_unitario_fiscal = composicao_ipi["valor_produto"] / item.quantidade
        det = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}det", {"nItem": str(numero)})
        prod = ET.SubElement(det, f"{{{NFE_NS}}}prod")
        _texto(prod, "cProd", produto.codigo_interno or produto.codigo_barras or produto.pk)
        _texto(prod, "cEAN", produto.codigo_barras or "SEM GTIN")
        _texto(prod, "xProd", produto.nome[:120])
        _texto(prod, "NCM", produto.ncm)
        if produto.cest:
            _texto(prod, "CEST", produto.cest)
        if produto.codigo_beneficio_fiscal:
            _texto(prod, "cBenef", produto.codigo_beneficio_fiscal)
        _texto(prod, "CFOP", natureza.cfop)
        _texto(prod, "uCom", produto.unidade)
        _texto(prod, "qCom", _valor(item.quantidade, casas=3))
        _texto(prod, "vUnCom", _valor(valor_unitario_fiscal, casas=10))
        _texto(prod, "vProd", _valor(composicao_ipi["valor_produto"]))
        _texto(prod, "cEANTrib", produto.codigo_barras or "SEM GTIN")
        _texto(prod, "uTrib", produto.unidade)
        _texto(prod, "qTrib", _valor(item.quantidade, casas=3))
        _texto(prod, "vUnTrib", _valor(valor_unitario_fiscal, casas=10))
        if composicao_ipi["desconto"]:
            _texto(prod, "vDesc", _valor(composicao_ipi["desconto"]))
        _texto(prod, "indTot", "1")
        imposto = ET.SubElement(det, f"{{{NFE_NS}}}imposto")
        calculo_icms = _icms_produto(imposto, produto, configuracao, composicao_ipi["base_icms"])
        base_icms_total += calculo_icms["base"]
        valor_icms_total += calculo_icms["valor_icms"]
        valor_fcp_total += calculo_icms["valor_fcp"]
        valor_ipi_total += _ipi_produto(
            imposto, produto, composicao_ipi["base_ipi"], composicao_ipi["valor_ipi"]
        )
        valor_pis, valor_cofins = _pis_cofins_produto(
            imposto, produto, composicao_ipi["base_pis_cofins"]
        )
        valor_pis_total += valor_pis
        valor_cofins_total += valor_cofins
        valor_produtos_total += composicao_ipi["valor_produto"]
        desconto_total += composicao_ipi["desconto"]

    _adicionar_totais_icms(
        inf_nfe,
        base_icms=base_icms_total,
        valor_icms=valor_icms_total,
        valor_fcp=valor_fcp_total,
        valor_ipi=valor_ipi_total,
        valor_pis=valor_pis_total,
        valor_cofins=valor_cofins_total,
        valor_produtos=valor_produtos_total,
        desconto=desconto_total,
        outros=pedido.taxa_entrega,
        total_nota=pedido.total,
    )

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
    erros = _pendencias_emissao_ibs_cbs(configuracao)
    if not configuracao.inscricao_estadual.strip():
        erros.append("Informe a inscricao estadual da filial.")
    if not configuracao.regime_tributario.strip():
        erros.append("Informe o regime tributario da filial.")
    if _crt_configuracao(configuracao) not in CodigoRegimeTributario.values:
        erros.append("Informe o Código de Regime Tributário (CRT) da filial.")
    erros.extend(pendencias_endpoints_nfce(venda.filial, configuracao))
    if not venda.filial.uf or venda.filial.uf not in CODIGOS_UF_IBGE:
        erros.append("Informe a UF da filial para emissao fiscal.")
    if not re.fullmatch(r"\d{7}", venda.filial.codigo_municipio_ibge or ""):
        erros.append("Informe o código IBGE do município da filial com 7 digitos.")
    if not configuracao.certificado_configurado:
        erros.append("Envie o certificado A1 da filial.")
    elif configuracao.certificado_status == "vencido":
        erros.append("O certificado A1 da filial está vencido.")
    if not natureza:
        erros.append("Cadastre uma natureza de operação NFC-e ativa.")
    elif not re.fullmatch(r"[1-7]\d{3}", natureza.cfop.strip()):
        erros.append("A natureza de operação deve possuir CFOP valido com 4 digitos.")

    simples_nacional = _usa_csosn(configuracao)
    itens = list(venda.itens.select_related("produto"))
    if not itens:
        erros.append("A venda não possui itens para emissao fiscal.")
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
            elif produto.csosn not in CSOSN_ICMS_SUPORTADOS:
                erros.append(f"{prefixo} CSOSN {produto.csosn} ainda nao e suportado pelo emissor fiscal local.")
        elif not re.fullmatch(r"\d{2}", produto.cst_icms or ""):
            erros.append(f"{prefixo} informe CST ICMS com 2 digitos.")
        elif produto.cst_icms not in CST_ICMS_SUPORTADOS:
            erros.append(f"{prefixo} CST ICMS {produto.cst_icms} ainda nao e suportado pelo emissor fiscal local.")
        elif produto.cst_icms == "20" and not (produto.reducao_base_icms and produto.reducao_base_icms > 0):
            erros.append(f"{prefixo} CST 20 exige percentual de reducao da base do ICMS.")
        elif produto.cst_icms != "20" and produto.reducao_base_icms and produto.reducao_base_icms > 0:
            erros.append(f"{prefixo} reducao de base exige CST ICMS compativel, como 20.")
        if produto.aliquota_icms is None or produto.aliquota_icms < 0:
            erros.append(f"{prefixo} informe a aliquota de ICMS, inclusive quando for zero.")
        erros.extend(f"{prefixo} {pendencia}." for pendencia in _pendencias_contribuicoes_produto(produto))
        erros.extend(
            f"{prefixo} {pendencia}."
            for pendencia in _pendencias_ibs_cbs_produto(produto, configuracao.ibs_cbs_exigido_em())
        )
        if produto.cst_ipi in CST_IPI_TRIBUTADO and (not natureza or not natureza.ipi_incluso_preco):
            erros.append(
                f"{prefixo} confirme na natureza da operacao que o IPI tributado esta incluido no preco."
            )
        erros.extend(f"{prefixo} {pendencia}." for pendencia in pendencias_produto_por_uf(produto, [venda.filial.uf]))
    return erros


def validar_preparacao_fiscal(venda, configuracao, natureza):
    erros = pendencias_preparacao_fiscal(venda, configuracao, natureza)
    if erros:
        raise ValidationError(erros)


def pendencias_preparacao_nfe_pedido(pedido, configuracao, natureza):
    erros = _pendencias_emissao_ibs_cbs(configuracao)
    if not configuracao.inscricao_estadual.strip():
        erros.append("Informe a inscricao estadual da filial.")
    if not configuracao.regime_tributario.strip():
        erros.append("Informe o regime tributario da filial.")
    if _crt_configuracao(configuracao) not in CodigoRegimeTributario.values:
        erros.append("Informe o Código de Regime Tributário (CRT) da filial.")
    if not pedido.filial.uf or pedido.filial.uf not in CODIGOS_UF_IBGE:
        erros.append("Informe a UF da filial para emissao fiscal.")
    if not re.fullmatch(r"\d{7}", pedido.filial.codigo_municipio_ibge or ""):
        erros.append("Informe o código IBGE do município da filial com 7 digitos.")
    if not configuracao.certificado_configurado:
        erros.append("Envie o certificado A1 da filial.")
    elif configuracao.certificado_status == "vencido":
        erros.append("O certificado A1 da filial está vencido.")
    if not natureza:
        erros.append("Cadastre uma natureza de operação NF-e ativa.")
    elif not re.fullmatch(r"[1-7]\d{3}", natureza.cfop.strip()):
        erros.append("A natureza de operação deve possuir CFOP valido com 4 digitos.")
    try:
        _documento_destinatario_pedido(pedido)
    except ValidationError as exc:
        erros.extend(exc.messages)
    itens = list(pedido.itens.select_related("produto"))
    if not itens:
        erros.append("O pedido online não possui itens para emissao fiscal.")
    simples_nacional = _usa_csosn(configuracao)
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
            elif produto.csosn not in CSOSN_ICMS_SUPORTADOS:
                erros.append(f"{prefixo} CSOSN {produto.csosn} ainda nao e suportado pelo emissor fiscal local.")
        elif not re.fullmatch(r"\d{2}", produto.cst_icms or ""):
            erros.append(f"{prefixo} informe CST ICMS com 2 digitos.")
        elif produto.cst_icms not in CST_ICMS_SUPORTADOS:
            erros.append(f"{prefixo} CST ICMS {produto.cst_icms} ainda nao e suportado pelo emissor fiscal local.")
        elif produto.cst_icms == "20" and not (produto.reducao_base_icms and produto.reducao_base_icms > 0):
            erros.append(f"{prefixo} CST 20 exige percentual de reducao da base do ICMS.")
        elif produto.cst_icms != "20" and produto.reducao_base_icms and produto.reducao_base_icms > 0:
            erros.append(f"{prefixo} reducao de base exige CST ICMS compativel, como 20.")
        if produto.aliquota_icms is None or produto.aliquota_icms < 0:
            erros.append(f"{prefixo} informe a aliquota de ICMS, inclusive quando for zero.")
        erros.extend(f"{prefixo} {pendencia}." for pendencia in _pendencias_contribuicoes_produto(produto))
        erros.extend(
            f"{prefixo} {pendencia}."
            for pendencia in _pendencias_ibs_cbs_produto(produto, configuracao.ibs_cbs_exigido_em())
        )
        if produto.cst_ipi in CST_IPI_TRIBUTADO and (not natureza or not natureza.ipi_incluso_preco):
            erros.append(
                f"{prefixo} confirme na natureza da operacao que o IPI tributado esta incluido no preco."
            )
        erros.extend(f"{prefixo} {pendencia}." for pendencia in pendencias_produto_por_uf(produto, [pedido.filial.uf]))
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
        raise ValidationError("A configuração fiscal da filial está inativa.")
    _documento_consumidor_nfce(venda)

    serie = (
        SerieFiscal.objects.select_for_update()
        .filter(filial=venda.filial, tipo_documento=TipoDocumentoFiscal.NFCE, ativo=True)
        .order_by("serie")
        .first()
    )
    if not serie:
        raise ValidationError("Cadastre uma serie NFC-e ativa para a filial.")

    natureza = natureza_operacao or NaturezaOperacao.objects.filter(
        empresa_id=venda.filial.empresa_id,
        tipo_documento=TipoDocumentoFiscal.NFCE,
        ativo=True,
        padrao=True,
    ).first()
    if natureza and natureza.empresa_id != venda.filial.empresa_id:
        raise ValidationError("A natureza de operacao nao pertence a empresa da venda.")
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
        mensagem_retorno="Documento preparado localmente. Transmissao SEFAZ pendente de integração fiscal.",
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
        raise ValidationError("A configuração fiscal da filial está inativa.")
    serie = (
        SerieFiscal.objects.select_for_update()
        .filter(filial=pedido.filial, tipo_documento=TipoDocumentoFiscal.NFE, ativo=True)
        .order_by("serie")
        .first()
    )
    if not serie:
        raise ValidationError("Cadastre uma serie NF-e ativa para a filial.")
    natureza = natureza_operacao or NaturezaOperacao.objects.filter(
        empresa_id=pedido.filial.empresa_id,
        tipo_documento=TipoDocumentoFiscal.NFE,
        ativo=True,
        padrao=True,
    ).first()
    if natureza and natureza.empresa_id != pedido.filial.empresa_id:
        raise ValidationError("A natureza de operacao nao pertence a empresa do pedido.")
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
        mensagem_retorno="NF-e de pedido online preparada localmente. Transmissao SEFAZ pendente de integração fiscal.",
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
        raise ValidationError("Somente documento pronto pode entrar em contingência offline.")
    if documento.aguardando_consulta_sefaz:
        raise ValidationError(
            "Consulte a situação da chave na SEFAZ antes de ativar a contingência."
        )
    try:
        configuracao = documento.filial.configuracao_fiscal
    except ConfiguracaoFiscal.DoesNotExist as exc:
        raise ValidationError("Configure os dados fiscais da filial antes de usar contingência.") from exc
    if not configuracao.ativo or not configuracao.permite_contingencia_offline:
        raise ValidationError("Contingencia offline não está autorizada na configuração fiscal desta filial.")
    justificativa = (justificativa or "").strip()
    if not 15 <= len(justificativa) <= 256:
        raise ValidationError("A justificativa da contingência deve ter entre 15 e 256 caracteres.")

    agora = timezone.now()
    documento.status = StatusDocumentoFiscal.CONTINGENCIA
    documento.contingencia_iniciada_em = agora
    documento.contingencia_justificativa = justificativa
    documento.transmissao_limite_em = agora + timedelta(hours=24)
    documento.mensagem_retorno = (
        "NFC-e emitida em contingência offline, ainda sem autorização da SEFAZ. "
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
    if documento.aguardando_consulta_sefaz:
        raise ValidationError(
            "Consulte a situação da chave antes de transmitir novamente."
        )
    if documento.ambiente != "HOMOLOGACAO":
        raise ValidationError("Transmissao simulada permitida somente em homologação. Em produção, configure o adaptador SEFAZ oficial.")
    if not documento.xml_conteudo:
        salvar_xml_documento(documento)

    if len(documento.chave_acesso) != 44 or not documento.chave_acesso.isdigit():
        raise ValidationError("Documento sem chave de acesso fiscal valida.")
    documento.protocolo = f"HOM{timezone.now():%Y%m%d%H%M%S}{documento.pk:06d}"
    documento.status = StatusDocumentoFiscal.EMITIDO
    documento.tentativas_transmissao += 1
    documento.ultima_tentativa_em = timezone.now()
    documento.mensagem_retorno = "Transmissao simulada em homologação. Substituir pelo adaptador oficial da SEFAZ em produção."
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
            raise ValidationError("Somente documentos prontos ou em contingência podem ser transmitidos.")
        if documento.aguardando_consulta_sefaz:
            raise ValidationError(
                "Consulte a situação da chave na SEFAZ antes de transmitir novamente."
            )
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
        documento.tentativas_consulta_sefaz = 0
        if resultado.status == "AUTORIZADO":
            documento.aguardando_consulta_sefaz = False
            documento.status = StatusDocumentoFiscal.EMITIDO
            documento.chave_acesso = resultado.chave_acesso
            documento.protocolo = resultado.protocolo
        elif resultado.status == "REJEITADO":
            documento.aguardando_consulta_sefaz = False
            documento.status = StatusDocumentoFiscal.REJEITADO
        else:
            documento.aguardando_consulta_sefaz = True
            documento.status = status_origem
        documento.save(
            update_fields=[
                "status",
                "chave_acesso",
                "protocolo",
                "mensagem_retorno",
                "aguardando_consulta_sefaz",
                "tentativas_consulta_sefaz",
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
    motivo = (motivo or "").strip()
    if not 15 <= len(motivo) <= 255:
        raise ValidationError("A justificativa do cancelamento deve ter entre 15 e 255 caracteres.")

    with transaction.atomic():
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        if documento.aguardando_consulta_sefaz:
            raise ValidationError(
                "Consulte a situação da chave na SEFAZ antes de cancelar o documento."
            )
        if documento.status in {
            StatusDocumentoFiscal.PRONTO,
            StatusDocumentoFiscal.REJEITADO,
        }:
            documento.status = StatusDocumentoFiscal.CANCELADO
            documento.motivo_cancelamento = motivo
            documento.cancelamento_em = timezone.now()
            documento.mensagem_cancelamento = "Cancelamento local antes da autorização SEFAZ."
            documento.save(
                update_fields=[
                    "status",
                    "motivo_cancelamento",
                    "cancelamento_em",
                    "mensagem_cancelamento",
                    "atualizado_em",
                ]
            )
            LogAuditoria.objects.create(
                usuario=usuario,
                modulo="fiscal",
                acao="CANCELA_DOCUMENTO",
                descricao=f"Documento fiscal {documento.id} cancelado antes da autorização. Motivo: {motivo}",
                objeto_tipo="DocumentoFiscal",
                objeto_id=str(documento.id),
                ip=ip,
            )
            return documento

        if documento.status != StatusDocumentoFiscal.EMITIDO:
            raise ValidationError("Somente documentos prontos, rejeitados ou emitidos podem ser cancelados.")
        if len(documento.chave_acesso) != 44 or not documento.chave_acesso.isdigit():
            raise ValidationError("Documento emitido sem chave de acesso válida para cancelamento.")
        if not documento.protocolo:
            raise ValidationError("Documento emitido sem protocolo de autorização para cancelamento.")

        if documento.ambiente == "HOMOLOGACAO" and documento.protocolo.startswith("HOM"):
            documento.status = StatusDocumentoFiscal.CANCELADO
            documento.motivo_cancelamento = motivo
            documento.protocolo_cancelamento = f"HOMC{timezone.now():%Y%m%d%H%M%S}{documento.pk:06d}"
            documento.cancelamento_em = timezone.now()
            documento.mensagem_cancelamento = "Cancelamento simulado em homologação."
            documento.save(
                update_fields=[
                    "status",
                    "motivo_cancelamento",
                    "protocolo_cancelamento",
                    "cancelamento_em",
                    "mensagem_cancelamento",
                    "atualizado_em",
                ]
            )
            LogAuditoria.objects.create(
                usuario=usuario,
                modulo="fiscal",
                acao="CANCELAMENTO_SIMULADO",
                descricao=f"Documento fiscal {documento.id} cancelado em homologação simulada. Motivo: {motivo}",
                objeto_tipo="DocumentoFiscal",
                objeto_id=str(documento.id),
                ip=ip,
            )
            return documento

        idempotency_key = (
            f"fiscal-cancelamento:{documento.pk}:{documento.protocolo}"
        )

    try:
        adapter = carregar_adaptador_sefaz()
        cancelar = getattr(adapter, "cancelar", None)
        if not callable(cancelar):
            raise SefazAdapterError(
                "O adaptador SEFAZ configurado não implementa cancelamento autorizado."
            )
        retorno = cancelar(
            documento=documento,
            chave_acesso=documento.chave_acesso,
            protocolo_autorizacao=documento.protocolo,
            justificativa=motivo,
            idempotency_key=idempotency_key,
            ambiente=documento.ambiente,
        )
        resultado = normalizar_retorno_cancelamento(retorno)
    except Exception as exc:
        mensagem = (
            str(exc)
            if isinstance(exc, (SefazAdapterError, ValidationError))
            else "Falha na comunicação com o adaptador SEFAZ durante o cancelamento."
        )
        DocumentoFiscal.objects.filter(pk=documento.pk).update(
            mensagem_cancelamento=mensagem,
            atualizado_em=timezone.now(),
        )
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="CANCELAMENTO_SEFAZ_FALHA",
            descricao=f"Falha ao cancelar documento fiscal {documento.id}: {mensagem}",
            objeto_tipo="DocumentoFiscal",
            objeto_id=str(documento.id),
            ip=ip,
        )
        raise ValidationError(mensagem) from exc

    with transaction.atomic():
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        if documento.status == StatusDocumentoFiscal.CANCELADO:
            return documento
        documento.motivo_cancelamento = motivo
        documento.mensagem_cancelamento = resultado.mensagem
        if resultado.status == "CANCELADO":
            documento.status = StatusDocumentoFiscal.CANCELADO
            documento.protocolo_cancelamento = resultado.protocolo
            documento.cancelamento_em = timezone.now()
        documento.save(
            update_fields=[
                "status",
                "motivo_cancelamento",
                "protocolo_cancelamento",
                "cancelamento_em",
                "mensagem_cancelamento",
                "atualizado_em",
            ]
        )

    acao = {
        "CANCELADO": "CANCELAMENTO_SEFAZ_AUTORIZADO",
        "REJEITADO": "CANCELAMENTO_SEFAZ_REJEITADO",
        "PENDENTE": "CANCELAMENTO_SEFAZ_PENDENTE",
    }[resultado.status]
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao=acao,
        descricao=(
            f"Cancelamento SEFAZ do documento fiscal {documento.id}: {resultado.status}. "
            f"Protocolo: {resultado.protocolo or '-'}; motivo: {motivo}"
        ),
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.id),
        ip=ip,
    )
    if resultado.status != "CANCELADO":
        raise ValidationError(
            resultado.mensagem
            or "O cancelamento ainda não foi autorizado pela SEFAZ."
        )
    return documento



def consultar_situacao_documento(documento, usuario, ip=None):
    with transaction.atomic():
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        if documento.status in {StatusDocumentoFiscal.RASCUNHO, StatusDocumentoFiscal.INUTILIZADO}:
            raise ValidationError("Este documento não possui situação consultável na SEFAZ.")
        if len(documento.chave_acesso) != 44 or not documento.chave_acesso.isdigit():
            raise ValidationError("Informe uma chave de acesso fiscal válida com 44 dígitos.")
        chave_acesso = documento.chave_acesso
        idempotency_key = f"fiscal-consulta:{documento.pk}:{chave_acesso}"
        documento.tentativas_consulta_sefaz += 1
        documento.save(
            update_fields=["tentativas_consulta_sefaz", "atualizado_em"]
        )

    try:
        adapter = carregar_adaptador_sefaz()
        consultar = getattr(adapter, "consultar", None)
        if not callable(consultar):
            raise SefazAdapterError(
                "O adaptador SEFAZ configurado não implementa consulta de protocolo."
            )
        resultado = normalizar_retorno_consulta(
            consultar(
                documento=documento,
                chave_acesso=chave_acesso,
                idempotency_key=idempotency_key,
                ambiente=documento.ambiente,
            )
        )
    except Exception as exc:
        mensagem = (
            str(exc)
            if isinstance(exc, (ImproperlyConfigured, SefazAdapterError, ValidationError))
            else "Falha na comunicação com o adaptador SEFAZ durante a consulta."
        )
        DocumentoFiscal.objects.filter(pk=documento.pk).update(
            consulta_sefaz_em=timezone.now(),
            mensagem_consulta_sefaz=mensagem,
            atualizado_em=timezone.now(),
        )
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="CONSULTA_SEFAZ_FALHA",
            descricao=f"Falha ao consultar documento fiscal {documento.pk}: {mensagem}",
            objeto_tipo="DocumentoFiscal",
            objeto_id=str(documento.pk),
            ip=ip,
        )
        raise ValidationError(mensagem) from exc

    agora = timezone.now()
    with transaction.atomic():
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        documento.consulta_sefaz_em = agora
        documento.mensagem_consulta_sefaz = resultado.mensagem
        update_fields = [
            "consulta_sefaz_em",
            "mensagem_consulta_sefaz",
            "atualizado_em",
        ]
        if resultado.status == "AUTORIZADO":
            documento.aguardando_consulta_sefaz = False
            documento.status = StatusDocumentoFiscal.EMITIDO
            documento.protocolo = resultado.protocolo
            documento.protocolo_cancelamento = ""
            documento.cancelamento_em = None
            update_fields.extend(
                [
                    "status",
                    "protocolo",
                    "protocolo_cancelamento",
                    "cancelamento_em",
                    "aguardando_consulta_sefaz",
                ]
            )
        elif resultado.status == "CANCELADO":
            documento.aguardando_consulta_sefaz = False
            documento.status = StatusDocumentoFiscal.CANCELADO
            if resultado.protocolo:
                documento.protocolo = resultado.protocolo
            documento.protocolo_cancelamento = resultado.protocolo_cancelamento
            update_fields.extend(
                ["status", "protocolo", "protocolo_cancelamento", "aguardando_consulta_sefaz"]
            )
        elif resultado.status == "DENEGADO":
            documento.aguardando_consulta_sefaz = False
            documento.status = StatusDocumentoFiscal.DENEGADO
            documento.protocolo = resultado.protocolo
            update_fields.extend(["status", "protocolo", "aguardando_consulta_sefaz"])
        elif resultado.status == "NAO_LOCALIZADO":
            documento.aguardando_consulta_sefaz = False
            documento.tentativas_transmissao = 0
            update_fields.extend(
                ["aguardando_consulta_sefaz", "tentativas_transmissao"]
            )
        else:
            documento.aguardando_consulta_sefaz = True
            update_fields.append("aguardando_consulta_sefaz")
        documento.save(update_fields=update_fields)

    acao = {
        "AUTORIZADO": "CONSULTA_SEFAZ_AUTORIZADO",
        "CANCELADO": "CONSULTA_SEFAZ_CANCELADO",
        "DENEGADO": "CONSULTA_SEFAZ_DENEGADO",
        "NAO_LOCALIZADO": "CONSULTA_SEFAZ_NAO_LOCALIZADO",
        "PENDENTE": "CONSULTA_SEFAZ_PENDENTE",
    }[resultado.status]
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao=acao,
        descricao=(
            f"Consulta SEFAZ do documento fiscal {documento.pk}: {resultado.status}. "
            f"Protocolo: {resultado.protocolo or '-'}; "
            f"evento: {resultado.protocolo_cancelamento or '-'}."
        ),
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.pk),
        ip=ip,
    )
    return documento, resultado


def solicitar_inutilizacao_numeracao(
    *,
    filial,
    tipo_documento,
    ano,
    serie,
    numero_inicial,
    numero_final,
    justificativa,
    usuario,
    ip=None,
):
    justificativa = (justificativa or "").strip()
    ano_atual = timezone.localdate().year
    if not 15 <= len(justificativa) <= 255:
        raise ValidationError("A justificativa deve ter entre 15 e 255 caracteres.")
    if ano < 2006 or ano > ano_atual:
        raise ValidationError(f"O ano deve estar entre 2006 e {ano_atual}.")
    if serie < 0 or serie > 889:
        raise ValidationError("A série fiscal deve estar entre 0 e 889.")
    if numero_inicial < 1 or numero_final > 999999999:
        raise ValidationError("Os números fiscais devem estar entre 1 e 999999999.")
    if numero_final < numero_inicial:
        raise ValidationError("O número final não pode ser menor que o número inicial.")
    if numero_final - numero_inicial + 1 > 10000:
        raise ValidationError("A faixa não pode ultrapassar 10.000 números por solicitação.")
    if tipo_documento not in TipoDocumentoFiscal.values:
        raise ValidationError("Tipo de documento fiscal inválido.")

    with transaction.atomic():
        configuracao = (
            ConfiguracaoFiscal.objects.select_for_update()
            .filter(filial=filial, ativo=True)
            .first()
        )
        if not configuracao:
            raise ValidationError("A filial não possui configuração fiscal ativa.")
        if not SerieFiscal.objects.select_for_update().filter(
            filial=filial,
            tipo_documento=tipo_documento,
            serie=serie,
            ativo=True,
        ).exists():
            raise ValidationError("A série informada não está ativa para esta filial e documento.")

        cnpj = re.sub(r"\D", "", filial.cnpj or filial.empresa.cnpj or "")
        if len(cnpj) != 14:
            raise ValidationError("A filial não possui CNPJ válido para a solicitação à SEFAZ.")

        sobreposta = InutilizacaoNumeracaoFiscal.objects.select_for_update().filter(
            filial=filial,
            tipo_documento=tipo_documento,
            ambiente=configuracao.ambiente,
            ano=ano,
            serie=serie,
            status__in=[StatusInutilizacaoFiscal.PENDENTE, StatusInutilizacaoFiscal.AUTORIZADA],
            numero_inicial__lte=numero_final,
            numero_final__gte=numero_inicial,
        ).exists()
        if sobreposta:
            raise ValidationError("A faixa cruza uma inutilização pendente ou já autorizada.")

        documento_usado = DocumentoFiscal.objects.filter(
            filial=filial,
            tipo_documento=tipo_documento,
            serie=serie,
            numero__gte=numero_inicial,
            numero__lte=numero_final,
        ).order_by("numero").first()
        if documento_usado:
            raise ValidationError(
                f"O número {documento_usado.numero} já foi usado por um documento fiscal "
                f"com status {documento_usado.get_status_display()}."
            )

        inutilizacao = InutilizacaoNumeracaoFiscal.objects.create(
            filial=filial,
            tipo_documento=tipo_documento,
            ambiente=configuracao.ambiente,
            ano=ano,
            serie=serie,
            numero_inicial=numero_inicial,
            numero_final=numero_final,
            justificativa=justificativa,
            usuario=usuario,
        )
        idempotency_key = (
            f"fiscal-inutilizacao:{filial.pk}:{tipo_documento}:{ano}:"
            f"{serie}:{numero_inicial}:{numero_final}:{configuracao.ambiente}"
        )

    try:
        adapter_path = getattr(settings, "FISCAL_SEFAZ_ADAPTER", "").strip()
        if configuracao.ambiente == AmbienteFiscal.HOMOLOGACAO and not adapter_path:
            resultado = normalizar_retorno_inutilizacao(
                {
                    "status": "INUTILIZADA",
                    "protocolo": f"HOMI{timezone.now():%Y%m%d%H%M%S}{inutilizacao.pk:06d}",
                    "mensagem": "Inutilização simulada em ambiente de homologação.",
                }
            )
        else:
            adapter = carregar_adaptador_sefaz()
            inutilizar = getattr(adapter, "inutilizar", None)
            if not callable(inutilizar):
                raise SefazAdapterError(
                    "O adaptador SEFAZ configurado não implementa inutilização de numeração."
                )
            resultado = normalizar_retorno_inutilizacao(
                inutilizar(
                    inutilizacao=inutilizacao,
                    cnpj=cnpj,
                    tipo_documento=tipo_documento,
                    ano=ano,
                    serie=serie,
                    numero_inicial=numero_inicial,
                    numero_final=numero_final,
                    justificativa=justificativa,
                    idempotency_key=idempotency_key,
                    ambiente=configuracao.ambiente,
                )
            )
    except Exception as exc:
        mensagem = (
            str(exc)
            if isinstance(exc, (ImproperlyConfigured, SefazAdapterError, ValidationError))
            else "Falha na comunicação com o adaptador SEFAZ durante a inutilização."
        )
        InutilizacaoNumeracaoFiscal.objects.filter(pk=inutilizacao.pk).update(
            mensagem_retorno=mensagem,
            atualizado_em=timezone.now(),
        )
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="INUTILIZACAO_SEFAZ_FALHA",
            descricao=f"Falha na inutilização fiscal {inutilizacao.pk}: {mensagem}",
            objeto_tipo="InutilizacaoNumeracaoFiscal",
            objeto_id=str(inutilizacao.pk),
            ip=ip,
        )
        raise ValidationError(mensagem) from exc

    with transaction.atomic():
        inutilizacao = InutilizacaoNumeracaoFiscal.objects.select_for_update().get(pk=inutilizacao.pk)
        inutilizacao.mensagem_retorno = resultado.mensagem
        if resultado.status == "INUTILIZADA":
            inutilizacao.status = StatusInutilizacaoFiscal.AUTORIZADA
            inutilizacao.protocolo = resultado.protocolo
        elif resultado.status == "REJEITADA":
            inutilizacao.status = StatusInutilizacaoFiscal.REJEITADA
        inutilizacao.save(
            update_fields=["status", "protocolo", "mensagem_retorno", "atualizado_em"]
        )

    acao = {
        "INUTILIZADA": "INUTILIZACAO_SEFAZ_AUTORIZADA",
        "REJEITADA": "INUTILIZACAO_SEFAZ_REJEITADA",
        "PENDENTE": "INUTILIZACAO_SEFAZ_PENDENTE",
    }[resultado.status]
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao=acao,
        descricao=(
            f"Inutilização {tipo_documento} série {serie}, faixa "
            f"{numero_inicial}-{numero_final}/{ano}: {resultado.status}. "
            f"Protocolo: {resultado.protocolo or '-'}."
        ),
        objeto_tipo="InutilizacaoNumeracaoFiscal",
        objeto_id=str(inutilizacao.pk),
        ip=ip,
    )
    if resultado.status != "INUTILIZADA":
        raise ValidationError(
            resultado.mensagem or "A inutilização ainda não foi autorizada pela SEFAZ."
        )
    return inutilizacao
