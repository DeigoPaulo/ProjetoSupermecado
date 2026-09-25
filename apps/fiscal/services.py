import re
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import Q, Subquery
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.marketplace.documentos_destinatario import normalizar_documento_cliente
from apps.vendas.models import StatusPagamento, TipoDocumentoConsumidor, Venda

from .adapters import (
    SefazAdapterError,
    caminho_adaptador_sefaz,
    carregar_adaptador_sefaz,
    normalizar_retorno_cancelamento,
    normalizar_retorno_consulta,
    normalizar_retorno_inutilizacao,
    normalizar_retorno_transmissao,
)
from .assinaturas import assinar_xml_documento, verificar_assinatura_xml
from .evidencias import registrar_evidencia_fiscal
from .cbenef import codigos_cbenef_go_validos
from .cest import queryset_codigos_cest_vigentes, validar_cest
from .cfop import validar_cfop
from .cenarios_tributarios import pendencias_cenario_fiscal_go
from .estrategia_normalizacao_cnpj import canonicalizar_cnpj
from .chave_acesso import (
    construir_chave_acesso,
    normalizar_chave_acesso,
    normalizar_cnpj_emitente,
)
from .ncm import queryset_codigos_ncm_vigentes, validar_ncm
from .ibs_cbs.calculo import calcular_base_operacao_padrao, calcular_ibs_cbs_padrao
from .ibs_cbs.catalogo import ClassificacaoIbsCbsInvalida, validar_classificacao
from .ibs_cbs.contrato import emissao_ibs_cbs_obrigatoria
from .ibs_cbs.xml import adicionar_grupo_item as adicionar_ibs_cbs_item
from .ibs_cbs.xml import adicionar_totais as adicionar_totais_ibs_cbs
from .validacoes import validar_xml_pre_transmissao
from .qrcode_nfce import gerar_url_qrcode_nfce
from .perfis_uf import codigo_beneficio_produto_operacao, pendencias_endpoints_nfce, pendencias_produto_por_uf
from .models import (
    AmbienteFiscal,
    CodigoRegimeTributario,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    TipoEvidenciaFiscal,
    InutilizacaoNumeracaoFiscal,
    ModoTransicaoIbsCbs,
    NaturezaOperacao,
    ParametrizacaoBeneficioFiscalProduto,
    SerieFiscal,
    StatusDocumentoFiscal,
    StatusInutilizacaoFiscal,
    TipoDocumentoFiscal,
)

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
ET.register_namespace("", NFE_NS)


def _canal_evidencia_fiscal(documento):
    try:
        return documento.filial.configuracao_fiscal.provedor_emissao
    except ConfiguracaoFiscal.DoesNotExist:
        return "PADRAO_SERVIDOR"


def _resultado_evidencia(resultado):
    return {
        campo: getattr(resultado, campo)
        for campo in (
            "status",
            "chave_acesso",
            "protocolo",
            "protocolo_cancelamento",
            "mensagem",
        )
        if hasattr(resultado, campo)
    }


def _reserva_transmissao(documento, reserva_token=None):
    """Confirma uma reserva da fila ou cria uma reserva exclusiva para chamada manual."""
    gerenciada_pela_fila = reserva_token is not None
    if gerenciada_pela_fila:
        try:
            token = uuid.UUID(str(reserva_token))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValidationError("A reserva da operação fiscal é inválida.") from exc
        if documento.transmissao_reserva_token != token:
            raise ValidationError(
                "A reserva da operação fiscal não pertence a este processo. Atualize a situação antes de continuar."
            )
        return token, True

    agora = timezone.now()
    lease_segundos = max(
        30, int(getattr(settings, "FISCAL_AUTO_TRANSMIT_LEASE_SECONDS", 300))
    )
    reserva_ativa = bool(
        documento.transmissao_reserva_token
        and documento.transmissao_reservada_em
        and documento.transmissao_reservada_em
        >= agora - timedelta(seconds=lease_segundos)
    )
    if reserva_ativa:
        raise ValidationError(
            "Este documento já está reservado por outro processo fiscal. Aguarde ou consulte a situação."
        )

    token = uuid.uuid4()
    documento.transmissao_reservada_em = agora
    documento.transmissao_reserva_token = token
    documento.save(
        update_fields=[
            "transmissao_reservada_em",
            "transmissao_reserva_token",
            "atualizado_em",
        ]
    )
    return token, False


def _confirmar_reserva_transmissao(documento, token):
    if documento.transmissao_reserva_token != token:
        raise ValidationError(
            "A reserva da operação fiscal expirou ou foi assumida por outro processo. "
            "Consulte a situação antes de repetir a operação."
        )

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


