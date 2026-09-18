from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial

from .models import (
    AmbienteFiscal,
    ConfiguracaoFiscal,
    EvidenciaHomologacaoCanal,
    ProvedorEmissaoFiscal,
    StatusEvidenciaHomologacaoCanal,
)
from .services_evidencias_homologacao import (
    registrar_evidencia_homologacao,
    revisar_evidencia_homologacao,
)


class EvidenciasHomologacaoCanaisTests(TestCase):
    def setUp(self):
        self.master = get_user_model().objects.create_superuser(
            "master_evidencia", "master-evidencia@example.com", "teste"
        )
        self.usuario = get_user_model().objects.create_user(
            "usuario_evidencia", password="teste"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Evidência",
            nome_fantasia="Mercado Evidência",
            cnpj="12345678000195",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Evidência",
            cnpj="12345678000195",
            uf="GO",
        )
        self.configuracao = ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            provedor_emissao=ProvedorEmissaoFiscal.FOCUS,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
        )

    def registrar(self, **extras):
        dados = {
            "operacao": "AUTORIZACAO",
            "referencia": "cofre://homologacao/focus/autorizacao-1",
            "conteudo_sha256": "a" * 64,
            "versao_aplicacao": "commit-abc123",
            "resultado_esperado": "Documento autorizado uma única vez.",
            "resultado_obtido": "Autorizado com protocolo de homologação.",
            "codigo_status": "100",
            "protocolo": "152260000000001",
            "usuario": self.master,
        }
        dados.update(extras)
        return registrar_evidencia_homologacao(self.configuracao, **dados)

    def test_registro_nasce_pendente_e_auditado_sem_conteudo_sensivel(self):
        evidencia = self.registrar()

        self.assertEqual(evidencia.status, StatusEvidenciaHomologacaoCanal.PENDENTE)
        self.assertEqual(evidencia.canal, ProvedorEmissaoFiscal.FOCUS)
        self.assertEqual(evidencia.ambiente, AmbienteFiscal.HOMOLOGACAO)
        self.assertEqual(evidencia.conteudo_sha256, "a" * 64)
        self.assertFalse(hasattr(evidencia, "conteudo_arquivo"))
        self.assertTrue(LogAuditoria.objects.filter(
            acao="REGISTRA_EVIDENCIA_HOMOLOGACAO_CANAL",
            objeto_id=str(evidencia.pk),
        ).exists())

    def test_eventos_focus_nao_aceitam_evidencia_enquanto_houver_lacuna(self):
        with self.assertRaisesMessage(ValidationError, "lacuna interna"):
            self.registrar(operacao="EVENTOS")

        self.assertFalse(EvidenciaHomologacaoCanal.objects.exists())

    def test_usuario_comum_nao_registra_nem_revisa(self):
        with self.assertRaises(PermissionDenied):
            self.registrar(usuario=self.usuario)
        evidencia = self.registrar()

        with self.assertRaises(PermissionDenied):
            revisar_evidencia_homologacao(
                evidencia,
                decisao="APROVADA",
                observacoes="Conferência técnica concluída.",
                usuario=self.usuario,
            )

    def test_revisao_exige_justificativa_e_se_torna_imutavel(self):
        evidencia = self.registrar()
        with self.assertRaisesMessage(ValidationError, "justificativa"):
            revisar_evidencia_homologacao(
                evidencia, decisao="APROVADA", observacoes="", usuario=self.master
            )

        revisada = revisar_evidencia_homologacao(
            evidencia,
            decisao="APROVADA",
            observacoes="Chave, protocolo e XML conferidos no cofre protegido.",
            usuario=self.master,
        )

        self.assertEqual(revisada.status, StatusEvidenciaHomologacaoCanal.APROVADA)
        self.assertEqual(revisada.revisada_por, self.master)
        self.assertIsNotNone(revisada.revisada_em)
        with self.assertRaisesMessage(ValidationError, "imutável"):
            revisar_evidencia_homologacao(
                revisada,
                decisao="REJEITADA",
                observacoes="Tentativa posterior.",
                usuario=self.master,
            )

    def test_producao_e_sha_invalido_falham_fechado(self):
        with self.assertRaisesMessage(ValidationError, "SHA-256"):
            self.registrar(conteudo_sha256="invalido")
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente", "atualizado_em"])

        with self.assertRaisesMessage(ValidationError, "só podem ser registradas em homologação"):
            self.registrar()

    def test_evidencia_nao_pode_ser_excluida(self):
        evidencia = self.registrar()

        with self.assertRaisesMessage(ValueError, "não podem ser excluídas"):
            evidencia.delete()

    def test_interface_master_registra_lista_e_revisa_sem_upload(self):
        self.client.force_login(self.master)
        url_registro = (
            f"/fiscal/configuracoes/{self.configuracao.pk}/"
            "homologacao-goias/evidencias/registrar/"
        )
        resposta = self.client.post(url_registro, {
            "operacao": "AUTORIZACAO",
            "referencia": "cofre://homologacao/focus/interface-1",
            "conteudo_sha256": "b" * 64,
            "versao_aplicacao": "commit-interface",
            "codigo_status": "100",
            "protocolo": "152260000000002",
            "resultado_esperado": "Autorizar uma vez.",
            "resultado_obtido": "Autorizado uma vez.",
        })

        self.assertRedirects(
            resposta,
            f"/fiscal/configuracoes/{self.configuracao.pk}/homologacao-goias/",
            fetch_redirect_response=False,
        )
        evidencia = EvidenciaHomologacaoCanal.objects.get()
        pagina = self.client.get(
            f"/fiscal/configuracoes/{self.configuracao.pk}/homologacao-goias/"
        )
        self.assertContains(pagina, "Evidências reais do canal")
        self.assertContains(pagina, evidencia.referencia)
        self.assertNotContains(pagina, 'type="file"')

        resposta = self.client.post(
            f"/fiscal/configuracoes/{self.configuracao.pk}/homologacao-goias/"
            f"evidencias/{evidencia.pk}/revisar/",
            {"decisao": "APROVADA", "observacoes": "Conferência manual concluída."},
        )
        self.assertEqual(resposta.status_code, 302)
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.status, StatusEvidenciaHomologacaoCanal.APROVADA)

    def test_interface_recusa_usuario_nao_master(self):
        self.client.force_login(self.usuario)

        resposta = self.client.post(
            f"/fiscal/configuracoes/{self.configuracao.pk}/"
            "homologacao-goias/evidencias/registrar/",
            {},
        )

        self.assertEqual(resposta.status_code, 403)
