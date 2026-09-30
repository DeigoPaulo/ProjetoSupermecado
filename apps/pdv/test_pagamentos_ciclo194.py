from decimal import Decimal

from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.test import RequestFactory, TestCase

from apps.empresas.models import Empresa, Filial
from apps.vendas.models import FormaPagamento, StatusPagamento

from .views import _pagamentos_from_request


class PagamentosMistosCiclo194Tests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(
            razao_social="Mercado Sintético Ltda",
            nome_fantasia="Mercado Sintético",
            cnpj="12.345.678/0001-95",
        )
        self.filial = Filial.objects.create(
            empresa=empresa, nome="Loja Sintética", cnpj=empresa.cnpj
        )
        self.dinheiro = FormaPagamento.objects.create(
            nome="Dinheiro", tipo="DINHEIRO", permite_troco=True
        )
        self.debito = FormaPagamento.objects.create(nome="Débito", tipo="DEBITO")

    def _request(self, parcelas):
        dados = QueryDict(mutable=True)
        campos = {
            "pagamento_forma": [],
            "pagamento_valor": [],
            "pagamento_status": [],
            "pagamento_transacao_externa_id": [],
            "pagamento_nsu": [],
            "pagamento_codigo_autorizacao": [],
        }
        for indice, (forma, valor) in enumerate(parcelas, start=1):
            eletronico = forma.tipo == "DEBITO"
            campos["pagamento_forma"].append(str(forma.pk))
            campos["pagamento_valor"].append(str(valor))
            campos["pagamento_status"].append(StatusPagamento.CONFIRMADO)
            campos["pagamento_transacao_externa_id"].append(
                f"TX-{indice}" if eletronico else ""
            )
            campos["pagamento_nsu"].append(f"NSU-{indice}" if eletronico else "")
            campos["pagamento_codigo_autorizacao"].append(
                f"AUT-{indice}" if eletronico else ""
            )
        for campo, valores in campos.items():
            dados.setlist(campo, valores)
        request = RequestFactory().post("/pdv/", data={})
        request.POST = dados
        return request

    def test_troco_misto_independe_da_ordem_das_parcelas(self):
        for parcelas in (
            [(self.dinheiro, "100.00"), (self.debito, "100.00")],
            [(self.debito, "100.00"), (self.dinheiro, "100.00")],
        ):
            with self.subTest(ordem=[forma.tipo for forma, _ in parcelas]):
                pagamentos, total_informado = _pagamentos_from_request(
                    self._request(parcelas), Decimal("150.00"), self.filial
                )
                por_tipo = {item["forma_pagamento"].tipo: item for item in pagamentos}
                self.assertEqual(total_informado, Decimal("200.00"))
                self.assertEqual(por_tipo["DEBITO"]["valor"], Decimal("100.00"))
                self.assertEqual(por_tipo["DINHEIRO"]["valor"], Decimal("50.00"))
                self.assertEqual(
                    por_tipo["DINHEIRO"]["valor_informado"], Decimal("100.00")
                )

    def test_pagamento_eletronico_acima_do_total_sem_troco_bloqueia(self):
        with self.assertRaisesMessage(ValidationError, "Nenhuma forma informada permite troco"):
            _pagamentos_from_request(
                self._request([(self.debito, "80.00")]),
                Decimal("50.00"),
                self.filial,
            )

    def test_parcela_nao_desaparece_depois_da_quitacao(self):
        with self.assertRaises(ValidationError):
            _pagamentos_from_request(
                self._request([(self.debito, "50.00"), (self.debito, "10.00")]),
                Decimal("50.00"),
                self.filial,
            )
