"""Fronteira interna TEF/PIX, sem driver ou rede habilitados.

Cada verificador futuro deve autenticar/consultar a resposta do provedor no servidor.
Nunca cadastrar um verificador que apenas devolva o POST ou aceite o simulador.
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ConfirmacaoPagamentoIntegrado, PagamentoVenda, StatusPagamento


# Allowlist vazia. Um driver exige implementação e testes; o cliente não o configura.
VERIFICADORES = {}
CAMPOS_CONFIRMADOS = (
    "status", "transacao_externa_id", "nsu", "codigo_autorizacao", "tipo_integracao",
    "cnpj_instituicao_pagamento", "bandeira_cartao", "cnpj_beneficiario_pagamento",
    "identificador_terminal_pagamento",
)


def confirmar_pagamento_no_servidor(*, provedor, referencia, caixa, forma_pagamento, valor):
    """Entrada exclusiva para integração backend; não há endpoint neste ciclo."""
    from apps.pdv.models import StatusCaixa
    from .services import _normalizar_dados_fiscais_pagamento

    verificador = VERIFICADORES.get(provedor)
    if verificador is None:
        raise ValidationError("Provedor sem verificador de pagamento confiável no servidor.")
    if caixa.status != StatusCaixa.ABERTO:
        raise ValidationError("A confirmação integrada exige caixa aberto.")
    resposta = verificador(
        referencia=referencia, caixa=caixa, forma_pagamento=forma_pagamento, valor=valor,
    )
    if not isinstance(resposta, dict):
        raise ValidationError("Resposta inválida do verificador de pagamento.")
    try:
        valor_confirmado = Decimal(str(resposta.get("valor")))
        valor_solicitado = Decimal(str(valor))
        valor_valido = (
            valor_confirmado.is_finite() and valor_solicitado.is_finite()
            and valor_confirmado > 0 and valor_confirmado == valor_solicitado
            and valor_confirmado == valor_confirmado.quantize(Decimal("0.01"))
        )
    except (InvalidOperation, ValueError):
        valor_valido = False
    if not valor_valido or resposta.get("tipo_forma") != forma_pagamento.tipo:
        raise ValidationError("Forma ou valor diverge da confirmação do provedor.")
    dados = _normalizar_dados_fiscais_pagamento(resposta)
    if (
        forma_pagamento.tipo not in {"CARTAO", "CREDITO", "DEBITO", "PIX"}
        or dados.get("status") != StatusPagamento.CONFIRMADO
        or dados.get("tipo_integracao") != "1"
        or any(not str(dados.get(campo) or "").strip() for campo in (
            "transacao_externa_id", "nsu", "codigo_autorizacao", "cnpj_instituicao_pagamento",
        ))
        or str(dados.get("transacao_externa_id", "")).startswith("TEF-SIM-")
        or (forma_pagamento.tipo == "PIX" and dados.get("bandeira_cartao"))
    ):
        raise ValidationError("Verificador não retornou confirmação fiscal integrada válida.")
    dados = {campo: str(dados.get(campo) or "").strip() for campo in CAMPOS_CONFIRMADOS}
    if len(dados["nsu"]) > 60:
        raise ValidationError("NSU confirmado excede 60 caracteres.")
    confirmacao = ConfirmacaoPagamentoIntegrado(
        caixa=caixa, forma_pagamento=forma_pagamento, tipo_forma=forma_pagamento.tipo,
        valor=valor_confirmado, provedor=provedor,
        transacao_externa_id=dados["transacao_externa_id"], dados=dados,
    )
    confirmacao.full_clean()
    confirmacao.save()
    return confirmacao


def resolver_confirmacao_pagamento(pagamento, *, caixa):
    """Bloqueio e unicidade impedem consumo em duas parcelas/vendas."""
    referencia = pagamento.get("confirmacao_integracao_id")
    if not referencia:
        if str(pagamento.get("tipo_integracao") or "").strip() == "1":
            raise ValidationError("Pagamento integrado exige confirmação confiável no servidor.")
        # Nunca aceitar objetos de confirmação fornecidos pelo chamador neste caminho.
        return {chave: valor for chave, valor in pagamento.items() if chave != "confirmacao_integracao"}
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("A confirmação deve ser consumida na transação da venda.")
    try:
        confirmacao = ConfirmacaoPagamentoIntegrado.objects.select_for_update().get(pk=referencia)
    except (ConfirmacaoPagamentoIntegrado.DoesNotExist, ValidationError, ValueError, TypeError) as exc:
        raise ValidationError("Confirmação integrada inexistente ou inválida.") from exc
    if (
        confirmacao.caixa_id != caixa.pk
        or confirmacao.forma_pagamento_id != pagamento["forma_pagamento"].pk
        or confirmacao.tipo_forma != pagamento["forma_pagamento"].tipo
        or confirmacao.valor != pagamento["valor"]
    ):
        raise ValidationError("Confirmação integrada não corresponde ao caixa, forma ou valor da parcela.")
    if PagamentoVenda.objects.filter(confirmacao_integracao=confirmacao).exists():
        raise ValidationError("Confirmação integrada já utilizada em outra parcela.")
    # Autorização e metadados vêm exclusivamente do registro do servidor.
    return {**pagamento, **confirmacao.dados, "confirmacao_integracao": confirmacao}


def validar_origem_integracao_fiscal(pagamento):
    """Protege também registros legados ou criados fora do serviço de venda."""
    if not pagamento.confirmacao_integracao_id:
        raise ValidationError("Pagamento integrado exige confirmação confiável no servidor.")
    confirmacao = pagamento.confirmacao_integracao
    if (
        confirmacao.caixa_id != pagamento.venda.caixa_id
        or confirmacao.forma_pagamento_id != pagamento.forma_pagamento_id
        or confirmacao.tipo_forma != pagamento.forma_pagamento.tipo
        or confirmacao.valor != pagamento.valor
        or any(getattr(pagamento, campo) != confirmacao.dados.get(campo) for campo in CAMPOS_CONFIRMADOS)
    ):
        raise ValidationError("Dados da parcela divergem da confirmação integrada do servidor.")
