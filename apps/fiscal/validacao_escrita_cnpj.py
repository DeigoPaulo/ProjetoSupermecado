"""Validação compartilhada para fronteiras cadastrais que gravam CNPJ."""

from .estrategia_normalizacao_cnpj import canonicalizar_cnpj, validar_dv_cnpj
from .portao_escrita_canonica_cnpj import preparar_escrita_canonica_cnpj


class ErroValidacaoEscritaCNPJ(ValueError):
    def __init__(self, codigo):
        self.codigo = codigo
        super().__init__(codigo)


def validar_proposta_cnpj(valor, *, fronteira, instance, empresa_id=None):
    operacao = "ATUALIZACAO" if instance and instance.pk else "CRIACAO"
    resultado = preparar_escrita_canonica_cnpj(
        valor,
        fronteira=fronteira,
        operacao=operacao,
        empresa_id=empresa_id,
        valor_atual=getattr(
            instance,
            "cpf_cnpj" if fronteira == "CLIENTE_PJ" else "cnpj",
            None,
        ),
    )
    status = resultado["status"]
    if status == "PROPOSTA_INVALIDA":
        raise ErroValidacaoEscritaCNPJ("cnpj_invalido")
    if status == "LEGADO_INVALIDO_REQUER_REVISAO":
        raise ErroValidacaoEscritaCNPJ("cnpj_legado_invalido")
    if status == "TROCA_IDENTIDADE_REQUER_CONTROLES_EXTERNOS":
        raise ErroValidacaoEscritaCNPJ("cnpj_troca_identidade")
    if status not in {"CANONICO_PREPARADO", "SEM_ALTERACAO_CANONICA"}:
        raise ErroValidacaoEscritaCNPJ("cnpj_nao_validado")
    return resultado["proposta"]["valor_canonico"]


def existe_colisao_cnpj(queryset, canonico, *, campo="cnpj", excluir_pk=None):
    if excluir_pk is not None:
        queryset = queryset.exclude(pk=excluir_pk)
    for valor in queryset.values_list(campo, flat=True).iterator():
        try:
            existente = canonicalizar_cnpj(valor)
        except ValueError:
            continue
        if existente and validar_dv_cnpj(existente) and existente == canonico:
            return True
    return False
