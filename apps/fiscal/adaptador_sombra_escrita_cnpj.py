"""Compara a escrita atual de Empresa/Filial com o portao canonico, sem salvar."""

from copy import copy

from .estrategia_normalizacao_cnpj import canonicalizar_cnpj, validar_dv_cnpj
from .portao_escrita_canonica_cnpj import preparar_escrita_canonica_cnpj


CONTRATO_ADAPTADOR_SOMBRA_ESCRITA_CNPJ = (
    "alphanumeric_cnpj_company_branch_shadow_write_adapter_v1"
)


def _canonico_valido(valor):
    try:
        canonico = canonicalizar_cnpj(valor)
    except ValueError:
        return ""
    return canonico if canonico and validar_dv_cnpj(canonico) else ""


def _contar_colisoes(queryset, proposta, *, excluir_pk=None):
    canonico_proposto = _canonico_valido(proposta)
    if not canonico_proposto:
        return 0
    if excluir_pk is not None:
        queryset = queryset.exclude(pk=excluir_pk)
    return sum(
        1
        for valor in queryset.values_list("cnpj", flat=True).iterator()
        if _canonico_valido(valor) == canonico_proposto
    )


def _classificar(*, formulario_valido, portao_status, colisoes):
    portao_aceita_estrutura = portao_status in {
        "CANONICO_PREPARADO",
        "SEM_ALTERACAO_CANONICA",
        "TROCA_IDENTIDADE_REQUER_CONTROLES_EXTERNOS",
    }
    if colisoes:
        return "COLISAO_CANONICA_DETECTADA"
    if formulario_valido and portao_aceita_estrutura:
        return "CONCORDAM_ESTRUTURALMENTE"
    if formulario_valido:
        return "FORMULARIO_ATUAL_ACEITA_PORTAO_RECUSA"
    if portao_aceita_estrutura:
        return "FORMULARIO_ATUAL_RECUSA_PORTAO_PREPARA"
    return "AMBOS_RECUSAM"


def _resposta(*, fronteira, formulario, portao, colisoes, ponto_integracao):
    formulario_valido = formulario.is_valid()
    return {
        "contrato": CONTRATO_ADAPTADOR_SOMBRA_ESCRITA_CNPJ,
        "fronteira": fronteira,
        "classificacao": _classificar(
            formulario_valido=formulario_valido,
            portao_status=portao["status"],
            colisoes=colisoes,
        ),
        "formulario_atual": {
            "valido": formulario_valido,
            "campos_com_erro": sorted(formulario.errors.as_data()),
        },
        "proposta_canonica": {
            "status": portao["status"],
            "estrutura_valida": portao["decisao"]["estrutura_valida"],
            "quantidade_colisoes": colisoes,
        },
        "ponto_integracao": ponto_integracao,
        "seguranca": {
            "somente_select": True,
            "chama_save": False,
            "altera_objeto_existente": False,
            "cnpj_completo_exposto": False,
            "identificador_interno_exposto": False,
            "consumidor_operacional_alterado": False,
            "libera_homologacao": False,
            "libera_producao": False,
            "libera_focus": False,
            "libera_sefaz_direta": False,
            "libera_emissao": False,
        },
    }


def observar_escrita_empresa(dados, *, instance=None):
    """Executa as duas validacoes de Empresa sem persistir o formulario."""
    from apps.empresas.forms import EmpresaForm
    from apps.empresas.models import Empresa

    instancia_observada = copy(instance) if instance is not None else None
    formulario = EmpresaForm(data=dados, instance=instancia_observada)
    operacao = "ATUALIZACAO" if instance and instance.pk else "CRIACAO"
    portao = preparar_escrita_canonica_cnpj(
        dados.get("cnpj"),
        fronteira="EMPRESA",
        operacao=operacao,
        valor_atual=getattr(instance, "cnpj", None),
    )
    colisoes = _contar_colisoes(
        Empresa.objects.all(), dados.get("cnpj"), excluir_pk=getattr(instance, "pk", None)
    )
    return _resposta(
        fronteira="EMPRESA",
        formulario=formulario,
        portao=portao,
        colisoes=colisoes,
        ponto_integracao="EmpresaForm.clean_cnpj_antes_da_validacao_de_unicidade",
    )


def observar_escrita_filial(dados, *, instance=None):
    """Executa as duas validacoes de Filial, dentro da Empresa, sem persistir."""
    from apps.empresas.forms import FilialForm
    from apps.empresas.models import Filial

    instancia_observada = copy(instance) if instance is not None else None
    formulario = FilialForm(data=dados, instance=instancia_observada)
    empresa_id = dados.get("empresa") or getattr(instance, "empresa_id", None)
    operacao = "ATUALIZACAO" if instance and instance.pk else "CRIACAO"
    portao = preparar_escrita_canonica_cnpj(
        dados.get("cnpj"),
        fronteira="FILIAL",
        operacao=operacao,
        empresa_id=empresa_id,
        valor_atual=getattr(instance, "cnpj", None),
    )
    queryset = Filial.objects.filter(empresa_id=empresa_id) if empresa_id else Filial.objects.none()
    colisoes = _contar_colisoes(
        queryset, dados.get("cnpj"), excluir_pk=getattr(instance, "pk", None)
    )
    return _resposta(
        fronteira="FILIAL",
        formulario=formulario,
        portao=portao,
        colisoes=colisoes,
        ponto_integracao="FilialForm.clean_cnpj_antes_da_validacao_do_modelo",
    )


def descrever_adaptador_sombra_escrita_cnpj():
    return {
        "contrato": CONTRATO_ADAPTADOR_SOMBRA_ESCRITA_CNPJ,
        "fronteiras": ["EMPRESA", "FILIAL"],
        "integracao_atual": {
            "formulario_atual_valida_dv": True,
            "empresa_detecta_equivalencia_canonica": True,
            "filial_detecta_equivalencia_canonica_no_escopo": True,
        },
        "pontos_integracao": [
            "EmpresaForm.clean_cnpj_antes_da_validacao_de_unicidade",
            "FilialForm.clean_cnpj_antes_da_validacao_do_modelo",
        ],
        "proximo_passo": "VALIDAR_REGRESSAO_DA_INTEGRACAO_CADASTRAL",
    }
