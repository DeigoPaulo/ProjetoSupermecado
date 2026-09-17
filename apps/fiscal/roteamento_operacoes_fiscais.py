"""Resolve adaptadores auxiliares pelo canal técnico selecionado na filial."""

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
