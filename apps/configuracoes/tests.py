from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.empresas.models import Empresa, Filial

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
        self.assertContains(impressoes, "Sem impressora")
        self.assertEqual(backup.status_code, 200)
        self.assertEqual(backup["Content-Type"], "application/json; charset=utf-8")
        self.assertTrue(backup.content.startswith(b"["))
        self.assertContains(checklist, "Testes automatizados")
        self.assertContains(checklist, "Padrao R$ em todos os formularios")
        self.assertContains(checklist, "Campos numericos de preco")

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

# Create your tests here.
