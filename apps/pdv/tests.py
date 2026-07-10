from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.configuracoes.models import ConfiguracaoImpressao, TipoDocumentoImpressao
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque
from apps.financeiro.models import ContaMovimentoFinanceiro, LancamentoFinanceiro, TipoContaMovimento, TipoLancamentoFinanceiro
from apps.fiscal.models import AmbienteFiscal, ConfiguracaoFiscal, DocumentoFiscal, NaturezaOperacao, SerieFiscal, TipoDocumentoFiscal
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento, StatusVenda, Venda

from .models import AcessoPdvNuvem, Caixa, ModoIntegracaoTef, ProtocoloBalanca, ProvedorTef, Sangria, StatusAcessoPdvNuvem, StatusCaixa, StatusLicencaTerminal, Suprimento, TerminalPdv
from .services_acesso import acesso_pdv_nuvem_aprovado, decidir_acesso_pdv_nuvem, solicitar_acesso_pdv_nuvem


class AcessoPdvNuvemTests(TestCase):
    def setUp(self):
        User = get_user_model()
        empresa = Empresa.objects.create(razao_social="Mercado Nuvem", nome_fantasia="Mercado Nuvem", cnpj="12345678000190")
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz")
        self.operador = User.objects.create_user(username="operador", password="senha")
        PerfilUsuario.objects.create(usuario=self.operador, filial=self.filial, tipo=TipoPerfil.OPERADOR_CAIXA)
        self.admin = User.objects.create_user(username="admin", password="senha")
        PerfilUsuario.objects.create(usuario=self.admin, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)

    def test_terminal_autenticado_inicializa_e_registra_conexao(self):
        terminal = TerminalPdv(
            filial=self.filial,
            nome="Caixa 01",
            emite_documento_fiscal=False,
            provedor_tef=ProvedorTef.PAGBANK,
            modo_integracao_tef=ModoIntegracaoTef.DESKTOP_BRIDGE,
            status_licenca=StatusLicencaTerminal.LIBERADA,
            usa_balanca=True,
            protocolo_balanca=ProtocoloBalanca.SERIAL,
            porta_balanca="COM3",
            modelo_balanca="Toledo Prix",
        )
        chave = terminal.gerar_chave_api()
        terminal.save()

        resposta = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            REMOTE_ADDR="192.168.1.25",
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["terminal"]["nome"], "Caixa 01")
        self.assertTrue(resposta.json()["recursos"]["venda_local"])
        self.assertFalse(resposta.json()["terminal"]["emite_documento_fiscal"])
        self.assertFalse(resposta.json()["recursos"]["emissao_fiscal_automatica"])
        self.assertTrue(resposta.json()["recursos"]["tef_integrado"])
        self.assertEqual(resposta.json()["terminal"]["provedor_tef"], ProvedorTef.PAGBANK)
        self.assertEqual(resposta.json()["terminal"]["licenca"]["status"], StatusLicencaTerminal.LIBERADA)
        self.assertTrue(resposta.json()["terminal"]["licenca"]["liberada"])
        self.assertEqual(resposta.json()["licenciamento"]["modelo"], "por_terminal")
        self.assertTrue(resposta.json()["licenciamento"]["terminal_autorizado"])
        self.assertTrue(resposta.json()["recursos"]["balanca_local"])
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["contrato"], "pdv_scale_v1")
        self.assertTrue(resposta.json()["dispositivos"]["balanca"]["habilitada"])
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["protocolo"], ProtocoloBalanca.SERIAL)
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["porta"], "COM3")
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["modelo"], "Toledo Prix")
        self.assertTrue(resposta.json()["dispositivos"]["balanca"]["leitura_automatica"])
        self.assertTrue(resposta.json()["dispositivos"]["balanca"]["fallback_manual"])
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["unidade_padrao"], "KG")
        self.assertEqual(resposta.json()["dispositivos"]["balanca"]["precisao_decimal"], 3)
        self.assertEqual(resposta.json()["tef"]["contrato"], "pdv_tef_v1")
        self.assertIn("PIX", resposta.json()["tef"]["tipos_pagamento"])
        self.assertIsNone(resposta.json()["aplicativo"]["versao_cliente"])
        self.assertFalse(resposta.json()["aplicativo"]["atualizacao_disponivel"])
        self.assertTrue(resposta.json()["aplicativo"]["atualizacao_requer_admin_master"])
        terminal.refresh_from_db()
        self.assertIsNotNone(terminal.ultima_conexao)
        self.assertEqual(terminal.ultimo_ip, "192.168.1.25")

    @override_settings(PDV_DESKTOP_VERSION="0.3.0", PDV_DESKTOP_MIN_VERSION="0.2.0")
    def test_bootstrap_controla_versao_instalada_sem_atualizacao_automatica(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa versao", status_licenca=StatusLicencaTerminal.LIBERADA)
        chave = terminal.gerar_chave_api()
        terminal.save()

        opcional = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            HTTP_X_PDV_VERSION="0.2.5",
        )
        obrigatoria = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            HTTP_X_PDV_VERSION="0.1.9",
        )

        self.assertEqual(opcional.status_code, 200)
        self.assertTrue(opcional.json()["aplicativo"]["atualizacao_disponivel"])
        self.assertFalse(opcional.json()["aplicativo"]["atualizacao_obrigatoria"])
        self.assertEqual(opcional.json()["aplicativo"]["versao_vigente"], "0.3.0")
        self.assertTrue(obrigatoria.json()["aplicativo"]["atualizacao_obrigatoria"])
        self.assertTrue(obrigatoria.json()["aplicativo"]["atualizacao_requer_admin_master"])

    def test_terminal_rejeita_chave_invalida_e_terminal_inativo(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa 02", status_licenca=StatusLicencaTerminal.LIBERADA)
        chave = terminal.gerar_chave_api()
        terminal.save()

        invalida = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY="chave-errada",
        )
        self.assertEqual(invalida.status_code, 401)

        terminal.ativo = False
        terminal.save(update_fields=["ativo"])
        inativo = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
        )
        self.assertEqual(inativo.status_code, 403)

    def test_terminal_com_licenca_pendente_nao_inicializa(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa pendente", status_licenca=StatusLicencaTerminal.PENDENTE)
        chave = terminal.gerar_chave_api()
        terminal.save()

        resposta = self.client.get(
            "/pdv/api/terminal/bootstrap/",
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            HTTP_X_TERMINAL_KEY=chave,
            REMOTE_ADDR="10.0.0.55",
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.json()["status"], "licenca_terminal_bloqueada")
        self.assertEqual(resposta.json()["licenca"]["status"], StatusLicencaTerminal.PENDENTE)
        terminal.refresh_from_db()
        self.assertIsNone(terminal.ultima_conexao)
        log = LogAuditoria.objects.get(acao="BOOTSTRAP_TERMINAL_SEM_LICENCA", objeto_id=str(terminal.id))
        self.assertEqual(log.modulo, "pdv")
        self.assertEqual(log.ip, "10.0.0.55")
        self.assertIn("Pendente", log.descricao)

    def test_solicitacao_pendente_nao_duplica(self):
        primeira, criada = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial, ip="127.0.0.1")
        segunda, criada_novamente = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial, ip="127.0.0.1")

        self.assertTrue(criada)
        self.assertFalse(criada_novamente)
        self.assertEqual(primeira, segunda)
        self.assertEqual(primeira.status, StatusAcessoPdvNuvem.PENDENTE)

    def test_admin_aprova_acesso_do_operador(self):
        solicitacao, _ = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)

        decidir_acesso_pdv_nuvem(solicitacao=solicitacao, admin=self.admin, aprovar=True)

        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusAcessoPdvNuvem.APROVADO)
        self.assertEqual(solicitacao.decidido_por, self.admin)
        self.assertTrue(acesso_pdv_nuvem_aprovado(self.operador, self.filial))

    def test_operador_nao_decide_solicitacao(self):
        solicitacao, _ = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)

        with self.assertRaises(ValidationError):
            decidir_acesso_pdv_nuvem(solicitacao=solicitacao, admin=self.operador, aprovar=False)

    def test_painel_de_acessos_exige_supervisao(self):
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/acessos-nuvem/")

        self.assertEqual(resposta.status_code, 403)

    def test_admin_aprova_pelo_painel_de_acessos(self):
        solicitacao, _ = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)
        self.client.force_login(self.admin)

        resposta = self.client.post(
            f"/pdv/acessos-nuvem/{solicitacao.id}/decidir/",
            {"acao": "aprovar", "justificativa": "Caixa autorizado"},
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/acessos-nuvem/")
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusAcessoPdvNuvem.APROVADO)
        self.assertEqual(solicitacao.decidido_por, self.admin)
        self.assertContains(resposta, "Caixa autorizado")

    def test_alerta_visual_de_acesso_pendente_aparece_para_admin(self):
        solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)
        self.client.force_login(self.admin)

        resposta = self.client.get("/pdv/acessos-nuvem/")

        self.assertContains(resposta, "1 acesso pendente")
        self.assertContains(resposta, "Ha operador aguardando liberacao")

    @override_settings(PDV_NUVEM_REQUER_APROVACAO=True)
    def test_pdv_nuvem_bloqueia_operador_sem_aprovacao(self):
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 403)
        self.assertContains(resposta, "Acesso ao PDV em nuvem pendente", status_code=403)
        self.assertEqual(AcessoPdvNuvem.objects.filter(usuario=self.operador, status=StatusAcessoPdvNuvem.PENDENTE).count(), 1)

    @override_settings(PDV_NUVEM_REQUER_APROVACAO=True)
    def test_pdv_nuvem_libera_operador_aprovado(self):
        solicitacao, _ = solicitar_acesso_pdv_nuvem(usuario=self.operador, filial=self.filial)
        decidir_acesso_pdv_nuvem(solicitacao=solicitacao, admin=self.admin, aprovar=True)
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)

    def test_finalizar_venda_volta_ao_pdv_limpa_carrinho_e_mostra_popup(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000001", nome="Arroz", categoria=categoria, preco_custo=Decimal("10"), preco_venda=Decimal("15"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "2"}
        session.save()
        self.client.force_login(self.operador)

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["30.00"],
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        self.assertContains(resposta, "Carrinho liberado para a proxima compra.")
        self.assertContains(resposta, "Nenhum item no carrinho.")
        venda = Venda.objects.get()
        self.assertContains(resposta, f'data-print-url="/pdv/vendas/{venda.id}/recibo/"')
        self.assertContains(resposta, f'data-desktop-print-url="/pdv/vendas/{venda.id}/impressao-desktop.json"')
        self.assertEqual(self.client.session["pdv_cart"], {})
        self.assertEqual(Venda.objects.count(), 1)

    def test_terminal_sem_fiscal_automatico_finaliza_venda_sem_preparar_nfce(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(
            codigo_barras="789100000006",
            nome="Macarrao",
            categoria=categoria,
            preco_custo=Decimal("4"),
            preco_venda=Decimal("9"),
            ncm="19021900",
            origem_mercadoria="0",
            cst_icms="00",
            aliquota_icms=Decimal("18.00"),
        )
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            regime_tributario="Regime normal",
            inscricao_estadual="123456789",
            csc_id="1",
            csc_token="token",
            certificado_a1_criptografado=b"certificado",
            certificado_senha_criptografada=b"senha",
        )
        SerieFiscal.objects.create(filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE, serie=1, proximo_numero=1)
        NaturezaOperacao.objects.create(descricao="Venda ao consumidor", cfop="5102", tipo_documento=TipoDocumentoFiscal.NFCE)
        terminal = TerminalPdv.objects.create(filial=self.filial, nome="Caixa sem fiscal", emite_documento_fiscal=False)
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "1"}
        session.save()
        self.client.force_login(self.operador)

        resposta = self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["9.00"],
            },
            HTTP_X_TERMINAL_ID=str(terminal.identificador),
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        self.assertEqual(Venda.objects.count(), 1)
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_pdv_exibe_fechamento_e_conferencia_no_modal_de_caixas(self):
        Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=self.operador,
            usuario_fechamento=self.operador,
            valor_inicial=Decimal("50"),
            valor_final=Decimal("80"),
            status=StatusCaixa.FECHADO,
        )
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Fechar caixa")
        self.assertContains(resposta, "Suprimento")
        self.assertContains(resposta, "Sangria")
        self.assertContains(resposta, "Aguardando conferencia")
        self.assertContains(resposta, "Conferir")

    def test_pdv_exibe_pagamento_eletronico_e_menu_superior_sem_menu_inferior_duplicado(self):
        FormaPagamento.objects.create(nome="Pix", tipo="PIX")
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<kbd>F3</kbd> Eletronico", html=True)
        self.assertContains(resposta, "<kbd>F3</kbd> PIX", html=True)
        self.assertContains(resposta, "Adicionar forma")
        self.assertContains(resposta, "Shift +")
        self.assertContains(resposta, "Remover forma de pagamento (Del)")
        self.assertContains(resposta, "Remover item (Del)")
        self.assertContains(resposta, "Ctrl+Del")
        self.assertContains(resposta, "data-remove-url")
        self.assertContains(resposta, "data-pdv-read-scale")
        self.assertContains(resposta, "<kbd>F12</kbd>", html=True)
        self.assertContains(resposta, "<kbd>Shift+M</kbd> Menu", count=1, html=True)
        self.assertContains(resposta, "Navegador")

    def test_pdv_exibe_status_fiscal_do_terminal_identificado(self):
        terminal = TerminalPdv.objects.create(filial=self.filial, nome="Caixa sem fiscal", emite_documento_fiscal=False)
        self.client.force_login(self.operador)

        resposta = self.client.get("/pdv/", HTTP_X_TERMINAL_ID=str(terminal.identificador))

        self.assertContains(resposta, "Fiscal")
        self.assertContains(resposta, "Desligado")

    def test_sangria_registrada_pelo_pdv_retorna_ao_pdv(self):
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        self.client.force_login(self.operador)

        resposta = self.client.post(
            f"/pdv/caixas/{caixa.id}/sangria/",
            {
                "next": "pdv",
                "valor": "10.00",
                "motivo": "Retirada parcial",
                "supervisor_usuario": "admin",
                "supervisor_senha": "senha",
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        self.assertEqual(Sangria.objects.filter(caixa=caixa, valor=Decimal("10.00")).count(), 1)
        sangria = Sangria.objects.get(caixa=caixa)
        conta = ContaMovimentoFinanceiro.objects.get(filial=self.filial, nome="Caixa PDV", tipo=TipoContaMovimento.CAIXA)
        lancamento = LancamentoFinanceiro.objects.get(sangria=sangria)
        self.assertEqual(lancamento.conta, conta)
        self.assertEqual(lancamento.tipo, TipoLancamentoFinanceiro.SAIDA)
        self.assertEqual(lancamento.valor, Decimal("10.00"))

    def test_suprimento_registrado_pelo_pdv_entra_no_livro_financeiro(self):
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        self.client.force_login(self.operador)

        resposta = self.client.post(
            f"/pdv/caixas/{caixa.id}/suprimento/",
            {
                "next": "pdv",
                "valor": "25.00",
                "motivo": "Troco inicial extra",
                "supervisor_usuario": "admin",
                "supervisor_senha": "senha",
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        suprimento = Suprimento.objects.get(caixa=caixa)
        conta = ContaMovimentoFinanceiro.objects.get(filial=self.filial, nome="Caixa PDV", tipo=TipoContaMovimento.CAIXA)
        lancamento = LancamentoFinanceiro.objects.get(suprimento=suprimento)
        self.assertEqual(lancamento.conta, conta)
        self.assertEqual(lancamento.tipo, TipoLancamentoFinanceiro.ENTRADA)
        self.assertEqual(lancamento.valor, Decimal("25.00"))

    def test_pdv_exibe_estorno_e_cancela_venda_com_supervisor(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000002", nome="Feijao", categoria=categoria, preco_custo=Decimal("7"), preco_venda=Decimal("12"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO")
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "1"}
        session.save()
        self.client.force_login(self.operador)
        self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["12.00"],
            },
        )
        venda = Venda.objects.get()

        tela = self.client.get("/pdv/")
        self.assertContains(tela, "Estorno")
        self.assertContains(tela, f"Venda #{venda.id}")

        resposta = self.client.post(
            f"/pdv/vendas/{venda.id}/cancelar/",
            {
                "next": "pdv",
                "motivo": "Cupom emitido incorreto",
                "supervisor_usuario": "admin",
                "supervisor_senha": "senha",
            },
            follow=True,
        )

        self.assertRedirects(resposta, "/pdv/")
        venda.refresh_from_db()
        self.assertEqual(venda.status, StatusVenda.CANCELADA)

    def test_payload_de_impressao_desktop_da_venda_inclui_gaveta_opcional(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        produto = Produto.objects.create(codigo_barras="789100000003", nome="Cafe", categoria=categoria, preco_custo=Decimal("8"), preco_venda=Decimal("14.50"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        ConfiguracaoImpressao.objects.create(
            empresa=self.filial.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="EPSON TM-T20",
            impressao_automatica=True,
            gaveta_automatica=True,
            abrir_gaveta_em_dinheiro=True,
        )
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "2"}
        session.save()
        self.client.force_login(self.operador)
        self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["29.00"],
            },
        )
        venda = Venda.objects.get()

        response = self.client.get(f"/pdv/vendas/{venda.id}/impressao-desktop.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["venda"]["cliente"], "Cliente avulso")
        self.assertEqual(payload["venda"]["total_liquido"], "29.00")
        self.assertEqual(payload["itens"][0]["quantidade"], "2")
        self.assertEqual(payload["pagamentos"][0]["tipo"], "DINHEIRO")
        self.assertEqual(payload["impressao"]["impressora_padrao"], "EPSON TM-T20")
        self.assertTrue(payload["impressao"]["impressao_automatica"])
        self.assertTrue(payload["gaveta"]["abrir"])
        self.assertFalse(payload["gaveta"]["bloqueia_venda_se_indisponivel"])

    def test_recibo_e_payload_desktop_exibem_autorizacao_eletronica(self):
        categoria = Categoria.objects.create(nome="Bebidas")
        produto = Produto.objects.create(codigo_barras="789100000004", nome="Suco", categoria=categoria, preco_custo=Decimal("3"), preco_venda=Decimal("8.50"))
        Estoque.objects.create(produto=produto, filial=self.filial, quantidade_atual=Decimal("10"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.operador, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="PIX dinamico", tipo="PIX")
        session = self.client.session
        session["pdv_cart"] = {str(produto.id): "1"}
        session.save()
        self.client.force_login(self.operador)
        self.client.post(
            "/pdv/",
            {
                "action": "finish",
                "caixa": caixa.id,
                "cliente": "",
                "desconto": "0",
                "vencimento_financeiro": "",
                "pagamento_forma": [forma.id],
                "pagamento_valor": ["8.50"],
            },
        )
        venda = Venda.objects.get()
        pagamento = venda.pagamentos.get()

        recibo = self.client.get(f"/pdv/vendas/{venda.id}/recibo/")
        payload = self.client.get(f"/pdv/vendas/{venda.id}/impressao-desktop.json").json()

        self.assertContains(recibo, f"NSU {pagamento.nsu}")
        self.assertContains(recibo, f"Aut. {pagamento.codigo_autorizacao}")
        self.assertContains(recibo, pagamento.transacao_externa_id)
        self.assertEqual(payload["pagamentos"][0]["tipo"], "PIX")
        self.assertEqual(payload["pagamentos"][0]["transacao_externa_id"], pagamento.transacao_externa_id)
        self.assertEqual(payload["pagamentos"][0]["nsu"], pagamento.nsu)
        self.assertEqual(payload["pagamentos"][0]["codigo_autorizacao"], pagamento.codigo_autorizacao)
        self.assertIn("Autorizacao eletronica simulada", payload["pagamentos"][0]["mensagem_processadora"])
