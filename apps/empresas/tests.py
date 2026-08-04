from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque, movimentar_estoque
from apps.financeiro.models import ContaMovimentoFinanceiro, TipoContaMovimento, TipoLancamentoFinanceiro
from apps.financeiro.services import registrar_lancamento
from apps.produtos.models import Categoria, CodigoBarrasProduto, Produto

from .forms import EmpresaForm
from .models import DocumentoFiscalSincronizado, Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, LancamentoFinanceiroSincronizado, ModoImplantacao, PoliticaConflitoSincronizacao, StatusEventoEntrada, StatusSincronizacao, VendaSincronizada
from . import services_eventos_entrada
from .services_eventos_entrada import ConflitoSincronizacao, processar_entrada_sincronizacao
from .services_sincronizacao import enviar_evento_http, enfileirar_evento, processar_fila


GIF_1X1 = (
    b"GIF87a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def png_1x1():
    arquivo = BytesIO()
    Image.new("RGB", (1, 1), color="white").save(arquivo, format="PNG")
    return arquivo.getvalue()


class FakeHTTPResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.closed = False

    def read(self):
        import json

        return json.dumps(self.payload).encode("utf-8")

    def close(self):
        self.closed = True


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
            modo_implantacao=ModoImplantacao.HIBRIDO,
            sincronizacao_automatica=True,
            url_sincronizacao="https://nuvem.exemplo.com/api/",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz",
            cnpj=self.empresa.cnpj,
            municipio="Sao Paulo",
            uf="SP",
            codigo_municipio_ibge="3550308",
        )

    def test_registrar_lancamento_publica_contrato_financeiro_idempotente(self):
        conta = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa principal",
            tipo=TipoContaMovimento.CAIXA,
        )

        lancamento = registrar_lancamento(
            conta=conta,
            tipo=TipoLancamentoFinanceiro.ENTRADA,
            descricao="Venda PDV #150",
            valor=Decimal("82.70"),
            data=timezone.localdate(),
            usuario=self.user,
            origem="PDV_VENDA",
        )

        evento = EventoSincronizacao.objects.get(
            tipo="financeiro.lancamento_registrado",
            objeto_id=str(lancamento.pk),
        )
        self.assertEqual(evento.filial, self.filial)
        self.assertEqual(evento.payload["contrato"], "financeiro_lancamento_v1")
        self.assertEqual(evento.payload["valor"], "82.70")
        self.assertEqual(evento.payload["conta_movimento"]["nome"], "Caixa principal")
        self.assertEqual(evento.chave_idempotencia, f"financeiro:lancamento:{self.empresa.pk}:{lancamento.pk}")

    def test_entrada_financeira_cria_espelho_e_expoe_painel_csv_diagnostico(self):
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="921bc683-b120-4a28-a29c-423b72dd4ea2",
            chave_idempotencia="financeiro:lancamento:loja:501",
            empresa=self.empresa,
            tipo="financeiro.lancamento_registrado",
            payload={
                "payload": {
                    "contrato": "financeiro_lancamento_v1",
                    "lancamento_id": "501",
                    "filial_cnpj": self.filial.cnpj,
                    "tipo": "ENTRADA",
                    "origem": "PDV_VENDA",
                    "descricao": "Venda PDV #501",
                    "valor": "35.40",
                    "data": "2026-08-03",
                    "conta_movimento": {"nome": "Caixa principal", "tipo": "CAIXA"},
                    "centro_custo": {"codigo": "PDV", "nome": "Frente de caixa"},
                    "conta_contabil": {"codigo": "3.1.1", "nome": "Receita de vendas"},
                    "usuario": "OPERADOR01",
                }
            },
        )

        resultado = processar_entrada_sincronizacao()

        evento.refresh_from_db()
        espelho = LancamentoFinanceiroSincronizado.objects.get(lancamento_externo_id="501")
        painel = self.client.get("/empresas/sincronizacao/", {"q": "Venda PDV #501"})
        csv_response = self.client.get("/empresas/sincronizacao/lancamentos-financeiros.csv", {"q": "Venda PDV #501"})
        diagnostico = self.client.get("/empresas/sincronizacao/diagnostico.json").json()

        self.assertEqual(resultado, {"processados": 1, "erros": 0})
        self.assertEqual(evento.status, StatusEventoEntrada.PROCESSADO)
        self.assertEqual(espelho.filial, self.filial)
        self.assertEqual(espelho.valor, Decimal("35.40"))
        self.assertEqual(espelho.conta_contabil, "3.1.1 - Receita de vendas")
        self.assertContains(painel, "Livro financeiro sincronizado para retaguarda")
        self.assertContains(painel, "Venda PDV #501")
        self.assertContains(painel, "R$ 35,40")
        self.assertEqual(csv_response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Venda PDV #501", csv_response.content.decode("utf-8-sig"))
        self.assertEqual(diagnostico["retaguarda"]["lancamentos_financeiros"], 1)
        self.assertEqual(diagnostico["retaguarda"]["entradas_financeiras"], "35.4000000000000")

    def test_entrada_financeira_rejeita_mesmo_id_com_valor_divergente(self):
        primeiro = EventoEntradaSincronizacao.objects.create(
            identificador="df347f6d-a15b-467b-b665-4a8535a52460",
            chave_idempotencia="financeiro:lancamento:loja:700:v1",
            empresa=self.empresa,
            tipo="financeiro.lancamento_registrado",
            payload={"payload": {
                "contrato": "financeiro_lancamento_v1", "lancamento_id": "700", "filial_cnpj": self.filial.cnpj, "tipo": "SAIDA",
                "origem": "PAGAMENTO", "descricao": "Fornecedor", "valor": "10.00", "data": "2026-08-03",
            }},
        )
        processar_entrada_sincronizacao()
        divergente = EventoEntradaSincronizacao.objects.create(
            identificador="4c955c3f-8bd8-4eca-81fd-6ed002c19760",
            chave_idempotencia="financeiro:lancamento:loja:700:v2",
            empresa=self.empresa,
            tipo="financeiro.lancamento_registrado",
            payload={"payload": {
                "contrato": "financeiro_lancamento_v1", "lancamento_id": "700", "filial_cnpj": self.filial.cnpj, "tipo": "SAIDA",
                "origem": "PAGAMENTO", "descricao": "Fornecedor", "valor": "12.00", "data": "2026-08-03",
            }},
        )

        processar_entrada_sincronizacao()

        divergente.refresh_from_db()
        self.assertEqual(divergente.status, StatusEventoEntrada.CONFLITO)
        self.assertIn("tipo ou valor diferente", divergente.ultimo_erro)
        self.assertEqual(LancamentoFinanceiroSincronizado.objects.filter(lancamento_externo_id="700").count(), 1)
        self.assertEqual(primeiro.lancamento_financeiro_sincronizado.valor, Decimal("10.00"))

    def test_lista_empresas_e_filiais(self):
        response = self.client.get("/empresas/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empresas e filiais")
        self.assertContains(response, "Mercado Teste")
        self.assertContains(response, "IBGE 3550308")
        self.assertContains(response, "Conflito: Resolver manualmente")

    def test_busca_json_retorna_filial_para_select2(self):
        response = self.client.get("/empresas/filiais/busca.json", {"q": "Matriz"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["id"], self.filial.id)
        self.assertIn("Mercado Teste - Matriz", payload["results"][0]["text"])

    def test_formularios_exibem_secoes_administrativas(self):
        empresa_response = self.client.get(f"/empresas/{self.empresa.pk}/editar/")
        filial_response = self.client.get(f"/empresas/filiais/{self.filial.pk}/editar/")

        self.assertEqual(empresa_response.status_code, 200)
        self.assertContains(empresa_response, "Identificação")
        self.assertContains(empresa_response, "Contato e visual")
        self.assertContains(empresa_response, "Implantacao e conectividade")
        self.assertContains(empresa_response, "Política de conflito")
        self.assertContains(empresa_response, "Nuvem prevalece para produtos e estoque")
        self.assertContains(empresa_response, "modo local não publica o sistema na internet")
        self.assertContains(empresa_response, "Consulta CNPJ/CEP preparada")
        self.assertContains(empresa_response, "Consultar CNPJ")
        self.assertContains(empresa_response, "data-cadastro-lookup-url")
        self.assertContains(empresa_response, "data-lookup-target")
        self.assertEqual(filial_response.status_code, 200)
        self.assertContains(filial_response, "Loja")
        self.assertContains(filial_response, "Dados fiscais da filial")
        self.assertContains(filial_response, "Necessário para preencher o XML da NFC-e")
        self.assertContains(filial_response, "select2-field")
        self.assertContains(filial_response, "data-cadastro-lookup-feedback")
        self.assertContains(filial_response, "Ver ponto de integração")
        self.assertContains(filial_response, "Diagnóstico JSON")

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
        self.assertEqual(empresa.politica_conflito_sincronizacao, PoliticaConflitoSincronizacao.MANUAL)

    def test_modelo_forca_politica_local_e_pausa_ou_retoma_as_filas(self):
        saida = EventoSincronizacao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo="produto.atualizado",
            objeto_tipo="Produto",
            objeto_id="10",
            chave_idempotencia="produto:10:politica",
            payload={"nome": "Arroz"},
        )
        entrada = EventoEntradaSincronizacao.objects.create(
            identificador="6ef320cd-4638-49f9-b25e-dfd0df2911ab",
            chave_idempotencia="produto:10:entrada:politica",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={"payload": {"nome": "Arroz remoto"}},
        )

        self.empresa.modo_implantacao = ModoImplantacao.LOCAL
        self.empresa.save(update_fields=["modo_implantacao"])
        saida.refresh_from_db()
        entrada.refresh_from_db()
        self.assertFalse(self.empresa.sincronizacao_automatica)
        self.assertEqual(self.empresa.url_sincronizacao, "")
        self.assertEqual(saida.status, StatusSincronizacao.PAUSADO)
        self.assertEqual(entrada.status, StatusEventoEntrada.PAUSADO)
        diagnostico = self.client.get("/empresas/sincronizacao/diagnostico.json").json()
        self.assertEqual(diagnostico["filas"]["saida"]["pausados"], 1)
        self.assertEqual(diagnostico["filas"]["entrada"]["pausados"], 1)
        self.client.post(f"/empresas/sincronizacao/{saida.pk}/reprocessar/")
        self.client.post(f"/empresas/sincronizacao/entrada/{entrada.pk}/reprocessar/")
        saida.refresh_from_db()
        entrada.refresh_from_db()
        self.assertEqual(saida.status, StatusSincronizacao.PAUSADO)
        self.assertEqual(entrada.status, StatusEventoEntrada.PAUSADO)

        enviados = []
        self.assertEqual(processar_fila(enviar=lambda evento: enviados.append(evento.pk)), {"enviados": 0, "erros": 0})
        self.assertEqual(processar_entrada_sincronizacao(), {"processados": 0, "erros": 0})
        self.assertEqual(enviados, [])

        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = "https://nuvem.exemplo.com/api/"
        self.empresa.save(update_fields=["modo_implantacao", "sincronizacao_automatica", "url_sincronizacao"])
        saida.refresh_from_db()
        entrada.refresh_from_db()
        self.assertTrue(self.empresa.sincronizacao_operacional_habilitada)
        self.assertEqual(saida.status, StatusSincronizacao.PENDENTE)
        self.assertEqual(entrada.status, StatusEventoEntrada.RECEBIDO)
        self.assertEqual(saida.ultimo_erro, "")
        self.assertEqual(entrada.ultimo_erro, "")
    def test_formulario_empresa_salva_politica_de_conflito(self):
        form = EmpresaForm(
            data={
                "razao_social": "Mercado Sync Ltda",
                "nome_fantasia": "Mercado Sync",
                "cnpj": "33.333.333/0001-33",
                "modo_implantacao": ModoImplantacao.HIBRIDO,
                "sincronizacao_automatica": "on",
                "url_sincronizacao": "https://nuvem.exemplo.com/api/",
                "politica_conflito_sincronizacao": PoliticaConflitoSincronizacao.REMOTO_PRODUTOS_ESTOQUE,
                "is_active": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        empresa = form.save()
        self.assertEqual(empresa.politica_conflito_sincronizacao, PoliticaConflitoSincronizacao.REMOTO_PRODUTOS_ESTOQUE)

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
        self.empresa.modo_implantacao = ModoImplantacao.LOCAL
        self.empresa.save(update_fields=["modo_implantacao"])

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

    def test_movimentacao_local_nao_publica_saldo_automaticamente(self):
        self.empresa.modo_implantacao = ModoImplantacao.LOCAL
        self.empresa.save(update_fields=["modo_implantacao"])
        categoria = Categoria.objects.create(nome="Mercearia local")
        produto = Produto.objects.create(
            codigo_barras="7891000000001",
            nome="Produto local",
            categoria=categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )

        movimentar_estoque(
            produto=produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.ENTRADA,
            quantidade=Decimal("5.000"),
            usuario=self.user,
            referencia="entrada:local:1",
        )

        self.assertFalse(EventoSincronizacao.objects.exists())

    def test_movimentacao_hibrida_publica_saldo_com_idempotencia(self):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = "https://nuvem.exemplo.com/api/"
        self.empresa.save()
        categoria = Categoria.objects.create(nome="Mercearia hibrida")
        produto = Produto.objects.create(
            codigo_barras="7891000000002",
            codigo_interno="SYNC-002",
            nome="Produto hibrido",
            categoria=categoria,
            preco_custo="4.00",
            preco_venda="6.00",
        )

        CodigoBarrasProduto.objects.create(
            produto=produto,
            codigo="17891000000029",
            tipo="CAIXA",
            fator_conversao=Decimal("12.000"),
        )

        movimentacao = movimentar_estoque(
            produto=produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.ENTRADA,
            quantidade=Decimal("7.500"),
            usuario=self.user,
            motivo="Recebimento local",
            referencia="entrada:compra:10",
            custo_unitario=Decimal("4.50"),
        )

        evento_produto = EventoSincronizacao.objects.get(tipo="produto.atualizado")
        evento = EventoSincronizacao.objects.get(tipo="estoque.saldo_atualizado")
        self.assertEqual(EventoSincronizacao.objects.count(), 2)
        self.assertEqual(evento_produto.payload["contrato"], "produto_snapshot_v1")
        self.assertEqual(evento_produto.payload["codigo_barras"], produto.codigo_barras)
        self.assertEqual(evento_produto.payload["preco_venda"], "6.00")
        self.assertEqual(evento_produto.payload["categoria"], {"nome": "Mercearia hibrida"})
        self.assertEqual(
            evento_produto.payload["categoria_hierarquia"],
            [{"nome": "Mercearia hibrida", "nivel": "GRUPO"}],
        )
        self.assertEqual(evento_produto.payload["tipo_produto"], "MERCADORIA")
        self.assertEqual(evento_produto.payload["unidade_compra"], "UN")
        self.assertEqual(evento_produto.payload["fator_conversao_compra"], "1")
        self.assertEqual(evento_produto.payload["codigos_adicionais"][0]["codigo"], "17891000000029")
        self.assertEqual(evento_produto.payload["codigos_adicionais"][0]["fator_conversao"], "12.000")
        self.assertEqual(evento.filial, self.filial)
        self.assertEqual(evento.objeto_tipo, "Estoque")
        self.assertEqual(
            evento.chave_idempotencia,
            f"estoque:{self.filial.pk}:{produto.pk}:movimentacao:{movimentacao.pk}",
        )
        self.assertEqual(evento.payload["contrato"], "estoque_saldo_v1")
        self.assertEqual(evento.payload["codigo_barras"], produto.codigo_barras)
        self.assertEqual(evento.payload["filial_cnpj"], self.filial.cnpj)
        self.assertEqual(evento.payload["quantidade_atual"], "7.500")
        self.assertEqual(evento.payload["quantidade_reservada"], "0.000")
        self.assertEqual(evento.payload["custo_medio"], "4.500000")
        self.assertEqual(evento.payload["movimentacao"]["tipo"], TipoMovimentacaoEstoque.ENTRADA)
        self.assertEqual(evento.payload["movimentacao"]["referencia"], "entrada:compra:10")

        produto.preco_venda = Decimal("6.50")
        produto.preco_promocional = Decimal("5.90")
        produto.exige_lote = True
        produto.save()

        revisoes = EventoSincronizacao.objects.filter(tipo="produto.atualizado").order_by("pk")
        self.assertEqual(revisoes.count(), 2)
        self.assertEqual(revisoes.last().payload["preco_venda"], "6.50")
        self.assertEqual(revisoes.last().payload["preco_promocional"], "5.90")
        self.assertTrue(revisoes.last().payload["exige_lote"])
        self.assertEqual(EventoSincronizacao.objects.filter(tipo="estoque.saldo_atualizado").count(), 1)

    def test_movimentacao_recebida_da_nuvem_nao_gera_evento_de_retorno(self):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = "https://nuvem.exemplo.com/api/"
        self.empresa.save()
        categoria = Categoria.objects.create(nome="Mercearia remota")
        produto = Produto.objects.create(
            codigo_barras="7891000000003",
            nome="Produto remoto",
            categoria=categoria,
            preco_custo="5.00",
            preco_venda="8.00",
        )
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("9.000"))

        MovimentacaoEstoque.objects.create(
            produto=produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.AJUSTE,
            quantidade=Decimal("9.000"),
            referencia="sync:11111111-1111-1111-1111-111111111111",
        )

        self.assertFalse(EventoSincronizacao.objects.exists())

    def test_produto_recebido_da_nuvem_nao_publica_snapshot_de_retorno(self):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = "https://nuvem.exemplo.com/api/"
        self.empresa.save()
        categoria = Categoria.objects.create(nome="Mercearia sem eco")
        produto = Produto.objects.create(
            codigo_barras="7891000000004",
            nome="Produto antes da nuvem",
            categoria=categoria,
            preco_custo="5.00",
            preco_venda="8.00",
        )
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("2.000"))
        EventoSincronizacao.objects.all().delete()
        evento_entrada = EventoEntradaSincronizacao.objects.create(
            identificador="22222222-2222-2222-2222-222222222222",
            chave_idempotencia="produto:sem-eco:1",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={
                "payload": {
                    "codigo_barras": produto.codigo_barras,
                    "nome": "Produto atualizado pela nuvem",
                    "categoria": {"nome": categoria.nome},
                    "preco_custo": "5.50",
                    "preco_venda": "9.00",
                    "preco_promocional": "8.50",
                    "estoque_minimo": "1.000",
                    "exige_lote": True,
                    "vendido_no_pdv": True,
                }
            },
        )

        processar_entrada_sincronizacao()

        evento_entrada.refresh_from_db()
        produto.refresh_from_db()
        self.assertEqual(evento_entrada.status, StatusEventoEntrada.PROCESSADO)
        self.assertEqual(produto.nome, "Produto atualizado pela nuvem")
        self.assertEqual(produto.preco_promocional, Decimal("8.50"))
        self.assertTrue(produto.exige_lote)
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
        self.assertContains(detalhe, "Evento de saída produto.atualizado")
        self.assertContains(detalhe, "Servidor indisponivel")
        self.assertContains(detalhe, "Payload enviado")

        resposta = self.client.post(f"/empresas/sincronizacao/{evento.pk}/reprocessar/", follow=True)
        evento.refresh_from_db()
        self.assertRedirects(resposta, "/empresas/sincronizacao/")
        self.assertEqual(evento.status, StatusSincronizacao.PENDENTE)
        log = LogAuditoria.objects.get(acao="REPROCESSA_SINCRONIZACAO_SAIDA", objeto_id=str(evento.pk))
        self.assertEqual(log.usuario, self.user)
        self.assertEqual(log.objeto_tipo, "EventoSincronizacao")
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
        self.assertIn("2 enviado(s), 1 erro(s) de saída", saida_stdout.getvalue())

    def test_comando_gera_carga_inicial_por_filial_com_idempotencia(self):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = "https://nuvem.exemplo.com/api/"
        self.empresa.save()
        filial_dois = Filial.objects.create(
            empresa=self.empresa,
            nome="Filial carga",
            cnpj="44.444.444/0002-25",
        )
        categoria = Categoria.objects.create(nome="Carga inicial")
        produto_a = Produto.objects.create(
            codigo_barras="7891000000010",
            nome="Produto carga A",
            categoria=categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        produto_b = Produto.objects.create(
            codigo_barras="7891000000011",
            nome="Produto carga B",
            categoria=categoria,
            preco_custo="4.00",
            preco_venda="6.00",
        )
        Estoque.objects.create(produto=produto_a, filial=self.filial, quantidade_atual=Decimal("99.000"))
        Estoque.objects.create(produto=produto_a, filial=filial_dois, quantidade_atual=Decimal("5.000"))
        Estoque.objects.create(
            produto=produto_b,
            filial=filial_dois,
            quantidade_atual=Decimal("8.000"),
            quantidade_reservada=Decimal("1.000"),
        )
        primeira_saida = StringIO()
        segunda_saida = StringIO()

        call_command(
            "gerar_snapshot_sincronizacao",
            empresa=self.empresa.pk,
            filial=filial_dois.pk,
            stdout=primeira_saida,
        )
        call_command(
            "gerar_snapshot_sincronizacao",
            empresa=self.empresa.pk,
            filial=filial_dois.pk,
            stdout=segunda_saida,
        )

        self.assertEqual(EventoSincronizacao.objects.filter(tipo="produto.atualizado").count(), 2)
        saldos = EventoSincronizacao.objects.filter(tipo="estoque.saldo_atualizado")
        self.assertEqual(saldos.count(), 2)
        self.assertEqual(set(saldos.values_list("filial_id", flat=True)), {filial_dois.pk})
        self.assertEqual(
            {evento.payload["quantidade_atual"] for evento in saldos},
            {"5.000", "8.000"},
        )
        self.assertIn("2 produto(s) novo(s)", primeira_saida.getvalue())
        self.assertIn("2 saldo(s) novo(s)", primeira_saida.getvalue())
        self.assertIn("0 produto(s) novo(s)", segunda_saida.getvalue())
        self.assertIn("0 saldo(s) novo(s)", segunda_saida.getvalue())

    def test_comando_carga_inicial_bloqueia_empresa_local(self):
        self.empresa.modo_implantacao = ModoImplantacao.LOCAL
        self.empresa.save(update_fields=["modo_implantacao"])
        with self.assertRaisesMessage(CommandError, "modo hibrido/agente"):
            call_command("gerar_snapshot_sincronizacao", empresa=self.empresa.pk)

    def test_painel_gera_carga_inicial_por_filial_com_auditoria(self):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = "https://nuvem.exemplo.com/api/"
        self.empresa.save()
        categoria = Categoria.objects.create(nome="Carga pelo painel")
        produto = Produto.objects.create(
            codigo_barras="7891000000020",
            nome="Produto carga painel",
            categoria=categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("12.000"))

        response = self.client.post(
            "/empresas/sincronizacao/carga-inicial/",
            {"empresa": self.empresa.pk, "filial": self.filial.pk, "limite": 100},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 produto(s) e 1 saldo(s) novo(s)")
        self.assertEqual(EventoSincronizacao.objects.filter(tipo="produto.atualizado").count(), 1)
        self.assertEqual(EventoSincronizacao.objects.filter(tipo="estoque.saldo_atualizado").count(), 1)
        log = LogAuditoria.objects.get(acao="GERA_CARGA_INICIAL_SINCRONIZACAO")
        self.assertEqual(log.usuario, self.user)
        self.assertEqual(log.objeto_tipo, "Filial")
        self.assertEqual(log.objeto_id, str(self.filial.pk))

        response = self.client.post(
            "/empresas/sincronizacao/carga-inicial/",
            {"empresa": self.empresa.pk, "filial": self.filial.pk, "limite": 100},
            follow=True,
        )
        self.assertContains(response, "0 produto(s) e 0 saldo(s) novo(s)")
        self.assertEqual(EventoSincronizacao.objects.count(), 2)

    def test_painel_carga_inicial_bloqueia_empresa_local(self):
        self.empresa.modo_implantacao = ModoImplantacao.LOCAL
        self.empresa.save(update_fields=["modo_implantacao"])
        response = self.client.post(
            "/empresas/sincronizacao/carga-inicial/",
            {"empresa": self.empresa.pk, "limite": 100},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "modo hibrido/agente")
        self.assertFalse(EventoSincronizacao.objects.exists())
        self.assertFalse(LogAuditoria.objects.filter(acao="GERA_CARGA_INICIAL_SINCRONIZACAO").exists())

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

    @override_settings(SINCRONIZACAO_API_TOKEN="token-seguro", SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=True)
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

    @override_settings(
        SINCRONIZACAO_API_TOKEN="",
        SINCRONIZACAO_TOKENS_EMPRESA={
            "44.444.444/0001-44": "token-empresa-a",
            "55.555.555/0001-55": "token-empresa-b",
        },
        SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=False,
    )
    def test_receptor_isola_credencial_por_cnpj(self):
        dados = {
            "id": "a8e6d892-2f72-40c8-9a63-aa2086e0d881",
            "tipo": "venda.finalizada",
            "empresa_cnpj": self.empresa.cnpj,
            "payload": {"total": "25.00"},
        }
        url = "/empresas/api/sincronizacao/eventos/"
        cabecalhos = {"HTTP_IDEMPOTENCY_KEY": "venda:credencial:empresa"}

        token_de_outra_empresa = self.client.post(
            url,
            data=dados,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer token-empresa-b",
            **cabecalhos,
        )
        token_correto = self.client.post(
            url,
            data=dados,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer token-empresa-a",
            **cabecalhos,
        )

        self.assertEqual(token_de_outra_empresa.status_code, 401)
        self.assertEqual(token_correto.status_code, 202)
        self.assertEqual(EventoEntradaSincronizacao.objects.count(), 1)

    @override_settings(
        SINCRONIZACAO_API_TOKEN="",
        SINCRONIZACAO_TOKENS_EMPRESA={
            "44.444.444/0001-44": {
                "atual": "token-empresa-novo",
                "anteriores": ["token-empresa-anterior"],
            },
        },
        SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=False,
    )
    def test_receptor_aceita_token_anterior_durante_rotacao(self):
        url = "/empresas/api/sincronizacao/eventos/"
        for indice, token in enumerate(
            ["token-empresa-novo", "token-empresa-anterior"],
            start=1,
        ):
            response = self.client.post(
                url,
                data={
                    "id": f"a8e6d892-2f72-40c8-9a63-aa2086e0d88{indice}",
                    "tipo": "venda.finalizada",
                    "empresa_cnpj": self.empresa.cnpj,
                    "payload": {"total": "25.00"},
                },
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
                HTTP_IDEMPOTENCY_KEY=f"venda:rotacao:{indice}",
            )
            self.assertEqual(response.status_code, 202)

        recusado = self.client.post(
            url,
            data={
                "id": "a8e6d892-2f72-40c8-9a63-aa2086e0d889",
                "tipo": "venda.finalizada",
                "empresa_cnpj": self.empresa.cnpj,
                "payload": {"total": "25.00"},
            },
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer token-desconhecido",
            HTTP_IDEMPOTENCY_KEY="venda:rotacao:recusada",
        )
        self.assertEqual(recusado.status_code, 401)
        self.assertEqual(EventoEntradaSincronizacao.objects.count(), 2)

    @override_settings(
        SINCRONIZACAO_API_TOKEN="",
        SINCRONIZACAO_TOKENS_EMPRESA={"44.444.444/0001-44": "token-empresa-a"},
        SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=False,
        SINCRONIZACAO_MAX_EVENTO_BYTES=180,
    )
    def test_receptor_rejeita_evento_acima_do_limite(self):
        response = self.client.post(
            "/empresas/api/sincronizacao/eventos/",
            data={
                "id": "b5c33d39-ed8c-493e-954f-e7a8ee44e227",
                "tipo": "produto.atualizado",
                "empresa_cnpj": self.empresa.cnpj,
                "payload": {"descricao": "x" * 500},
            },
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer token-empresa-a",
            HTTP_IDEMPOTENCY_KEY="produto:grande:1",
        )

        self.assertEqual(response.status_code, 413)
        self.assertFalse(EventoEntradaSincronizacao.objects.exists())

    @override_settings(
        SINCRONIZACAO_API_TOKEN="",
        SINCRONIZACAO_TOKENS_EMPRESA={
            "44444444000144": {
                "atual": "token-empresa-a",
                "anteriores": ["token-empresa-antigo"],
            },
        },
        SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=False,
    )
    def test_emissor_usa_credencial_da_propria_empresa(self):
        evento = self._evento_hibrido("venda:credencial:saida")

        class Resposta:
            status = 202

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with patch(
            "apps.empresas.services_sincronizacao.urlopen",
            return_value=Resposta(),
        ) as chamada:
            enviar_evento_http(evento)

        requisicao = chamada.call_args.args[0]
        self.assertEqual(
            requisicao.get_header("Authorization"),
            "Bearer token-empresa-a",
        )

    @override_settings(SINCRONIZACAO_API_TOKEN="token-seguro", SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=True)
    def test_receptor_bloqueia_novo_evento_local_e_confirma_duplicado_anterior(self):
        dados = {
            "id": "f73edb66-bba6-4ca9-a8dd-bf34ab595c85",
            "tipo": "venda.finalizada",
            "empresa_cnpj": self.empresa.cnpj,
            "payload": {"total": "25.00"},
        }
        cabecalhos = {
            "HTTP_AUTHORIZATION": "Bearer token-seguro",
            "HTTP_IDEMPOTENCY_KEY": "venda:local:politica",
        }
        aceita = self.client.post(
            "/empresas/api/sincronizacao/eventos/",
            data=dados,
            content_type="application/json",
            **cabecalhos,
        )
        self.empresa.modo_implantacao = ModoImplantacao.LOCAL
        self.empresa.save(update_fields=["modo_implantacao"])
        duplicado = self.client.post(
            "/empresas/api/sincronizacao/eventos/",
            data=dados,
            content_type="application/json",
            **cabecalhos,
        )
        dados["id"] = "63585dab-0f1e-4ef1-9aef-9cc64dd5e9c0"
        cabecalhos["HTTP_IDEMPOTENCY_KEY"] = "venda:local:nova"
        bloqueado = self.client.post(
            "/empresas/api/sincronizacao/eventos/",
            data=dados,
            content_type="application/json",
            **cabecalhos,
        )

        self.assertEqual(aceita.status_code, 202)
        self.assertEqual(duplicado.status_code, 200)
        self.assertEqual(duplicado.json()["status"], "duplicado")
        self.assertEqual(bloqueado.status_code, 409)
        self.assertIn("não permite sincronização operacional", bloqueado.json()["mensagem"])
        self.assertEqual(EventoEntradaSincronizacao.objects.count(), 1)
    @override_settings(SINCRONIZACAO_API_TOKEN="token-seguro", SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=True)
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
                    "categoria_hierarquia": [
                        {"nome": "Alimentos", "nivel": "DEPARTAMENTO"},
                        {"nome": "Mercearia", "nivel": "SECAO"},
                    ],
                    "tipo_produto": "INSUMO",
                    "marca": {"nome": "Casa Boa"},
                    "unidade": "UN",
                    "unidade_compra": "CX",
                    "fator_conversao_compra": "12.000",
                    "peso_liquido": "5.500",
                    "peso_bruto": "5.800",
                    "codigos_adicionais": [
                        {
                            "codigo": "17899000000018",
                            "tipo": "CAIXA",
                            "fator_conversao": "12.000",
                            "permite_venda": True,
                            "is_active": True,
                        }
                    ],
                    "preco_custo": "3.20",
                    "preco_venda": "5.49",
                    "estoque_minimo": "6",
                    "vendido_no_pdv": True,
                    "vendido_no_marketplace": True,
                    "informacao_nutricional": {
                        "base_calculo": "100G",
                        "porcao_quantidade": "80.00",
                        "porcao_unidade": "g",
                        "valor_energetico_kcal": "286.00",
                        "carboidratos_g": "58.00",
                        "proteinas_g": "10.00",
                        "ingredientes": "Farinha de trigo.",
                        "gluten": "CONTEM",
                    },
                    "produtos_similares": [],
                    "ncm": "19021900",
                    "origem_mercadoria": "0",
                    "cst_icms": "00",
                    "aliquota_icms": "18",
                    "reducao_base_icms": "12.50",
                    "aliquota_fcp": "2.00",
                    "codigo_beneficio_fiscal": "GO123456",
                    "cst_pis": "01",
                    "aliquota_pis": "1.6500",
                    "cst_cofins": "01",
                    "aliquota_cofins": "7.6000",
                    "cst_ipi": "50",
                    "codigo_enquadramento_ipi": "999",
                    "aliquota_ipi": "5.0000",
                    "cst_ibs_cbs": "000",
                    "classificacao_tributaria_ibs_cbs": "000001",
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
        self.assertEqual(produto.categoria.caminho_completo, "Alimentos > Mercearia")
        self.assertEqual(produto.tipo_produto, "INSUMO")
        self.assertEqual(produto.marca.nome, "Casa Boa")
        self.assertEqual(produto.preco_venda, Decimal("5.49"))
        self.assertTrue(produto.vendido_no_marketplace)
        self.assertEqual(produto.unidade_compra, "CX")
        self.assertEqual(produto.fator_conversao_compra, Decimal("12.000"))
        self.assertEqual(produto.peso_liquido, Decimal("5.500"))
        self.assertEqual(produto.codigos_adicionais.get().codigo, "17899000000018")
        self.assertEqual(produto.informacao_nutricional.porcao_quantidade, Decimal("80.00"))
        self.assertEqual(produto.informacao_nutricional.gluten, "CONTEM")
        self.assertEqual(produto.reducao_base_icms, Decimal("12.50"))
        self.assertEqual(produto.aliquota_fcp, Decimal("2.00"))
        self.assertEqual(produto.codigo_beneficio_fiscal, "GO123456")
        self.assertEqual(produto.cst_pis, "01")
        self.assertEqual(produto.aliquota_pis, Decimal("1.6500"))
        self.assertEqual(produto.cst_cofins, "01")
        self.assertEqual(produto.aliquota_cofins, Decimal("7.6000"))
        self.assertEqual(produto.cst_ipi, "50")
        self.assertEqual(produto.codigo_enquadramento_ipi, "999")
        self.assertEqual(produto.aliquota_ipi, Decimal("5.0000"))
        self.assertEqual(produto.cst_ibs_cbs, "000")
        self.assertEqual(produto.classificacao_tributaria_ibs_cbs, "000001")
        self.assertFalse(produto.produtos_similares.exists())

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
                    "custo_medio": "8.750000",
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
        self.assertEqual(estoque.custo_medio, Decimal("8.750000"))
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
        self.assertIn("Produto do saldo de estoque não encontrado", evento.ultimo_erro)

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
        diagnostico_response = self.client.get("/empresas/sincronizacao/diagnostico.json")
        diagnostico = diagnostico_response.json()

        self.assertContains(busca, "CAIXA FILTRADO")
        self.assertNotContains(busca, "Produto sem categoria")
        self.assertContains(busca_fiscal, "Documentos fiscais sincronizados")
        self.assertContains(busca_fiscal, "nfce-200")
        self.assertContains(busca_fiscal, "CHAVE-FISCAL-FILTRADA")
        self.assertContains(busca_fiscal, "Fiscal CSV")
        self.assertContains(busca_fiscal, "Saida CSV")
        self.assertContains(busca_fiscal, "Entrada CSV")
        self.assertContains(busca_fiscal, "Diagnóstico JSON")
        self.assertContains(busca_fiscal, f"/empresas/sincronizacao/documentos-fiscais/{documento.pk}/")
        self.assertContains(detalhe_fiscal, "Documento fiscal sincronizado nfce-200")
        self.assertContains(detalhe_fiscal, "CHAVE-FISCAL-FILTRADA")
        self.assertContains(detalhe_fiscal, "PROTOCOLO-FILTRADO")
        self.assertContains(detalhe_fiscal, "Payload recebido")
        self.assertContains(erro, "Produto sem categoria")
        self.assertContains(erro, "Status entrada")
        self.assertContains(erro, "Agendamento no servidor local")
        self.assertContains(erro, "register_sync_task.ps1")
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
        self.assertEqual(diagnostico_response.status_code, 200)
        self.assertEqual(diagnostico["status"], "ok")
        self.assertEqual(diagnostico["filas"]["saida"]["erros"], 1)
        self.assertEqual(diagnostico["filas"]["entrada"]["erros"], 1)
        self.assertGreaterEqual(diagnostico["retaguarda"]["vendas"], 2)
        self.assertGreaterEqual(diagnostico["retaguarda"]["documentos_fiscais"], 1)
        self.assertGreaterEqual(diagnostico["empresas"]["politica_manual"], 1)
        self.assertEqual(diagnostico["empresas"]["politica_local_produtos_estoque"], 0)
        self.assertIn("MANUAL", diagnostico["empresas"]["politicas_conflito"])
        self.assertIn("Politica manual", erro.content.decode("utf-8"))
        self.assertIn("Nuvem produtos/estoque", erro.content.decode("utf-8"))
        self.assertIn("Loja produtos/estoque", erro.content.decode("utf-8"))
        self.assertIn("processar_sincronizacao_completa", diagnostico["operacao"]["comando"])
        self.assertIn("--limite-saida 50", diagnostico["operacao"]["comando"])
        self.assertNotIn("?", diagnostico["operacao"]["comando"])
        self.assertFalse(diagnostico["operacao"]["pronto"])
        self.assertTrue(diagnostico["operacao"]["alertas"])
        self.assertEqual(diagnostico["prontidao"]["contrato"], "sync_readiness_v1")
        self.assertContains(erro, "Prontidão da sincronização")

    def test_diagnostico_sincronizacao_exibe_idade_e_tentativas_esgotadas(self):
        saida = EventoSincronizacao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo="produto.atualizado",
            objeto_tipo="Produto",
            objeto_id="987",
            chave_idempotencia="produto:saida:esgotado",
            payload={"codigo_barras": "789987"},
            status=StatusSincronizacao.ERRO,
            tentativas=settings.SINCRONIZACAO_MAX_TENTATIVAS,
            ultimo_erro="Timeout permanente",
        )
        entrada = EventoEntradaSincronizacao.objects.create(
            identificador="5c1b2d0f-5a0d-4b2f-9b3c-5a4f93d01a22",
            chave_idempotencia="produto:entrada:antigo",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={"payload": {"nome": "Produto antigo"}},
            status=StatusEventoEntrada.CONFLITO,
            ultimo_erro="Conflito antigo",
        )
        EventoSincronizacao.objects.filter(pk=saida.pk).update(criado_em=timezone.now() - timedelta(minutes=42))
        EventoEntradaSincronizacao.objects.filter(pk=entrada.pk).update(recebido_em=timezone.now() - timedelta(minutes=31))

        painel = self.client.get("/empresas/sincronizacao/")
        diagnostico_response = self.client.get("/empresas/sincronizacao/diagnostico.json")
        diagnostico = diagnostico_response.json()

        self.assertEqual(diagnostico_response.status_code, 200)
        self.assertEqual(diagnostico["filas"]["saida"]["esgotados"], 1)
        self.assertGreaterEqual(diagnostico["filas"]["saida"]["idade_mais_antigo_minutos"], 41)
        self.assertGreaterEqual(diagnostico["filas"]["entrada"]["idade_mais_antigo_minutos"], 30)
        self.assertIn("esgotaram as tentativas automaticas", " ".join(diagnostico["operacao"]["alertas"]))
        self.assertContains(painel, "Fila saída mais antiga")
        self.assertContains(painel, "Saída esgotada")
        self.assertContains(painel, "Status operacional da sincronizacao")
        self.assertContains(painel, "Politica manual")
        self.assertContains(painel, "Nuvem produtos/estoque")
        self.assertContains(painel, "sync_readiness_v1")

    @override_settings(
        SINCRONIZACAO_API_TOKEN="",
        SINCRONIZACAO_TOKENS_EMPRESA={},
        SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=False,
    )
    def test_prontidao_sincronizacao_bloqueia_hibrido_sem_configuracao(self):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = ""
        self.empresa.save(update_fields=["modo_implantacao", "sincronizacao_automatica", "url_sincronizacao"])

        painel = self.client.get("/empresas/sincronizacao/")
        diagnostico = self.client.get("/empresas/sincronizacao/diagnostico.json").json()

        self.assertEqual(diagnostico["prontidao"]["contrato"], "sync_readiness_v1")
        self.assertEqual(diagnostico["prontidao"]["status"], "Bloqueada")
        self.assertEqual(diagnostico["prontidao"]["empresas"]["hibrido"], 1)
        self.assertIn("credencial individual", " ".join(diagnostico["prontidao"]["bloqueios"]))
        self.assertEqual(diagnostico["prontidao"]["credenciais"]["sem_credencial"], 1)
        self.assertContains(painel, "Prontidão da sincronização: Bloqueada")

    @override_settings(
        SINCRONIZACAO_API_TOKEN="",
        SINCRONIZACAO_TOKENS_EMPRESA={
            "44.444.444/0001-44": {
                "atual": "token-empresa-novo",
                "anteriores": ["token-empresa-anterior"],
            },
        },
        SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=False,
    )
    def test_prontidao_sinaliza_credencial_em_rotacao(self):
        self.empresa.modo_implantacao = ModoImplantacao.HIBRIDO
        self.empresa.sincronizacao_automatica = True
        self.empresa.url_sincronizacao = "https://nuvem.exemplo/api/"
        self.empresa.save(
            update_fields=[
                "modo_implantacao",
                "sincronizacao_automatica",
                "url_sincronizacao",
            ]
        )

        diagnostico = self.client.get(
            "/empresas/sincronizacao/diagnostico.json"
        ).json()["prontidao"]

        self.assertEqual(diagnostico["status"], "Atencao")
        self.assertEqual(diagnostico["credenciais"]["individuais"], 1)
        self.assertEqual(diagnostico["credenciais"]["em_rotacao"], 1)
        self.assertIn("rotacao de credencial", " ".join(diagnostico["recomendacoes"]))

    def test_politica_de_conflito_aceita_remoto_para_produto_e_audita_resolucao(self):
        self.empresa.politica_conflito_sincronizacao = PoliticaConflitoSincronizacao.REMOTO_PRODUTOS_ESTOQUE
        self.empresa.save(update_fields=["politica_conflito_sincronizacao"])
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(
            nome="Arroz Local",
            codigo_barras="7890001112223",
            categoria=categoria,
            preco_custo=Decimal("10.00"),
            preco_venda=Decimal("15.00"),
        )
        Produto.objects.filter(pk=produto.pk).update(updated_at=timezone.now())
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="ba5d3849-d8ed-4a59-9d9e-230d10309fed",
            chave_idempotencia="produto:remoto:prevalece",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={
                "criado_em": (timezone.now() - timedelta(days=1)).isoformat(),
                "payload": {
                    "codigo_barras": "7890001112223",
                    "nome": "Arroz Remoto",
                    "categoria": {"nome": "Mercearia"},
                    "preco_custo": "11.00",
                    "preco_venda": "17.50",
                    "vendido_no_pdv": True,
                },
            },
        )

        resultado = processar_entrada_sincronizacao()

        evento.refresh_from_db()
        produto.refresh_from_db()
        self.assertEqual(resultado, {"processados": 1, "erros": 0})
        self.assertEqual(evento.status, StatusEventoEntrada.PROCESSADO)
        self.assertIn("nuvem prevalece", evento.resolucao_conflito)
        self.assertIsNotNone(evento.resolvido_em)
        self.assertEqual(produto.nome, "Arroz Remoto")
        self.assertEqual(produto.preco_venda, Decimal("17.50"))

    def test_politica_de_conflito_preserva_produto_local_mais_recente(self):
        self.empresa.politica_conflito_sincronizacao = PoliticaConflitoSincronizacao.LOCAL_PRODUTOS_ESTOQUE
        self.empresa.save(update_fields=["politica_conflito_sincronizacao"])
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(
            nome="Feijao Local",
            codigo_barras="7890001113336",
            categoria=categoria,
            preco_custo=Decimal("8.00"),
            preco_venda=Decimal("12.00"),
        )
        Produto.objects.filter(pk=produto.pk).update(updated_at=timezone.now())
        evento = EventoEntradaSincronizacao.objects.create(
            identificador="e1b53c66-ef05-4d0c-b05a-726cfef93f51",
            chave_idempotencia="produto:local:prevalece",
            empresa=self.empresa,
            tipo="produto.atualizado",
            payload={
                "criado_em": (timezone.now() - timedelta(days=1)).isoformat(),
                "payload": {
                    "codigo_barras": "7890001113336",
                    "nome": "Feijao Remoto",
                    "categoria": {"nome": "Mercearia"},
                    "preco_custo": "9.00",
                    "preco_venda": "14.50",
                    "vendido_no_pdv": True,
                },
            },
        )

        resultado = processar_entrada_sincronizacao()

        evento.refresh_from_db()
        produto.refresh_from_db()
        self.assertEqual(resultado, {"processados": 1, "erros": 0})
        self.assertEqual(evento.status, StatusEventoEntrada.PROCESSADO)
        self.assertEqual(evento.ultimo_erro, "")
        self.assertIn("loja prevalece", evento.resolucao_conflito)
        self.assertIn("evento remoto descartado", evento.resolucao_conflito)
        self.assertIsNotNone(evento.resolvido_em)
        self.assertIsNotNone(evento.processado_em)
        self.assertEqual(produto.nome, "Feijao Local")
        self.assertEqual(produto.preco_venda, Decimal("12.00"))

    def test_processador_de_entrada_marca_conflito_para_venda_com_total_diferente(self):
        self.empresa.politica_conflito_sincronizacao = PoliticaConflitoSincronizacao.LOCAL_PRODUTOS_ESTOQUE
        self.empresa.save(update_fields=["politica_conflito_sincronizacao"])
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
        self.assertContains(detalhe, "Política de conflito")
        self.assertContains(detalhe, "Resolver manualmente")
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
        log = LogAuditoria.objects.get(acao="REPROCESSA_SINCRONIZACAO_ENTRADA", objeto_id=str(evento.pk))
        self.assertEqual(log.usuario, self.user)
        self.assertEqual(log.objeto_tipo, "EventoEntradaSincronizacao")

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
        self.assertContains(detalhe, "Conflito aguardando decisão")
        self.assertContains(detalhe, "Venda e fiscal permanecem manuais por segurança")
        self.assertContains(detalhe, "Política da empresa")
        self.assertContains(vazio, "Informe a decisao tomada")
        self.assertEqual(evento.status, StatusEventoEntrada.RESOLVIDO)
        self.assertEqual(evento.resolvido_por, self.user)
        self.assertIsNotNone(evento.resolvido_em)
        self.assertIn("manter documento local", evento.resolucao_conflito)
        self.assertContains(resolvido, "Resolvido manualmente")
        self.assertContains(resolvido, "manter documento local")
        self.assertContains(painel, "Conflitos resolvidos")
        log = LogAuditoria.objects.get(acao="RESOLVE_CONFLITO_SINCRONIZACAO", objeto_id=str(evento.pk))
        self.assertEqual(log.usuario, self.user)
        self.assertIn("manter documento local", log.descricao)

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
                "nome": "Loja inválida",
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
        self.assertContains(response, "Informe o código IBGE com 7 digitos.")
        self.assertFalse(Filial.objects.filter(nome="Loja inválida").exists())

    def test_endpoint_consulta_cadastro_prepara_integracao_externa(self):
        response = self.client.get("/empresas/consulta-cadastro.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "integration_pending")
        self.assertEqual(payload["contrato"], "cadastro_lookup_v1")
        self.assertIn("codigo_municipio_ibge", payload["campos_previstos"])


    def test_endpoint_consulta_cadastro_diagnostico_mostra_modo_local_e_base(self):
        response = self.client.get("/empresas/consulta-cadastro/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["contrato"], "cadastro_lookup_v1")
        self.assertEqual(payload["status"], "ready_with_local_fallback")
        self.assertEqual(payload["provedores"]["modo_operacao"], "local_offline")
        self.assertFalse(payload["provedores"]["cnpj_configurado"])
        self.assertFalse(payload["provedores"]["cep_configurado"])
        self.assertTrue(payload["fallback_local"])
        self.assertEqual(payload["prontidao"]["contrato"], "cadastro_lookup_readiness_v1")
        self.assertEqual(payload["prontidao"]["status"], "local_fallback_only")
        self.assertEqual(payload["prontidao"]["provedores_configurados"], 0)
        self.assertTrue(payload["prontidao"]["fallback_local_disponivel"])
        self.assertGreaterEqual(payload["base_local"]["empresas_com_cnpj"], 1)
        self.assertGreaterEqual(payload["base_local"]["filiais_com_cnpj"], 1)
        self.assertIn("CNPJ opera", payload["alertas"][0])

    @override_settings(
        CADASTRO_CNPJ_PROVIDER_URL="https://cadastro.example/cnpj/{cnpj}",
        CADASTRO_CEP_PROVIDER_URL="https://cep.example/{cep}",
        CADASTRO_LOOKUP_TIMEOUT_SEGUNDOS=3,
    )
    def test_endpoint_consulta_cadastro_diagnostico_mostra_provedores_configurados(self):
        response = self.client.get("/empresas/consulta-cadastro/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready_with_external_provider")
        self.assertEqual(payload["provedores"]["modo_operacao"], "externo_com_fallback_local")
        self.assertTrue(payload["provedores"]["cnpj_configurado"])
        self.assertTrue(payload["provedores"]["cep_configurado"])
        self.assertEqual(payload["provedores"]["timeout_segundos"], 3)
        self.assertEqual(payload["prontidao"]["contrato"], "cadastro_lookup_readiness_v1")
        self.assertEqual(payload["prontidao"]["status"], "ready_for_provider_homologation")
        self.assertEqual(payload["prontidao"]["provedores_configurados"], 2)
        self.assertEqual(payload["alertas"], [])

    @override_settings(
        CADASTRO_CNPJ_PROVIDER_URL="https://cadastro.example/cnpj/{cnpj}",
        CADASTRO_CEP_PROVIDER_URL="",
    )
    def test_endpoint_consulta_cadastro_diagnostico_mostra_configuracao_parcial(self):
        response = self.client.get("/empresas/consulta-cadastro/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["prontidao"]["status"], "partially_configured")
        self.assertEqual(payload["prontidao"]["provedores_configurados"], 1)
        self.assertEqual(payload["prontidao"]["provedores_necessarios"], 2)
        self.assertTrue(payload["prontidao"]["recomendacoes"])
    def test_endpoint_consulta_cadastro_valida_cnpj_e_reaproveita_dados_locais(self):
        empresa = Empresa.objects.create(
            razao_social="Empresa Consulta Ltda",
            nome_fantasia="Empresa Consulta",
            cnpj="12.345.678/0001-95",
            telefone="(11) 99999-0000",
            email="consulta@example.com",
            endereco="Rua Local, 100",
            regime_tributario="Lucro Presumido",
        )
        Filial.objects.create(
            empresa=empresa,
            nome="Loja Consulta",
            cnpj="11.222.333/0001-81",
            telefone="(11) 98888-0000",
            endereco="Av Filial, 200 - CEP 01001-000",
            municipio="Sao Paulo",
            uf="SP",
            codigo_municipio_ibge="3550308",
        )

        empresa_response = self.client.get("/empresas/consulta-cadastro.json", {"cnpj": "12345678000195"})
        filial_response = self.client.get("/empresas/consulta-cadastro.json", {"cnpj": "11.222.333/0001-81"})
        invalido = self.client.get("/empresas/consulta-cadastro.json", {"cnpj": "11.111.111/1111-11"})
        cep_local = self.client.get("/empresas/consulta-cadastro.json", {"cep": "01001000"})
        externo = self.client.get("/empresas/consulta-cadastro.json", {"cep": "30140071"})

        self.assertEqual(empresa_response.status_code, 200)
        self.assertEqual(empresa_response.json()["status"], "local_match")
        self.assertEqual(empresa_response.json()["dados"]["nome_fantasia"], "Empresa Consulta")
        self.assertEqual(filial_response.json()["dados"]["tipo"], "filial")
        self.assertEqual(filial_response.json()["dados"]["codigo_municipio_ibge"], "3550308")
        self.assertEqual(cep_local.json()["status"], "local_match")
        self.assertEqual(cep_local.json()["consulta"]["tipo"], "cep")
        self.assertEqual(cep_local.json()["dados"]["municipio"], "Sao Paulo")
        self.assertEqual(invalido.status_code, 400)
        self.assertEqual(invalido.json()["status"], "invalid")
        self.assertEqual(externo.json()["status"], "external_provider_required")

    @override_settings(
        CADASTRO_CNPJ_PROVIDER_URL="https://cadastro.example/cnpj/{cnpj}",
        CADASTRO_CEP_PROVIDER_URL="https://cep.example/{cep}",
        CADASTRO_LOOKUP_TIMEOUT_SEGUNDOS=3,
    )
    def test_endpoint_consulta_cadastro_usa_provider_externo_configurado(self):
        cep_payload = {
            "cep": "01001-000",
            "logradouro": "Praca da Se",
            "bairro": "Se",
            "localidade": "Sao Paulo",
            "uf": "SP",
            "ibge": "3550308",
        }
        cnpj_payload = {
            "cnpj": "04.252.011/0001-10",
            "nome": "Empresa Externa Ltda",
            "fantasia": "Empresa Externa",
            "logradouro": "Rua API",
            "numero": "10",
            "municipio": "Sao Paulo",
            "uf": "SP",
            "ibge": "3550308",
        }

        with patch("apps.empresas.views.urlopen", side_effect=[FakeHTTPResponse(cep_payload), FakeHTTPResponse(cnpj_payload)]) as urlopen_mock:
            cep_response = self.client.get("/empresas/consulta-cadastro.json", {"cep": "01001000"})
            cnpj_response = self.client.get("/empresas/consulta-cadastro.json", {"cnpj": "04.252.011/0001-10"})

        self.assertEqual(cep_response.status_code, 200)
        self.assertEqual(cep_response.json()["status"], "external_match")
        self.assertEqual(cep_response.json()["dados"]["municipio"], "Sao Paulo")
        self.assertEqual(cep_response.json()["dados"]["codigo_municipio_ibge"], "3550308")
        self.assertEqual(cnpj_response.json()["status"], "external_match")
        self.assertEqual(cnpj_response.json()["dados"]["razao_social"], "Empresa Externa Ltda")
        self.assertEqual(cnpj_response.json()["dados"]["nome_fantasia"], "Empresa Externa")
        self.assertIn("Rua API", cnpj_response.json()["dados"]["endereco"])
        self.assertEqual(urlopen_mock.call_args_list[0].kwargs["timeout"], 3)

class EmpresasLicenciamentoTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")
        self.empresa = Empresa.objects.create(
            razao_social="Cliente Um Ltda",
            nome_fantasia="Cliente Um",
            cnpj="11.111.111/0001-11",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Cliente Um",
            cnpj=self.empresa.cnpj,
        )
        self.outra_empresa = Empresa.objects.create(
            razao_social="Cliente Dois Ltda",
            nome_fantasia="Cliente Dois",
            cnpj="22.222.222/0001-22",
        )
        self.outra_filial = Filial.objects.create(
            empresa=self.outra_empresa,
            nome="Matriz Cliente Dois",
            cnpj=self.outra_empresa.cnpj,
        )
        self.admin_empresa = get_user_model().objects.create_user("dono_cliente", password="123")
        PerfilUsuario.objects.create(
            usuario=self.admin_empresa,
            filial=self.filial,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.client.force_login(self.admin_empresa)

    def test_admin_empresa_enxerga_somente_a_propria_estrutura(self):
        response = self.client.get("/empresas/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Um")
        self.assertNotContains(response, "Cliente Dois")
        self.assertNotContains(response, "Nova empresa")
        self.assertNotContains(response, "Nova filial")

    def test_admin_empresa_nao_cria_matriz_ou_filial_por_url(self):
        empresas_antes = Empresa.objects.count()
        filiais_antes = Filial.objects.count()

        for url in ("/empresas/nova/", "/empresas/filiais/nova/"):
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)

        self.assertEqual(Empresa.objects.count(), empresas_antes)
        self.assertEqual(Filial.objects.count(), filiais_antes)

    def test_admin_empresa_edita_apenas_a_propria_estrutura(self):
        self.assertEqual(self.client.get(f"/empresas/{self.empresa.pk}/editar/").status_code, 200)
        self.assertEqual(self.client.get(f"/empresas/filiais/{self.filial.pk}/editar/").status_code, 200)
        self.assertEqual(self.client.get(f"/empresas/{self.outra_empresa.pk}/editar/").status_code, 404)
        self.assertEqual(self.client.get(f"/empresas/filiais/{self.outra_filial.pk}/editar/").status_code, 404)

    def test_busca_de_filial_respeita_empresa_do_usuario(self):
        response = self.client.get("/empresas/filiais/busca.json", {"q": "Matriz Cliente"})

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [self.filial.pk])

    def test_super_admin_cria_filial_licenciada_com_auditoria(self):
        super_admin = get_user_model().objects.create_superuser("software_owner", password="123")
        self.client.force_login(super_admin)

        response = self.client.post(
            "/empresas/filiais/nova/",
            {
                "empresa": self.empresa.pk,
                "nome": "Loja 2",
                "cnpj": "11.111.111/0002-00",
                "telefone": "",
                "endereco": "",
                "municipio": "",
                "uf": "",
                "codigo_municipio_ibge": "",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, "/empresas/")
        filial = Filial.objects.get(empresa=self.empresa, nome="Loja 2")
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=super_admin,
                acao="filial_licenciada_criada",
                objeto_id=str(filial.pk),
            ).exists()
        )