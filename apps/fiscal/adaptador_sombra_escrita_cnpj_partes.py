"""Compara Cliente PJ e Fornecedor com o portão canônico, sem salvar."""

import re
from copy import copy

from .estrategia_normalizacao_cnpj import canonicalizar_cnpj, validar_dv_cnpj
from .portao_escrita_canonica_cnpj import preparar_escrita_canonica_cnpj


CONTRATO_ADAPTADOR_SOMBRA_ESCRITA_CNPJ_PARTES = (
    "alphanumeric_cnpj_customer_supplier_shadow_write_adapter_v1"
)
PADRAO_CPF = re.compile(r"^(?:\d{11}|\d{3}\.\d{3}\.\d{3}-\d{2})$")


def _canonico_valido(valor):
    try:
        canonico = canonicalizar_cnpj(valor)
    except ValueError:
        return ""
    return canonico if canonico and validar_dv_cnpj(canonico) else ""


def _contar_colisoes(queryset, proposta, *, campo, excluir_pk=None):
    canonico = _canonico_valido(proposta)
    if not canonico:
        return 0
    if excluir_pk is not None:
        queryset = queryset.exclude(pk=excluir_pk)
    return sum(
        1
        for valor in queryset.values_list(campo, flat=True).iterator()
        if _canonico_valido(valor) == canonico
    )


def _resposta(*, fronteira, formulario, status, colisoes, documento_tipo):
    formulario_valido = formulario.is_valid()
    if colisoes:
        classificacao = "COLISAO_CANONICA_DETECTADA"
    elif documento_tipo == "CPF":
        classificacao = "CPF_PRESERVADO_FORA_ESCOPO_CNPJ"
    elif documento_tipo == "VAZIO":
        classificacao = "VAZIO_OPCIONAL_PRESERVADO"
    elif formulario_valido and status in {
        "CANONICO_PREPARADO",
        "SEM_ALTERACAO_CANONICA",
        "TROCA_IDENTIDADE_REQUER_CONTROLES_EXTERNOS",
    }:
        classificacao = "CONCORDAM_ESTRUTURALMENTE"
    elif formulario_valido:
        classificacao = "FORMULARIO_ATUAL_ACEITA_PORTAO_RECUSA"
    elif status in {"CANONICO_PREPARADO", "SEM_ALTERACAO_CANONICA"}:
        classificacao = "FORMULARIO_ATUAL_RECUSA_PORTAO_PREPARA"
    else:
        classificacao = "AMBOS_RECUSAM"
    return {
        "contrato": CONTRATO_ADAPTADOR_SOMBRA_ESCRITA_CNPJ_PARTES,
        "fronteira": fronteira,
        "documento_tipo": documento_tipo,
        "classificacao": classificacao,
        "formulario_atual": {
            "valido": formulario_valido,
            "campos_com_erro": sorted(formulario.errors.as_data()),
        },
        "proposta_canonica": {"status": status, "quantidade_colisoes": colisoes},
        "seguranca": {
            "somente_select": True,
            "chama_save": False,
            "altera_objeto_existente": False,
            "cnpj_ou_cpf_exposto": False,
            "identificador_interno_exposto": False,
            "consumidor_operacional_alterado": False,
            "libera_emissao": False,
        },
    }


def observar_escrita_cliente(dados, *, instance=None):
    from apps.clientes.forms import ClienteForm
    from apps.clientes.models import Cliente

    formulario = ClienteForm(data=dados, instance=copy(instance) if instance else None)
    valor = str(dados.get("cpf_cnpj") or "").strip()
    if not valor:
        return _resposta(
            fronteira="CLIENTE_PJ", formulario=formulario, status="VAZIO_PERMITIDO",
            colisoes=0, documento_tipo="VAZIO",
        )
    if PADRAO_CPF.fullmatch(valor):
        return _resposta(
            fronteira="CLIENTE_PJ", formulario=formulario, status="CPF_FORA_ESCOPO_CNPJ",
            colisoes=0, documento_tipo="CPF",
        )
    empresa_id = dados.get("empresa") or getattr(instance, "empresa_id", None)
    operacao = "ATUALIZACAO" if instance and instance.pk else "CRIACAO"
    portao = preparar_escrita_canonica_cnpj(
        valor,
        fronteira="CLIENTE_PJ",
        operacao=operacao,
        empresa_id=empresa_id,
        valor_atual=getattr(instance, "cpf_cnpj", None),
    )
    queryset = Cliente.objects.filter(empresa_id=empresa_id) if empresa_id else Cliente.objects.none()
    return _resposta(
        fronteira="CLIENTE_PJ",
        formulario=formulario,
        status=portao["status"],
        colisoes=_contar_colisoes(
            queryset, valor, campo="cpf_cnpj", excluir_pk=getattr(instance, "pk", None)
        ),
        documento_tipo="CNPJ",
    )


def observar_escrita_fornecedor(dados, *, instance=None):
    from apps.fornecedores.forms import FornecedorForm
    from apps.fornecedores.models import Fornecedor

    formulario = FornecedorForm(data=dados, instance=copy(instance) if instance else None)
    valor = str(dados.get("cnpj") or "").strip()
    if not valor:
        return _resposta(
            fronteira="FORNECEDOR_PJ", formulario=formulario, status="VAZIO_PERMITIDO",
            colisoes=0, documento_tipo="VAZIO",
        )
    empresa_id = dados.get("empresa") or getattr(instance, "empresa_id", None)
    operacao = "ATUALIZACAO" if instance and instance.pk else "CRIACAO"
    portao = preparar_escrita_canonica_cnpj(
        valor,
        fronteira="FORNECEDOR_PJ",
        operacao=operacao,
        empresa_id=empresa_id,
        valor_atual=getattr(instance, "cnpj", None),
    )
    queryset = (
        Fornecedor.objects.filter(empresa_id=empresa_id)
        if empresa_id
        else Fornecedor.objects.none()
    )
    return _resposta(
        fronteira="FORNECEDOR_PJ",
        formulario=formulario,
        status=portao["status"],
        colisoes=_contar_colisoes(
            queryset, valor, campo="cnpj", excluir_pk=getattr(instance, "pk", None)
        ),
        documento_tipo="CNPJ",
    )
