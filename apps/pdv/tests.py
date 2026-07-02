from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento, StatusVenda, Venda

from .models import AcessoPdvNuvem, Caixa, Sangria, StatusAcessoPdvNuvem, StatusCaixa
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
        self.assertEqual(self.client.session["pdv_cart"], {})
        self.assertEqual(Venda.objects.count(), 1)

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
        self.assertContains(resposta, "<kbd>Shift+M</kbd> Menu", count=1, html=True)

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
