from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from PIL import Image

from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.produtos.models import Categoria, Produto

from .forms import EmpresaForm
from .models import DocumentoFiscalSincronizado, Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, ModoImplantacao, StatusEventoEntrada, StatusSincronizacao, VendaSincronizada
from . import services_eventos_entrada
from .services_eventos_entrada import ConflitoSincronizacao, processar_entrada_sincronizacao
from .services_sincronizacao import enfileirar_evento, processar_fila


GIF_1X1 = (
    b"GIF87a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def png_1x1():
    arquivo = BytesIO()
    Image.new("RGB", (1, 1), color="white").save(arquivo, format="PNG")
    return arquivo.getvalue()


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

    def test_logo_da_empresa_aceita_png_e_bloqueia_gif(self):
        dados = {
            "razao_social": "Mercado Imagem Ltda",
            "nome_fantasia": "Mercado Imagem",
            "cnpj": "12.345.678/0001-90",
            "modo_implantacao": ModoImplantacao.LOCAL,
            "is_active": "on",
        }
        png = SimpleUploadedFile("logo.png", png_1x1(), content_type="image/png")
        gif = SimpleUploadedFile("logo.gif", GIF_1X1, content_type="image/gif")

        valido = EmpresaForm(data=dados, files={"logo": png})
        self.assertTrue(valido.is_valid(), valido.errors)

        dados["cnpj"] = "12.345.678/0001-91"
        invalido = EmpresaForm(data=dados, files={"logo": gif})
        self.assertFalse(invalido.is_valid())
        self.assertIn("Envie uma imagem PNG, JPG ou JPEG.", invalido.errors["logo"])

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
        detalhe = self.client.get(f"/empresas/sincronizacao/eventos/{evento.pk}/")
        self.assertContains(painel, "Servidor indisponivel")
        self.assertContains(painel, "Cada evento possui chave idempotente")
        self.assertContains(painel, f"/empresas/sincronizacao/eventos/{evento.pk}/")
        self.assertContains(detalhe, "Evento de saida produto.atualizado")
        self.assertContains(detalhe, "Servidor indisponivel")
        self.assertContains(detalhe, "Payload enviado")

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

    def test_comando_sincronizacao_completa_processa_saida_e_entrada(self):
        saida_stdout = StringIO()
        chamadas = []

        def saida(*, limite):
            chamadas.append(("saida", limite))
            return {"enviados": 2, "erros": 1}

        def entrada(*, limite):
            chamadas.append(("entrada", limite))
            return {"processados": 3, "erros": 0}

        with patch("apps.empresas.management.commands.processar_sincronizacao_completa.processar_fila", side_effect=saida), patch(
            "apps.empresas.management.commands.processar_sincronizacao_completa.processar_entrada_sincronizacao",
            side_effect=entrada,
        ):
            call_command(
                "processar_sincronizacao_completa",
                "--limite-saida",
                "10",
                "--limite-entrada",
                "5",
                stdout=saida_stdout,
            )

        self.assertEqual(chamadas, [("saida", 10), ("entrada", 5)])
        self.assertIn("2 enviado(s), 1 erro(s) de saida", saida_stdout.getvalue())

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
        venda = VendaSincronizada.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            evento=evento,
            venda_externa_id="pdv-102",
            caixa_externo="#2",
            operador="OPERADOR",
            cliente="Cliente avulso",
            total_bruto=Decimal("35.00"),
            total_liquido=Decimal("35.00"),
            itens=[{"nome": "Arroz Branco", "codigo_barras": "789", "quantidade": "1.000", "preco_unitario": "35.00", "total": "35.00"}],
            pagamentos=[{"tipo": "DINHEIRO", "valor": "35.00", "status": "Confirmado"}],
        )

        response = self.client.get("/empresas/sincronizacao/")
        detalhe = self.client.get(f"/empresas/sincronizacao/vendas/{venda.pk}/")

        self.assertContains(response, "Vendas sincronizadas para retaguarda")
        self.assertContains(response, "pdv-102")
        self.assertContains(response, "R$ 35,00")
        self.assertContains(response, f"/empresas/sincronizacao/vendas/{venda.pk}/")
        self.assertContains(detalhe, "Venda sincronizada pdv-102")
        self.assertContains(detalhe, "Arroz Branco")
        self.assertContains(detalhe, "DINHEIRO")
        self.assertContains(detalhe, "Espelho de retaguarda")

    def test_painel_sincronizacao_filtra_vendas_e_eventos_de_entrada(self):
        evento_processado = EventoEntradaSincronizacao.objects.create(
            identificador="8d2d443c-d777-4b94-a692-ce04cb5b77f7",
            chave_idempotencia="venda:pdv-200:finalizada",
            empresa=self.empresa,
            tipo="venda.finalizada",
            payload={"payload": {}},
            status=StatusEventoEntrada.PROCESSADO,
        )
        EventoEntradaSincronizacao.objects.create(
            identificador="c8c4d969-b7d2-44fd-b803-a1599dd57d0c",
            chave_idempotencia="produto:erro:filtro",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={"payload": {}},
            status=StatusEventoEntrada.ERRO,
            ultimo_erro="Produto sem categoria",
        )
        VendaSincronizada.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            evento=evento_processado,
            venda_externa_id="pdv-200",
            operador="CAIXA FILTRADO",
            total_bruto=Decimal("20.00"),
            total_liquido=Decimal("20.00"),
        )
        outro_evento = EventoEntradaSincronizacao.objects.create(
            identificador="75f9e454-8d40-42a4-9309-1d33553a3d27",
            chave_idempotencia="venda:pdv-201:finalizada",
            empresa=self.empresa,
            tipo="venda.finalizada",
            payload={"payload": {}},
            status=StatusEventoEntrada.PROCESSADO,
        )
        VendaSincronizada.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            evento=outro_evento,
            venda_externa_id="pdv-201",
            operador="OUTRO CAIXA",
            total_bruto=Decimal("40.00"),
            total_liquido=Decimal("40.00"),
        )
        documento_evento = EventoEntradaSincronizacao.objects.create(
            identificador="7b74bdd2-2293-4627-9651-0a9fa4559438",
            chave_idempotencia="fiscal:nfce-200:emitido",
            empresa=self.empresa,
            tipo="fiscal.documento_emitido",
            payload={"payload": {}},
            status=StatusEventoEntrada.PROCESSADO,
        )
        documento = DocumentoFiscalSincronizado.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            evento=documento_evento,
            documento_externo_id="nfce-200",
            venda_externa_id="pdv-200",
            tipo_documento="NFCE",
            serie="1",
            numero="200",
            chave_acesso="CHAVE-FISCAL-FILTRADA",
            protocolo="PROTOCOLO-FILTRADO",
            status="EMITIDO",
            valor_total=Decimal("20.00"),
            payload={"sefaz": {"chave": "CHAVE-FISCAL-FILTRADA", "protocolo": "PROTOCOLO-FILTRADO"}},
        )
        EventoSincronizacao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo="produto.atualizado",
            objeto_tipo="Produto",
            objeto_id="321",
            chave_idempotencia="produto:saida:filtro",
            payload={"codigo_barras": "789321"},
            status=StatusSincronizacao.ERRO,
            tentativas=2,
            ultimo_erro="Timeout da nuvem",
        )

        busca = self.client.get("/empresas/sincronizacao/", {"q": "CAIXA FILTRADO"})
        busca_fiscal = self.client.get("/empresas/sincronizacao/", {"q": "CHAVE-FISCAL-FILTRADA"})
        detalhe_fiscal = self.client.get(f"/empresas/sincronizacao/documentos-fiscais/{documento.pk}/")
        erro = self.client.get("/empresas/sincronizacao/", {"status_entrada": StatusEventoEntrada.ERRO})
        csv_response = self.client.get("/empresas/sincronizacao/vendas.csv", {"q": "CAIXA FILTRADO"})
        csv_texto = csv_response.content.decode("utf-8-sig")
        fiscal_csv_response = self.client.get("/empresas/sincronizacao/documentos-fiscais.csv", {"q": "CHAVE-FISCAL-FILTRADA"})
        fiscal_csv_texto = fiscal_csv_response.content.decode("utf-8-sig")
        saida_csv_response = self.client.get("/empresas/sincronizacao/eventos.csv", {"q": "produto:saida:filtro"})
        saida_csv_texto = saida_csv_response.content.decode("utf-8-sig")
        entrada_csv_response = self.client.get("/empresas/sincronizacao/entrada.csv", {"status_entrada": StatusEventoEntrada.ERRO})
        entrada_csv_texto = entrada_csv_response.content.decode("utf-8-sig")

        self.assertContains(busca, "CAIXA FILTRADO")
        self.assertNotContains(busca, "Produto sem categoria")
        self.assertContains(busca_fiscal, "Documentos fiscais sincronizados")
        self.assertContains(busca_fiscal, "nfce-200")
        self.assertContains(busca_fiscal, "CHAVE-FISCAL-FILTRADA")
        self.assertContains(busca_fiscal, "Fiscal CSV")
        self.assertContains(busca_fiscal, "Saida CSV")
        self.assertContains(busca_fiscal, "Entrada CSV")
        self.assertContains(busca_fiscal, f"/empresas/sincronizacao/documentos-fiscais/{documento.pk}/")
        self.assertContains(detalhe_fiscal, "Documento fiscal sincronizado nfce-200")
        self.assertContains(detalhe_fiscal, "CHAVE-FISCAL-FILTRADA")
        self.assertContains(detalhe_fiscal, "PROTOCOLO-FILTRADO")
        self.assertContains(detalhe_fiscal, "Payload recebido")
        self.assertContains(erro, "Produto sem categoria")
        self.assertContains(erro, "Status entrada")
        self.assertContains(erro, "Agendamento no servidor local")
        self.assertContains(erro, "processar_sincronizacao_completa")
        self.assertContains(erro, "schtasks /Create")
        self.assertEqual(csv_response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("vendas_sincronizadas.csv", csv_response["Content-Disposition"])
        self.assertIn("pdv-200", csv_texto)
        self.assertIn("CAIXA FILTRADO", csv_texto)
        self.assertNotIn("pdv-201", csv_texto)
        self.assertEqual(fiscal_csv_response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("documentos_fiscais_sincronizados.csv", fiscal_csv_response["Content-Disposition"])
        self.assertIn("nfce-200", fiscal_csv_texto)
        self.assertIn("CHAVE-FISCAL-FILTRADA", fiscal_csv_texto)
        self.assertEqual(saida_csv_response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("eventos_sincronizacao_saida.csv", saida_csv_response["Content-Disposition"])
        self.assertIn("produto:saida:filtro", saida_csv_texto)
        self.assertIn("Timeout da nuvem", saida_csv_texto)
        self.assertEqual(entrada_csv_response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("eventos_sincronizacao_entrada.csv", entrada_csv_response["Content-Disposition"])
        self.assertIn("produto:erro:filtro", entrada_csv_texto)
        self.assertIn("Produto sem categoria", entrada_csv_texto)
        self.assertNotIn("venda:pdv-200:finalizada", entrada_csv_texto)

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

    def test_processador_de_entrada_registra_documento_fiscal_sincronizado(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="930918be-2852-48d9-909c-71d8a0840f72",
            chave_idempotencia="fiscal:nfce-100:emitido",
            empresa=self.empresa,
            tipo="fiscal.documento_emitido",
            payload={
                "id": "930918be-2852-48d9-909c-71d8a0840f72",
                "payload": {
                    "documento_id": "nfce-100",
                    "venda_id": "pdv-100",
                    "filial_cnpj": self.filial.cnpj,
                    "tipo_documento": "NFCE",
                    "ambiente": "HOMOLOGACAO",
                    "serie": "1",
                    "numero": "100",
                    "chave_acesso": "35260744444444000144650010000001001000001000",
                    "protocolo": "135260000000001",
                    "status": "EMITIDO",
                    "valor_total": "82.70",
                    "emitido_em": "2026-07-01T14:12:00Z",
                },
            },
        )

        resultado = processar_entrada_sincronizacao()

        evento.refresh_from_db()
        documento = DocumentoFiscalSincronizado.objects.get(documento_externo_id="nfce-100")
        self.assertEqual(resultado, {"processados": 1, "erros": 0})
        self.assertEqual(evento.status, StatusEventoEntrada.PROCESSADO)
        self.assertEqual(documento.filial, self.filial)
        self.assertEqual(documento.valor_total, Decimal("82.70"))
        self.assertEqual(documento.chave_acesso, "35260744444444000144650010000001001000001000")

    def test_processador_de_entrada_marca_conflito_para_documento_fiscal_com_chave_diferente(self):
        evento_original = EventoEntradaSincronizacao.objects.create(
            identificador="1487fb65-6303-46d5-8ef0-8cf58f364432",
            chave_idempotencia="fiscal:nfce-101:original",
            empresa=self.empresa,
            tipo="fiscal.documento_emitido",
            payload={"payload": {}},
            status=StatusEventoEntrada.PROCESSADO,
        )
        DocumentoFiscalSincronizado.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            evento=evento_original,
            documento_externo_id="nfce-101",
            tipo_documento="NFCE",
            chave_acesso="CHAVE-ORIGINAL",
            valor_total=Decimal("50.00"),
        )
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="8afd1e39-050c-4ab6-a8b1-d2e2de3b1828",
            chave_idempotencia="fiscal:nfce-101:divergente",
            empresa=self.empresa,
            tipo="fiscal.documento_emitido",
            payload={
                "id": "8afd1e39-050c-4ab6-a8b1-d2e2de3b1828",
                "payload": {
                    "documento_id": "nfce-101",
                    "filial_cnpj": self.filial.cnpj,
                    "chave_acesso": "CHAVE-DIFERENTE",
                    "valor_total": "50.00",
                },
            },
        )

        processar_entrada_sincronizacao()

        evento.refresh_from_db()
        self.assertEqual(evento.status, StatusEventoEntrada.CONFLITO)
        self.assertIn("chave de acesso diferente", evento.ultimo_erro)

    def test_painel_exibe_eventos_recebidos_da_sincronizacao(self):
        EventoEntradaSincronizacao.objects.create(
            identificador="7e336c07-f8c8-428c-b0d3-5e55ef07c38d",
            chave_idempotencia="sistema:ping:2",
            empresa=self.empresa,
            tipo="sistema.ping",
            payload={"id": "7e336c07-f8c8-428c-b0d3-5e55ef07c38d", "payload": {}},
        )

        response = self.client.get("/empresas/sincronizacao/")
        detalhe = self.client.get(f"/empresas/sincronizacao/entrada/{EventoEntradaSincronizacao.objects.get(chave_idempotencia='sistema:ping:2').pk}/")

        self.assertContains(response, "Entrada recebida da nuvem/local")
        self.assertContains(response, "sistema.ping")
        self.assertContains(response, "/empresas/sincronizacao/entrada/")
        self.assertContains(detalhe, "Evento de entrada sistema.ping")
        self.assertContains(detalhe, "Payload recebido")

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

        detalhe = self.client.get(f"/empresas/sincronizacao/entrada/{evento.pk}/")
        response = self.client.post(f"/empresas/sincronizacao/entrada/{evento.pk}/reprocessar/", follow=True)

        evento.refresh_from_db()
        self.assertContains(detalhe, "Evento de entrada produto.atualizado")
        self.assertContains(detalhe, "Produto sem categoria")
        self.assertContains(detalhe, "Reprocessar entrada")
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

    def test_resolve_conflito_de_entrada_com_decisao_auditavel(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="7153780f-0805-4846-8297-b28adfb49688",
            chave_idempotencia="fiscal:nfce:conflito:manual",
            empresa=self.empresa,
            tipo="fiscal.documento_emitido",
            payload={"id": "7153780f-0805-4846-8297-b28adfb49688", "payload": {"documento_id": "nfce-500"}},
            status=StatusEventoEntrada.CONFLITO,
            ultimo_erro="Documento fiscal externo ja existe com chave de acesso diferente.",
        )

        detalhe = self.client.get(f"/empresas/sincronizacao/entrada/{evento.pk}/")
        vazio = self.client.post(f"/empresas/sincronizacao/entrada/{evento.pk}/resolver-conflito/", {"resolucao_conflito": ""}, follow=True)
        resolvido = self.client.post(
            f"/empresas/sincronizacao/entrada/{evento.pk}/resolver-conflito/",
            {"resolucao_conflito": "Conferido com a loja; manter documento local e arquivar evento duplicado."},
            follow=True,
        )

        evento.refresh_from_db()
        painel = self.client.get("/empresas/sincronizacao/")
        self.assertContains(detalhe, "Marcar conflito como resolvido")
        self.assertContains(vazio, "Informe a decisao tomada")
        self.assertEqual(evento.status, StatusEventoEntrada.RESOLVIDO)
        self.assertEqual(evento.resolvido_por, self.user)
        self.assertIsNotNone(evento.resolvido_em)
        self.assertIn("manter documento local", evento.resolucao_conflito)
        self.assertContains(resolvido, "Resolvido manualmente")
        self.assertContains(resolvido, "manter documento local")
        self.assertContains(painel, "Conflitos resolvidos")

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