def _chave_acesso_documento(documento, filial, modelo, tipo_emissao):
    cnpj = str(filial.cnpj or filial.empresa.cnpj or "").strip()
    codigo_uf = CODIGOS_UF_IBGE.get(filial.uf)
    if not codigo_uf:
        raise ValidationError("UF do emitente inválida para gerar a chave fiscal.")
    data = timezone.localtime(documento.criado_em).strftime("%y%m")
    serie = f"{documento.serie:03d}"
    numero = f"{documento.numero:09d}"
    codigo_numerico = f"{documento.pk:08d}"[-8:]
    try:
        chave = construir_chave_acesso(
            codigo_uf=codigo_uf,
            aamm=data,
            cnpj_emitente=cnpj,
            modelo=modelo,
            serie=serie,
            numero=numero,
            tipo_emissao=tipo_emissao,
            codigo_numerico=codigo_numerico,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return chave, codigo_numerico


def documento_em_contingencia_offline(documento):
    """Identifica NFC-e tpEmis 9 mesmo durante correção de rejeição."""
    chave = normalizar_chave_acesso(getattr(documento, "chave_acesso", ""))
    return bool(
        documento.tipo_documento == TipoDocumentoFiscal.NFCE
        and documento.contingencia_iniciada_em
        and documento.contingencia_justificativa
        and (
            documento.status == StatusDocumentoFiscal.CONTINGENCIA
            or (len(chave) == 44 and chave[34] == "9")
        )
    )


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


PAGAMENTOS_ELETRONICOS_COM_VINCULO = {"03", "04", "10", "11", "17"}
PAGAMENTOS_COM_BANDEIRA = {"03", "04", "10", "11"}


def validar_vinculos_pagamentos_xml(documento, inf_nfe):
    """Revalida XML já preparado, antes de qualquer envio por Focus/SEFAZ."""
    if documento.tipo_documento != TipoDocumentoFiscal.NFCE or not documento.venda_id:
        return
    parcelas_xml = inf_nfe.findall(f"{{{NFE_NS}}}pag/{{{NFE_NS}}}detPag")
    pagamentos = list(documento.venda.pagamentos.select_related(
        "forma_pagamento", "confirmacao_integracao", "venda",
    ).order_by("pk"))
    possui_integracao = any(
        item.find(f"{{{NFE_NS}}}card") is not None for item in parcelas_xml
    ) or any(
        p.tipo_integracao or p.confirmacao_integracao_id
        or (documento.filial.uf == "GO" and _codigo_pagamento(p.forma_pagamento.tipo) in PAGAMENTOS_ELETRONICOS_COM_VINCULO)
        for p in pagamentos
    )
    if not possui_integracao:
        return
    if len(parcelas_xml) != len(pagamentos):
        raise ValidationError("Parcelas do XML divergem dos pagamentos confirmados no servidor.")
    for parcela_xml, pagamento in zip(parcelas_xml, pagamentos):
        esperado = ET.Element(f"{{{NFE_NS}}}detPag")
        codigo = _codigo_pagamento(pagamento.forma_pagamento.tipo)
        _adicionar_integracao_pagamento_nfce(
            esperado, pagamento, codigo, uf_emitente=documento.filial.uf,
        )
        card_esperado = esperado.find(f"{{{NFE_NS}}}card")
        card_xml = parcela_xml.find(f"{{{NFE_NS}}}card")
        campos = lambda card: None if card is None else [(item.tag, item.text) for item in card]
        if (
            parcela_xml.findtext(f"{{{NFE_NS}}}tPag") != codigo
            or parcela_xml.findtext(f"{{{NFE_NS}}}vPag") != _valor(pagamento.valor)
            or len(parcela_xml.findall(f"{{{NFE_NS}}}card")) != (0 if card_esperado is None else 1)
            or campos(card_xml) != campos(card_esperado)
        ):
            raise ValidationError("Vínculo fiscal do XML diverge da confirmação integrada do servidor.")


def _adicionar_integracao_pagamento_nfce(
    det_pag, pagamento, codigo_pagamento, *, uf_emitente
):
    from apps.vendas.integracao_pagamentos import validar_origem_integracao_fiscal

    if pagamento.confirmacao_integracao_id:
        validar_origem_integracao_fiscal(pagamento)
    tipo_integracao = str(pagamento.tipo_integracao or "").strip()
    try:
        cnpj_instituicao = canonicalizar_cnpj(
            pagamento.cnpj_instituicao_pagamento or ""
        )
        cnpj_beneficiario = canonicalizar_cnpj(
            pagamento.cnpj_beneficiario_pagamento or ""
        )
    except ValueError as exc:
        raise ValidationError(f"CNPJ do pagamento eletrônico inválido: {exc}") from exc
    bandeira = str(pagamento.bandeira_cartao or "").strip()
    autorizacao = str(pagamento.codigo_autorizacao or "").strip()
    terminal = str(pagamento.identificador_terminal_pagamento or "").strip()
    possui_dados = any(
        (
            tipo_integracao, cnpj_instituicao, bandeira, autorizacao,
            cnpj_beneficiario, terminal,
        )
    )

    if codigo_pagamento not in PAGAMENTOS_ELETRONICOS_COM_VINCULO:
        if possui_dados:
            raise ValidationError(
                "Dados de integração eletrônica informados em forma de pagamento incompatível."
            )
        return

    if uf_emitente != "GO" and not any(
        (tipo_integracao, cnpj_instituicao, bandeira, cnpj_beneficiario, terminal)
    ):
        return
    if tipo_integracao not in {"1", "2"}:
        raise ValidationError(
            "Informe o tipo de integração fiscal da parcela eletrônica antes de emitir a NFC-e."
        )
    if tipo_integracao == "1" and not cnpj_instituicao:
        raise ValidationError(
            "Pagamento eletrônico integrado exige o CNPJ da instituição de pagamento."
        )
    if tipo_integracao == "1" and not autorizacao:
        raise ValidationError(
            "Pagamento eletrônico integrado exige a autorização confirmada pelo adaptador."
        )
    if tipo_integracao == "1" and (
        pagamento.status != StatusPagamento.CONFIRMADO
        or not pagamento.transacao_externa_id
        or not pagamento.nsu
    ):
        raise ValidationError(
            "Pagamento integrado exige confirmação, transação externa e NSU do adaptador."
        )
    for cnpj, rotulo in (
        (cnpj_instituicao, "CNPJ da instituição de pagamento"),
        (cnpj_beneficiario, "CNPJ do beneficiário do pagamento"),
    ):
        if cnpj and len(cnpj) != 14:
            raise ValidationError(f"{rotulo} deve conter 14 caracteres canônicos.")
    if bandeira and (len(bandeira) != 2 or not bandeira.isdigit()):
        raise ValidationError("Bandeira do cartão deve usar o código fiscal de 2 dígitos.")
    if codigo_pagamento not in PAGAMENTOS_COM_BANDEIRA and bandeira:
        raise ValidationError("Pagamento PIX não aceita bandeira de cartão no XML da NFC-e.")
    if len(autorizacao) > 128:
        raise ValidationError("Código de autorização do pagamento excede 128 caracteres.")
    if len(terminal) > 40:
        raise ValidationError("Identificador do terminal de pagamento excede 40 caracteres.")

    # cAut sem confirmação autenticada pode vir do POST, do legado ou do
    # simulador, inclusive quando tpIntegra=2. O XSD não prova sua origem.
    if autorizacao and not pagamento.confirmacao_integracao_id:
        raise ValidationError(
            "Código de autorização fiscal exige confirmação confiável no servidor; "
            "não use autorização simulada, NSU, ID externo ou texto digitado."
        )
    card = ET.SubElement(det_pag, f"{{{NFE_NS}}}card")
    _texto(card, "tpIntegra", tipo_integracao)
    if cnpj_instituicao:
        _texto(card, "CNPJ", cnpj_instituicao)
    if bandeira:
        _texto(card, "tBand", bandeira)
    if autorizacao:
        _texto(card, "cAut", autorizacao)
    if cnpj_beneficiario:
        _texto(card, "CNPJReceb", cnpj_beneficiario)
    if terminal:
        _texto(card, "idTermPag", terminal)


def _crt_configuracao(configuracao):
    return str(configuracao.crt or "").strip()


def _usa_csosn(configuracao):
    return _crt_configuracao(configuracao) in {
        CodigoRegimeTributario.SIMPLES_NACIONAL,
        CodigoRegimeTributario.MEI,
    }


def _documento_consumidor_nfce(venda):
    tipo = venda.documento_consumidor_tipo
    original = str(venda.documento_consumidor or "").strip()
    if tipo == TipoDocumentoConsumidor.NAO_IDENTIFICADO or not original:
        return None
    tipo, documento = normalizar_documento_cliente(tipo, original)
    if tipo in {
        TipoDocumentoConsumidor.CPF,
        TipoDocumentoConsumidor.CNPJ,
        TipoDocumentoConsumidor.ESTRANGEIRO,
    }:
        return {"tipo": tipo, "documento": documento}
    raise ValidationError("Documento do consumidor inválido para NFC-e.")


def _endereco_emitente_nfce(emit, filial):
    """Usa somente endereço estruturado da filial; ausência fica visível no XSD."""
    obrigatorios = (
        filial.logradouro, filial.numero, filial.bairro, filial.codigo_municipio_ibge,
        filial.municipio, filial.uf,
    )
    if not all(str(valor or "").strip() for valor in obrigatorios):
        return
    endereco = ET.SubElement(emit, f"{{{NFE_NS}}}enderEmit")
    _texto(endereco, "xLgr", filial.logradouro.strip()[:60])
    _texto(endereco, "nro", filial.numero.strip()[:60])
    if filial.complemento.strip():
        _texto(endereco, "xCpl", filial.complemento.strip()[:60])
    _texto(endereco, "xBairro", filial.bairro.strip()[:60])
    _texto(endereco, "cMun", filial.codigo_municipio_ibge.strip())
    _texto(endereco, "xMun", filial.municipio.strip()[:60])
    _texto(endereco, "UF", filial.uf.strip())
    if filial.cep.strip():
        _texto(endereco, "CEP", _somente_digitos(filial.cep))
    _texto(endereco, "cPais", "1058")
    _texto(endereco, "xPais", "BRASIL")
    if filial.telefone.strip():
        _texto(endereco, "fone", _somente_digitos(filial.telefone)[:14])


def pendencias_endereco_emitente_nfce(filial):
    """Preflight local GO: o cadastro deve fornecer o enderEmit, sem inferências."""
    if filial.uf != "GO":
        return []
    campos = (
        ("logradouro", filial.logradouro), ("número", filial.numero),
        ("bairro", filial.bairro), ("código IBGE do município", filial.codigo_municipio_ibge),
        ("município", filial.municipio), ("UF", filial.uf),
    )
    erros = [
        f"Informe {nome} do endereço fiscal da filial para NFC-e GO."
        for nome, valor in campos if not str(valor or "").strip()
    ]
    codigo = str(filial.codigo_municipio_ibge or "").strip()
    if codigo and (not re.fullmatch(r"\d{7}", codigo) or not codigo.startswith("52")):
        erros.append("O código IBGE do município da filial deve ter 7 dígitos e pertencer a Goiás (52).")
    if not re.fullmatch(r"[A-Z]{2}", str(filial.uf or "")) or filial.uf != "GO":
        erros.append("A UF do emitente da NFC-e GO deve ser GO.")
    cep = str(filial.cep or "").strip()
    if not cep:
        erros.append("Informe o CEP do endereço fiscal da filial para NFC-e GO.")
    elif not re.fullmatch(r"\d{5}-?\d{3}", cep):
        erros.append("O CEP do emitente, quando informado, deve possuir 8 dígitos.")
    telefone = str(filial.telefone or "").strip()
    if telefone and not 6 <= len(_somente_digitos(telefone)) <= 14:
        erros.append("O telefone do emitente, quando informado, deve possuir 6 a 14 dígitos.")
    return erros


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
            "emissao_xml_recorte": "GO CRT 3, modelos 55/65, CST 000 e cClassTrib 000001",
            "modo_seguro": "contrato normativo por cenário e falha fechada fora do catálogo",
            "bloqueio": (
                "O suporte genérico permanece bloqueado; monofasia, regimes especiais e "
                "classificações fora do recorte GO CRT 3 exigem contrato e homologação próprios."
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


def filtro_pendencias_produto_fiscal(
    regimes_tributarios=None,
    ufs=None,
    crts=None,
    exigir_ibs_cbs=False,
    naturezas_operacao=None,
):
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
    codigos_ncm = queryset_codigos_ncm_vigentes()
    if codigos_ncm is not None:
        pendente |= ~Q(ncm__in=Subquery(codigos_ncm))
    codigos_cest = queryset_codigos_cest_vigentes()
    if codigos_cest is not None:
        pendente |= ~Q(cest="") & ~Q(cest__in=Subquery(codigos_cest))
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
        naturezas = [natureza for natureza in (naturezas_operacao or []) if natureza]
        if exige_normal and naturezas:
            codigos_catalogados = codigos_cbenef_go_validos()
            for natureza in naturezas:
                parametros_natureza = ParametrizacaoBeneficioFiscalProduto.objects.filter(
                    natureza_operacao=natureza,
                )
                parametros_definidos = parametros_natureza.filter(
                    situacao__in=["SEM_BENEFICIO", "COM_BENEFICIO"],
                )
                pendente |= ~Q(pk__in=Subquery(parametros_definidos.values("produto_id")))

                parametros_com_codigo = parametros_natureza.filter(
                    codigo_beneficio_fiscal__regex=r"^(GO\d{6}|SEM CBENEF)$",
                )
                pendente |= Q(reducao_base_icms__gt=0) & ~Q(
                    pk__in=Subquery(parametros_com_codigo.values("produto_id"))
                )
                if codigos_catalogados:
                    parametros_com_beneficio = parametros_natureza.filter(
                        situacao="COM_BENEFICIO",
                    )
                    parametros_com_beneficio_valido = parametros_com_beneficio.filter(
                        codigo_beneficio_fiscal__in=sorted(codigos_catalogados),
                    )
                    pendente |= Q(
                        pk__in=Subquery(parametros_com_beneficio.values("produto_id"))
                    ) & ~Q(
                        pk__in=Subquery(parametros_com_beneficio_valido.values("produto_id"))
                    )
        else:
            if exige_normal:
                pendente |= Q(reducao_base_icms__gt=0, codigo_beneficio_fiscal="")
            codigos_catalogados = codigos_cbenef_go_validos()
            if not codigos_catalogados:
                pendente |= ~Q(codigo_beneficio_fiscal="")
            else:
                pendente |= ~Q(codigo_beneficio_fiscal="") & ~Q(
                    codigo_beneficio_fiscal__in=sorted(codigos_catalogados)
                )
    return pendente


def _pendencias_ibs_cbs_produto(
    produto, exigido=False, modelo="65", *, validar_catalogo=False
):
    if not exigido:
        return []
    pendencias = []
    if not re.fullmatch(r"\d{3}", produto.cst_ibs_cbs or ""):
        pendencias.append("CST IBS/CBS com 3 dígitos")
    if not re.fullmatch(r"\d{6}", produto.classificacao_tributaria_ibs_cbs or ""):
        pendencias.append("cClassTrib IBS/CBS com 6 dígitos")
    if pendencias or not validar_catalogo:
        return pendencias
    try:
        validar_classificacao(
            produto.cst_ibs_cbs,
            produto.classificacao_tributaria_ibs_cbs,
            modelo,
        )
    except ClassificacaoIbsCbsInvalida as exc:
        pendencias.append(str(exc))
    return pendencias


def _pendencias_emissao_ibs_cbs(configuracao, filial, modelo):
    if configuracao.modo_transicao_ibs_cbs != ModoTransicaoIbsCbs.EMISSAO_HOMOLOGADA:
        return []
    if _ibs_cbs_obrigatorio(configuracao, filial, modelo):
        return []
    return [
        "Emissão XML IBS/CBS fora do recorte GO CRT 3 padrão permanece bloqueada; "
        "classifique a operação e homologue um contrato fiscal específico."
    ]


def _ibs_cbs_obrigatorio(configuracao, filial, modelo, data_emissao=None):
    return emissao_ibs_cbs_obrigatoria(
        uf=filial.uf,
        crt=_crt_configuracao(configuracao),
        modelo=modelo,
        ambiente=configuracao.ambiente,
        data_emissao=data_emissao or timezone.localdate(),
    )


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
    container = ET.SubElement(imposto, f"{{{NFE_NS}}}{nome}")
    if cst in CST_CONTRIBUICAO_ALIQUOTA:
        grupo = ET.SubElement(container, f"{{{NFE_NS}}}{nome}Aliq")
        base = _moeda(valor_operacao)
        percentual = Decimal(aliquota or 0)
        valor = _moeda(base * percentual / Decimal("100"))
        _texto(grupo, "CST", cst)
        _texto(grupo, "vBC", _valor(base))
        _texto(grupo, f"p{nome}", _valor(percentual, casas=4))
        _texto(grupo, f"v{nome}", _valor(valor))
        return valor
    if cst in CST_CONTRIBUICAO_NAO_TRIBUTADA:
        grupo = ET.SubElement(container, f"{{{NFE_NS}}}{nome}NT")
        _texto(grupo, "CST", cst)
        return Decimal("0.00")
    if cst in CST_CONTRIBUICAO_OUTRAS:
        grupo = ET.SubElement(container, f"{{{NFE_NS}}}{nome}Outr")
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
    return total

def pendencias_produto_fiscal(
    produto,
    regimes_tributarios=None,
    ufs=None,
    crts=None,
    exigir_ibs_cbs=False,
    naturezas_operacao=None,
):
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
    else:
        pendencia_ncm = validar_ncm(produto.ncm)
        if pendencia_ncm:
            pendencias.append(pendencia_ncm)
    if produto.cest:
        pendencia_cest = validar_cest(produto.cest, produto.ncm)
        if pendencia_cest:
            pendencias.append(pendencia_cest)
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
    naturezas = [natureza for natureza in (naturezas_operacao or []) if natureza]
    if naturezas:
        for natureza in naturezas:
            pendencias.extend(
                f"{natureza.descricao}: {pendencia}"
                for pendencia in pendencias_produto_por_uf(
                    produto, ufs, crts, natureza_operacao=natureza
                )
            )
    else:
        pendencias.extend(pendencias_produto_por_uf(produto, ufs, crts))
    return pendencias


def gerar_xml_nfce(documento):
    if not documento.venda:
        raise ValidationError("Documento fiscal sem venda vinculada.")
    venda = documento.venda
    pendencias_emitente = pendencias_endereco_emitente_nfce(venda.filial)
    if pendencias_emitente:
        raise ValidationError(pendencias_emitente)
    configuracao = venda.filial.configuracao_fiscal
    natureza = documento.natureza_operacao
    erros_cenario = pendencias_cenario_fiscal_go(
        uf_emitente=venda.filial.uf,
        modelo="65",
        cfop=getattr(natureza, "cfop", ""),
        finalidade="1",
        destinatario_contribuinte=False,
        possui_frete=False,
    )
    if erros_cenario:
        raise ValidationError(erros_cenario)
    empresa = venda.filial.empresa
    try:
        cnpj_emitente = normalizar_cnpj_emitente(venda.filial.cnpj or empresa.cnpj)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    data_emissao = timezone.localtime(documento.criado_em).replace(microsecond=0).isoformat()
    exigir_ibs_cbs = _ibs_cbs_obrigatorio(
        configuracao,
        venda.filial,
        "65",
        timezone.localtime(documento.criado_em).date(),
    )
    em_contingencia = documento_em_contingencia_offline(documento)
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
    _endereco_emitente_nfce(emit, venda.filial)
    _texto(emit, "IE", configuracao.inscricao_estadual)
    _texto(emit, "CRT", _crt_configuracao(configuracao))

    consumidor = _documento_consumidor_nfce(venda)
    if consumidor:
        dest = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}dest")
        if consumidor["tipo"] == TipoDocumentoConsumidor.CPF:
            _texto(dest, "CPF", consumidor["documento"])
        elif consumidor["tipo"] == TipoDocumentoConsumidor.CNPJ:
            _texto(dest, "CNPJ", consumidor["documento"])
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
    calculos_ibs_cbs = []
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
        cbenef = codigo_beneficio_produto_operacao(
            produto,
            documento.natureza_operacao,
            uf=documento.filial.uf,
            crt=_crt_configuracao(configuracao),
        )
        if cbenef:
            _texto(prod, "cBenef", cbenef)
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
        if exigir_ibs_cbs:
            try:
                calculo_ibs_cbs = calcular_ibs_cbs_padrao(
                    valor_operacao=calcular_base_operacao_padrao(
                        valor_produtos=composicao_ipi["valor_produto"],
                        desconto=composicao_ipi["desconto"],
                        valor_pis=valor_pis,
                        valor_cofins=valor_cofins,
                        valor_icms=calculo_icms["valor_icms"],
                        valor_fcp=calculo_icms["valor_fcp"],
                    ),
                    cst=produto.cst_ibs_cbs,
                    cclass_trib=produto.classificacao_tributaria_ibs_cbs,
                    modelo="65",
                )
            except (ClassificacaoIbsCbsInvalida, ValueError) as exc:
                raise ValidationError(str(exc)) from exc
            adicionar_ibs_cbs_item(imposto, calculo_ibs_cbs, namespace=NFE_NS)
            calculos_ibs_cbs.append(calculo_ibs_cbs)
        valor_pis_total += valor_pis
        valor_cofins_total += valor_cofins
        valor_produtos_total += composicao_ipi["valor_produto"]
        desconto_total += composicao_ipi["desconto"]

    total = _adicionar_totais_icms(
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
    if exigir_ibs_cbs:
        adicionar_totais_ibs_cbs(total, calculos_ibs_cbs, namespace=NFE_NS)
    transp = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}transp")
    _texto(transp, "modFrete", "9")

    pag = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}pag")
    for pagamento in venda.pagamentos.select_related("forma_pagamento", "confirmacao_integracao").order_by("pk"):
        det_pag = ET.SubElement(pag, f"{{{NFE_NS}}}detPag")
        _texto(det_pag, "indPag", "0")
        codigo_pagamento = _codigo_pagamento(pagamento.forma_pagamento.tipo)
        _texto(det_pag, "tPag", codigo_pagamento)
        _texto(det_pag, "vPag", _valor(pagamento.valor))
        _adicionar_integracao_pagamento_nfce(
            det_pag, pagamento, codigo_pagamento, uf_emitente=venda.filial.uf
        )

    inf_adic = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}infAdic")
    _texto(inf_adic, "infCpl", "XML local de preparacao. Assinatura e transmissao SEFAZ pendentes.")

    inf_supl = ET.SubElement(nfe, f"{{{NFE_NS}}}infNFeSupl")
    _texto(inf_supl, "qrCode", gerar_url_qrcode_nfce(documento, configuracao))
    _texto(inf_supl, "urlChave", configuracao.url_consulta_nfce.strip())

    return ET.tostring(nfe, encoding="unicode", xml_declaration=True)


