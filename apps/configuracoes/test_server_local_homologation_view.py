import hashlib
import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria

from .homologation import (
    CODIGOS_CRITICOS_HOMOLOGACAO_SERVIDOR_LOCAL,
    diagnostico_homologacao_servidor_local,
)
from .models import HomologacaoServidorLocal, ResultadoHomologacaoServidor


class ServidorLocalHomologacaoViewTests(TestCase):
    def setUp(self):
        self.url = reverse("configuracoes:servidor_local")
        self.superadmin = User.objects.create_superuser(
            username="master_homologacao",
            email="master@example.com",
            password="senha-forte",
        )
        self.usuario = User.objects.create_user(
            username="admin_empresa_homologacao",
            password="senha-forte",
        )
        PerfilUsuario.objects.create(
            usuario=self.usuario,
            tipo=TipoPerfil.ADMINISTRADOR,
        )

    def arquivos_evidencia(self, *, liberavel=True, contrato=None):
        payload = {
            "contrato": contrato or "local_installation_acceptance_evidence_v1",
            "gerado_em": "2026-08-04T12:00:00-03:00",
            "perfil": "servidor-local",
            "alvo": "producao",
            "liberavel": liberavel,
            "status": "ready" if liberavel else "blocked",
            "dossie": {
                "sha256": "b" * 64,
                "validacao": {
                    "liberavel": liberavel,
                    "perfil": "servidor-local",
                    "alvo": "producao",
                    "erros": [],
                    "avisos": [] if liberavel else ["Pacote pendente."],
                },
            },
            "pos_implantacao": {
                "contrato": "local_post_deployment_health_v1",
                "pronto": liberavel,
                "bloqueios": [] if liberavel else ["Backup recente não localizado."],
            },
            "bloqueios": [] if liberavel else ["pos_implantacao: backup pendente"],
            "seguranca": {
                "segredos_expostos": False,
                "caminhos_absolutos_expostos": False,
            },
        }
        conteudo = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        digest = hashlib.sha256(conteudo).hexdigest()
        return {
            "json": SimpleUploadedFile(
                "evidencia_aceite.json",
                conteudo,
                content_type="application/json",
            ),
            "sha256": SimpleUploadedFile(
                "evidencia_aceite.json.sha256",
                f"{digest}  evidencia_aceite.json\n".encode("ascii"),
                content_type="text/plain",
            ),
            "digest": digest,
        }

    def payload(self, *, liberavel=True, contrato=None, **alteracoes):
        arquivos = self.arquivos_evidencia(
            liberavel=liberavel,
            contrato=contrato,
        )
        dados = {
            "homologacao-maquina": "SRV-LOJA-01",
            "homologacao-sistema_operacional": "Windows Server 2022",
            "homologacao-versao_artefato": "1.0.0",
            "homologacao-resultado": ResultadoHomologacaoServidor.APROVADA,
            "homologacao-itens_validados": list(CODIGOS_CRITICOS_HOMOLOGACAO_SERVIDOR_LOCAL),
            "homologacao-arquivo_evidencia": arquivos["json"],
            "homologacao-arquivo_sha256": arquivos["sha256"],
            "homologacao-observacoes": "Instalação, backup e restauração validados.",
        }
        dados.update(alteracoes)
        return dados, arquivos["digest"]

    def test_superadmin_registra_homologacao_aprovada_e_auditoria(self):
        self.client.force_login(self.superadmin)
        dados, digest = self.payload()
        response = self.client.post(self.url, dados)

        self.assertRedirects(response, self.url + "#homologacoes")
        homologacao = HomologacaoServidorLocal.objects.get()
        self.assertEqual(homologacao.registrada_por, self.superadmin)
        self.assertEqual(homologacao.hash_evidencia, digest)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="REGISTRO_HOMOLOGACAO_SERVIDOR_LOCAL",
                objeto_id=str(homologacao.pk),
            ).exists()
        )

    def test_checksum_divergente_nao_e_registrado(self):
        self.client.force_login(self.superadmin)
        dados, _ = self.payload()
        dados["homologacao-arquivo_sha256"] = SimpleUploadedFile(
            "evidencia_aceite.json.sha256",
            f"{'f' * 64}  evidencia_aceite.json\n".encode("ascii"),
            content_type="text/plain",
        )
        response = self.client.post(self.url, dados)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "O SHA-256 não corresponde")
        self.assertFalse(HomologacaoServidorLocal.objects.exists())

    def test_contrato_incompativel_nao_e_registrado(self):
        self.client.force_login(self.superadmin)
        dados, _ = self.payload(contrato="contrato_desconhecido")
        response = self.client.post(self.url, dados)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contrato de evidência incompatível")
        self.assertFalse(HomologacaoServidorLocal.objects.exists())

    def test_evidencia_bloqueada_nao_pode_ser_aprovada(self):
        self.client.force_login(self.superadmin)
        dados, _ = self.payload(liberavel=False)
        response = self.client.post(self.url, dados)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "exige evidência com status liberável")
        self.assertFalse(HomologacaoServidorLocal.objects.exists())


    def test_aprovacao_exige_todos_os_testes_criticos(self):
        self.client.force_login(self.superadmin)
        dados, _ = self.payload()
        dados["homologacao-itens_validados"] = ["INSTALACAO_LIMPA"]
        response = self.client.post(self.url, dados)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Uma aprovação exige todos os testes críticos da máquina limpa.",
        )
        self.assertFalse(HomologacaoServidorLocal.objects.exists())

    def test_reprovacao_exige_observacao(self):
        self.client.force_login(self.superadmin)
        dados, _ = self.payload(
            liberavel=False,
            **{
                "homologacao-resultado": ResultadoHomologacaoServidor.REPROVADA,
                "homologacao-observacoes": "",
            },
        )
        response = self.client.post(self.url, dados)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Descreva o motivo")
        self.assertFalse(HomologacaoServidorLocal.objects.exists())

    def test_reprovacao_aceita_evidencia_bloqueada_com_justificativa(self):
        self.client.force_login(self.superadmin)
        dados, digest = self.payload(
            liberavel=False,
            **{
                "homologacao-resultado": ResultadoHomologacaoServidor.REPROVADA,
                "homologacao-observacoes": "Restauração do backup falhou.",
            },
        )
        response = self.client.post(self.url, dados)

        self.assertRedirects(response, self.url + "#homologacoes")
        homologacao = HomologacaoServidorLocal.objects.get()
        self.assertEqual(homologacao.resultado, ResultadoHomologacaoServidor.REPROVADA)
        self.assertEqual(homologacao.hash_evidencia, digest)

    def test_evidencia_duplicada_e_rejeitada(self):
        dados, digest = self.payload()
        HomologacaoServidorLocal.objects.create(
            maquina="SRV-ANTERIOR",
            sistema_operacional="Windows Server 2022",
            versao_artefato="1.0.0",
            hash_evidencia=digest,
            resultado=ResultadoHomologacaoServidor.APROVADA,
            registrada_por=self.superadmin,
        )
        self.client.force_login(self.superadmin)
        response = self.client.post(self.url, dados)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Esta evidência já foi registrada")
        self.assertEqual(HomologacaoServidorLocal.objects.count(), 1)

    def test_usuario_da_empresa_nao_pode_registrar_homologacao(self):
        self.client.force_login(self.usuario)
        dados, _ = self.payload()
        response = self.client.post(self.url, dados)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(HomologacaoServidorLocal.objects.exists())

    def test_historico_e_paginado_em_vinte_registros(self):
        HomologacaoServidorLocal.objects.bulk_create(
            [
                HomologacaoServidorLocal(
                    maquina=f"SRV-{indice:02d}",
                    sistema_operacional="Windows Server 2022",
                    versao_artefato="1.0.0",
                    hash_evidencia=f"{indice:064x}",
                    resultado=ResultadoHomologacaoServidor.APROVADA,
                    registrada_por=self.superadmin,
                )
                for indice in range(21)
            ]
        )
        self.client.force_login(self.superadmin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["homologacoes"]), 20)
        self.assertContains(response, "Página 1 de 2")

    def test_superadmin_visualiza_formulario_e_historico(self):
        self.client.force_login(self.superadmin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Homologação em máquina limpa")
        self.assertContains(response, "Máquina homologada")
        self.assertContains(response, "Evidência de aceite (JSON)")
        self.assertContains(response, "Checksum da evidência (SHA-256)")
        self.assertContains(response, "Validação antes da publicação")
        self.assertContains(response, "verificar_homologacao_servidor_local --estrito")
        self.assertContains(response, "Nenhuma homologação em máquina limpa registrada")

    def test_administrador_da_empresa_nao_visualiza_bloco_de_homologacao(self):
        self.client.force_login(self.usuario)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Homologação em máquina limpa")
        self.assertNotContains(response, 'name="homologacao-arquivo_evidencia"')


class HomologacaoServidorLocalReadinessTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username="master_readiness",
            email="readiness@example.com",
            password="senha-forte",
        )

    def criar(self, versao, resultado):
        return HomologacaoServidorLocal.objects.create(
            maquina="SRV-TESTE",
            sistema_operacional="Windows Server 2022",
            versao_artefato=versao,
            hash_evidencia=(versao + resultado).encode().hex().ljust(64, "0")[:64],
            resultado=resultado,
            itens_validados=(
                list(CODIGOS_CRITICOS_HOMOLOGACAO_SERVIDOR_LOCAL)
                if resultado == ResultadoHomologacaoServidor.APROVADA
                else []
            ),
            registrada_por=self.superadmin,
        )

    @override_settings(LOCAL_SERVER_VERSION="1.2.0")
    def test_sem_registro_permanece_pendente(self):
        diagnostico = diagnostico_homologacao_servidor_local()

        self.assertEqual(diagnostico["status"], "PENDENTE")
        self.assertFalse(diagnostico["pronta"])

    @override_settings(LOCAL_SERVER_VERSION="1.2.0")
    def test_aprovacao_da_versao_vigente_libera_diagnostico(self):
        self.criar("1.2.0", ResultadoHomologacaoServidor.APROVADA)

        diagnostico = diagnostico_homologacao_servidor_local()

        self.assertEqual(diagnostico["status"], "APROVADA")
        self.assertTrue(diagnostico["pronta"])


    @override_settings(LOCAL_SERVER_VERSION="1.2.0")
    def test_aprovacao_antiga_sem_checklist_fica_incompleta(self):
        HomologacaoServidorLocal.objects.create(
            maquina="SRV-LEGADO",
            sistema_operacional="Windows Server 2022",
            versao_artefato="1.2.0",
            hash_evidencia="f" * 64,
            resultado=ResultadoHomologacaoServidor.APROVADA,
            registrada_por=self.superadmin,
        )

        diagnostico = diagnostico_homologacao_servidor_local()

        self.assertEqual(diagnostico["status"], "INCOMPLETA")
        self.assertFalse(diagnostico["pronta"])

    @override_settings(LOCAL_SERVER_VERSION="1.2.0")
    def test_reprovacao_da_versao_vigente_bloqueia_diagnostico(self):
        self.criar("1.2.0", ResultadoHomologacaoServidor.REPROVADA)

        diagnostico = diagnostico_homologacao_servidor_local()

        self.assertEqual(diagnostico["status"], "REPROVADA")
        self.assertFalse(diagnostico["pronta"])

    @override_settings(LOCAL_SERVER_VERSION="1.2.0")
    def test_aprovacao_de_outra_versao_fica_desatualizada(self):
        self.criar("1.1.0", ResultadoHomologacaoServidor.APROVADA)

        diagnostico = diagnostico_homologacao_servidor_local()

        self.assertEqual(diagnostico["status"], "DESATUALIZADA")
        self.assertFalse(diagnostico["pronta"])
