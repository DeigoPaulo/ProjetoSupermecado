from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.produtos.models import Categoria, Produto

from .forms import EmpresaForm
from .models import Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, ModoImplantacao, StatusEventoEntrada, StatusSincronizacao, VendaSincronizada
from . import services_eventos_entrada
from .services_eventos_entrada import ConflitoSincronizacao, processar_entrada_sincronizacao
from .services_sincronizacao import enfileirar_evento, processar_fila


class EmpresasViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Teste Ltda",
            nome_fantasia="Mercado Teste",
            cnpj="44.444.444/0001-44",
            regime_tributario="Simples Nacional",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz",
            cnpj=self.empresa.cnpj,
            municipio="Sao Paulo",
            uf="SP",
            codigo_municipio_ibge="3550308",
        )

    def test_lista_empresas_e_filiais(self):
        response = self.client.get("/empresas/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empresas e filiais")
        self.assertContains(response, "Mercado Teste")
        self.assertContains(response, "IBGE 3550308")

    def test_formularios_exibem_secoes_administrativas(self):
        empresa_response = self.client.get(f"/empresas/{self.empresa.pk}/editar/")
        filial_response = self.client.get(f"/empresas/filiais/{self.filial.pk}/editar/")

        self.assertEqual(empresa_response.status_code, 200)
        self.assertContains(empresa_response, "Identificacao")
        self.assertContains(empresa_response, "Contato e visual")
        self.assertContains(empresa_response, "Implantacao e conectividade")
        self.assertContains(empresa_response, "modo local nao publica o sistema na internet")
        self.assertContains(empresa_response, "Consulta CNPJ/CEP preparada")
        self.assertContains(empresa_response, "data-lookup-target")
        self.assertEqual(filial_response.status_code, 200)
        self.assertContains(filial_response, "Loja")
        self.assertContains(filial_response, "Dados fiscais da filial")
        self.assertContains(filial_response, "Necessario para preencher o XML da NFC-e")
        self.assertContains(filial_response, "select2-field")
        self.assertContains(filial_response, "Ver ponto de integracao")

    def test_modo_local_desativa_e_remove_sincronizacao_externa(self):
        form = EmpresaForm(
            data={
                "razao_social": "Mercado Local Ltda",
                "nome_fantasia": "Mercado Local",
                "cnpj": "11.111.111/0001-11",
                "modo_implantacao": ModoImplantacao.LOCAL,
                "sincronizacao_automatica": "on",
                "url_sincronizacao": "https://nuvem.exemplo.com/api/",
                "is_active": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        empresa = form.save()
        self.assertFalse(empresa.sincronizacao_automatica)
        self.assertEqual(empresa.url_sincronizacao, "")

    def test_modo_hibrido_exige_url_https_para_sincronizacao(self):
        dados = {
            "razao_social": "Mercado Hibrido Ltda",
            "nome_fantasia": "Mercado Hibrido",
            "cnpj": "22.222.222/0001-22",
            "modo_implantacao": ModoImplantacao.HIBRIDO,
            "sincronizacao_automatica": "on",
            "url_sincronizacao": "http://nuvem.exemplo.com/api/",
            "is_active": "on",
        }
        inseguro = EmpresaForm(data=dados)
        self.assertFalse(inseguro.is_valid())
        self.assertIn("url_sincronizacao", inseguro.errors)

        dados["url_sincronizacao"] = "https://nuvem.exemplo.com/api/"
        seguro = EmpresaForm(data=dados)
        self.assertTrue(seguro.is_valid(), seguro.errors)

    def test_empresa_local_nao_enfileira_evento_para_nuvem(self):
        evento, criado = enfileirar_evento(
            empresa=self.empresa,
            filial=self.filial,
            tipo="produto.atualizado",
            objeto_tipo="Produto",
            objeto_id=10,
            payload={"nome": "Arroz"},
            chave_idempotencia="produto:10:v1",
        )

        self.assertIsNone(evento)
        self.assertFalse(criado)
        self.assertFalse(EventoSincronizacao.objects.exists())

    def test_fila_hibrida_e_idempotente(self):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = "https://nuvem.exemplo.com/api/"
        self.empresa.save()
        dados = {
            "empresa": self.empresa,
            "filial": self.filial,
            "tipo": "venda.finalizada",
            "objeto_tipo": "Venda",
            "objeto_id": 25,
            "payload": {"total": "89.90"},
            "chave_idempotencia": "venda:25:finalizada",
        }

        primeiro, criado = enfileirar_evento(**dados)
        repetido, criado_novamente = enfileirar_evento(**dados)

        self.assertTrue(criado)
        self.assertFalse(criado_novamente)
        self.assertEqual(primeiro, repetido)
        self.assertEqual(EventoSincronizacao.objects.count(), 1)

    def test_painel_reprocessa_evento_com_erro(self):
        evento = EventoSincronizacao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo="produto.atualizado",
            objeto_tipo="Produto",
            objeto_id="10",
            chave_idempotencia="produto:10:erro",
            payload={},
            status=StatusSincronizacao.ERRO,
            tentativas=3,
            ultimo_erro="Servidor indisponivel",
        )

        painel = self.client.get("/empresas/sincronizacao/")
        self.assertContains(painel, "Servidor indisponivel")
        self.assertContains(painel, "Cada evento possui chave idempotente")

        resposta = self.client.post(f"/empresas/sincronizacao/{evento.pk}/reprocessar/", follow=True)
        evento.refresh_from_db()
        self.assertRedirects(resposta, "/empresas/sincronizacao/")
        self.assertEqual(evento.status, StatusSincronizacao.PENDENTE)
        self.assertEqual(evento.tentativas, 0)
        self.assertEqual(evento.ultimo_erro, "")

    def _evento_hibrido(self, chave="venda:99:finalizada"):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = "https://nuvem.exemplo.com/api/"
        self.empresa.save()
        evento, _ = enfileirar_evento(
            empresa=self.empresa,
            filial=self.filial,
            tipo="venda.finalizada",
            objeto_tipo="Venda",
            objeto_id=99,
            payload={"total": "50.00"},
            chave_idempotencia=chave,
        )
        return evento

    def test_processador_marca_evento_como_enviado(self):
        evento = self._evento_hibrido()
        recebidos = []

        resultado = processar_fila(enviar=lambda item: recebidos.append(item.identificador))

        evento.refresh_from_db()
        self.assertEqual(resultado, {"enviados": 1, "erros": 0})
        self.assertEqual(recebidos, [evento.identificador])
        self.assertEqual(evento.status, StatusSincronizacao.ENVIADO)
        self.assertEqual(evento.tentativas, 1)
        self.assertIsNotNone(evento.processado_em)

    @override_settings(
        SINCRONIZACAO_RETRY_BASE_SEGUNDOS=30,
        SINCRONIZACAO_RETRY_MAX_SEGUNDOS=3600,
        SINCRONIZACAO_MAX_TENTATIVAS=8,
    )
    def test_processador_registra_erro_e_agenda_nova_tentativa(self):
        evento = self._evento_hibrido("venda:100:finalizada")

        def falhar(_evento):
            raise RuntimeError("Nuvem indisponivel")

        resultado = processar_fila(enviar=falhar)

        evento.refresh_from_db()
        self.assertEqual(resultado, {"enviados": 0, "erros": 1})
        self.assertEqual(evento.status, StatusSincronizacao.ERRO)
        self.assertEqual(evento.tentativas, 1)
        self.assertIn("Nuvem indisponivel", evento.ultimo_erro)
        self.assertIsNotNone(evento.proxima_tentativa_em)

    @override_settings(SINCRONIZACAO_API_TOKEN="token-seguro")
    def test_receptor_autenticado_armazena_evento_e_elimina_duplicidade(self):
        dados = {
            "id": "9ad3ac53-1f99-4de5-9e8a-90ac1ee015ad",
            "tipo": "venda.finalizada",
            "empresa_cnpj": self.empresa.cnpj,
            "payload": {"total": "125.90"},
        }
        cabecalhos = {
            "HTTP_AUTHORIZATION": "Bearer token-seguro",
            "HTTP_IDEMPOTENCY_KEY": "venda:125:finalizada",
        }

        primeira = self.client.post(
            "/empresas/api/sincronizacao/eventos/",
            data=dados,
            content_type="application/json",
            **cabecalhos,
        )
        repetida = self.client.post(
            "/empresas/api/sincronizacao/eventos/",
            data=dados,
            content_type="application/json",
            **cabecalhos,
        )

        self.assertEqual(primeira.status_code, 202)
        self.assertEqual(repetida.status_code, 200)
        self.assertEqual(repetida.json()["status"], "duplicado")
        self.assertEqual(EventoEntradaSincronizacao.objects.count(), 1)
        entrada = EventoEntradaSincronizacao.objects.get()
        self.assertEqual(entrada.empresa, self.empresa)
        self.assertEqual(entrada.payload["payload"]["total"], "125.90")

    @override_settings(SINCRONIZACAO_API_TOKEN="token-seguro")
    def test_receptor_rejeita_token_invalido_e_empresa_desconhecida(self):
        dados = {
            "id": "07ef1a44-22b8-4056-bef4-bce452e3ca94",
            "tipo": "produto.atualizado",
            "empresa_cnpj": "00.000.000/9999-00",
            "payload": {},
        }
        invalido = self.client.post(
            "/empresas/api/sincronizacao/eventos/",
            data=dados,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer incorreto",
            HTTP_IDEMPOTENCY_KEY="produto:1:v2",
        )
        desconhecida = self.client.post(
            "/empresas/api/sincronizacao/eventos/",
            data=dados,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer token-seguro",
            HTTP_IDEMPOTENCY_KEY="produto:1:v2",
        )

        self.assertEqual(invalido.status_code, 401)
        self.assertEqual(desconhecida.status_code, 422)
        self.assertFalse(EventoEntradaSincronizacao.objects.exists())

    def test_processador_de_entrada_processa_ping_e_isola_tipo_sem_handler(self):
        ping = EventoEntradaSincronizacao.objects.create(
            identificador="233015dc-9485-4724-ac50-3bf511d31fb8",
            chave_idempotencia="sistema:ping:1",
            empresa=self.empresa,
            tipo="sistema.ping",
            payload={"id": "233015dc-9485-4724-ac50-3bf511d31fb8", "payload": {}},
        )
        desconhecido = EventoEntradaSincronizacao.objects.create(
            identificador="2e5be651-a71e-438e-8540-6c32cc08d54f",
            chave_idempotencia="produto:99:v2",
            empresa=self.empresa,
            tipo="dominio.desconhecido",
            payload={"id": "2e5be651-a71e-438e-8540-6c32cc08d54f", "payload": {"nome": "Arroz"}},
        )

        resultado = processar_entrada_sincronizacao()

        ping.refresh_from_db()
        desconhecido.refresh_from_db()
        self.assertEqual(resultado, {"processados": 1, "erros": 1})
        self.assertEqual(ping.status, StatusEventoEntrada.PROCESSADO)
        self.assertIsNotNone(ping.processado_em)
        self.assertEqual(desconhecido.status, StatusEventoEntrada.ERRO)
        self.assertIn("Evento sem manipulador de dominio", desconhecido.ultimo_erro)

    def test_processador_de_entrada_separa_conflito_de_erro_tecnico(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="11f469af-44e6-4e96-bb39-bd86996df0c8",
            chave_idempotencia="produto:conflito:1",
            empresa=self.empresa,
            tipo="produto.conflito",
            payload={"id": "11f469af-44e6-4e96-bb39-bd86996df0c8", "payload": {"sku": "789"}},
        )

        def conflitar(_evento):
            raise ConflitoSincronizacao("Produto local foi alterado depois do evento remoto.")

        services_eventos_entrada.MANIPULADORES["produto.conflito"] = conflitar
        try:
            resultado = processar_entrada_sincronizacao()
        finally:
            services_eventos_entrada.MANIPULADORES.pop("produto.conflito", None)

        evento.refresh_from_db()
        self.assertEqual(resultado, {"processados": 0, "erros": 1})
        self.assertEqual(evento.status, StatusEventoEntrada.CONFLITO)
        self.assertIn("Produto local foi alterado", evento.ultimo_erro)

    def test_processador_de_entrada_cria_produto(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="747fd38b-0e68-4315-92d4-1827ba53c84d",
            chave_idempotencia="produto:789900000001:criado",
            empresa=self.empresa,
            tipo="produto.criado",
            payload={
                "id": "747fd38b-0e68-4315-92d4-1827ba53c84d",
                "payload": {
                    "codigo_barras": "789900000001",
                    "nome": "Macarrao Parafuso",
                    "categoria": "Mercearia",
                    "marca": {"nome": "Casa Boa"},
                    "unidade": "UN",
                    "preco_custo": "3.20",
                    "preco_venda": "5.49",
                    "estoque_minimo": "6",
                    "vendido_no_pdv": True,
                    "vendido_no_marketplace": True,
                    "ncm": "19021900",
                    "origem_mercadoria": "0",
                    "cst_icms": "00",
                    "aliquota_icms": "18",
                    "is_active": True,
                },
            },
        )

        resultado = processar_entrada_sincronizacao()

        evento.refresh_from_db()
        produto = Produto.objects.get(codigo_barras="789900000001")
        self.assertEqual(resultado, {"processados": 1, "erros": 0})
        self.assertEqual(evento.status, StatusEventoEntrada.PROCESSADO)
        self.assertEqual(produto.nome, "Macarrao Parafuso")
        self.assertEqual(produto.categoria.nome, "Mercearia")
        self.assertEqual(produto.marca.nome, "Casa Boa")
        self.assertEqual(produto.preco_venda, Decimal("5.49"))
        self.assertTrue(produto.vendido_no_marketplace)

    def test_processador_de_entrada_atualiza_produto_existente(self):
        categoria = Categoria.objects.create(nome="Bebidas")
        produto = Produto.objects.create(
            codigo_barras="789900000002",
            nome="Refrigerante",
            categoria=categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("7.00"),
        )
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="4560a3f2-e846-4d8d-a3dc-bc766ca6643f",
            chave_idempotencia="produto:789900000002:atualizado",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={
                "id": "4560a3f2-e846-4d8d-a3dc-bc766ca6643f",
                "criado_em": "2099-01-01T10:00:00Z",
                "payload": {
                    "codigo_barras": "789900000002",
                    "nome": "Refrigerante Cola 2L",
                    "categoria": "Bebidas",
                    "preco_custo": "4.50",
                    "preco_venda": "8.99",
                    "vendido_no_pdv": True,
                    "is_active": True,
                },
            },
        )

        processar_entrada_sincronizacao()

        evento.refresh_from_db()
        produto.refresh_from_db()
        self.assertEqual(evento.status, StatusEventoEntrada.PROCESSADO)
        self.assertEqual(produto.nome, "Refrigerante Cola 2L")
        self.assertEqual(produto.preco_venda, Decimal("8.99"))

    def test_processador_de_entrada_marca_conflito_quando_produto_local_e_mais_novo(self):
        categoria = Categoria.objects.create(nome="Higiene")
        produto = Produto.objects.create(
            codigo_barras="789900000003",
            nome="Sabonete Local",
            categoria=categoria,
            preco_custo=Decimal("1.00"),
            preco_venda=Decimal("2.50"),
        )
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="6f94013b-7854-4ceb-ba6b-99ec26c13865",
            chave_idempotencia="produto:789900000003:antigo",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={
                "id": "6f94013b-7854-4ceb-ba6b-99ec26c13865",
                "criado_em": "2020-01-01T10:00:00Z",
                "payload": {
                    "codigo_barras": produto.codigo_barras,
                    "nome": "Sabonete Remoto Antigo",
                    "categoria": "Higiene",
                    "preco_venda": "2.10",
                },
            },
        )

        resultado = processar_entrada_sincronizacao()

        evento.refresh_from_db()
        produto.refresh_from_db()
        self.assertEqual(resultado, {"processados": 0, "erros": 1})
        self.assertEqual(evento.status, StatusEventoEntrada.CONFLITO)
        self.assertEqual(produto.nome, "Sabonete Local")

    def test_processador_de_entrada_atualiza_saldo_de_estoque_por_filial(self):
        categoria = Categoria.objects.create(nome="Congelados")
        produto = Produto.objects.create(
            codigo_barras="789900000004",
            nome="Pizza Congelada",
            categoria=categoria,
            preco_custo=Decimal("8.00"),
            preco_venda=Decimal("15.00"),
        )
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("3.000"))
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="65ff5c07-0e5c-4801-a466-07490f3d2974",
            chave_idempotencia="estoque:789900000004:matriz:saldo",
            empresa=self.empresa,
            tipo="estoque.saldo_atualizado",
            payload={
                "id": "65ff5c07-0e5c-4801-a466-07490f3d2974",
                "criado_em": "2099-01-01T10:00:00Z",
                "payload": {
                    "codigo_barras": produto.codigo_barras,
                    "filial_cnpj": self.filial.cnpj,
                    "quantidade_atual": "12.500",
                    "quantidade_reservada": "2.000",
                },
            },
        )

        resultado = processar_entrada_sincronizacao()

        evento.refresh_from_db()
        estoque = Estoque.objects.get(produto=produto, filial=self.filial)
        movimentacao = MovimentacaoEstoque.objects.get(referencia=f"sync:{evento.identificador}")
        self.assertEqual(resultado, {"processados": 1, "erros": 0})
        self.assertEqual(evento.status, StatusEventoEntrada.PROCESSADO)
        self.assertEqual(estoque.quantidade_atual, Decimal("12.500"))
        self.assertEqual(estoque.quantidade_reservada, Decimal("2.000"))
        self.assertEqual(movimentacao.tipo, TipoMovimentacaoEstoque.AJUSTE)
        self.assertEqual(movimentacao.quantidade, Decimal("9.500"))

    def test_processador_de_entrada_marca_conflito_quando_estoque_tem_produto_desconhecido(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="b8c5dd89-4212-4930-98be-1a05a4ec192d",
            chave_idempotencia="estoque:desconhecido:saldo",
            empresa=self.empresa,
            tipo="estoque.saldo_atualizado",
            payload={
                "id": "b8c5dd89-4212-4930-98be-1a05a4ec192d",
                "payload": {
                    "codigo_barras": "789000000999",
                    "filial_cnpj": self.filial.cnpj,
                    "quantidade_atual": "4",
                },
            },
        )

        processar_entrada_sincronizacao()

        evento.refresh_from_db()
        self.assertEqual(evento.status, StatusEventoEntrada.CONFLITO)
        self.assertIn("Produto do saldo de estoque nao encontrado", evento.ultimo_erro)

    def test_processador_de_entrada_registra_venda_finalizada_sincronizada(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="3a96e255-1c2c-4f13-9df5-ff12f0a74669",
            chave_idempotencia="venda:pdv-100:finalizada",
            empresa=self.empresa,
            tipo="venda.finalizada",
            payload={
                "id": "3a96e255-1c2c-4f13-9df5-ff12f0a74669",
                "payload": {
                    "venda_id": "pdv-100",
                    "filial_cnpj": self.filial.cnpj,
                    "caixa": "#1",
                    "operador": "DEIGOPAULO",
                    "cliente": "Cliente avulso",
                    "total_bruto": "82.70",
                    "desconto": "0",
                    "total_liquido": "82.70",
                    "realizada_em": "2026-07-01T14:09:00Z",
                    "itens": [{"codigo_barras": "789", "quantidade": "1.000", "total": "82.70"}],
                    "pagamentos": [{"tipo": "PIX", "valor": "82.70"}],
                },
            },
        )

        resultado = processar_entrada_sincronizacao()

        evento.refresh_from_db()
        venda = VendaSincronizada.objects.get(venda_externa_id="pdv-100")
        self.assertEqual(resultado, {"processados": 1, "erros": 0})
        self.assertEqual(evento.status, StatusEventoEntrada.PROCESSADO)
        self.assertEqual(venda.filial, self.filial)
        self.assertEqual(venda.total_liquido, Decimal("82.70"))
        self.assertEqual(venda.pagamentos[0]["tipo"], "PIX")

    def test_painel_exibe_vendas_sincronizadas_para_retaguarda(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="8513d7ec-966d-473f-ab79-a83f745e97b7",
            chave_idempotencia="venda:pdv-102:finalizada",
            empresa=self.empresa,
            tipo="venda.finalizada",
            payload={"payload": {}},
            status=StatusEventoEntrada.PROCESSADO,
        )
        VendaSincronizada.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            evento=evento,
            venda_externa_id="pdv-102",
            caixa_externo="#2",
            operador="OPERADOR",
            cliente="Cliente avulso",
            total_bruto=Decimal("35.00"),
            total_liquido=Decimal("35.00"),
            pagamentos=[{"tipo": "DINHEIRO", "valor": "35.00"}],
        )

        response = self.client.get("/empresas/sincronizacao/")

        self.assertContains(response, "Vendas sincronizadas para retaguarda")
        self.assertContains(response, "pdv-102")
        self.assertContains(response, "R$ 35,00")

    def test_processador_de_entrada_marca_conflito_para_venda_com_total_diferente(self):
        existente_evento = EventoEntradaSincronizacao.objects.create(
            identificador="6995a918-c8c1-4fc4-9dc4-70476369100f",
            chave_idempotencia="venda:pdv-101:original",
            empresa=self.empresa,
            tipo="venda.finalizada",
            payload={"payload": {}},
            status=StatusEventoEntrada.PROCESSADO,
        )
        VendaSincronizada.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            evento=existente_evento,
            venda_externa_id="pdv-101",
            total_bruto=Decimal("50.00"),
            total_liquido=Decimal("50.00"),
        )
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="8df091f7-13d1-4ab5-864d-a3d26177ec7f",
            chave_idempotencia="venda:pdv-101:divergente",
            empresa=self.empresa,
            tipo="venda.finalizada",
            payload={
                "id": "8df091f7-13d1-4ab5-864d-a3d26177ec7f",
                "payload": {
                    "venda_id": "pdv-101",
                    "filial_cnpj": self.filial.cnpj,
                    "total_bruto": "60.00",
                    "desconto": "0",
                    "total_liquido": "60.00",
                    "itens": [],
                    "pagamentos": [],
                },
            },
        )

        processar_entrada_sincronizacao()

        evento.refresh_from_db()
        self.assertEqual(evento.status, StatusEventoEntrada.CONFLITO)
        self.assertIn("total diferente", evento.ultimo_erro)

    def test_painel_exibe_eventos_recebidos_da_sincronizacao(self):
        EventoEntradaSincronizacao.objects.create(
            identificador="7e336c07-f8c8-428c-b0d3-5e55ef07c38d",
            chave_idempotencia="sistema:ping:2",
            empresa=self.empresa,
            tipo="sistema.ping",
            payload={"id": "7e336c07-f8c8-428c-b0d3-5e55ef07c38d", "payload": {}},
        )

        response = self.client.get("/empresas/sincronizacao/")

        self.assertContains(response, "Entrada recebida da nuvem/local")
        self.assertContains(response, "sistema.ping")

    def test_painel_reprocessa_evento_de_entrada_com_erro(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="8fbf1280-f1f6-452b-84a5-d8d27a080b45",
            chave_idempotencia="produto:erro:entrada",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={"id": "8fbf1280-f1f6-452b-84a5-d8d27a080b45", "payload": {"nome": "Feijao"}},
            status=StatusEventoEntrada.ERRO,
            ultimo_erro="Produto sem categoria",
        )

        response = self.client.post(f"/empresas/sincronizacao/entrada/{evento.pk}/reprocessar/", follow=True)

        evento.refresh_from_db()
        self.assertRedirects(response, "/empresas/sincronizacao/")
        self.assertEqual(evento.status, StatusEventoEntrada.RECEBIDO)
        self.assertEqual(evento.ultimo_erro, "")

    def test_painel_reprocessa_evento_de_entrada_com_conflito(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="401e4d57-dafb-46e0-8f4b-794a75ed6835",
            chave_idempotencia="produto:conflito:entrada",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={"id": "401e4d57-dafb-46e0-8f4b-794a75ed6835", "payload": {"nome": "Cafe"}},
            status=StatusEventoEntrada.CONFLITO,
            ultimo_erro="Produto alterado na loja e na nuvem",
        )

        painel = self.client.get("/empresas/sincronizacao/")
        response = self.client.post(f"/empresas/sincronizacao/entrada/{evento.pk}/reprocessar/", follow=True)

        evento.refresh_from_db()
        self.assertContains(painel, "Entrada em conflito")
        self.assertRedirects(response, "/empresas/sincronizacao/")
        self.assertEqual(evento.status, StatusEventoEntrada.RECEBIDO)
        self.assertEqual(evento.ultimo_erro, "")

    def test_cria_filial_com_dados_fiscais(self):
        response = self.client.post(
            "/empresas/filiais/nova/",
            {
                "empresa": self.empresa.pk,
                "nome": "Loja 2",
                "cnpj": "55.555.555/0001-55",
                "telefone": "",
                "endereco": "Rua Teste",
                "municipio": "Sao Paulo",
                "uf": "SP",
                "codigo_municipio_ibge": "3550308",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Filial.objects.filter(nome="Loja 2", codigo_municipio_ibge="3550308").exists())

    def test_bloqueia_codigo_ibge_invalido(self):
        response = self.client.post(
            "/empresas/filiais/nova/",
            {
                "empresa": self.empresa.pk,
                "nome": "Loja invalida",
                "cnpj": "",
                "telefone": "",
                "endereco": "",
                "municipio": "Sao Paulo",
                "uf": "SP",
                "codigo_municipio_ibge": "123",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe o codigo IBGE com 7 digitos.")
        self.assertFalse(Filial.objects.filter(nome="Loja invalida").exists())

    def test_endpoint_consulta_cadastro_prepara_integracao_externa(self):
        response = self.client.get("/empresas/consulta-cadastro.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "integration_pending")
        self.assertIn("codigo_municipio_ibge", payload["campos_previstos"])