def _documento_destinatario_pedido(pedido):
    tipo = pedido.documento_cliente_tipo
    documento = str(pedido.documento_cliente or "").strip()
    if not documento and pedido.cliente and pedido.cliente.cpf_cnpj:
        documento = pedido.cliente.cpf_cnpj
    try:
        tipo, documento = normalizar_documento_cliente(
            tipo,
            documento,
            inferir=(tipo == TipoDocumentoConsumidor.NAO_IDENTIFICADO),
        )
    except ValidationError as exc:
        raise ValidationError(exc.messages) from exc
    if tipo == TipoDocumentoConsumidor.CPF:
        return "CPF", documento
    if tipo == TipoDocumentoConsumidor.CNPJ:
        return "CNPJ", documento
    if tipo == TipoDocumentoConsumidor.ESTRANGEIRO and documento:
        return "idEstrangeiro", documento
    raise ValidationError("Pedido online precisa ter CPF, CNPJ ou documento estrangeiro do destinatario para NF-e.")


def _pendencias_destinatario_nfe_pedido(pedido):
    erros = []
    indicador_ie = str(pedido.destinatario_indicador_ie or "").strip()
    inscricao_estadual = _somente_digitos(pedido.destinatario_inscricao_estadual)
    if indicador_ie not in {"1", "2", "9"}:
        erros.append("Informe o indicador de inscrição estadual do destinatário da NF-e.")
    elif indicador_ie == "1" and not inscricao_estadual:
        erros.append("Informe a inscrição estadual do destinatário contribuinte.")
    elif indicador_ie != "1" and inscricao_estadual:
        erros.append("Remova a inscrição estadual ou marque o destinatário como contribuinte.")

    campos = (
        ("logradouro", pedido.destinatario_logradouro),
        ("número", pedido.destinatario_numero),
        ("bairro", pedido.destinatario_bairro),
        ("código IBGE do município", pedido.destinatario_codigo_municipio_ibge),
        ("município", pedido.destinatario_municipio),
        ("UF", pedido.destinatario_uf),
        ("CEP", pedido.destinatario_cep),
    )
    for nome, valor in campos:
        if not str(valor or "").strip():
            erros.append(f"Informe {nome} do endereço fiscal do destinatário.")
    if (
        pedido.destinatario_codigo_municipio_ibge
        and not re.fullmatch(r"\d{7}", pedido.destinatario_codigo_municipio_ibge.strip())
    ):
        erros.append("O código IBGE do município do destinatário deve possuir 7 dígitos.")
    if pedido.destinatario_uf and not re.fullmatch(r"[A-Za-z]{2}", pedido.destinatario_uf.strip()):
        erros.append("A UF do destinatário deve possuir 2 letras.")
    if pedido.destinatario_cep and not re.fullmatch(r"\d{5}-?\d{3}", pedido.destinatario_cep.strip()):
        erros.append("O CEP do destinatário deve possuir 8 dígitos.")
    return erros


