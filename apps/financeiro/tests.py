from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.fiscal.models import AmbienteFiscal, DocumentoFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal
from apps.pdv.models import Caixa
from apps.vendas.models import FormaPagamento, PagamentoVenda, StatusVenda, Venda

from .forms import CategoriaFinanceiraForm, ContaContabilForm, ContaFinanceiraForm
from .models import CategoriaFinanceira, CentroCusto, ContaContabil, ConciliacaoLancamentoFinanceiro, ContaFinanceira, ContaMovimentoFinanceiro, ExportacaoContabil, LancamentoFinanceiro, StatusContaFinanceira, StatusExportacaoContabil, TipoContaContabil, TipoContaFinanceira, TipoContaMovimento, TipoLancamentoFinanceiro, TransferenciaFinanceira
from .services import baixar_conta, cancelar_conta, conciliar_lancamento, estornar_lancamento, realizar_transferencia



class FakeContabilAdapter:
    nome = "Contabilidade Teste"
    chamadas = 0
    ultimo_payload = None
    ultima_chave = ""

    def exportar(self, *, payload, chave_idempotencia):
        type(self).chamadas += 1
        type(self).ultimo_payload = payload
        type(self).ultima_chave = chave_idempotencia
        return {"status": "ENVIADO", "protocolo": "CONT-2026-0001", "mensagem": "Recebido"}

class FinanceiroTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(razao_social="Mercado Teste", nome_fantasia="Mercado", cnpj="33.333.333/0001-33")
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)
        self.categoria = CategoriaFinanceira.objects.create(empresa=self.empresa, nome="Mercadorias", tipo=TipoContaFinanceira.PAGAR)
        self.conta = ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            descricao="Compra de mercadorias",
            categoria=self.categoria,
            filial=self.filial,
            valor=Decimal("150.00"),
            vencimento=timezone.localdate(),
            usuario=self.user,
        )
        self.conta_receber = ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.RECEBER,
            descricao="Crediario cliente",
            filial=self.filial,
            valor=Decimal("210.00"),
            vencimento=timezone.localdate(),
            usuario=self.user,
        )

    def test_super_admin_escolhe_empresa_ao_criar_categoria(self):
        outra_empresa = Empresa.objects.create(
            razao_social="Outro Mercado LTDA",
            nome_fantasia="Outro Mercado",
            cnpj="44.444.444/0001-44",
        )

        resposta = self.client.post(
            "/financeiro/categorias/nova/",
            {"empresa": outra_empresa.id, "nome": "Receitas de entrega", "tipo": TipoContaFinanceira.RECEBER, "is_active": "on"},
        )

        self.assertRedirects(resposta, "/financeiro/categorias/")
        categoria = CategoriaFinanceira.objects.get(nome="Receitas de entrega")
        self.assertEqual(categoria.empresa, outra_empresa)

    def test_form_conta_rejeita_categoria_de_outra_empresa(self):
        outra_empresa = Empresa.objects.create(
            razao_social="Outro Mercado LTDA",
            nome_fantasia="Outro Mercado",
            cnpj="55.555.555/0001-55",
        )
        categoria_outra_empresa = CategoriaFinanceira.objects.create(
            empresa=outra_empresa,
            nome="Despesa externa",
            tipo=TipoContaFinanceira.PAGAR,
        )
        form = ContaFinanceiraForm(
            data={
                "tipo": TipoContaFinanceira.PAGAR,
                "descricao": "Conta isolada",
                "categoria": categoria_outra_empresa.id,
                "filial": self.filial.id,
                "fornecedor": "",
                "cliente": "",
                "valor": "10.00",
                "vencimento": timezone.localdate().isoformat(),
                "observacoes": "",
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("categoria", form.errors)

    def test_baixa_conta_e_registra_auditoria(self):
        baixar_conta(
            conta=self.conta,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("150.00"),
            forma_pagamento="Pix",
        )

        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status, StatusContaFinanceira.PAGA)
        self.assertEqual(self.conta.valor_pago, Decimal("150.00"))
        self.assertTrue(LogAuditoria.objects.filter(modulo="financeiro", acao="BAIXA_CONTA").exists())

    def test_cancelar_conta_aberta(self):
        cancelar_conta(conta=self.conta, usuario=self.user, motivo="Duplicidade")

        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status, StatusContaFinanceira.CANCELADA)
        self.assertIn("Duplicidade", self.conta.observacoes)

    def test_tela_financeiro_lista_contas(self):
        response = self.client.get("/financeiro/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Financeiro")
        self.assertContains(response, "Compra de mercadorias")
        self.assertContains(response, "Saldo previsto")
        self.assertContains(response, "Vencimentos")
        self.assertContains(response, "Conferencia e exportacao")

    def test_formularios_financeiros_exibem_secoes_operacionais(self):
        conta_form = self.client.get(f"/financeiro/{self.conta.pk}/editar/")
        categoria_form = self.client.get(f"/financeiro/categorias/{self.categoria.pk}/editar/")
        baixa_form = self.client.get(f"/financeiro/{self.conta.pk}/baixar/")

        self.assertEqual(conta_form.status_code, 200)
        self.assertContains(conta_form, "Classificação")
        self.assertContains(conta_form, "Origem e parceiro")
        self.assertContains(conta_form, "Valores e vencimento")
        self.assertContains(conta_form, "select2-field")
        self.assertEqual(categoria_form.status_code, 200)
        self.assertContains(categoria_form, "Categoria")
        self.assertEqual(baixa_form.status_code, 200)
        self.assertContains(baixa_form, "Pagamento / recebimento")

    def test_baixa_conta_respeita_retorno_seguro_para_origem(self):
        response = self.client.post(
            f"/financeiro/{self.conta.pk}/baixar/",
            {
                "data_pagamento": timezone.localdate().isoformat(),
                "valor_pago": "150.00",
                "forma_pagamento": "Pix",
                "conta_movimento": "",
                "next": "/compras/10/",
            },
        )

        self.conta.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/compras/10/")
        self.assertEqual(self.conta.status, StatusContaFinanceira.PAGA)

    def test_exporta_financeiro_csv_e_pdf(self):
        response_csv = self.client.get("/financeiro/exportar.csv")
        response_pdf = self.client.get("/financeiro/imprimir/")

        self.assertEqual(response_csv.status_code, 200)
        self.assertEqual(response_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("financeiro_", response_csv["Content-Disposition"])
        self.assertIn(b"Compra de mercadorias", response_csv.content)
        self.assertEqual(response_pdf.status_code, 200)
        self.assertContains(response_pdf, "Imprimir / Salvar como PDF")
        self.assertContains(response_pdf, "Compra de mercadorias")

    def test_fluxo_caixa_e_exportacao(self):
        response = self.client.get("/financeiro/fluxo-caixa/")
        response_csv = self.client.get("/financeiro/fluxo-caixa/exportar.csv")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fluxo de caixa")
        self.assertContains(response, "Saldo previsto")
        self.assertContains(response, "Previsao por vencimento")
        self.assertContains(response, "Realizado por baixa")
        self.assertContains(response, "210,00")
        self.assertEqual(response_csv.status_code, 200)
        self.assertEqual(response_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"Saldo previsto", response_csv.content)

    def test_conciliacao_soma_pdv_recebimentos_e_saidas(self):
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.user, valor_inicial=Decimal("100.00"))
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        venda = Venda.objects.create(
            filial=self.filial,
            caixa=caixa,
            usuario=self.user,
            total_bruto=Decimal("70.00"),
            total_liquido=Decimal("70.00"),
            status=StatusVenda.FINALIZADA,
        )
        PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=Decimal("70.00"))
        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="Pix",
        )
        baixar_conta(
            conta=self.conta,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("150.00"),
            forma_pagamento="Pix",
        )

        response = self.client.get("/financeiro/conciliacao/")
        response_csv = self.client.get("/financeiro/conciliacao/exportar.csv")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conciliacao financeira")
        self.assertContains(response, "Entradas PDV")
        self.assertContains(response, "PDV x financeiro")
        self.assertContains(response, "Conferencia diaria")
        self.assertContains(response, "130,00")
        self.assertEqual(response_csv.status_code, 200)
        self.assertEqual(response_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"Saldo operacional", response_csv.content)

    def test_plano_contas_preserva_classificacao_no_livro_estorno_e_relatorios(self):
        grupo = ContaContabil.objects.create(
            empresa=self.empresa,
            codigo="3",
            nome="Despesas",
            natureza="DESPESA",
            tipo=TipoContaContabil.SINTETICA,
        )
        conta_contabil = ContaContabil.objects.create(
            empresa=self.empresa,
            codigo="3.01.001",
            nome="Compra de mercadorias",
            natureza="DESPESA",
            tipo=TipoContaContabil.ANALITICA,
            conta_pai=grupo,
        )
        outra_conta = ContaContabil.objects.create(
            empresa=self.empresa,
            codigo="3.01.002",
            nome="Fretes sobre compras",
            natureza="DESPESA",
            tipo=TipoContaContabil.ANALITICA,
            conta_pai=grupo,
        )
        self.categoria.conta_contabil = conta_contabil
        self.categoria.save(update_fields=["conta_contabil"])
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa plano contabil",
            tipo=TipoContaMovimento.CAIXA,
        )

        baixar_conta(
            conta=self.conta,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("150.00"),
            forma_pagamento="PIX",
            conta_movimento=caixa,
        )
        lancamento = LancamentoFinanceiro.objects.get(conta_financeira=self.conta)
        self.assertEqual(lancamento.conta_contabil, conta_contabil)

        self.categoria.conta_contabil = outra_conta
        self.categoria.save(update_fields=["conta_contabil"])
        estorno = estornar_lancamento(
            lancamento=lancamento,
            usuario=self.user,
            motivo="Correcao operacional",
        )
        self.assertEqual(estorno.conta_contabil, conta_contabil)

        tela = self.client.get("/financeiro/resultado/")
        csv_texto = self.client.get("/financeiro/resultado/exportar.csv").content.decode("utf-8-sig")
        pacote = self.client.get("/financeiro/resultado/pacote-contabil.json").json()
        self.assertContains(tela, "Resultado por conta cont?bil")
        self.assertContains(tela, "Compra de mercadorias")
        self.assertIn("Codigo;Conta contabil;Natureza;Receitas;Despesas;Resultado", csv_texto)
        self.assertIn("3.01.001;Compra de mercadorias;Despesa", csv_texto)
        self.assertEqual(pacote["plano_contas"][0]["codigo"], "3.01.001")

    def test_plano_contas_bloqueia_ciclo_e_vinculos_invalidos(self):
        raiz = ContaContabil.objects.create(
            empresa=self.empresa, codigo="1", nome="Ativo", natureza="ATIVO",
            tipo=TipoContaContabil.SINTETICA,
        )
        filha = ContaContabil.objects.create(
            empresa=self.empresa, codigo="1.01", nome="Disponivel", natureza="ATIVO",
            tipo=TipoContaContabil.SINTETICA, conta_pai=raiz,
        )
        raiz.conta_pai = filha
        with self.assertRaises(ValidationError):
            raiz.full_clean()
        raiz.conta_pai = None
        analitica = ContaContabil.objects.create(
            empresa=self.empresa, codigo="1.01.001", nome="Caixa", natureza="ATIVO",
            tipo=TipoContaContabil.ANALITICA, conta_pai=filha,
        )
        subconta_invalida = ContaContabil(
            empresa=self.empresa, codigo="1.01.001.01", nome="Subcaixa", natureza="ATIVO",
            tipo=TipoContaContabil.ANALITICA, conta_pai=analitica,
        )
        with self.assertRaises(ValidationError):
            subconta_invalida.full_clean()
        self.categoria.conta_contabil = analitica
        self.categoria.save(update_fields=["conta_contabil"])
        analitica.tipo = TipoContaContabil.SINTETICA
        with self.assertRaises(ValidationError):
            analitica.full_clean()

        outra_empresa = Empresa.objects.create(
            razao_social="Empresa Contabil Externa LTDA",
            nome_fantasia="Contabil Externa",
            cnpj="77.777.777/0001-77",
        )
        externa = ContaContabil.objects.create(
            empresa=outra_empresa, codigo="4.01", nome="Receita externa", natureza="RECEITA",
            tipo=TipoContaContabil.ANALITICA,
        )
        form = CategoriaFinanceiraForm(
            data={
                "empresa": self.empresa.pk,
                "nome": "Categoria isolada",
                "tipo": TipoContaFinanceira.RECEBER,
                "conta_contabil": externa.pk,
                "is_active": "on",
            },
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("conta_contabil", form.errors)

        form_sintetica = CategoriaFinanceiraForm(
            data={
                "empresa": self.empresa.pk,
                "nome": "Categoria sintetica",
                "tipo": TipoContaFinanceira.PAGAR,
                "conta_contabil": raiz.pk,
                "is_active": "on",
            },
            user=self.user,
        )
        self.assertFalse(form_sintetica.is_valid())
        self.assertIn("conta_contabil", form_sintetica.errors)

    def test_cadastro_conta_contabil_registra_auditoria(self):
        resposta = self.client.post(
            "/financeiro/plano-contas/nova/",
            {
                "empresa": self.empresa.pk,
                "codigo": "3.02.001",
                "nome": "Energia eletrica",
                "natureza": "DESPESA",
                "tipo": TipoContaContabil.ANALITICA,
                "conta_pai": "",
                "ativa": "on",
            },
        )
        self.assertRedirects(resposta, "/financeiro/plano-contas/")
        conta = ContaContabil.objects.get(codigo="3.02.001")
        self.assertTrue(LogAuditoria.objects.filter(
            acao="CADASTRO_CONTA_CONTABIL", objeto_id=str(conta.pk)
        ).exists())

    def test_centro_custo_isolado_e_preservado_no_livro_e_relatorios(self):
        centro = CentroCusto.objects.create(
            empresa=self.empresa, codigo="ADM", nome="Administrativo"
        )
        self.conta.centro_custo = centro
        self.conta.save(update_fields=["centro_custo", "atualizado_em"])
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa centro de custo",
            tipo=TipoContaMovimento.CAIXA,
        )

        baixar_conta(
            conta=self.conta,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("150.00"),
            forma_pagamento="PIX",
            conta_movimento=caixa,
        )
        lancamento = LancamentoFinanceiro.objects.get(conta_financeira=self.conta)
        self.assertEqual(lancamento.centro_custo, centro)

        self.conta.centro_custo = None
        self.conta.save(update_fields=["centro_custo", "atualizado_em"])
        estorno = estornar_lancamento(
            lancamento=lancamento,
            usuario=self.user,
            motivo="Correcao de classificacao",
        )
        self.assertEqual(estorno.centro_custo, centro)

        tela = self.client.get("/financeiro/resultado/")
        csv_texto = self.client.get("/financeiro/resultado/exportar.csv").content.decode("utf-8-sig")
        pacote = self.client.get("/financeiro/resultado/pacote-contabil.json").json()

        self.assertContains(tela, "Resultado por centro de custo")
        self.assertContains(tela, "Administrativo")
        self.assertIn("Codigo;Centro de custo;Receitas;Despesas;Resultado", csv_texto)
        self.assertIn("ADM;Administrativo", csv_texto)
        self.assertEqual(pacote["centros_custo"][0]["codigo"], "ADM")
        self.assertEqual(pacote["centros_custo"][0]["centro_custo"], "Administrativo")

    def test_form_conta_rejeita_centro_custo_de_outra_empresa(self):
        outra_empresa = Empresa.objects.create(
            razao_social="Empresa Centro Externo LTDA",
            nome_fantasia="Centro Externo",
            cnpj="66.666.666/0001-66",
        )
        centro_externo = CentroCusto.objects.create(
            empresa=outra_empresa, codigo="EXT", nome="Centro externo"
        )
        form = ContaFinanceiraForm(
            data={
                "tipo": TipoContaFinanceira.PAGAR,
                "descricao": "Conta com centro invalido",
                "categoria": self.categoria.id,
                "centro_custo": centro_externo.id,
                "filial": self.filial.id,
                "fornecedor": "",
                "cliente": "",
                "valor": "10.00",
                "vencimento": timezone.localdate().isoformat(),
                "observacoes": "",
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("centro_custo", form.errors)

    def test_cadastro_centro_custo_registra_auditoria(self):
        resposta = self.client.post(
            "/financeiro/centros-custo/novo/",
            {
                "empresa": self.empresa.id,
                "codigo": "LOJA",
                "nome": "Operacao da loja",
                "ativo": "on",
            },
        )

        self.assertRedirects(resposta, "/financeiro/centros-custo/")
        centro = CentroCusto.objects.get(codigo="LOJA")
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CADASTRO_CENTRO_CUSTO", objeto_id=str(centro.pk)
            ).exists()
        )

    def test_resultado_financeiro_ignora_transferencias_e_exporta_csv(self):
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa resultado",
            tipo=TipoContaMovimento.CAIXA,
            saldo_inicial=Decimal("500.00"),
        )
        banco = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco resultado",
            tipo=TipoContaMovimento.BANCO,
            saldo_inicial=Decimal("0.00"),
        )
        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="PIX",
            conta_movimento=caixa,
        )
        baixar_conta(
            conta=self.conta,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("150.00"),
            forma_pagamento="PIX",
            conta_movimento=caixa,
        )
        realizar_transferencia(
            conta_origem=caixa,
            conta_destino=banco,
            valor=Decimal("50.00"),
            data=timezone.localdate(),
            usuario=self.user,
            descricao="Deposito interno",
        )
        lancamento_receita = LancamentoFinanceiro.objects.get(conta_financeira=self.conta_receber)
        conciliar_lancamento(
            lancamento=lancamento_receita,
            data_conciliacao=timezone.localdate(),
            referencia_externa="EXTRATO-RESULTADO-01",
            usuario=self.user,
        )

        response = self.client.get("/financeiro/resultado/")
        response_csv = self.client.get("/financeiro/resultado/exportar.csv")
        response_json = self.client.get("/financeiro/resultado/pacote-contabil.json")
        csv_texto = response_csv.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resultado financeiro")
        self.assertContains(response, "Receitas realizadas")
        self.assertContains(response, "Despesas realizadas")
        self.assertContains(response, "Resultado por categoria")
        self.assertContains(response, "DRE gerencial")
        self.assertContains(response, "Margem operacional")
        self.assertContains(response, "Saldos por conta de movimento")
        self.assertContains(response, "Balancete gerencial")
        self.assertContains(response, "Pacote contábil gerencial")
        self.assertContains(response, "Pacote contábil JSON")
        self.assertContains(response, "não substitui SPED, ECD, ECF")
        self.assertContains(response, "Transferências internas")
        self.assertContains(response, "Estornos rastreados")
        self.assertContains(response, "Cobertura conciliada")
        self.assertContains(response, "25,00%")
        self.assertContains(response, "R$ 210,00")
        self.assertContains(response, "R$ 250,00")
        self.assertContains(response, "Mercadorias")
        self.assertContains(response, "Caixa resultado")
        self.assertContains(response, "Banco resultado")
        self.assertContains(response, "60,00")
        self.assertNotContains(response, "TRANSFERENCIA")
        self.assertEqual(response_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("resultado_financeiro_", response_csv["Content-Disposition"])
        self.assertIn("Periodo;210,00;150,00;60,00", csv_texto)
        self.assertIn("DRE gerencial", csv_texto)
        self.assertIn("Receita operacional;210,00", csv_texto)
        self.assertIn("Despesas operacionais;150,00", csv_texto)
        self.assertIn("Resultado operacional;60,00", csv_texto)
        self.assertIn("Margem operacional;28,57%", csv_texto)
        self.assertIn("Categoria;Tipo;Receitas;Despesas;Resultado", csv_texto)
        self.assertIn("Mercadorias;Conta a pagar;0,00;150,00;-150,00", csv_texto)
        self.assertIn("Filial;Conta movimento;Tipo;Saldo inicial;Entradas período;Saidas período;Saldo atual", csv_texto)
        self.assertIn("Matriz;Caixa resultado;Caixa físico;500,00;210,00;150,00;510,00", csv_texto)
        self.assertIn("Pacote contabil gerencial", csv_texto)
        self.assertIn("Movimentação total do livro;60,00", csv_texto)
        self.assertIn("Transferências internas;2;Entradas 50,00 / Saidas 50,00", csv_texto)
        self.assertIn("Conciliação bancária;25,00%;1 conciliados / 3 pendentes", csv_texto)
        self.assertIn("Valor conciliado;210,00;Pendente 250,00", csv_texto)
        self.assertIn("Alerta;;", csv_texto)
        self.assertIn("Pacote gerencial para conferência interna", csv_texto)
        self.assertEqual(response_json.status_code, 200)
        payload = response_json.json()
        self.assertEqual(payload["contrato"], "financial_accounting_package_v1")
        self.assertEqual(payload["resumo"]["receitas"], "210.00")
        self.assertEqual(payload["resumo"]["despesas"], "150.00")
        self.assertEqual(payload["resumo"]["resultado"], "60.00")
        self.assertEqual(payload["resumo"]["transferencias_internas"], 2)
        self.assertEqual(payload["conciliacao_bancaria"]["conciliados"], 1)
        self.assertEqual(payload["conciliacao_bancaria"]["pendentes"], 3)
        self.assertEqual(payload["conciliacao_bancaria"]["percentual"], "25.00")
        self.assertEqual(payload["conciliacao_bancaria"]["valor_conciliado"], "210.00")
        self.assertIn("dre_gerencial", payload)
        self.assertIn("balancete_contas", payload)
        self.assertIn("não substitui SPED", " ".join(payload["alertas"]))
        self.assertIn("Balancete gerencial por conta", csv_texto)
        self.assertIn("Filial;Conta movimento;Tipo;Saldo anterior;Entradas;Saidas;Saldo final", csv_texto)
        self.assertIn("Matriz;Caixa resultado;Caixa físico;500,00;210,00;200,00;510,00", csv_texto)
        self.assertIn("Matriz;Banco resultado;Conta bancária;0,00;50,00;0,00;50,00", csv_texto)
        self.assertNotIn("TRANSFERENCIA", csv_texto)

    def test_resultado_concilia_documento_fiscal_com_livro_da_venda(self):
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.user, valor_inicial=Decimal("100.00"))
        conta_caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial, nome="Caixa fiscal", tipo=TipoContaMovimento.CAIXA,
        )
        forma = FormaPagamento.objects.create(nome="Dinheiro fiscal", tipo="DINHEIRO", permite_troco=True)
        venda = Venda.objects.create(
            filial=self.filial, caixa=caixa, usuario=self.user,
            total_bruto=Decimal("100.00"), total_liquido=Decimal("100.00"), status=StatusVenda.FINALIZADA,
        )
        pagamento = PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=Decimal("100.00"))
        LancamentoFinanceiro.objects.create(
            conta=conta_caixa, tipo=TipoLancamentoFinanceiro.ENTRADA, origem="VENDA_PDV",
            descricao=f"Venda #{venda.pk}", valor=Decimal("100.00"), data=timezone.localdate(),
            pagamento_venda=pagamento, usuario=self.user,
        )
        DocumentoFiscal.objects.create(
            filial=self.filial, venda=venda, tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.HOMOLOGACAO, serie=1, numero=1,
            status=StatusDocumentoFiscal.EMITIDO, valor_total=Decimal("95.00"), usuario=self.user,
        )

        venda_sem_documento = Venda.objects.create(
            filial=self.filial, caixa=caixa, usuario=self.user,
            total_bruto=Decimal("30.00"), total_liquido=Decimal("30.00"), status=StatusVenda.FINALIZADA,
        )
        pagamento_sem_documento = PagamentoVenda.objects.create(
            venda=venda_sem_documento, forma_pagamento=forma, valor=Decimal("30.00"),
        )
        LancamentoFinanceiro.objects.create(
            conta=conta_caixa, tipo=TipoLancamentoFinanceiro.ENTRADA, origem="VENDA_PDV",
            descricao=f"Venda #{venda_sem_documento.pk}", valor=Decimal("30.00"), data=timezone.localdate(),
            pagamento_venda=pagamento_sem_documento, usuario=self.user,
        )

        tela = self.client.get("/financeiro/resultado/")
        csv_response = self.client.get("/financeiro/resultado/exportar.csv")
        pacote = self.client.get("/financeiro/resultado/pacote-contabil.json").json()

        self.assertContains(tela, "Conferência fiscal x financeiro")
        self.assertContains(tela, "Valores divergentes")
        self.assertContains(tela, "Sem documento fiscal")
        self.assertIn("Conferencia fiscal x financeiro", csv_response.content.decode("utf-8-sig"))
        self.assertEqual(pacote["integracao_fiscal"]["contrato"], "financial_fiscal_reconciliation_v1")
        self.assertEqual(pacote["integracao_fiscal"]["total_divergencias"], 2)
        self.assertEqual(pacote["integracao_fiscal"]["vendas_sem_documento"], 1)
        por_situacao = {item["situacao"]: item for item in pacote["integracao_fiscal"]["divergencias"]}
        self.assertEqual(por_situacao["Valores divergentes"]["diferenca"], "5.00")
        self.assertEqual(por_situacao["Sem documento fiscal"]["valor_financeiro"], "30.00")

    def test_administrador_da_empresa_consolida_e_filtra_somente_suas_filiais(self):
        filial_loja = Filial.objects.create(
            empresa=self.empresa,
            nome="Loja bairro",
            cnpj="33.333.333/0002-14",
        )
        empresa_externa = Empresa.objects.create(
            razao_social="Concorrente Teste Ltda",
            nome_fantasia="Concorrente",
            cnpj="55.555.555/0001-55",
        )
        filial_externa = Filial.objects.create(
            empresa=empresa_externa,
            nome="Matriz externa",
            cnpj=empresa_externa.cnpj,
        )
        conta_matriz = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial, nome="Caixa matriz empresa", tipo=TipoContaMovimento.CAIXA,
        )
        conta_loja = ContaMovimentoFinanceiro.objects.create(
            filial=filial_loja, nome="Caixa filial empresa", tipo=TipoContaMovimento.CAIXA,
        )
        conta_externa = ContaMovimentoFinanceiro.objects.create(
            filial=filial_externa, nome="Caixa outra empresa", tipo=TipoContaMovimento.CAIXA,
        )
        for conta, valor in (
            (conta_matriz, Decimal("100.00")),
            (conta_loja, Decimal("200.00")),
            (conta_externa, Decimal("900.00")),
        ):
            LancamentoFinanceiro.objects.create(
                conta=conta,
                tipo=TipoLancamentoFinanceiro.ENTRADA,
                origem="AJUSTE",
                descricao=f"Receita {conta.nome}",
                valor=valor,
                data=timezone.localdate(),
                usuario=self.user,
            )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            descricao="Despesa da filial da empresa",
            filial=filial_loja,
            valor=Decimal("40.00"),
            vencimento=timezone.localdate(),
            usuario=self.user,
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            descricao="Despesa sigilosa externa",
            filial=filial_externa,
            valor=Decimal("900.00"),
            vencimento=timezone.localdate(),
            usuario=self.user,
        )

        administrador = get_user_model().objects.create_user(
            "administrador_empresa", "admin.empresa@example.com", "123"
        )
        PerfilUsuario.objects.create(
            usuario=administrador,
            filial=self.filial,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.client.force_login(administrador)

        consolidado = self.client.get("/financeiro/resultado/")
        pacote_consolidado = self.client.get(
            "/financeiro/resultado/pacote-contabil.json"
        ).json()
        pacote_filial = self.client.get(
            "/financeiro/resultado/pacote-contabil.json", {"filial": filial_loja.pk}
        ).json()
        filial_externa_negada = self.client.get(
            "/financeiro/resultado/", {"filial": filial_externa.pk}
        )
        livro = self.client.get("/financeiro/livro/")
        livro_csv = self.client.get("/financeiro/livro/exportar.csv")
        conciliacao = self.client.get("/financeiro/conciliacao-bancaria/")
        livro_externo_negado = self.client.get(
            "/financeiro/livro/", {"filial": filial_externa.pk}
        )
        conciliacao_externa_negada = self.client.get(
            "/financeiro/conciliacao-bancaria/", {"filial": filial_externa.pk}
        )
        contas = self.client.get("/financeiro/")
        fluxo = self.client.get("/financeiro/fluxo-caixa/")
        fluxo_filial = self.client.get("/financeiro/fluxo-caixa/", {"filial": filial_loja.pk})
        contas_externas_negadas = self.client.get("/financeiro/", {"filial": filial_externa.pk})
        fluxo_externo_negado = self.client.get(
            "/financeiro/fluxo-caixa/", {"filial": filial_externa.pk}
        )
        conciliacao_diaria_externa_negada = self.client.get(
            "/financeiro/conciliacao/", {"filial": filial_externa.pk}
        )

        self.assertEqual(consolidado.status_code, 200)
        self.assertContains(consolidado, "Todas as filiais da empresa")
        self.assertContains(consolidado, "Caixa matriz empresa")
        self.assertContains(consolidado, "Caixa filial empresa")
        self.assertNotContains(consolidado, "Caixa outra empresa")
        self.assertIsNone(pacote_consolidado["filial"])
        self.assertEqual(pacote_consolidado["resumo"]["receitas"], "300.00")
        self.assertEqual(pacote_filial["filial"]["id"], filial_loja.pk)
        self.assertEqual(pacote_filial["resumo"]["receitas"], "200.00")
        self.assertContains(livro, "Caixa matriz empresa")
        self.assertContains(livro, "Caixa filial empresa")
        self.assertNotContains(livro, "Caixa outra empresa")
        self.assertContains(conciliacao, "Caixa matriz empresa")
        self.assertContains(conciliacao, "Caixa filial empresa")
        self.assertNotContains(conciliacao, "Caixa outra empresa")
        livro_csv_texto = livro_csv.content.decode("utf-8-sig")
        self.assertIn("Caixa matriz empresa", livro_csv_texto)
        self.assertIn("Caixa filial empresa", livro_csv_texto)
        self.assertNotIn("Caixa outra empresa", livro_csv_texto)
        self.assertEqual(filial_externa_negada.status_code, 403)
        self.assertEqual(livro_externo_negado.status_code, 403)
        self.assertEqual(conciliacao_externa_negada.status_code, 403)
        self.assertContains(contas, "Compra de mercadorias")
        self.assertContains(contas, "Despesa da filial da empresa")
        self.assertNotContains(contas, "Despesa sigilosa externa")
        self.assertEqual(fluxo.context["total_previsto_pagar"], Decimal("190.00"))
        self.assertEqual(fluxo_filial.context["total_previsto_pagar"], Decimal("40.00"))
        self.assertEqual(contas_externas_negadas.status_code, 403)
        self.assertEqual(fluxo_externo_negado.status_code, 403)
        self.assertEqual(conciliacao_diaria_externa_negada.status_code, 403)
    def test_resultado_financeiro_isola_filial_e_bloqueia_acesso_fora_do_perfil(self):
        outra_empresa = Empresa.objects.create(
            razao_social="Mercado Outra Empresa",
            nome_fantasia="Mercado Outra",
            cnpj="44.444.444/0001-44",
        )
        outra_filial = Filial.objects.create(
            empresa=outra_empresa,
            nome="Filial externa",
            cnpj=outra_empresa.cnpj,
        )
        conta_matriz = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial, nome="Caixa matriz isolado", tipo=TipoContaMovimento.CAIXA,
        )
        conta_externa = ContaMovimentoFinanceiro.objects.create(
            filial=outra_filial, nome="Caixa externo sigiloso", tipo=TipoContaMovimento.CAIXA,
        )
        LancamentoFinanceiro.objects.create(
            conta=conta_matriz, tipo=TipoLancamentoFinanceiro.ENTRADA,
            origem="AJUSTE", descricao="Receita matriz", valor=Decimal("100.00"),
            data=timezone.localdate(), usuario=self.user,
        )
        LancamentoFinanceiro.objects.create(
            conta=conta_externa, tipo=TipoLancamentoFinanceiro.ENTRADA,
            origem="AJUSTE", descricao="Receita externa", valor=Decimal("900.00"),
            data=timezone.localdate(), usuario=self.user,
        )

        tela = self.client.get("/financeiro/resultado/", {"filial": self.filial.pk})
        csv_response = self.client.get("/financeiro/resultado/exportar.csv", {"filial": self.filial.pk})
        pacote = self.client.get(
            "/financeiro/resultado/pacote-contabil.json", {"filial": self.filial.pk}
        ).json()

        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, "Caixa matriz isolado")
        self.assertNotContains(tela, "Caixa externo sigiloso")
        csv_texto = csv_response.content.decode("utf-8-sig")
        self.assertIn("Caixa matriz isolado", csv_texto)
        self.assertNotIn("Caixa externo sigiloso", csv_texto)
        self.assertEqual(pacote["filial"]["id"], self.filial.pk)
        self.assertEqual(pacote["resumo"]["receitas"], "100.00")

        usuario_financeiro = get_user_model().objects.create_user(
            "financeiro", "financeiro@example.com", "123"
        )
        PerfilUsuario.objects.create(
            usuario=usuario_financeiro,
            filial=self.filial,
            tipo=TipoPerfil.FINANCEIRO,
        )
        self.client.force_login(usuario_financeiro)
        permitido = self.client.get("/financeiro/resultado/")
        negado = self.client.get("/financeiro/resultado/", {"filial": outra_filial.pk})
        csv_negado = self.client.get(
            "/financeiro/resultado/exportar.csv", {"filial": outra_filial.pk}
        )
        json_negado = self.client.get(
            "/financeiro/resultado/pacote-contabil.json", {"filial": outra_filial.pk}
        )

        self.assertEqual(permitido.status_code, 200)
        self.assertContains(permitido, "Caixa matriz isolado")
        self.assertNotContains(permitido, "Caixa externo sigiloso")
        self.assertEqual(negado.status_code, 403)
        self.assertEqual(csv_negado.status_code, 403)
        self.assertEqual(json_negado.status_code, 403)
    def test_baixa_em_conta_movimento_registra_livro_imutavel(self):
        conta_pix = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX Matriz",
            tipo=TipoContaMovimento.PIX,
            saldo_inicial=Decimal("50.00"),
        )

        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="PIX",
            conta_movimento=conta_pix,
        )

        lancamento = LancamentoFinanceiro.objects.get(conta_financeira=self.conta_receber)
        self.conta_receber.refresh_from_db()
        self.assertEqual(self.conta_receber.conta_movimento, conta_pix)
        self.assertEqual(lancamento.tipo, TipoLancamentoFinanceiro.ENTRADA)
        self.assertEqual(lancamento.valor, Decimal("210.00"))
        self.assertEqual(conta_pix.saldo_atual, Decimal("260.00"))
        with self.assertRaises(ValidationError):
            lancamento.save()
        with self.assertRaises(ValidationError):
            lancamento.delete()

        contas = self.client.get("/financeiro/contas-movimento/")
        livro = self.client.get("/financeiro/livro/")
        livro_csv = self.client.get("/financeiro/livro/exportar.csv")
        self.assertContains(contas, "PIX Matriz")
        self.assertContains(contas, "260,00")
        self.assertContains(livro, "Livro financeiro")
        self.assertContains(livro, "Crediario cliente")
        self.assertContains(livro, "R$ 210,00")
        self.assertEqual(livro_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("livro_financeiro_", livro_csv["Content-Disposition"])
        self.assertIn(b"PIX Matriz", livro_csv.content)

    def test_cadastra_conta_movimento_e_filtra_na_baixa(self):
        response = self.client.post(
            "/financeiro/contas-movimento/nova/",
            {
                "filial": self.filial.pk,
                "nome": "Caixa administrativo",
                "tipo": TipoContaMovimento.CAIXA,
                "saldo_inicial": "100.00",
                "ativa": "on",
            },
            follow=True,
        )

        self.assertRedirects(response, "/financeiro/contas-movimento/")
        self.assertContains(response, "Caixa administrativo")
        baixa = self.client.get(f"/financeiro/{self.conta.pk}/baixar/")
        self.assertContains(baixa, "Conta de movimento")
        self.assertContains(baixa, "Caixa administrativo")

    def test_transferencia_entre_contas_gera_lancamentos_espelhados(self):
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa loja",
            tipo=TipoContaMovimento.CAIXA,
            saldo_inicial=Decimal("300.00"),
        )
        banco = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco operacional",
            tipo=TipoContaMovimento.BANCO,
            saldo_inicial=Decimal("20.00"),
        )

        transferencia = realizar_transferencia(
            conta_origem=caixa,
            conta_destino=banco,
            valor=Decimal("120.00"),
            data=timezone.localdate(),
            usuario=self.user,
            descricao="Deposito no banco",
        )

        self.assertEqual(TransferenciaFinanceira.objects.count(), 1)
        self.assertEqual(transferencia.lancamentos.count(), 2)
        self.assertEqual(caixa.saldo_atual, Decimal("180.00"))
        self.assertEqual(banco.saldo_atual, Decimal("140.00"))
        self.assertTrue(LogAuditoria.objects.filter(modulo="financeiro", acao="TRANSFERENCIA").exists())
        self.assertEqual(
            LancamentoFinanceiro.objects.filter(transferencia=transferencia, tipo=TipoLancamentoFinanceiro.SAIDA).count(),
            1,
        )
        self.assertEqual(
            LancamentoFinanceiro.objects.filter(transferencia=transferencia, tipo=TipoLancamentoFinanceiro.ENTRADA).count(),
            1,
        )
        with self.assertRaises(ValidationError):
            transferencia.save()
        with self.assertRaises(ValidationError):
            transferencia.delete()

    def test_transferencia_bloqueia_saldo_insuficiente(self):
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa pequeno",
            tipo=TipoContaMovimento.CAIXA,
            saldo_inicial=Decimal("30.00"),
        )
        banco = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco",
            tipo=TipoContaMovimento.BANCO,
            saldo_inicial=Decimal("0.00"),
        )

        with self.assertRaisesMessage(ValidationError, "Saldo insuficiente"):
            realizar_transferencia(
                conta_origem=caixa,
                conta_destino=banco,
                valor=Decimal("31.00"),
                data=timezone.localdate(),
                usuario=self.user,
            )

        self.assertFalse(TransferenciaFinanceira.objects.exists())
        self.assertFalse(LancamentoFinanceiro.objects.filter(origem="TRANSFERENCIA").exists())

    def test_tela_de_transferencia_financeira(self):
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa financeiro",
            tipo=TipoContaMovimento.CAIXA,
            saldo_inicial=Decimal("200.00"),
        )
        banco = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco caixa",
            tipo=TipoContaMovimento.BANCO,
            saldo_inicial=Decimal("0.00"),
        )

        formulario = self.client.get("/financeiro/transferencias/nova/")
        response = self.client.post(
            "/financeiro/transferencias/nova/",
            {
                "conta_origem": caixa.pk,
                "conta_destino": banco.pk,
                "valor": "75.00",
                "data": timezone.localdate().isoformat(),
                "descricao": "Sangria para banco",
            },
            follow=True,
        )

        self.assertContains(formulario, "Transferencia entre contas")
        self.assertContains(formulario, "Transferencias recentes")
        self.assertRedirects(response, "/financeiro/livro/")
        self.assertContains(response, "Transferencia #")
        self.assertContains(response, "Sangria para banco")

    def test_estorno_cria_lancamento_inverso_e_bloqueia_duplicidade(self):
        conta_pix = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX estorno",
            tipo=TipoContaMovimento.PIX,
            saldo_inicial=Decimal("10.00"),
        )
        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="PIX",
            conta_movimento=conta_pix,
        )
        lancamento = LancamentoFinanceiro.objects.get(conta_financeira=self.conta_receber)

        estorno = estornar_lancamento(
            lancamento=lancamento,
            usuario=self.user,
            motivo="Recebimento duplicado",
            data=timezone.localdate(),
        )

        self.assertEqual(estorno.tipo, TipoLancamentoFinanceiro.SAIDA)
        self.assertEqual(estorno.valor, lancamento.valor)
        self.assertEqual(estorno.estorno_de, lancamento)
        self.assertEqual(conta_pix.saldo_atual, Decimal("10.00"))
        self.assertTrue(LogAuditoria.objects.filter(modulo="financeiro", acao="ESTORNO_LANCAMENTO").exists())
        with self.assertRaisesMessage(ValidationError, "ja possui estorno"):
            estornar_lancamento(lancamento=lancamento, usuario=self.user, motivo="Repetido")
        with self.assertRaisesMessage(ValidationError, "não pode ser estornado novamente"):
            estornar_lancamento(lancamento=estorno, usuario=self.user, motivo="Reversao indevida")

    def test_tela_livro_estorna_lancamento_com_motivo(self):
        conta_pix = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX livro",
            tipo=TipoContaMovimento.PIX,
            saldo_inicial=Decimal("0.00"),
        )
        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="PIX",
            conta_movimento=conta_pix,
        )
        lancamento = LancamentoFinanceiro.objects.get(conta_financeira=self.conta_receber)

        response = self.client.post(
            f"/financeiro/livro/{lancamento.pk}/estornar/",
            {"motivo": "Erro de baixa"},
            follow=True,
        )

        self.assertRedirects(response, "/financeiro/livro/")
        self.assertContains(response, "Estorno registrado")
        self.assertContains(response, "Estorno do lançamento")
        self.assertContains(response, "Fechado")
        self.assertEqual(LancamentoFinanceiro.objects.filter(estorno_de=lancamento).count(), 1)
    def test_conciliacao_bancaria_preserva_livro_audita_e_exporta(self):
        conta_banco = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco Matriz",
            tipo=TipoContaMovimento.BANCO,
        )
        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="TED",
            conta_movimento=conta_banco,
        )
        lancamento = LancamentoFinanceiro.objects.get(conta_financeira=self.conta_receber)

        tela_pendente = self.client.get("/financeiro/conciliacao-bancaria/", {"status": "pendente"})
        response = self.client.post(
            f"/financeiro/conciliacao-bancaria/{lancamento.pk}/conciliar/",
            {
                "data_conciliacao": timezone.localdate().isoformat(),
                "referencia_externa": "TED-2026-00091",
                "observacao": "Conferido no extrato bancario",
            },
            REMOTE_ADDR="127.0.0.20",
            follow=True,
        )
        duplicada = self.client.post(
            f"/financeiro/conciliacao-bancaria/{lancamento.pk}/conciliar/",
            {"referencia_externa": "OUTRA-REFERENCIA"},
            follow=True,
        )
        tela_conciliada = self.client.get("/financeiro/conciliacao-bancaria/", {"status": "conciliado"})
        csv_response = self.client.get("/financeiro/conciliacao-bancaria/exportar.csv", {"status": "conciliado"})

        self.assertContains(tela_pendente, "Pendente")
        self.assertRedirects(response, "/financeiro/conciliacao-bancaria/")
        self.assertContains(response, "conciliado com o extrato")
        conciliacao = ConciliacaoLancamentoFinanceiro.objects.get(lancamento=lancamento)
        self.assertEqual(conciliacao.referencia_externa, "TED-2026-00091")
        self.assertContains(duplicada, "ja foi conciliado")
        self.assertEqual(ConciliacaoLancamentoFinanceiro.objects.filter(lancamento=lancamento).count(), 1)
        self.assertContains(tela_conciliada, "TED-2026-00091")
        self.assertIn("TED-2026-00091", csv_response.content.decode("utf-8-sig"))
        log = LogAuditoria.objects.get(acao="CONCILIA_LANCAMENTO_FINANCEIRO", objeto_id=str(conciliacao.pk))
        self.assertEqual(log.usuario, self.user)
        self.assertEqual(log.ip, "127.0.0.20")
        with self.assertRaises(ValidationError):
            conciliacao.save()
        lancamento.refresh_from_db()
        self.assertEqual(lancamento.valor, Decimal("210.00"))
    def test_diagnostico_contabil_informa_quando_adaptador_nao_esta_configurado(self):
        response = self.client.get("/financeiro/resultado/integracao-contabil.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["contrato"], "financial_accounting_adapter_readiness_v1")
        self.assertFalse(response.json()["configurado"])
        self.assertTrue(response.json()["envio_permitido"])
        tela = self.client.get("/financeiro/resultado/")
        self.assertContains(tela, "Integração ainda não configurada")
        self.assertContains(tela, "Histórico de integração contábil")

    @override_settings(FINANCEIRO_CONTABIL_ADAPTER="apps.financeiro.tests.FakeContabilAdapter")
    def test_envio_contabil_e_idempotente_e_auditado(self):
        FakeContabilAdapter.chamadas = 0
        data = timezone.localdate()
        url = (
            f"/financeiro/resultado/enviar-contabilidade/?data_inicio={data.isoformat()}"
            f"&data_fim={data.isoformat()}&filial={self.filial.pk}"
        )

        primeira = self.client.post(url, REMOTE_ADDR="127.0.0.31", follow=True)
        segunda = self.client.post(url, REMOTE_ADDR="127.0.0.31", follow=True)

        self.assertContains(primeira, "Pacote contábil enviado")
        self.assertContains(segunda, "já foi enviado")
        self.assertEqual(FakeContabilAdapter.chamadas, 1)
        exportacao = ExportacaoContabil.objects.get()
        self.assertEqual(exportacao.empresa, self.empresa)
        self.assertEqual(exportacao.filial, self.filial)
        self.assertEqual(exportacao.status, StatusExportacaoContabil.ENVIADO)
        self.assertEqual(exportacao.protocolo, "CONT-2026-0001")
        self.assertEqual(len(exportacao.chave_idempotencia), 64)
        self.assertEqual(FakeContabilAdapter.ultimo_payload["empresa"]["id"], self.empresa.pk)
        self.assertEqual(FakeContabilAdapter.ultimo_payload["filial"]["id"], self.filial.pk)
        self.assertEqual(FakeContabilAdapter.ultima_chave, exportacao.chave_idempotencia)
        log = LogAuditoria.objects.get(acao="EXPORTACAO_CONTABIL", objeto_id=str(exportacao.pk))
        self.assertEqual(log.usuario, self.user)
        self.assertEqual(log.ip, "127.0.0.31")

    @override_settings(FINANCEIRO_CONTABIL_ADAPTER="apps.financeiro.tests.FakeContabilAdapter")
    def test_usuario_financeiro_consulta_mas_nao_envia_pacote_contabil(self):
        usuario = get_user_model().objects.create_user("financeiro", password="123")
        PerfilUsuario.objects.create(usuario=usuario, filial=self.filial, tipo=TipoPerfil.FINANCEIRO)
        self.client.force_login(usuario)
        data = timezone.localdate().isoformat()

        diagnostico = self.client.get("/financeiro/resultado/integracao-contabil.json")
        envio = self.client.post(
            f"/financeiro/resultado/enviar-contabilidade/?data_inicio={data}&data_fim={data}&filial={self.filial.pk}"
        )

        self.assertEqual(diagnostico.status_code, 200)
        self.assertFalse(diagnostico.json()["envio_permitido"])
        self.assertEqual(envio.status_code, 403)
        self.assertFalse(ExportacaoContabil.objects.exists())