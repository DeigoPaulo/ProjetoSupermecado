"""Resolve adaptadores auxiliares pelo canal técnico selecionado na filial."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist


PROVEDOR_PADRAO = "PADRAO_SERVIDOR"
PROVEDOR_DESATIVADO = "DESATIVADO"
PROVEDOR_FOCUS = "FOCUS"
PROVEDOR_SEFAZ_DIRETA_GO = "SEFAZ_DIRETA_GO"

ADAPTADORES_POR_OPERACAO = {
    "DFE": {
        PROVEDOR_FOCUS: "apps.fiscal.focus_dfe_adapter.FocusNFeDFeAdapter",
        PROVEDOR_SEFAZ_DIRETA_GO: "apps.fiscal.sefaz_direta.dfe.SefazDiretaDFeAdapter",
    },
    "CCE": {
        PROVEDOR_SEFAZ_DIRETA_GO: "apps.fiscal.sefaz_direta.cce.SefazDiretaCartaCorrecaoAdapter",
    },
    "MANIFESTACAO": {
        PROVEDOR_SEFAZ_DIRETA_GO: "apps.fiscal.sefaz_direta.manifestacao.SefazDiretaManifestacaoAdapter",
    },
}

ADAPTADORES_EMISSAO = {
    PROVEDOR_FOCUS: "apps.fiscal.focus_sefaz_adapter.FocusNFeSefazAdapter",
    PROVEDOR_SEFAZ_DIRETA_GO: "apps.fiscal.sefaz_direta.SefazDiretaAdapter",
}


def provedor_fiscal_da_filial(filial):
    if filial is None:
        return PROVEDOR_PADRAO
    try:
        configuracao = filial.configuracao_fiscal
    except (AttributeError, ObjectDoesNotExist):
        return PROVEDOR_PADRAO
    return str(getattr(configuracao, "provedor_emissao", "") or PROVEDOR_PADRAO)


def resolver_adaptador_operacao(*, filial, operacao, fallback=""):
    operacao = str(operacao or "").strip().upper()
    if operacao not in ADAPTADORES_POR_OPERACAO:
        raise ImproperlyConfigured(f"Operação fiscal auxiliar desconhecida: {operacao or '-'}.")
    provedor = provedor_fiscal_da_filial(filial)
    if provedor == PROVEDOR_DESATIVADO:
        return {"provedor": provedor, "adaptador": "", "motivo": "CANAL_DESATIVADO"}
    if provedor == PROVEDOR_PADRAO:
        return {
            "provedor": provedor,
            "adaptador": str(fallback or "").strip(),
            "motivo": "COMPATIBILIDADE_SERVIDOR",
        }
    if provedor == PROVEDOR_SEFAZ_DIRETA_GO and str(getattr(filial, "uf", "") or "").upper() != "GO":
        raise ImproperlyConfigured(
            "A conexão direta SEFAZ está disponível somente para filiais de Goiás."
        )
    adaptador = ADAPTADORES_POR_OPERACAO[operacao].get(provedor, "")
    if not adaptador:
        raise ImproperlyConfigured(
            f"O canal {provedor} não implementa a operação fiscal {operacao}."
        )
    return {"provedor": provedor, "adaptador": adaptador, "motivo": "CANAL_DA_FILIAL"}


def diagnosticar_capacidades_filial(filial):
    """Expõe a topologia local; não instancia adaptadores nem consulta credenciais."""
    provedor = provedor_fiscal_da_filial(filial)
    fallback_emissao = str(getattr(settings, "FISCAL_SEFAZ_ADAPTER", "") or "").strip()
    if provedor == PROVEDOR_PADRAO:
        adaptador_emissao = fallback_emissao
    elif provedor == PROVEDOR_DESATIVADO:
        adaptador_emissao = ""
    else:
        adaptador_emissao = ADAPTADORES_EMISSAO.get(provedor, "")

    capacidades = []
    for codigo, titulo in (
        ("AUTORIZACAO", "Autorização e rejeições"),
        ("CONSULTA", "Consulta do documento"),
        ("CANCELAMENTO", "Cancelamento"),
        ("INUTILIZACAO", "Inutilização"),
    ):
        capacidades.append({
            "codigo": codigo,
            "titulo": titulo,
            "disponivel_estrutural": bool(adaptador_emissao),
            "adaptador": adaptador_emissao,
            "detalhe": (
                "Capacidade estrutural do canal de emissão; exige homologação real."
                if adaptador_emissao else "Canal de emissão desativado ou não configurado."
            ),
            "homologada": False,
            "producao_liberada": False,
        })

    auxiliares = (
        ("DFE", "Distribuição DF-e", getattr(settings, "FISCAL_DFE_ADAPTER", "")),
        ("CCE", "Carta de Correção", getattr(settings, "FISCAL_CCE_ADAPTER", "")),
        ("MANIFESTACAO", "Manifestação do destinatário", getattr(settings, "FISCAL_MANIFESTACAO_ADAPTER", "")),
    )
    for codigo, titulo, fallback in auxiliares:
        try:
            roteamento = resolver_adaptador_operacao(
                filial=filial, operacao=codigo, fallback=fallback
            )
            adaptador = roteamento["adaptador"]
            detalhe = (
                "Capacidade estrutural resolvida pelo canal da filial; exige homologação real."
                if adaptador else "Canal desativado ou adaptador não configurado."
            )
        except ImproperlyConfigured as exc:
            adaptador = ""
            detalhe = str(exc)
        capacidades.append({
            "codigo": codigo,
            "titulo": titulo,
            "disponivel_estrutural": bool(adaptador),
            "adaptador": adaptador,
            "detalhe": detalhe,
            "homologada": False,
            "producao_liberada": False,
        })

    return {
        "contrato": "fiscal_branch_channel_capabilities_v1",
        "provedor": provedor,
        "capacidades": capacidades,
        "total": len(capacidades),
        "disponiveis_estruturais": sum(item["disponivel_estrutural"] for item in capacidades),
        "homologacao_real_executada": False,
        "producao_liberada": False,
    }