def _dados_destinatario_nfe_pedido(pedido):
    erros = _pendencias_destinatario_nfe_pedido(pedido)
    if erros:
        raise ValidationError(erros)
    doc_tag, doc_valor = _documento_destinatario_pedido(pedido)
    return {
        "doc_tag": doc_tag,
        "doc_valor": doc_valor,
        "indicador_ie": str(pedido.destinatario_indicador_ie).strip(),
        "inscricao_estadual": _somente_digitos(pedido.destinatario_inscricao_estadual),
        "logradouro": pedido.destinatario_logradouro.strip(),
        "numero": pedido.destinatario_numero.strip(),
        "complemento": pedido.destinatario_complemento.strip(),
        "bairro": pedido.destinatario_bairro.strip(),
        "codigo_municipio_ibge": pedido.destinatario_codigo_municipio_ibge.strip(),
        "municipio": pedido.destinatario_municipio.strip(),
        "uf": pedido.destinatario_uf.strip().upper(),
        "cep": _somente_digitos(pedido.destinatario_cep),
        "telefone": _somente_digitos(pedido.telefone),
    }


def gerar_xml_nfe_pedido_online(documento):
    if not documento.pedido_online:
        raise ValidationError("Documento fiscal sem pedido online vinculado.")
    pedido = documento.pedido_online
    configuracao = pedido.filial.configuracao_fiscal
    natureza = documento.natureza_operacao
    empresa = pedido.filial.empresa
    try:
        cnpj_emitente = normalizar_cnpj_emitente(pedido.filial.cnpj or empresa.cnpj)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    data_emissao = timezone.localtime(documento.criado_em).replace(microsecond=0).isoformat()
    exigir_ibs_cbs = _ibs_cbs_obrigatorio(
        configuracao,
        pedido.filial,
        "55",
        timezone.localtime(documento.criado_em).date(),
    )
    destinatario = _dados_destinatario_nfe_pedido(pedido)
    em_svc = bool(
        documento.status == StatusDocumentoFiscal.CONTINGENCIA
        and documento.contingencia_iniciada_em
    )
    tipo_emissao = "7" if em_svc else "1"
    chave_acesso, codigo_numerico = _chave_acesso_documento(
        documento, pedido.filial, "55", tipo_emissao
    )
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
    _texto(ide, "tpEmis", tipo_emissao)
    _texto(ide, "cDV", chave_acesso[-1])
    _texto(ide, "tpAmb", "2" if configuracao.ambiente == "HOMOLOGACAO" else "1")
    _texto(ide, "finNFe", "1")
    _texto(ide, "indFinal", "1")
    _texto(ide, "indPres", "2" if pedido.canal == "LOJA_ONLINE" else "9")
    _texto(ide, "procEmi", "0")
    _texto(ide, "verProc", "SupermercadoERP-0.1")
    if em_svc:
        _texto(
            ide,
            "dhCont",
            timezone.localtime(documento.contingencia_iniciada_em)
            .replace(microsecond=0)
            .isoformat(),
        )
        _texto(ide, "xJust", documento.contingencia_justificativa)

    emit = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}emit")
    _texto(emit, "CNPJ", cnpj_emitente)
    _texto(emit, "xNome", empresa.razao_social[:60])
    _texto(emit, "xFant", empresa.nome_fantasia[:60])
    _texto(emit, "IE", configuracao.inscricao_estadual)
    _texto(emit, "CRT", _crt_configuracao(configuracao))

    dest = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}dest")
    _texto(dest, destinatario["doc_tag"], destinatario["doc_valor"])
    _texto(dest, "xNome", pedido.nome_cliente[:60])
    ender_dest = ET.SubElement(dest, f"{{{NFE_NS}}}enderDest")
    _texto(ender_dest, "xLgr", destinatario["logradouro"][:60])
    _texto(ender_dest, "nro", destinatario["numero"][:60])
    if destinatario["complemento"]:
        _texto(ender_dest, "xCpl", destinatario["complemento"][:60])
    _texto(ender_dest, "xBairro", destinatario["bairro"][:60])
    _texto(ender_dest, "cMun", destinatario["codigo_municipio_ibge"])
    _texto(ender_dest, "xMun", destinatario["municipio"][:60])
    _texto(ender_dest, "UF", destinatario["uf"])
    _texto(ender_dest, "CEP", destinatario["cep"])
    _texto(ender_dest, "cPais", "1058")
    _texto(ender_dest, "xPais", "BRASIL")
    if destinatario["telefone"]:
        _texto(ender_dest, "fone", destinatario["telefone"][:14])
    _texto(dest, "indIEDest", destinatario["indicador_ie"])
    if destinatario["indicador_ie"] == "1":
        _texto(dest, "IE", destinatario["inscricao_estadual"])

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
    calculos_ibs_cbs = []
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
        cbenef = codigo_beneficio_produto_operacao(
            produto,
            documento.natureza_operacao,
            uf=documento.filial.uf,
            crt=_crt_configuracao(configuracao),
        )
        if cbenef:
            _texto(prod, "cBenef", cbenef)
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
        if exigir_ibs_cbs:
            try:
                calculo_ibs_cbs = calcular_ibs_cbs_padrao(
                    valor_operacao=calcular_base_operacao_padrao(
                        valor_produtos=composicao_ipi["valor_produto"],
                        desconto=composicao_ipi["desconto"],
                        valor_pis=valor_pis,
                        valor_cofins=valor_cofins,
                        valor_icms=calculo_icms["valor_icms"],
                        valor_fcp=calculo_icms["valor_fcp"],
                    ),
                    cst=produto.cst_ibs_cbs,
                    cclass_trib=produto.classificacao_tributaria_ibs_cbs,
                    modelo="55",
                )
            except (ClassificacaoIbsCbsInvalida, ValueError) as exc:
                raise ValidationError(str(exc)) from exc
            adicionar_ibs_cbs_item(imposto, calculo_ibs_cbs, namespace=NFE_NS)
            calculos_ibs_cbs.append(calculo_ibs_cbs)
        valor_pis_total += valor_pis
        valor_cofins_total += valor_cofins
        valor_produtos_total += composicao_ipi["valor_produto"]
        desconto_total += composicao_ipi["desconto"]

    total = _adicionar_totais_icms(
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
    if exigir_ibs_cbs:
        adicionar_totais_ibs_cbs(total, calculos_ibs_cbs, namespace=NFE_NS)

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
    erros = _pendencias_emissao_ibs_cbs(configuracao, venda.filial, "65")
    erros.extend(pendencias_endereco_emitente_nfce(venda.filial))
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
    else:
        pendencia_cfop = validar_cfop(natureza.cfop, direcao="SAIDA", modelo="NFCE")
        if pendencia_cfop:
            erros.append(f"Natureza de operação: {pendencia_cfop}.")
    erros.extend(
        pendencias_cenario_fiscal_go(
            uf_emitente=venda.filial.uf,
            modelo="65",
            cfop=getattr(natureza, "cfop", ""),
            finalidade="1",
            destinatario_contribuinte=False,
            possui_frete=False,
        )
    )

    simples_nacional = _usa_csosn(configuracao)
    exigir_ibs_cbs = _ibs_cbs_obrigatorio(configuracao, venda.filial, "65")
    itens = list(venda.itens.select_related("produto"))
    if not itens:
        erros.append("A venda não possui itens para emissao fiscal.")
    for item in itens:
        produto = item.produto
        prefixo = f"Produto {produto.nome}:"
        if not re.fullmatch(r"\d{8}", produto.ncm or ""):
            erros.append(f"{prefixo} informe NCM com 8 digitos.")
        else:
            pendencia_ncm = validar_ncm(produto.ncm)
            if pendencia_ncm:
                erros.append(f"{prefixo} {pendencia_ncm}.")
        if produto.cest:
            pendencia_cest = validar_cest(produto.cest, produto.ncm)
            if pendencia_cest:
                erros.append(f"{prefixo} {pendencia_cest}.")
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
            for pendencia in _pendencias_ibs_cbs_produto(
                produto, exigir_ibs_cbs, "65", validar_catalogo=True
            )
        )
        if produto.cst_ipi in CST_IPI_TRIBUTADO and (not natureza or not natureza.ipi_incluso_preco):
            erros.append(
                f"{prefixo} confirme na natureza da operacao que o IPI tributado esta incluido no preco."
            )
        erros.extend(
            f"{prefixo} {pendencia}."
            for pendencia in pendencias_produto_por_uf(
                produto, [venda.filial.uf], [_crt_configuracao(configuracao)], natureza_operacao=natureza
            )
        )
    return erros


