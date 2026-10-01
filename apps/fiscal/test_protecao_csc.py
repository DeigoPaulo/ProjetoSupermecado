from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
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

    def _dados_troca_ambiente_com_a1(self, ambiente):
        endpoints = endpoints_nfce_uf("GO", ambiente)
        return self._dados(
            ambiente=ambiente,
            url_qrcode_nfce=endpoints["qrcode"],
            url_consulta_nfce=endpoints["consulta"],
            confirmar_troca_ambiente="on",
            inscricao_estadual="987654321",
            certificado_arquivo=SimpleUploadedFile("teste.pfx", b"certificado-sintetico"),
            certificado_senha="senha-teste",
        )

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

    def test_troca_ambiente_exige_confirmacao_e_registra_auditoria_nos_dois_sentidos(self):
        self.client.force_login(self.master)
        url = f"/fiscal/configuracoes/{self.configuracao.pk}/editar/"
        for novo_ambiente, anterior in (
            (AmbienteFiscal.PRODUCAO, AmbienteFiscal.HOMOLOGACAO),
            (AmbienteFiscal.HOMOLOGACAO, AmbienteFiscal.PRODUCAO),
        ):
            with self.subTest(novo_ambiente=novo_ambiente):
                endpoints = endpoints_nfce_uf("GO", novo_ambiente)
                dados = self._dados(
                    ambiente=novo_ambiente,
                    url_qrcode_nfce=endpoints["qrcode"],
                    url_consulta_nfce=endpoints["consulta"],
                )
                sem_confirmacao = self.client.post(url, dados, REMOTE_ADDR="192.0.2.10")
                self.assertEqual(sem_confirmacao.status_code, 200)
                self.assertContains(sem_confirmacao, "Confirme explicitamente")
                self.configuracao.refresh_from_db()
                self.assertEqual(self.configuracao.ambiente, anterior)

                resposta = self.client.post(
                    url,
                    {**dados, "confirmar_troca_ambiente": "on"},
                    REMOTE_ADDR="192.0.2.10",
                )
                self.assertEqual(resposta.status_code, 302)
                self.configuracao.refresh_from_db()
                self.assertEqual(self.configuracao.ambiente, novo_ambiente)
                log = LogAuditoria.objects.filter(acao="ALTERA_AMBIENTE_FISCAL").latest("pk")
                self.assertEqual(log.usuario, self.master)
                self.assertEqual(log.objeto_id, str(self.configuracao.pk))
                self.assertEqual(log.ip, "192.0.2.10")
                self.assertIn(anterior, log.descricao)
                self.assertIn(novo_ambiente, log.descricao)

    def test_certificado_invalido_nao_salva_troca_de_ambiente_em_nenhum_sentido(self):
        self.client.force_login(self.master)
        url = f"/fiscal/configuracoes/{self.configuracao.pk}/editar/"
        for anterior, novo in (
            (AmbienteFiscal.HOMOLOGACAO, AmbienteFiscal.PRODUCAO),
            (AmbienteFiscal.PRODUCAO, AmbienteFiscal.HOMOLOGACAO),
        ):
            with self.subTest(anterior=anterior, novo=novo):
                self.configuracao.ambiente = anterior
                self.configuracao.save(update_fields=["ambiente"])
                with patch(
                    "apps.fiscal.certificados.load_key_and_certificates",
                    side_effect=ValueError("A1 inválido"),
                ):
                    resposta = self.client.post(
                        url, self._dados_troca_ambiente_com_a1(novo)
                    )
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "Certificado A1 inválido ou senha incorreta")
                self.configuracao.refresh_from_db()
                self.assertEqual(self.configuracao.ambiente, anterior)
                self.assertEqual(self.configuracao.inscricao_estadual, "123456789")
                self.assertFalse(self.configuracao.certificado_configurado)
                self.assertFalse(
                    LogAuditoria.objects.filter(acao="ALTERA_AMBIENTE_FISCAL").exists()
                )

    def test_certificado_valido_salva_troca_e_auditoria_em_ambos_os_sentidos(self):
        self.client.force_login(self.master)
        url = f"/fiscal/configuracoes/{self.configuracao.pk}/editar/"
        certificado = SimpleNamespace(
            not_valid_after_utc=datetime(2030, 1, 1, tzinfo=timezone.utc)
        )
        for anterior, novo in (
            (AmbienteFiscal.HOMOLOGACAO, AmbienteFiscal.PRODUCAO),
            (AmbienteFiscal.PRODUCAO, AmbienteFiscal.HOMOLOGACAO),
        ):
            with self.subTest(anterior=anterior, novo=novo):
                with patch(
                    "apps.fiscal.certificados.load_key_and_certificates",
                    return_value=(None, certificado, None),
                ) as validar:
                    resposta = self.client.post(
                        url, self._dados_troca_ambiente_com_a1(novo)
                    )
                self.assertEqual(resposta.status_code, 302)
                self.assertEqual(validar.call_count, 2)
                self.configuracao.refresh_from_db()
                self.assertEqual(self.configuracao.ambiente, novo)
                self.assertEqual(self.configuracao.inscricao_estadual, "987654321")
                self.assertTrue(self.configuracao.certificado_configurado)
                log = LogAuditoria.objects.filter(acao="ALTERA_AMBIENTE_FISCAL").latest("pk")
                self.assertEqual(log.objeto_id, str(self.configuracao.pk))
                self.assertIn(anterior, log.descricao)
                self.assertIn(novo, log.descricao)

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
