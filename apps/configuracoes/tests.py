from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.empresas.models import Empresa, Filial
from apps.financeiro.models import ContaMovimentoFinanceiro, TipoContaMovimento
from apps.pdv.models import TerminalPdv
from apps.vendas.models import FormaPagamento

from .models import ConfiguracaoImpressao, ModeloPapel, TipoDocumentoImpressao
from .services import configuracao_impressao_para, criar_configuracoes_padrao, estilos_impressao


class ConfiguracoesOperacionaisTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(
            razao_social="Supermercado Modelo Ltda",
            nome_fantasia="Supermercado Modelo",
            cnpj="22.222.222/0001-22",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)

    def test_cria_configuracoes_padrao_e_resolve_por_filial(self):
        criadas = criar_configuracoes_padrao()

        self.assertGreater(criadas, 0)
        config = configuracao_impressao_para(self.filial, TipoDocumentoImpressao.CUPOM_NAO_FISCAL)
        self.assertIsNotNone(config)
        self.assertEqual(config.modelo_papel, ModeloPapel.BOBINA_80)
        self.assertIsNotNone(configuracao_impressao_para(self.filial, TipoDocumentoImpressao.CUPOM_FISCAL))
        estilo = estilos_impressao(config)
        self.assertEqual(estilo["largura"], "80mm")
        self.assertIn("mm", estilo["margem_css"])

    def test_tela_impressoes_e_backup_operacional(self):
        criar_configuracoes_padrao()

        impressoes = self.client.get("/configuracoes/impressoes/")
        backup = self.client.get("/configuracoes/backup/download/")
        checklist = self.client.get("/configuracoes/checklist/")

        self.assertEqual(impressoes.status_code, 200)
        self.assertContains(impressoes, "Central de impressao")
        self.assertContains(impressoes, "Cupom fiscal")
        self.assertContains(impressoes, "Com gaveta")
        self.assertContains(impressoes, "Sem impressora")
        self.assertContains(impressoes, "Descoberta local preparada para o app desktop")
        self.assertContains(impressoes, "Ver ponto de integracao")
        self.assertContains(impressoes, "Configuracoes do desktop")
        self.assertEqual(backup.status_code, 200)
        self.assertEqual(backup["Content-Type"], "application/json; charset=utf-8")
        self.assertTrue(backup.content.startswith(b"["))
        self.assertContains(checklist, "Testes automatizados")
        self.assertContains(checklist, "Padrao R$ em todos os formularios")
        self.assertContains(checklist, "Campos numericos de preco")
        self.assertContains(checklist, "Entradas, saidas e livro contabil")
        self.assertContains(checklist, "livro financeiro imutavel")
        self.assertContains(checklist, "Contas de movimento por filial")
        self.assertContains(checklist, "vendas a vista do PDV geram entradas automaticas")
        self.assertContains(checklist, "sangria e suprimento geram saida/entrada automatica")
        self.assertContains(checklist, "transferencias entre contas")
        self.assertContains(checklist, "estornos por lancamento inverso")
        self.assertContains(checklist, "relatorio de receitas, despesas e resultado")
        self.assertContains(checklist, "Gaveta de dinheiro opcional")
        self.assertContains(checklist, "Central de impressao permite")
        self.assertContains(checklist, "PIX dinamico")
        self.assertContains(checklist, "somente apos pagamento confirmado")
        self.assertContains(checklist, "autorizacao simulada rastreavel")
        self.assertContains(checklist, "Arquitetura PDV desktop local")
        self.assertContains(checklist, "sem telas administrativas completas")
        self.assertContains(checklist, "Sincronizacao loja-nuvem")
        self.assertContains(checklist, "Empresa escolhe entre servidor local")
        self.assertContains(checklist, "dados de pagamento eletronico")
        self.assertContains(checklist, "Eventos recebidos ficam armazenados")
        self.assertContains(checklist, "Caixa de saida, processador HTTP")
        self.assertContains(checklist, "retentativa exponencial")
        self.assertContains(checklist, "caixa de entrada autenticada")
        self.assertContains(checklist, "processador interno com handlers por tipo")
        self.assertContains(checklist, "handler inicial de produtos")
        self.assertContains(checklist, "handler de saldo de estoque por filial")
        self.assertContains(checklist, "espelho de venda finalizada com painel")
        self.assertContains(checklist, "espelho fiscal sincronizado")
        self.assertContains(checklist, "detalhe auditavel de eventos")
        self.assertContains(checklist, "resolucao manual de conflitos")
        self.assertContains(checklist, "exportacao CSV das filas")
        self.assertContains(checklist, "comando unico agendavel")
        self.assertContains(checklist, "roteiro do Agendador de Tarefas")

    def test_painel_sistema_centraliza_admin_proprio(self):
        response = self.client.get("/configuracoes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Painel do sistema")
        self.assertContains(response, "Empresas e filiais")
        self.assertContains(response, "Usuarios")
        self.assertContains(response, "Fiscal")
        self.assertContains(response, "Formas de pagamento")
        self.assertContains(response, "Terminais PDV")
        self.assertNotContains(response, "Admin Django")
        self.assertContains(response, "Checklist")

    def test_cadastra_e_edita_forma_pagamento_no_painel_proprio(self):
        conta_pix = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX Caixa 01",
            tipo=TipoContaMovimento.PIX,
        )
        form_response = self.client.get("/configuracoes/formas-pagamento/nova/")
        response = self.client.post(
            "/configuracoes/formas-pagamento/nova/",
            {"nome": "PIX integrado", "tipo": "PIX", "conta_movimento_padrao": conta_pix.pk, "exige_autorizacao": "on", "ativo": "on"},
        )

        self.assertContains(form_response, "Conta movimento padrao")
        self.assertContains(form_response, "select2-field")
        self.assertRedirects(response, "/configuracoes/formas-pagamento/")
        forma = FormaPagamento.objects.get(nome="PIX integrado")
        self.assertTrue(forma.exige_autorizacao)
        self.assertEqual(forma.conta_movimento_padrao, conta_pix)
        lista = self.client.get("/configuracoes/formas-pagamento/")
        self.assertContains(lista, "PIX integrado")
        self.assertContains(lista, "PIX Caixa 01")

        invalida = self.client.post(
            f"/configuracoes/formas-pagamento/{forma.pk}/editar/",
            {"nome": forma.nome, "tipo": "PIX", "permite_troco": "on", "ativo": "on"},
        )
        self.assertContains(invalida, "Troco deve ser habilitado somente")

    def test_cadastra_terminal_pdv_no_painel_proprio(self):
        response = self.client.post(
            "/configuracoes/terminais-pdv/novo/",
            {
                "filial": self.filial.id,
                "nome": "Caixa 01",
                "descricao": "Frente de loja",
                "permite_modo_offline": "on",
                "ativo": "on",
            },
            follow=True,
        )

        self.assertRedirects(response, "/configuracoes/terminais-pdv/")
        terminal = TerminalPdv.objects.get(nome="Caixa 01")
        self.assertEqual(terminal.filial, self.filial)
        self.assertTrue(terminal.permite_modo_offline)
        self.assertTrue(terminal.chave_api_hash)
        self.assertTrue(terminal.chave_api_prefixo)
        self.assertContains(response, "Caixa 01")
        self.assertContains(response, "servidor local da loja")
        self.assertContains(response, str(terminal.identificador))
        self.assertContains(response, "sera mostrada somente agora")
        self.assertContains(response, terminal.chave_api_prefixo)

        segunda_visualizacao = self.client.get("/configuracoes/terminais-pdv/")
        self.assertNotContains(segunda_visualizacao, "sera mostrada somente agora")

        form_response = self.client.get(f"/configuracoes/terminais-pdv/{terminal.pk}/editar/")
        self.assertContains(form_response, "select2-field")
        self.assertContains(form_response, str(terminal.identificador))

    def test_renova_chave_do_terminal_e_invalida_a_anterior(self):
        terminal = TerminalPdv(filial=self.filial, nome="Caixa 03")
        chave_anterior = terminal.gerar_chave_api()
        terminal.save()

        response = self.client.post(
            f"/configuracoes/terminais-pdv/{terminal.pk}/regenerar-chave/",
            follow=True,
        )

        terminal.refresh_from_db()
        self.assertRedirects(response, "/configuracoes/terminais-pdv/")
        self.assertFalse(terminal.validar_chave_api(chave_anterior))
        self.assertContains(response, "Chave do terminal renovada")
        self.assertContains(response, "sera mostrada somente agora")

    def test_edita_configuracao_impressao(self):
        ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            modelo_papel=ModeloPapel.BOBINA_58,
        )
        config = ConfiguracaoImpressao.objects.get()

        response = self.client.post(
            f"/configuracoes/impressoes/{config.id}/editar/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "tipo_documento": TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
                "modelo_papel": ModeloPapel.BOBINA_80,
                "exibir_logo": "on",
                "tamanho_fonte": 12,
                "margem_superior_mm": 4,
                "margem_inferior_mm": 4,
                "margem_esquerda_mm": 4,
                "margem_direita_mm": 4,
                "mensagem_rodape": "Obrigado pela preferencia.",
                "impressora_padrao": "Caixa 01",
                "gaveta_automatica": "on",
                "abrir_gaveta_em_dinheiro": "on",
                "abrir_gaveta_em_movimento_caixa": "on",
                "numero_vias": 2,
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        config.refresh_from_db()
        self.assertEqual(config.modelo_papel, ModeloPapel.BOBINA_80)
        self.assertEqual(config.numero_vias, 2)
        self.assertEqual(config.impressora_padrao, "Caixa 01")
        self.assertTrue(config.gaveta_automatica)
        self.assertTrue(config.abrir_gaveta_em_dinheiro)
        self.assertTrue(config.abrir_gaveta_em_movimento_caixa)

        form_response = self.client.get(f"/configuracoes/impressoes/{config.id}/editar/")
        self.assertContains(form_response, "printer-suggestions")
        self.assertContains(form_response, "select2-field")
        self.assertContains(form_response, "impressoras detectadas na maquina")
        self.assertContains(form_response, "Gaveta de dinheiro")
        self.assertContains(form_response, "sem tentar acionar gaveta fisica")

        list_response = self.client.get("/configuracoes/impressoes/")
        self.assertContains(list_response, "Com gaveta")
        self.assertContains(list_response, "Dinheiro")

    def test_gaveta_automatica_nao_e_obrigatoria_e_so_serve_para_caixa(self):
        response = self.client.post(
            "/configuracoes/impressoes/nova/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "tipo_documento": TipoDocumentoImpressao.RELATORIO,
                "modelo_papel": ModeloPapel.A4,
                "tamanho_fonte": 10,
                "margem_superior_mm": 5,
                "margem_inferior_mm": 5,
                "margem_esquerda_mm": 5,
                "margem_direita_mm": 5,
                "impressora_padrao": "PDF",
                "gaveta_automatica": "on",
                "abrir_gaveta_em_dinheiro": "on",
                "numero_vias": 1,
                "is_active": "on",
            },
        )
        self.assertContains(response, "Gaveta automatica deve ser configurada apenas")

        response = self.client.post(
            "/configuracoes/impressoes/nova/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "tipo_documento": TipoDocumentoImpressao.RELATORIO,
                "modelo_papel": ModeloPapel.A4,
                "tamanho_fonte": 10,
                "margem_superior_mm": 5,
                "margem_inferior_mm": 5,
                "margem_esquerda_mm": 5,
                "margem_direita_mm": 5,
                "impressora_padrao": "PDF",
                "numero_vias": 1,
                "is_active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        config = ConfiguracaoImpressao.objects.get(tipo_documento=TipoDocumentoImpressao.RELATORIO)
        self.assertFalse(config.gaveta_automatica)
        self.assertFalse(config.abrir_gaveta_em_dinheiro)

    def test_endpoint_impressoras_locais_prepara_app_desktop(self):
        ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="Caixa 01",
        )

        response = self.client.get("/configuracoes/impressoes/impressoras-locais.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "desktop_bridge_required")
        self.assertIn("Caixa 01", payload["impressoras_cadastradas"])

    def test_endpoint_impressoes_desktop_expõe_regras_de_gaveta(self):
        ConfiguracaoImpressao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            impressora_padrao="EPSON TM-T20",
            impressao_automatica=True,
            gaveta_automatica=True,
            abrir_gaveta_em_dinheiro=True,
            abrir_gaveta_em_movimento_caixa=False,
        )

        response = self.client.get("/configuracoes/impressoes/desktop.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        config = payload["configuracoes"][0]
        self.assertEqual(config["impressora_padrao"], "EPSON TM-T20")
        self.assertTrue(config["impressao_automatica"])
        self.assertTrue(config["gaveta"]["automatica"])
        self.assertTrue(config["gaveta"]["abrir_em_dinheiro"])
        self.assertFalse(config["gaveta"]["abrir_em_movimento_caixa"])
        self.assertFalse(config["gaveta"]["bloqueia_venda_se_indisponivel"])

# Create your tests here.