def validar_preparacao_fiscal(venda, configuracao, natureza):
    erros = pendencias_preparacao_fiscal(venda, configuracao, natureza)
    if erros:
        raise ValidationError(erros)


def pendencias_preparacao_nfe_pedido(pedido, configuracao, natureza):
    erros = _pendencias_emissao_ibs_cbs(configuracao, pedido.filial, "55")
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
    else:
        pendencia_cfop = validar_cfop(natureza.cfop, direcao="SAIDA", modelo="NFE")
        if pendencia_cfop:
            erros.append(f"Natureza de operação: {pendencia_cfop}.")
    try:
        _documento_destinatario_pedido(pedido)
    except ValidationError as exc:
        erros.extend(exc.messages)
    erros.extend(_pendencias_destinatario_nfe_pedido(pedido))
    erros.extend(
        pendencias_cenario_fiscal_go(
            uf_emitente=pedido.filial.uf,
            modelo="55",
            cfop=getattr(natureza, "cfop", ""),
            finalidade="1",
            destinatario_contribuinte=pedido.destinatario_indicador_ie == "1",
            possui_frete=(
                pedido.tipo_entrega == "ENTREGA" or bool(Decimal(pedido.taxa_entrega or 0))
            ),
            uf_destinatario=pedido.destinatario_uf,
        )
    )
    itens = list(pedido.itens.select_related("produto"))
    if not itens:
        erros.append("O pedido online não possui itens para emissao fiscal.")
    simples_nacional = _usa_csosn(configuracao)
    exigir_ibs_cbs = _ibs_cbs_obrigatorio(configuracao, pedido.filial, "55")
    for item in itens:
        produto = item.produto
        prefixo = f"Produto {produto.nome}:"
        if not re.fullmatch(r"\d{8}", produto.ncm or ""):
            erros.append(f"{prefixo} informe NCM com 8 digitos.")
        else:
            pendencia_ncm = validar_ncm(produto.ncm)
            if pendencia_ncm:
                erros.append(f"{prefixo} {pendencia_ncm}.")
        if produto.cest:
            pendencia_cest = validar_cest(produto.cest, produto.ncm)
            if pendencia_cest:
                erros.append(f"{prefixo} {pendencia_cest}.")
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
            for pendencia in _pendencias_ibs_cbs_produto(
                produto, exigir_ibs_cbs, "55", validar_catalogo=True
            )
        )
        if produto.cst_ipi in CST_IPI_TRIBUTADO and (not natureza or not natureza.ipi_incluso_preco):
            erros.append(
                f"{prefixo} confirme na natureza da operacao que o IPI tributado esta incluido no preco."
            )
        erros.extend(
            f"{prefixo} {pendencia}."
            for pendencia in pendencias_produto_por_uf(
                produto, [pedido.filial.uf], [_crt_configuracao(configuracao)], natureza_operacao=natureza
            )
        )
    return erros


