from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial

from .admin import ConfiguracaoFiscalAdmin
from .certificados import abrir_csc, salvar_csc
from .models import AmbienteFiscal, CodigoRegimeTributario, ConfiguracaoFiscal, ModoTransicaoIbsCbs
from .perfis_uf import endpoints_nfce_uf


class ProtecaoCSCTests(TestCase):
    SEGREDO = "CSC-super-secreto-987"

    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Mercado CSC Ltda",
            nome_fantasia="Mercado CSC",
            cnpj="12345678000195",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Goiânia",
            cnpj="12345678000195",
            municipio="Goiânia",
            uf="GO",
            codigo_municipio_ibge="5208707",
        )
        urls = endpoints_nfce_uf("GO", AmbienteFiscal.HOMOLOGACAO)
        self.configuracao = ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            regime_tributario="Regime normal",
            crt=CodigoRegimeTributario.REGIME_NORMAL,
            inscricao_estadual="123456789",
            csc_id="1",
            url_qrcode_nfce=urls["qrcode"],
            url_consulta_nfce=urls["consulta"],
        )
        salvar_csc(self.configuracao, self.SEGREDO)
        self.master = get_user_model().objects.create_superuser(
            "master-csc", password="teste-123"
        )

    def _dados(self, **alteracoes):
        dados = {
            "filial": self.filial.pk,
            "ambiente": AmbienteFiscal.HOMOLOGACAO,
            "regime_tributario": "Regime normal",
            "crt": CodigoRegimeTributario.REGIME_NORMAL,
            "inscricao_estadual": "123456789",
            "csc_id": "1",
            "csc_token": "",
            "url_qrcode_nfce": self.configuracao.url_qrcode_nfce,
            "url_consulta_nfce": self.configuracao.url_consulta_nfce,
            "modo_transicao_ibs_cbs": ModoTransicaoIbsCbs.LEGADO,
            "ativo": "on",
        }
        dados.update(alteracoes)
        return dados

    def test_csc_e_criptografado_em_repouso_e_aberto_apenas_explicitamente(self):
        self.configuracao.refresh_from_db()

        self.assertTrue(self.configuracao.csc_configurado)
        self.assertEqual(abrir_csc(self.configuracao), self.SEGREDO)
        self.assertNotIn(
            self.SEGREDO.encode("utf-8"),
            bytes(self.configuracao.csc_token_criptografado),
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT csc_token_criptografado FROM fiscal_configuracaofiscal WHERE id = %s",
                [self.configuracao.pk],
            )
            armazenado = bytes(cursor.fetchone()[0])
        self.assertNotIn(self.SEGREDO.encode("utf-8"), armazenado)

    def test_tela_master_nao_reexibe_segredo_e_branco_preserva_token(self):
        self.client.force_login(self.master)
        url = f"/fiscal/configuracoes/{self.configuracao.pk}/editar/"

        pagina = self.client.get(url)
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Existe um token criptografado cadastrado")
        self.assertNotContains(pagina, self.SEGREDO)

        cifra_anterior = bytes(self.configuracao.csc_token_criptografado)
        resposta = self.client.post(url, self._dados())
        self.assertEqual(resposta.status_code, 302)
        self.configuracao.refresh_from_db()
        self.assertEqual(bytes(self.configuracao.csc_token_criptografado), cifra_anterior)
        self.assertEqual(abrir_csc(self.configuracao), self.SEGREDO)

    def test_rotacao_e_revogacao_sao_auditadas_sem_expor_token(self):
        self.client.force_login(self.master)
        url = f"/fiscal/configuracoes/{self.configuracao.pk}/editar/"
        novo_segredo = "CSC-rotacionado-654"

        resposta = self.client.post(url, self._dados(csc_token=novo_segredo))
        self.assertEqual(resposta.status_code, 302)
        self.configuracao.refresh_from_db()
        self.assertEqual(abrir_csc(self.configuracao), novo_segredo)
        log = LogAuditoria.objects.get(acao="ROTACIONA_CSC_FISCAL")
        self.assertNotIn(novo_segredo, log.descricao)

        resposta = self.client.post(url, self._dados(revogar_csc="on"))
        self.assertEqual(resposta.status_code, 302)
        self.configuracao.refresh_from_db()
        self.assertFalse(self.configuracao.csc_configurado)
        self.assertTrue(LogAuditoria.objects.filter(acao="REVOGA_CSC_FISCAL").exists())

    def test_administrador_nao_ve_nem_altera_csc(self):
        usuario = get_user_model().objects.create_user("admin-csc", password="teste-123")
        PerfilUsuario.objects.create(
            usuario=usuario,
            filial=self.filial,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.client.force_login(usuario)
        url = f"/fiscal/configuracoes/{self.configuracao.pk}/editar/"

        pagina = self.client.get(url)
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, "Novo token CSC")
        self.assertNotContains(pagina, "ID CSC")

        resposta = self.client.post(
            url,
            self._dados(csc_id="99", csc_token="tentativa-maliciosa", revogar_csc="on"),
        )
        self.assertEqual(resposta.status_code, 302)
        self.configuracao.refresh_from_db()
        self.assertEqual(self.configuracao.csc_id, "1")
        self.assertEqual(abrir_csc(self.configuracao), self.SEGREDO)

    @override_settings(FISCAL_CERTIFICATE_KEY="chave-incorreta")
    def test_chave_incorreta_falha_sem_vazar_segredo(self):
        with self.assertRaisesMessage(ValidationError, "segredo fiscal protegido") as erro:
            abrir_csc(self.configuracao)
        self.assertNotIn(self.SEGREDO, str(erro.exception))

    def test_admin_nao_oferece_campos_criptografados(self):
        cadastro = ConfiguracaoFiscalAdmin(ConfiguracaoFiscal, admin.site)
        formulario = cadastro.get_form(type("Request", (), {"user": self.master})())
        self.assertNotIn("csc_token_criptografado", formulario.base_fields)
        self.assertNotIn("certificado_a1_criptografado", formulario.base_fields)

        usuario = get_user_model().objects.create_user("staff-csc", is_staff=True)
        formulario_staff = cadastro.get_form(type("Request", (), {"user": usuario})())
        self.assertNotIn("csc_id", formulario_staff.base_fields)
