import hashlib
import json
import zipfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.auditoria.models import LogAuditoria


class ServidorLocalEvidenciasViewTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_superuser("master", "master@example.com", "senha")
        self.usuario_comum = User.objects.create_user("comum", password="senha")

    @patch("apps.configuracoes.views.gerar_evidencia_aceite")
    @patch("apps.configuracoes.views.diagnostico_pos_implantacao_local")
    @patch("apps.configuracoes.views.gerar_dossie_implantacao")
    def test_super_admin_baixa_zip_com_hashes_e_auditoria(self, dossie, pos, aceite):
        dossie.return_value = {
            "contrato": "deployment_evidence_v1",
            "perfil": "servidor-local",
        }
        pos.return_value = {"contrato": "local_post_deployment_health_v1", "pronto": False}
        aceite.return_value = {
            "contrato": "local_installation_acceptance_evidence_v1",
            "liberavel": False,
        }
        self.client.force_login(self.super_admin)

        resposta = self.client.get(reverse("configuracoes:servidor_local_evidencias"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/zip")
        with zipfile.ZipFile(BytesIO(resposta.content)) as pacote:
            self.assertEqual(
                set(pacote.namelist()),
                {
                    "dossie_implantacao.json",
                    "dossie_implantacao.json.sha256",
                    "evidencia_aceite.json",
                    "evidencia_aceite.json.sha256",
                    "LEIA-ME.txt",
                },
            )
            for nome in ("dossie_implantacao.json", "evidencia_aceite.json"):
                conteudo = pacote.read(nome)
                declarado = pacote.read(nome + ".sha256").decode("ascii").split()[0]
                self.assertEqual(declarado, hashlib.sha256(conteudo).hexdigest())
                json.loads(conteudo.decode("utf-8"))
        self.assertTrue(
            LogAuditoria.objects.filter(acao="DOWNLOAD_EVIDENCIAS_IMPLANTACAO").exists()
        )

    def test_usuario_comum_nao_baixa_evidencias(self):
        self.client.force_login(self.usuario_comum)

        resposta = self.client.get(reverse("configuracoes:servidor_local_evidencias"))

        self.assertEqual(resposta.status_code, 403)


class ServidorLocalEvidenciasOfflineViewTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            "master_offline",
            "master_offline@example.com",
            "senha",
        )

    @patch("apps.configuracoes.views.gerar_evidencia_aceite")
    @patch("apps.configuracoes.views.diagnostico_pos_implantacao_local")
    @patch("apps.configuracoes.views.gerar_dossie_implantacao")
    def test_master_gera_dossie_com_midia_offline_obrigatoria(self, dossie, pos, aceite):
        dossie.return_value = {
            "contrato": "deployment_evidence_v1",
            "perfil": "servidor-local",
        }
        pos.return_value = {"contrato": "local_post_deployment_health_v1", "pronto": False}
        aceite.return_value = {
            "contrato": "local_installation_acceptance_evidence_v1",
            "liberavel": False,
        }
        self.client.force_login(self.super_admin)

        resposta = self.client.get(
            reverse("configuracoes:servidor_local_evidencias") + "?modo=offline"
        )

        self.assertEqual(resposta.status_code, 200)
        dossie.assert_called_once_with(
            perfil="servidor-local",
            producao=True,
            exigir_midia_offline=True,
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="DOWNLOAD_EVIDENCIAS_IMPLANTACAO",
                descricao__contains="Mídia offline obrigatória",
            ).exists()
        )