def validar_preparacao_nfe_pedido(pedido, configuracao, natureza):
    erros = pendencias_preparacao_nfe_pedido(pedido, configuracao, natureza)
    if erros:
        raise ValidationError(erros)


@transaction.atomic
def preparar_documento_venda(venda, usuario, natureza_operacao=None, ip=None):
    venda = (
        Venda.objects.select_for_update()
        .select_related("filial__empresa")
        .get(pk=venda.pk)
    )
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
        .filter(
            filial=venda.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=configuracao.ambiente,
            ativo=True,
        )
        .order_by("serie")
        .first()
    )
    if not serie:
        raise ValidationError(
            "Cadastre uma serie NFC-e ativa para a filial no ambiente "
            f"{configuracao.get_ambiente_display()}."
        )

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
    from apps.marketplace.models import PedidoOnline

    pedido = (
        PedidoOnline.objects.select_for_update()
        .select_related("filial__empresa")
        .get(pk=pedido.pk)
    )
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
        .filter(
            filial=pedido.filial,
            tipo_documento=TipoDocumentoFiscal.NFE,
            ambiente=configuracao.ambiente,
            ativo=True,
        )
        .order_by("serie")
        .first()
    )
    if not serie:
        raise ValidationError(
            "Cadastre uma serie NF-e ativa para a filial no ambiente "
            f"{configuracao.get_ambiente_display()}."
        )
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
    documento.confirmacoes_nao_localizado = 0
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
            "confirmacoes_nao_localizado",
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
def ativar_contingencia_svc(documento, usuario, justificativa, ip=None):
    """Prepara uma NF-e de Goias para autorizacao na SVC-RS (tpEmis=7)."""
    if not getattr(usuario, "is_superuser", False):
        raise ValidationError("Somente o Master pode ativar a contingência SVC.")
    if not getattr(settings, "SEFAZ_DIRETA_SVC_ENABLED", False):
        raise ValidationError("A contingência SVC permanece desligada no servidor.")

    documento = (
        DocumentoFiscal.objects.select_for_update()
        .select_related("filial")
        .get(pk=documento.pk)
    )
    if documento.tipo_documento != TipoDocumentoFiscal.NFE:
        raise ValidationError("A contingência SVC é exclusiva para NF-e modelo 55.")
    if documento.filial.uf != "GO":
        raise ValidationError("Nesta etapa, a SVC direta está limitada a Goiás.")
    if documento.status != StatusDocumentoFiscal.PRONTO:
        raise ValidationError("Somente NF-e pronta pode entrar em contingência SVC.")
    if documento.aguardando_consulta_sefaz:
        raise ValidationError(
            "Consulte a situação da chave na SEFAZ antes de ativar a contingência."
        )
    try:
        configuracao = documento.filial.configuracao_fiscal
    except ConfiguracaoFiscal.DoesNotExist as exc:
        raise ValidationError("Configure os dados fiscais da filial antes de usar SVC.") from exc
    from .models import ProvedorEmissaoFiscal

    if configuracao.provedor_emissao != ProvedorEmissaoFiscal.SEFAZ_DIRETA_GO:
        raise ValidationError(
            "A SVC direta exige que a filial esteja no canal técnico SEFAZ direta."
        )
    justificativa = (justificativa or "").strip()
    if not 15 <= len(justificativa) <= 256:
        raise ValidationError("A justificativa da contingência deve ter entre 15 e 256 caracteres.")

    documento.status = StatusDocumentoFiscal.CONTINGENCIA
    documento.contingencia_iniciada_em = timezone.now()
    documento.contingencia_justificativa = justificativa
    documento.transmissao_limite_em = None
    documento.xml_assinado_em = None
    documento.certificado_serial_assinatura = ""
    documento.mensagem_retorno = (
        "NF-e preparada para autorização em contingência SVC-RS. "
        "O documento ainda não está autorizado."
    )
    documento.save(
        update_fields=[
            "status",
            "contingencia_iniciada_em",
            "contingencia_justificativa",
            "transmissao_limite_em",
            "xml_assinado_em",
            "certificado_serial_assinatura",
            "mensagem_retorno",
            "atualizado_em",
        ]
    )
    salvar_xml_documento(documento)
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="ATIVA_CONTINGENCIA_SVC_RS",
        descricao=(
            f"NF-e {documento.id} preparada para contingência SVC-RS por decisão do Master. "
            f"Justificativa: {justificativa}"
        ),
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.id),
        ip=ip,
    )
    return documento


