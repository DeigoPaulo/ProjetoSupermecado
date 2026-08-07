import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.configuracoes.homologation import (
    CODIGOS_CRITICOS_HOMOLOGACAO_SERVIDOR_LOCAL,
)
from apps.configuracoes.models import (
    HomologacaoServidorLocal,
    ResultadoHomologacaoServidor,
)


@override_settings(LOCAL_SERVER_VERSION="1.2.0")
class VerificarHomologacaoServidorLocalCommandTests(TestCase):
    def test_json_informa_pendencia_sem_registro(self):
        stdout = StringIO()
        call_command(
            "verificar_homologacao_servidor_local", "--json", stdout=stdout
        )
        diagnostico = json.loads(stdout.getvalue())
        self.assertEqual(diagnostico["status"], "PENDENTE")
        self.assertFalse(diagnostico["pronta"])
        self.assertEqual(diagnostico["versao_vigente"], "1.2.0")

    def test_modo_estrito_falha_sem_homologacao(self):
        with self.assertRaises(CommandError):
            call_command(
                "verificar_homologacao_servidor_local",
                "--estrito",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_modo_estrito_aceita_versao_aprovada_com_checklist_completo(self):
        usuario = get_user_model().objects.create_user(
            username="supervisor.homologacao", password="senha-segura"
        )
        HomologacaoServidorLocal.objects.create(
            maquina="SERVIDOR-LOJA-01",
            sistema_operacional="Windows Server 2022",
            versao_artefato="1.2.0",
            hash_evidencia="a" * 64,
            resultado=ResultadoHomologacaoServidor.APROVADA,
            registrada_por=usuario,
            itens_validados=list(CODIGOS_CRITICOS_HOMOLOGACAO_SERVIDOR_LOCAL),
        )
        stdout = StringIO()
        call_command(
            "verificar_homologacao_servidor_local", "--estrito", stdout=stdout
        )
        self.assertIn("APROVADA", stdout.getvalue())
        self.assertIn("SERVIDOR-LOJA-01", stdout.getvalue())

    def test_versao_explicita_pode_validar_artefato_anterior(self):
        usuario = get_user_model().objects.create_user(username="homologador")
        HomologacaoServidorLocal.objects.create(
            maquina="SERVIDOR-LEGADO",
            sistema_operacional="Windows 11",
            versao_artefato="1.1.0",
            hash_evidencia="b" * 64,
            resultado=ResultadoHomologacaoServidor.APROVADA,
            registrada_por=usuario,
            itens_validados=list(CODIGOS_CRITICOS_HOMOLOGACAO_SERVIDOR_LOCAL),
        )
        stdout = StringIO()
        call_command(
            "verificar_homologacao_servidor_local",
            "--versao",
            "1.1.0",
            "--estrito",
            stdout=stdout,
        )
        self.assertIn("1.1.0: APROVADA", stdout.getvalue())
