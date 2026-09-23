"""Verificador sintético exclusivo dos testes; não habilita integração operacional."""

from unittest.mock import patch
from uuid import uuid4

from .integracao_pagamentos import confirmar_pagamento_no_servidor


def confirmar_parcela_teste(*, caixa, forma_pagamento, valor, **dados):
    resposta = {
        "valor": str(valor), "tipo_forma": forma_pagamento.tipo,
        "status": "CONFIRMADO", "tipo_integracao": "1",
        "transacao_externa_id": f"TESTE-{uuid4().hex}", "nsu": "NSU-TESTE",
        "codigo_autorizacao": "AUT-TESTE", "cnpj_instituicao_pagamento": "12ABC34501DE35",
        **dados,
    }
    with patch.dict("apps.vendas.integracao_pagamentos.VERIFICADORES", {"TESTE": lambda **kwargs: resposta}):
        return confirmar_pagamento_no_servidor(
            provedor="TESTE", referencia="referencia-sintetica", caixa=caixa,
            forma_pagamento=forma_pagamento, valor=valor,
        )