@transaction.atomic
def transmitir_documento_simulado(documento, usuario, ip=None, reserva_token=None):
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
    token, gerenciada_pela_fila = _reserva_transmissao(documento, reserva_token)
    if not documento.xml_conteudo:
        salvar_xml_documento(documento)
    # O emissor simulado não valida schema nem assina, mas não pode marcar como
    # emitido um XML legado que os canais reais recusariam no preflight.
    validar_xml_pre_transmissao(
        documento, SimpleNamespace(assina_xml=True, valida_schema=True),
    )

    if not normalizar_chave_acesso(documento.chave_acesso):
        raise ValidationError("Documento sem chave de acesso fiscal valida.")
    documento.protocolo = f"HOM{timezone.now():%Y%m%d%H%M%S}{documento.pk:06d}"
    documento.status = StatusDocumentoFiscal.EMITIDO
    documento.tentativas_transmissao += 1
    documento.ultima_tentativa_em = timezone.now()
    documento.mensagem_retorno = "Transmissao simulada em homologação. Substituir pelo adaptador oficial da SEFAZ em produção."
    update_fields = ["chave_acesso", "protocolo", "status", "tentativas_transmissao", "ultima_tentativa_em", "mensagem_retorno", "atualizado_em"]
    if not gerenciada_pela_fila:
        _confirmar_reserva_transmissao(documento, token)
        documento.transmissao_reservada_em = None
        documento.transmissao_reserva_token = None
        update_fields.extend(["transmissao_reservada_em", "transmissao_reserva_token"])
    documento.save(update_fields=update_fields)
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



