from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque
from apps.produtos.models import Categoria, Produto

from .models import FaixaTaxaEntrega, FormaPagamentoPedido, IntegracaoMarketplace, ItemPedidoOnline, PedidoOnline, PoliticaEntrega, StatusPagamentoPedido, StatusPedido, TipoEntrega
from .services import alterar_status_pedido, calcular_entrega_pedido, cancelar_pedido, gerar_token_integracao, registrar_pagamento, reservar_pedido


class FluxoPedidoOnlineTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("admin_market", "admin@example.com", "senha")
        empresa = Empresa.objects.create(razao_social="Mercado Teste", nome_fantasia="Mercado Teste", cnpj="12345678000190")
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz")
        categoria = Categoria.objects.create(nome="Mercearia")
        self.produto = Produto.objects.create(codigo_barras="789100000001", nome="Arroz", categoria=categoria, preco_custo=Decimal("10"), preco_venda=Decimal("15"), vendido_no_marketplace=True)
        self.estoque = Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("10"))
        self.pedido = PedidoOnline.objects.create(filial=self.filial, nome_cliente="Cliente Online", usuario=self.usuario)
        ItemPedidoOnline.objects.create(pedido=self.pedido, produto=self.produto, quantidade=Decimal("2"), preco_unitario=Decimal("15"))
        self.pedido.recalcular()

    def test_reserva_e_cancelamento_liberam_estoque(self):
        reservar_pedido(pedido=self.pedido, usuario=self.usuario)
        self.pedido.refresh_from_db()
        self.estoque.refresh_from_db()
        self.assertEqual(self.pedido.status, StatusPedido.EM_SEPARACAO)
        self.assertEqual(self.estoque.quantidade_reservada, Decimal("2"))

        cancelar_pedido(pedido=self.pedido, usuario=self.usuario)
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_reservada, Decimal("0"))
        self.assertTrue(LogAuditoria.objects.filter(modulo="marketplace", acao="CANCELAMENTO_PEDIDO").exists())

    def test_conclusao_consume_estoque_reservado(self):
        reservar_pedido(pedido=self.pedido, usuario=self.usuario)
        self.pedido.itens.update(quantidade_separada=Decimal("2"))
        alterar_status_pedido(pedido=self.pedido, destino=StatusPedido.PRONTO, usuario=self.usuario)
        registrar_pagamento(pedido=self.pedido, forma_pagamento=FormaPagamentoPedido.PIX, valor_pago=Decimal("30"), usuario=self.usuario)
        alterar_status_pedido(pedido=self.pedido, destino=StatusPedido.CONCLUIDO, usuario=self.usuario)
        self.estoque.refresh_from_db()
        self.pedido.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("8"))
        self.assertEqual(self.estoque.quantidade_reservada, Decimal("0"))
        self.assertEqual(self.pedido.status, StatusPedido.CONCLUIDO)

    def test_nao_fica_pronto_com_separacao_incompleta(self):
        reservar_pedido(pedido=self.pedido, usuario=self.usuario)
        with self.assertRaises(ValidationError):
            alterar_status_pedido(pedido=self.pedido, destino=StatusPedido.PRONTO, usuario=self.usuario)

    def test_cancelamento_de_pedido_pago_registra_estorno(self):
        registrar_pagamento(pedido=self.pedido, forma_pagamento=FormaPagamentoPedido.PIX, valor_pago=Decimal("30"), usuario=self.usuario)
        cancelar_pedido(pedido=self.pedido, usuario=self.usuario)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status_pagamento, StatusPagamentoPedido.ESTORNADO)

    def test_reserva_insuficiente_reverte_operacao(self):
        self.pedido.itens.update(quantidade=Decimal("20"), total=Decimal("300"))
        with self.assertRaises(ValidationError):
            reservar_pedido(pedido=self.pedido, usuario=self.usuario)
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_reservada, Decimal("0"))

    def test_tela_de_pedidos_exige_login_e_renderiza(self):
        self.assertEqual(self.client.get("/pedidos-online/").status_code, 302)
        self.client.force_login(self.usuario)
        resposta = self.client.get("/pedidos-online/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Cliente Online")
        self.assertContains(resposta, "Separacao")
        self.assertContains(resposta, "Pagamento")
        self.assertContains(resposta, "order-progress")

    def test_forms_marketplace_exibem_secoes_operacionais(self):
        self.client.force_login(self.usuario)

        pedido_form = self.client.get("/pedidos-online/novo/")
        integracao_form = self.client.get("/pedidos-online/integracoes/nova/")

        self.assertEqual(pedido_form.status_code, 200)
        self.assertContains(pedido_form, "Origem do pedido")
        self.assertContains(pedido_form, "Cliente")
        self.assertContains(pedido_form, "Entrega e valores")
        self.assertEqual(integracao_form.status_code, 200)
        self.assertContains(integracao_form, "Plataforma")
        self.assertContains(integracao_form, "site proprio")

    def test_detalhe_bloqueia_separacao_quando_entrega_nao_foi_calculada(self):
        PoliticaEntrega.objects.create(filial=self.filial, raio_maximo_km=Decimal("10"), valor_minimo_pedido=Decimal("0"))
        self.pedido.tipo_entrega = TipoEntrega.ENTREGA
        self.pedido.endereco_entrega = "Rua Teste, 10"
        self.pedido.save()
        self.client.force_login(self.usuario)

        resposta = self.client.get(f"/pedidos-online/{self.pedido.pk}/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Calcule a entrega antes de iniciar a separacao.")
        self.assertContains(resposta, "Entrega pendente de calculo.")
        self.assertContains(resposta, "disabled")

    def test_folha_de_separacao_renderiza_sem_configuracao_especifica(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(f"/pedidos-online/{self.pedido.pk}/separacao/imprimir/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, f"Pedido de separacao #{self.pedido.pk}")
        self.assertContains(resposta, self.produto.codigo_barras)

    def test_api_exige_chave_valida(self):
        resposta = self.client.post("/pedidos-online/api/pedidos/", data="{}", content_type="application/json")
        self.assertEqual(resposta.status_code, 401)

    def test_api_cria_pedido_e_impede_duplicidade(self):
        integracao = IntegracaoMarketplace.objects.create(nome="Parceiro", filial=self.filial, usuario=self.usuario, token_prefixo="temporario", token_hash="temporario")
        token = gerar_token_integracao(integracao)
        payload = {
            "referencia_externa": "EXT-100",
            "nome_cliente": "Maria Online",
            "tipo_entrega": "RETIRADA",
            "itens": [{"codigo_barras": self.produto.codigo_barras, "quantidade": "2", "preco_unitario": "14.50"}],
        }
        primeira = self.client.post("/pedidos-online/api/pedidos/", data=json.dumps(payload), content_type="application/json", HTTP_X_INTEGRATION_KEY=token)
        self.assertEqual(primeira.status_code, 201)
        pedido_id = primeira.json()["pedido_id"]
        pedido = PedidoOnline.objects.get(pk=pedido_id)
        self.assertEqual(pedido.total, Decimal("29.00"))
        self.assertEqual(pedido.integracao, integracao)

        repetida = self.client.post("/pedidos-online/api/pedidos/", data=json.dumps(payload), content_type="application/json", HTTP_X_INTEGRATION_KEY=token)
        self.assertEqual(repetida.status_code, 200)
        self.assertTrue(repetida.json()["duplicado"])
        self.assertEqual(PedidoOnline.objects.filter(integracao=integracao, referencia_externa="EXT-100").count(), 1)

    def test_calculo_de_entrega_aplica_faixa_e_frete_gratis(self):
        politica = PoliticaEntrega.objects.create(filial=self.filial, raio_maximo_km=Decimal("10"), valor_minimo_pedido=Decimal("20"), frete_gratis_acima=Decimal("50"))
        FaixaTaxaEntrega.objects.create(politica=politica, distancia_inicial_km=Decimal("0"), distancia_final_km=Decimal("5"), taxa=Decimal("8"))
        self.pedido.tipo_entrega = TipoEntrega.ENTREGA
        self.pedido.endereco_entrega = "Rua Teste, 10"
        self.pedido.save()

        calcular_entrega_pedido(pedido=self.pedido, distancia_km=Decimal("4"))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.taxa_entrega, Decimal("8"))
        self.assertEqual(self.pedido.total, Decimal("38"))

        self.pedido.itens.update(quantidade=Decimal("4"), total=Decimal("60"))
        self.pedido.recalcular()
        calcular_entrega_pedido(pedido=self.pedido, distancia_km=Decimal("4"))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.taxa_entrega, Decimal("0"))
        self.assertIn("Frete gratis", self.pedido.regra_entrega_aplicada)

    def test_calculo_de_entrega_recusa_distancia_fora_do_raio(self):
        PoliticaEntrega.objects.create(filial=self.filial, raio_maximo_km=Decimal("5"), valor_minimo_pedido=Decimal("0"))
        self.pedido.tipo_entrega = TipoEntrega.ENTREGA
        self.pedido.endereco_entrega = "Rua Teste, 10"
        self.pedido.save()
        with self.assertRaises(ValidationError):
            calcular_entrega_pedido(pedido=self.pedido, distancia_km=Decimal("6"))
