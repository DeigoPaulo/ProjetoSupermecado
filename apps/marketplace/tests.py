from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque
from apps.fiscal.models import AmbienteFiscal, ConfiguracaoFiscal, DocumentoFiscal, NaturezaOperacao, SerieFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal
from apps.fiscal.services import preparar_documento_pedido_online
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import TipoDocumentoConsumidor

from .models import FaixaTaxaEntrega, FormaPagamentoPedido, IntegracaoMarketplace, ItemPedidoOnline, PedidoOnline, PoliticaEntrega, StatusPagamentoPedido, StatusPedido, TipoEntrega
from .services import alterar_status_pedido, calcular_entrega_pedido, cancelar_pedido, gerar_token_integracao, registrar_pagamento, reservar_pedido


class FakeHTTPResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def close(self):
        pass


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
        self.assertContains(pedido_form, 'data-ajax-url="/empresas/filiais/busca.json"')
        self.assertContains(pedido_form, 'data-ajax-url="/clientes/busca.json"')
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
            "documento_cliente_tipo": "CPF",
            "documento_cliente": "12345678909",
            "tipo_entrega": "RETIRADA",
            "itens": [{"codigo_barras": self.produto.codigo_barras, "quantidade": "2", "preco_unitario": "14.50"}],
        }
        primeira = self.client.post("/pedidos-online/api/pedidos/", data=json.dumps(payload), content_type="application/json", HTTP_X_INTEGRATION_KEY=token)
        self.assertEqual(primeira.status_code, 201)
        pedido_id = primeira.json()["pedido_id"]
        pedido = PedidoOnline.objects.get(pk=pedido_id)
        self.assertEqual(pedido.total, Decimal("29.00"))
        self.assertEqual(pedido.integracao, integracao)
        self.assertEqual(pedido.documento_cliente_tipo, TipoDocumentoConsumidor.CPF)
        self.assertEqual(pedido.documento_cliente, "12345678909")

        repetida = self.client.post("/pedidos-online/api/pedidos/", data=json.dumps(payload), content_type="application/json", HTTP_X_INTEGRATION_KEY=token)
        self.assertEqual(repetida.status_code, 200)
        self.assertTrue(repetida.json()["duplicado"])
        self.assertEqual(PedidoOnline.objects.filter(integracao=integracao, referencia_externa="EXT-100").count(), 1)

    def test_prepara_nfe_modelo_55_para_pedido_online(self):
        self.filial.uf = "SP"
        self.filial.codigo_municipio_ibge = "3550308"
        self.filial.save(update_fields=["uf", "codigo_municipio_ibge"])
        self.produto.ncm = "10063021"
        self.produto.origem_mercadoria = "0"
        self.produto.cst_icms = "00"
        self.produto.aliquota_icms = Decimal("18.00")
        self.produto.save(update_fields=["ncm", "origem_mercadoria", "cst_icms", "aliquota_icms"])
        ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            regime_tributario="Regime normal",
            inscricao_estadual="123456789",
            certificado_a1_criptografado=b"certificado",
            certificado_senha_criptografada=b"senha",
        )
        SerieFiscal.objects.create(filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFE, serie=55, proximo_numero=200)
        NaturezaOperacao.objects.create(descricao="Venda online de mercadorias", cfop="5102", tipo_documento=TipoDocumentoFiscal.NFE)
        self.pedido.documento_cliente_tipo = TipoDocumentoConsumidor.CNPJ
        self.pedido.documento_cliente = "12345678000190"
        self.pedido.status_pagamento = StatusPagamentoPedido.PAGO
        self.pedido.forma_pagamento = FormaPagamentoPedido.GATEWAY
        self.pedido.valor_pago = self.pedido.total
        self.pedido.save(update_fields=["documento_cliente_tipo", "documento_cliente", "status_pagamento", "forma_pagamento", "valor_pago"])

        documento = preparar_documento_pedido_online(self.pedido, self.usuario)

        self.assertEqual(documento.tipo_documento, TipoDocumentoFiscal.NFE)
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.numero, 200)
        self.assertEqual(documento.pedido_online, self.pedido)
        self.assertIn("<mod>55</mod>", documento.xml_conteudo)
        self.assertIn("<CNPJ>12345678000190</CNPJ>", documento.xml_conteudo)
        self.assertEqual(DocumentoFiscal.objects.filter(pedido_online=self.pedido).count(), 1)

    def test_integracoes_mostram_saude_operacional_e_diagnostico_json(self):
        integracao = IntegracaoMarketplace.objects.create(nome="Parceiro", filial=self.filial, usuario=self.usuario, token_prefixo="temporario", token_hash="temporario")
        token = gerar_token_integracao(integracao)
        payload = {
            "referencia_externa": "EXT-200",
            "nome_cliente": "Cliente Marketplace",
            "tipo_entrega": "RETIRADA",
            "itens": [{"codigo_barras": self.produto.codigo_barras, "quantidade": "1", "preco_unitario": "15.00"}],
        }
        self.client.post("/pedidos-online/api/pedidos/", data=json.dumps(payload), content_type="application/json", HTTP_X_INTEGRATION_KEY=token)
        self.client.force_login(self.usuario)

        pagina = self.client.get("/pedidos-online/integracoes/")
        diagnostico = self.client.get("/pedidos-online/integracoes/diagnostico.json")

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Pedidos recebidos")
        self.assertContains(pagina, "Parceiro")
        self.assertContains(pagina, "pedido(s) em fluxo operacional")
        self.assertEqual(diagnostico.status_code, 200)
        dados = diagnostico.json()
        self.assertEqual(dados["resumo"]["integracoes"], 1)
        self.assertEqual(dados["resumo"]["pedidos_recebidos"], 1)
        self.assertEqual(dados["resumo"]["pedidos_abertos"], 1)
        self.assertEqual(dados["integracoes"][0]["token_prefixo"], integracao.token_prefixo)
        self.assertNotIn(token, json.dumps(dados))

    def test_diagnostico_de_integracoes_exige_perfil_de_sistema(self):
        usuario_comum = get_user_model().objects.create_user("usuario_comum", "comum@example.com", "senha")
        self.client.force_login(usuario_comum)

        resposta = self.client.get("/pedidos-online/integracoes/diagnostico.json")

        self.assertEqual(resposta.status_code, 403)

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

    def test_calculo_de_entrega_valida_bairros_atendidos_e_bloqueados(self):
        politica = PoliticaEntrega.objects.create(
            filial=self.filial,
            raio_maximo_km=Decimal("10"),
            valor_minimo_pedido=Decimal("0"),
            bairros_atendidos="Centro, Jardim",
            bairros_bloqueados="Industrial",
        )
        FaixaTaxaEntrega.objects.create(politica=politica, distancia_inicial_km=Decimal("0"), distancia_final_km=Decimal("10"), taxa=Decimal("9"))
        self.pedido.tipo_entrega = TipoEntrega.ENTREGA
        self.pedido.save()

        calcular_entrega_pedido(pedido=self.pedido, distancia_km=Decimal("4"), bairro_entrega="centro")
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.taxa_entrega, Decimal("9"))

        with self.assertRaises(ValidationError):
            calcular_entrega_pedido(pedido=self.pedido, distancia_km=Decimal("4"), bairro_entrega="Industrial")

    def test_politicas_entrega_simula_taxa_e_expoe_diagnostico(self):
        politica = PoliticaEntrega.objects.create(filial=self.filial, raio_maximo_km=Decimal("8"), valor_minimo_pedido=Decimal("20"))
        FaixaTaxaEntrega.objects.create(politica=politica, distancia_inicial_km=Decimal("0"), distancia_final_km=Decimal("4"), taxa=Decimal("7.50"))
        self.client.force_login(self.usuario)

        pagina = self.client.get(f"/pedidos-online/politicas-entrega/?simular=1&politica={politica.pk}&subtotal=30&distancia=3")
        diagnostico = self.client.get("/pedidos-online/politicas-entrega/diagnostico.json")

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Simular entrega")
        self.assertContains(pagina, "R$ 7,50")
        self.assertEqual(diagnostico.status_code, 200)
        dados = diagnostico.json()
        self.assertEqual(dados["resumo"]["politicas"], 1)
        self.assertEqual(dados["resumo"]["ativas"], 1)
        self.assertEqual(dados["politicas"][0]["filial"], str(self.filial))
        self.assertEqual(dados["geocodificacao"]["contrato"], "delivery_geocode_v1")
        self.assertTrue(dados["geocodificacao"]["fallback_manual_distancia"])

    @override_settings(MARKETPLACE_GEOCODING_PROVIDER_URL="https://mapas.example/rota?destino={destino}", MARKETPLACE_GEOCODING_TIMEOUT_SEGUNDOS=4)
    def test_politicas_entrega_simula_distancia_com_geocodificacao_configurada(self):
        politica = PoliticaEntrega.objects.create(filial=self.filial, raio_maximo_km=Decimal("8"), valor_minimo_pedido=Decimal("20"))
        FaixaTaxaEntrega.objects.create(politica=politica, distancia_inicial_km=Decimal("0"), distancia_final_km=Decimal("4"), taxa=Decimal("7.50"))
        self.client.force_login(self.usuario)

        with patch("apps.marketplace.views.urlopen", return_value=FakeHTTPResponse({"distancia_km": "3.2"})) as urlopen_mock:
            pagina = self.client.get(f"/pedidos-online/politicas-entrega/?simular=1&politica={politica.pk}&subtotal=30&endereco=Rua%20Cliente")

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "3,2 km")
        self.assertContains(pagina, "Distância calculada pelo provedor")
        self.assertContains(pagina, "R$ 7,50")
        self.assertEqual(urlopen_mock.call_args.kwargs["timeout"], 4)

    def test_simulador_de_entrega_avisa_bairro_fora_da_area(self):
        politica = PoliticaEntrega.objects.create(filial=self.filial, raio_maximo_km=Decimal("8"), valor_minimo_pedido=Decimal("20"), bairros_atendidos="Centro")
        FaixaTaxaEntrega.objects.create(politica=politica, distancia_inicial_km=Decimal("0"), distancia_final_km=Decimal("8"), taxa=Decimal("7.50"))
        self.client.force_login(self.usuario)

        resposta = self.client.get(f"/pedidos-online/politicas-entrega/?simular=1&politica={politica.pk}&subtotal=30&distancia=3&bairro=Industrial")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Bairro fora da area atendida")