def transmitir_documento_sefaz(documento, usuario, ip=None, reserva_token=None):
    with transaction.atomic():
        documento = (
            DocumentoFiscal.objects.select_for_update()
            .select_related("filial__empresa")
            .get(pk=documento.pk)
        )
        status_origem = documento.status
        em_svc = bool(
            documento.tipo_documento == TipoDocumentoFiscal.NFE
            and documento.contingencia_iniciada_em
            and len(documento.chave_acesso) == 44
            and documento.chave_acesso[34] == "7"
        )
        if em_svc and not getattr(usuario, "is_superuser", False):
            raise ValidationError("Somente o Master pode transmitir uma NF-e pela SVC.")
        if status_origem not in {StatusDocumentoFiscal.PRONTO, StatusDocumentoFiscal.CONTINGENCIA}:
            raise ValidationError("Somente documentos prontos ou em contingência podem ser transmitidos.")
        if documento.aguardando_consulta_sefaz:
            raise ValidationError(
                "Consulte a situação da chave na SEFAZ antes de transmitir novamente."
            )
        token, gerenciada_pela_fila = _reserva_transmissao(documento, reserva_token)
        if not documento.xml_conteudo:
            salvar_xml_documento(documento)
        documento.tentativas_transmissao += 1
        documento.ultima_tentativa_em = timezone.now()
        documento.save(update_fields=["tentativas_transmissao", "ultima_tentativa_em", "atualizado_em"])
        idempotency_key = (
            f"fiscal:{documento.pk}:{documento.numero or 0}:"
            f"{documento.xml_gerado_em.isoformat() if documento.xml_gerado_em else 'sem-xml'}"
        )

    envio_iniciado = False
    try:
        adapter = carregar_adaptador_sefaz(filial=documento.filial)
        if not bool(getattr(adapter, "assina_xml", False)):
            assinar_xml_documento(documento)
            verificar_assinatura_xml(documento.xml_conteudo)
        validar_xml_pre_transmissao(documento, adapter)
        registrar_evidencia_fiscal(
            documento=documento,
            tipo=TipoEvidenciaFiscal.XML_ENVIO,
            referencia=f"{idempotency_key}:xml-envio",
            conteudo=documento.xml_conteudo,
            usuario=usuario,
            canal=_canal_evidencia_fiscal(documento),
            chave_acesso=documento.chave_acesso,
        )
        with transaction.atomic():
            reservado = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
            _confirmar_reserva_transmissao(reservado, token)
            reservado.aguardando_consulta_sefaz = True
            reservado.mensagem_retorno = (
                "Envio iniciado. A situação deve ser consultada antes de qualquer retransmissão."
            )
            reservado.save(
                update_fields=["aguardando_consulta_sefaz", "mensagem_retorno", "atualizado_em"]
            )
        envio_iniciado = True
        retorno = adapter.transmitir(
            documento=documento,
            xml=documento.xml_conteudo,
            idempotency_key=idempotency_key,
            ambiente=documento.ambiente,
        )
        resultado = normalizar_retorno_transmissao(retorno)
        registrar_evidencia_fiscal(
            documento=documento,
            tipo=TipoEvidenciaFiscal.RETORNO_TRANSMISSAO,
            referencia=f"{idempotency_key}:retorno",
            conteudo=_resultado_evidencia(resultado),
            usuario=usuario,
            canal=_canal_evidencia_fiscal(documento),
            chave_acesso=resultado.chave_acesso or documento.chave_acesso,
            protocolo=resultado.protocolo,
        )
        if resultado.xml_autorizado:
            registrar_evidencia_fiscal(
                documento=documento,
                tipo=TipoEvidenciaFiscal.XML_AUTORIZADO,
                referencia=f"{idempotency_key}:xml-autorizado",
                conteudo=resultado.xml_autorizado,
                usuario=usuario,
                canal=_canal_evidencia_fiscal(documento),
                chave_acesso=resultado.chave_acesso,
                protocolo=resultado.protocolo,
            )
        if resultado.status == "AUTORIZADO":
            preserva_chave_local = bool(
                getattr(adapter, "preserva_chave_local", True)
            )
            if preserva_chave_local and resultado.chave_acesso != documento.chave_acesso:
                raise SefazAdapterError(
                    "A SEFAZ autorizou uma chave diferente do documento transmitido."
                )
            if not preserva_chave_local and not resultado.xml_autorizado:
                raise SefazAdapterError(
                    "O provedor autorizou uma nova chave sem devolver o XML processado."
                )
    except Exception as exc:
        mensagem = (
            str(exc)
            if isinstance(exc, (SefazAdapterError, ValidationError))
            else "Falha na comunicacao com o adaptador SEFAZ."
        )
        campos_falha = {
            "mensagem_retorno": mensagem,
            "atualizado_em": timezone.now(),
        }
        if envio_iniciado:
            campos_falha["aguardando_consulta_sefaz"] = True
        if not gerenciada_pela_fila:
            campos_falha["transmissao_reservada_em"] = None
            campos_falha["transmissao_reserva_token"] = None
        DocumentoFiscal.objects.filter(
            pk=documento.pk, transmissao_reserva_token=token
        ).update(**campos_falha)
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
        _confirmar_reserva_transmissao(documento, token)
        if documento.status == StatusDocumentoFiscal.EMITIDO:
            if not gerenciada_pela_fila:
                documento.transmissao_reservada_em = None
                documento.transmissao_reserva_token = None
                documento.save(
                    update_fields=[
                        "transmissao_reservada_em",
                        "transmissao_reserva_token",
                        "atualizado_em",
                    ]
                )
            return documento

        documento.mensagem_retorno = resultado.mensagem
        documento.tentativas_consulta_sefaz = 0
        documento.confirmacoes_nao_localizado = 0
        if resultado.status == "AUTORIZADO":
            documento.aguardando_consulta_sefaz = False
            documento.status = StatusDocumentoFiscal.EMITIDO
            documento.chave_acesso = resultado.chave_acesso
            documento.protocolo = resultado.protocolo
            if resultado.xml_autorizado:
                documento.xml_conteudo = resultado.xml_autorizado
                documento.xml_gerado_em = timezone.now()
        elif resultado.status == "REJEITADO":
            documento.aguardando_consulta_sefaz = False
            documento.status = StatusDocumentoFiscal.REJEITADO
        else:
            documento.aguardando_consulta_sefaz = True
            documento.status = status_origem
        update_fields = [
                "status",
                "chave_acesso",
                "protocolo",
                "xml_conteudo",
                "xml_gerado_em",
                "mensagem_retorno",
                "aguardando_consulta_sefaz",
                "tentativas_consulta_sefaz",
                "confirmacoes_nao_localizado",
                "atualizado_em",
            ]
        if not gerenciada_pela_fila:
            documento.transmissao_reservada_em = None
            documento.transmissao_reserva_token = None
            update_fields.extend(["transmissao_reservada_em", "transmissao_reserva_token"])
        documento.save(update_fields=update_fields)

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
            if documento_em_contingencia_offline(documento):
                raise ValidationError(
                    "NFC-e emitida em contingência offline não pode ser cancelada "
                    "apenas no sistema. Corrija a rejeição e conclua a regularização "
                    "na SEFAZ."
                )
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
        if not normalizar_chave_acesso(documento.chave_acesso):
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
        adapter = carregar_adaptador_sefaz(filial=documento.filial)
        cancelar = getattr(adapter, "cancelar", None)
        if not callable(cancelar):
            raise SefazAdapterError(
                "O adaptador SEFAZ configurado não implementa cancelamento autorizado."
            )
        registrar_evidencia_fiscal(
            documento=documento,
            tipo=TipoEvidenciaFiscal.EVENTO_CANCELAMENTO_ENVIO,
            referencia=f"{idempotency_key}:envio",
            conteudo={
                "chave_acesso": documento.chave_acesso,
                "protocolo_autorizacao": documento.protocolo,
                "justificativa": motivo,
            },
            usuario=usuario,
            canal=_canal_evidencia_fiscal(documento),
            chave_acesso=documento.chave_acesso,
            protocolo=documento.protocolo,
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
        registrar_evidencia_fiscal(
            documento=documento,
            tipo=TipoEvidenciaFiscal.EVENTO_CANCELAMENTO_RETORNO,
            referencia=f"{idempotency_key}:retorno",
            conteudo=_resultado_evidencia(resultado),
            usuario=usuario,
            canal=_canal_evidencia_fiscal(documento),
            chave_acesso=documento.chave_acesso,
            protocolo=resultado.protocolo,
        )
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



def consultar_situacao_documento(documento, usuario, ip=None, reserva_token=None):
    with transaction.atomic():
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        if documento.status in {StatusDocumentoFiscal.RASCUNHO, StatusDocumentoFiscal.INUTILIZADO}:
            raise ValidationError("Este documento não possui situação consultável na SEFAZ.")
        if not normalizar_chave_acesso(documento.chave_acesso):
            raise ValidationError("Informe uma chave de acesso fiscal válida com 44 caracteres.")
        token, gerenciada_pela_fila = _reserva_transmissao(documento, reserva_token)
        aguardando_consulta_antes = documento.aguardando_consulta_sefaz
        chave_acesso = documento.chave_acesso
        idempotency_key = f"fiscal-consulta:{documento.pk}:{chave_acesso}"
        documento.tentativas_consulta_sefaz += 1
        documento.save(
            update_fields=["tentativas_consulta_sefaz", "atualizado_em"]
        )

    try:
        adapter = carregar_adaptador_sefaz(filial=documento.filial)
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
        referencia_consulta = (
            f"{idempotency_key}:tentativa-{documento.tentativas_consulta_sefaz}:retorno"
        )
        registrar_evidencia_fiscal(
            documento=documento,
            tipo=TipoEvidenciaFiscal.RETORNO_CONSULTA,
            referencia=referencia_consulta,
            conteudo=_resultado_evidencia(resultado),
            usuario=usuario,
            canal=_canal_evidencia_fiscal(documento),
            chave_acesso=resultado.chave_acesso or documento.chave_acesso,
            protocolo=resultado.protocolo or resultado.protocolo_cancelamento,
        )
        if resultado.xml_autorizado:
            registrar_evidencia_fiscal(
                documento=documento,
                tipo=TipoEvidenciaFiscal.XML_AUTORIZADO,
                referencia=f"{referencia_consulta}:xml-autorizado",
                conteudo=resultado.xml_autorizado,
                usuario=usuario,
                canal=_canal_evidencia_fiscal(documento),
                chave_acesso=resultado.chave_acesso or documento.chave_acesso,
                protocolo=resultado.protocolo,
            )
    except Exception as exc:
        mensagem = (
            str(exc)
            if isinstance(exc, (ImproperlyConfigured, SefazAdapterError, ValidationError))
            else "Falha na comunicação com o adaptador SEFAZ durante a consulta."
        )
        campos_falha = dict(
            consulta_sefaz_em=timezone.now(),
            mensagem_consulta_sefaz=mensagem,
            confirmacoes_nao_localizado=0,
            atualizado_em=timezone.now(),
        )
        if not gerenciada_pela_fila:
            campos_falha["transmissao_reservada_em"] = None
            campos_falha["transmissao_reserva_token"] = None
        DocumentoFiscal.objects.filter(
            pk=documento.pk, transmissao_reserva_token=token
        ).update(**campos_falha)
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
        _confirmar_reserva_transmissao(documento, token)
        documento.consulta_sefaz_em = agora
        documento.mensagem_consulta_sefaz = resultado.mensagem
        confirmacoes_anteriores = documento.confirmacoes_nao_localizado
        documento.confirmacoes_nao_localizado = 0
        update_fields = [
            "consulta_sefaz_em",
            "mensagem_consulta_sefaz",
            "confirmacoes_nao_localizado",
            "atualizado_em",
        ]
        if resultado.status == "AUTORIZADO":
            documento.aguardando_consulta_sefaz = False
            documento.status = StatusDocumentoFiscal.EMITIDO
            if resultado.chave_acesso:
                documento.chave_acesso = resultado.chave_acesso
                update_fields.append("chave_acesso")
            if resultado.xml_autorizado:
                documento.xml_conteudo = resultado.xml_autorizado
                documento.xml_gerado_em = agora
                update_fields.extend(["xml_conteudo", "xml_gerado_em"])
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
            if aguardando_consulta_antes or documento_em_contingencia_offline(documento):
                confirmacoes_exigidas = max(
                    2,
                    int(
                        getattr(
                            settings,
                            "FISCAL_CONTINGENCY_NOT_FOUND_CONFIRMATIONS",
                            2,
                        )
                    ),
                )
                documento.confirmacoes_nao_localizado = confirmacoes_anteriores + 1
                if documento.confirmacoes_nao_localizado < confirmacoes_exigidas:
                    documento.aguardando_consulta_sefaz = True
                    documento.mensagem_consulta_sefaz = (
                        f"Documento não localizado; confirmação "
                        f"{documento.confirmacoes_nao_localizado}/{confirmacoes_exigidas}. "
                        "A retransmissão continua bloqueada."
                    )
                else:
                    documento.aguardando_consulta_sefaz = False
                    documento.tentativas_transmissao = 0
                    update_fields.append("tentativas_transmissao")
            else:
                documento.aguardando_consulta_sefaz = False
                documento.tentativas_transmissao = 0
                update_fields.append("tentativas_transmissao")
            update_fields.append("aguardando_consulta_sefaz")
        else:
            documento.aguardando_consulta_sefaz = True
            update_fields.append("aguardando_consulta_sefaz")
        if not gerenciada_pela_fila:
            documento.transmissao_reservada_em = None
            documento.transmissao_reserva_token = None
            update_fields.extend(["transmissao_reservada_em", "transmissao_reserva_token"])
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
            ambiente=configuracao.ambiente,
            serie=serie,
            ativo=True,
        ).exists():
            raise ValidationError(
                "A série informada não está ativa para esta filial, documento e ambiente."
            )

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
        adapter_path = caminho_adaptador_sefaz(filial=filial)
        if configuracao.ambiente == AmbienteFiscal.HOMOLOGACAO and not adapter_path:
            resultado = normalizar_retorno_inutilizacao(
                {
                    "status": "INUTILIZADA",
                    "protocolo": f"HOMI{timezone.now():%Y%m%d%H%M%S}{inutilizacao.pk:06d}",
                    "mensagem": "Inutilização simulada em ambiente de homologação.",
                }
            )
        else:
            adapter = carregar_adaptador_sefaz(filial=filial)
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
