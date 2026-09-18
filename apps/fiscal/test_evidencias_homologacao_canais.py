from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial

from .models import (
    AmbienteFiscal,
    ConfiguracaoFiscal,
    EvidenciaHomologacaoCanal,
    HomologacaoFiscal,
    OperacaoHomologacaoFiscal,
    ProvedorEmissaoFiscal,
    StatusEvidenciaHomologacaoCanal,
    StatusHomologacaoFiscal,
)
from .services_evidencias_homologacao import (
    avaliar_portao_conclusao_homologacao,
    diagnosticar_cobertura_evidencias_homologacao,
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

    def test_diagnostico_distingue_estados_e_preserva_lacuna_focus(self):
        pendente = self.registrar(operacao="AUTORIZACAO")
        aprovada = self.registrar(operacao="CONSULTA", referencia="cofre://consulta")
        rejeitada = self.registrar(operacao="CANCELAMENTO", referencia="cofre://cancelamento")
        revisar_evidencia_homologacao(
            aprovada, decisao="APROVADA", observacoes="Conferida.", usuario=self.master
        )
        revisar_evidencia_homologacao(
            rejeitada, decisao="REJEITADA", observacoes="Retorno divergiu.", usuario=self.master
        )

        diagnostico = diagnosticar_cobertura_evidencias_homologacao(self.configuracao)
        estados = {item["operacao"]: item["estado"] for item in diagnostico["itens"]}

        self.assertEqual(estados["AUTORIZACAO"], "PENDENTE")
        self.assertEqual(estados["CONSULTA"], "APROVADA")
        self.assertEqual(estados["CANCELAMENTO"], "REJEITADA")
        self.assertEqual(estados["REJEICAO"], "AUSENTE")
        self.assertEqual(estados["EVENTOS"], "BLOQUEADA_LACUNA_INTERNA")
        self.assertFalse(diagnostico["cobertura_completa"])
        self.assertFalse(diagnostico["altera_homologacao"])
        self.assertFalse(diagnostico["libera_producao"])
        self.assertEqual(pendente.status, StatusEvidenciaHomologacaoCanal.PENDENTE)

    def test_interface_master_exibe_diagnostico_sem_mudar_homologacao(self):
        self.client.force_login(self.master)

        pagina = self.client.get(
            f"/fiscal/configuracoes/{self.configuracao.pk}/homologacao-goias/"
        )

        self.assertContains(pagina, "Cobertura das evidências")
        self.assertContains(pagina, "0/7 aprovadas")
        self.assertContains(pagina, "Bloqueada por lacuna interna")
        self.assertContains(pagina, "Não conclui a homologação nem libera produção")

    def test_portao_falha_fechado_com_ausencia_e_lacuna_sem_liberar_producao(self):
        portao = avaliar_portao_conclusao_homologacao(self.configuracao)

        self.assertFalse(portao["permitido"])
        self.assertFalse(portao["libera_producao"])
        self.assertTrue(any("sem evidência" in motivo for motivo in portao["motivos"]))
        self.assertTrue(any("lacuna interna" in motivo for motivo in portao["motivos"]))

    def test_interface_bloqueia_conclusao_mesmo_com_checklist_automatico_pronto(self):
        self.client.force_login(self.master)
        checklist_pronto = [{"titulo": "Teste", "pronto": True, "detalhe": "OK"}]

        from unittest.mock import patch
        with patch("apps.fiscal.views._checklist_homologacao_goias", return_value=checklist_pronto):
            resposta = self.client.post(
                f"/fiscal/configuracoes/{self.configuracao.pk}/homologacao-goias/",
                {
                    "status": StatusHomologacaoFiscal.CONCLUIDA,
                    "responsavel_tecnico": "Equipe fiscal",
                    "evidencia_referencia": "cofre://dossie",
                    "observacoes": "Revisão solicitada.",
                },
            )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "A conclusão exige evidência aprovada")
        homologacao = HomologacaoFiscal.objects.get(configuracao=self.configuracao)
        self.assertNotEqual(homologacao.status, StatusHomologacaoFiscal.CONCLUIDA)

    def test_sefaz_direta_com_cobertura_completa_libera_conclusao_sem_producao(self):
        self.configuracao.provedor_emissao = ProvedorEmissaoFiscal.SEFAZ_DIRETA_GO
        self.configuracao.save(update_fields=["provedor_emissao", "atualizado_em"])
        for indice, operacao in enumerate(OperacaoHomologacaoFiscal.values, start=1):
            evidencia = self.registrar(
                operacao=operacao,
                referencia=f"cofre://sefaz-direta/{operacao.lower()}",
                conteudo_sha256=f"{indice:x}" * 64,
            )
            revisar_evidencia_homologacao(
                evidencia,
                decisao="APROVADA",
                observacoes="Cenário isolado aprovado para validar o portão.",
                usuario=self.master,
            )

        portao = avaliar_portao_conclusao_homologacao(self.configuracao)
        self.assertTrue(portao["permitido"])
        self.assertFalse(portao["libera_producao"])

        self.client.force_login(self.master)
        checklist_pronto = [{"titulo": "Teste", "pronto": True, "detalhe": "OK"}]
        from unittest.mock import patch
        with patch("apps.fiscal.views._checklist_homologacao_goias", return_value=checklist_pronto):
            pagina = self.client.get(
                f"/fiscal/configuracoes/{self.configuracao.pk}/homologacao-goias/"
            )
            resposta = self.client.post(
                f"/fiscal/configuracoes/{self.configuracao.pk}/homologacao-goias/",
                {
                    "status": StatusHomologacaoFiscal.CONCLUIDA,
                    "responsavel_tecnico": "Equipe fiscal",
                    "evidencia_referencia": "cofre://dossie-sefaz-direta",
                    "observacoes": "Conclusão técnica do cenário isolado.",
                },
            )

        self.assertContains(pagina, "Portão de conclusão liberado")
        self.assertContains(pagina, "7/7 aprovadas")
        self.assertEqual(resposta.status_code, 302)
        homologacao = HomologacaoFiscal.objects.get(configuracao=self.configuracao)
        self.assertEqual(homologacao.status, StatusHomologacaoFiscal.CONCLUIDA)
        self.configuracao.refresh_from_db()
        self.assertEqual(self.configuracao.ambiente, AmbienteFiscal.HOMOLOGACAO)
