from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.financeiro.contrato_contabil import registrar_contrato_contabil, resumo_contrato_contabil
from apps.financeiro.models import (
    ContratoIntegracaoContabil,
    FormatoEntregaContabil,
    ResponsavelEFDICMSIPI,
    StatusContratoIntegracaoContabil,
)


class ContratoIntegracaoContabilTests(TestCase):
    def setUp(self):
        self.master = get_user_model().objects.create_superuser(
            "master-contrato", "master-contrato@example.com", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Contrato LTDA",
            nome_fantasia="Mercado Contrato",
            cnpj="23.456.789/0001-10",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz Contrato", cnpj=self.empresa.cnpj
        )

    def test_cria_versoes_imutaveis_e_resume_a_validada(self):
        rascunho = registrar_contrato_contabil(
            empresa=self.empresa,
            usuario=self.master,
            software_contabil="Escritorio Exemplo",
            formato_entrega=FormatoEntregaContabil.PACOTE_ZIP_V2,
            responsavel_efd_icms_ipi=ResponsavelEFDICMSIPI.NAO_DEFINIDO,
        )
        validado = registrar_contrato_contabil(
            empresa=self.empresa,
            usuario=self.master,
            software_contabil="Software Contabil Externo",
            formato_entrega=FormatoEntregaContabil.API_JSON_V1,
            responsavel_efd_icms_ipi=ResponsavelEFDICMSIPI.ESCRITORIO_CONTABIL,
            responsavel_efd_nome="Escritorio responsavel",
            aceite_referencia="ACEITE-INTERNO-2026-001",
            validar=True,
            ip="127.0.0.41",
        )

        self.assertEqual(rascunho.versao, 1)
        self.assertEqual(rascunho.status, StatusContratoIntegracaoContabil.RASCUNHO)
        self.assertEqual(validado.versao, 2)
        self.assertEqual(validado.contrato_tecnico, "accounting_monthly_api_v1")
        resumo = resumo_contrato_contabil(self.empresa)
        self.assertTrue(resumo["validado"])
        self.assertEqual(resumo["versao_validada"], 2)
        self.assertEqual(resumo["responsavel_efd_nome"], "Escritorio responsavel")
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="VALIDAR_CONTRATO_CONTABIL", objeto_id=str(validado.pk), ip="127.0.0.41"
            ).exists()
        )

        validado.software_contabil = "Alteracao indevida"
        with self.assertRaises(ValidationError):
            validado.save()
        with self.assertRaises(ValidationError):
            ContratoIntegracaoContabil.objects.filter(pk=validado.pk).update(
                software_contabil="Alteracao indevida"
            )
        with self.assertRaises(ValidationError):
            validado.delete()

    def test_validacao_exige_destino_responsavel_e_aceite(self):
        with self.assertRaises(ValidationError):
            registrar_contrato_contabil(
                empresa=self.empresa,
                usuario=self.master,
                software_contabil="",
                formato_entrega=FormatoEntregaContabil.PACOTE_ZIP_V2,
                responsavel_efd_icms_ipi=ResponsavelEFDICMSIPI.NAO_DEFINIDO,
                validar=True,
            )
        self.assertFalse(ContratoIntegracaoContabil.objects.exists())

    def test_servico_recusa_usuario_que_nao_e_master(self):
        administrador = get_user_model().objects.create_user("admin-contrato", password="123")
        PerfilUsuario.objects.create(
            usuario=administrador, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR
        )
        with self.assertRaises(PermissionDenied):
            registrar_contrato_contabil(
                empresa=self.empresa,
                usuario=administrador,
                software_contabil="Destino",
                formato_entrega=FormatoEntregaContabil.PACOTE_ZIP_V2,
                responsavel_efd_icms_ipi=ResponsavelEFDICMSIPI.NAO_DEFINIDO,
            )

    def test_tela_permite_master_e_deixa_administrador_somente_consultar(self):
        cliente = Client(HTTP_HOST="localhost")
        cliente.force_login(self.master)
        resposta = cliente.post(
            "/financeiro/contabilidade/chaves/",
            {
                "acao": "registrar_contrato",
                "empresa": self.empresa.pk,
                "software_contabil": "Destino em definicao",
                "formato_entrega": FormatoEntregaContabil.PACOTE_ZIP_V2,
                "responsavel_efd_icms_ipi": ResponsavelEFDICMSIPI.NAO_DEFINIDO,
                "responsavel_efd_nome": "",
                "aceite_referencia": "",
                "observacoes": "Rascunho sem dados reais.",
            },
        )
        self.assertRedirects(resposta, "/financeiro/contabilidade/chaves/")
        self.assertEqual(ContratoIntegracaoContabil.objects.get().status, StatusContratoIntegracaoContabil.RASCUNHO)

        administrador = get_user_model().objects.create_user("admin-tela-contrato", password="123")
        PerfilUsuario.objects.create(
            usuario=administrador, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR
        )
        cliente.force_login(administrador)
        consulta = cliente.get("/financeiro/contabilidade/chaves/")
        gravacao = cliente.post(
            "/financeiro/contabilidade/chaves/",
            {
                "acao": "registrar_contrato",
                "empresa": self.empresa.pk,
                "formato_entrega": FormatoEntregaContabil.PACOTE_ZIP_V2,
                "responsavel_efd_icms_ipi": ResponsavelEFDICMSIPI.NAO_DEFINIDO,
            },
        )
        self.assertEqual(consulta.status_code, 200)
        self.assertContains(consulta, "Apenas o Master registra ou valida")
        self.assertNotContains(consulta, "Registrar nova versão")
        self.assertEqual(gravacao.status_code, 403)
        self.assertEqual(ContratoIntegracaoContabil.objects.count(), 1)
