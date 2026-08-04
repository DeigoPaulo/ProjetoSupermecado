import json
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from apps.configuracoes.deployment_evidence import (
    gerar_dossie_implantacao,
    validar_dossie_implantacao,
)


def _artefato(tipo):
    base = {
        "nome": "pacote.zip" if tipo == "servidor_local" else "pdv.msi",
        "arquivo_encontrado": True,
        "tamanho": 123,
        "sha256": "a" * 64,
        "integridade_valida": True,
        "versao_valida": True,
        "publicavel": True,
        "problemas": [],
    }
    if tipo == "pdv_desktop":
        base.update(assinatura_exigida=False, assinatura_valida=False)
    else:
        base.update(conteudo_valido=True, origem_rastreavel=True)
    return base


class DossieImplantacaoTests(SimpleTestCase):
    @override_settings(PDV_DESKTOP_VERSION="1.2.3", LOCAL_SERVER_VERSION="4.5.6")
    @patch("apps.configuracoes.deployment_evidence.artefato_servidor_local")
    @patch("apps.configuracoes.deployment_evidence.artefato_pdv_desktop")
    @patch("apps.configuracoes.deployment_evidence.diagnostico_prontidao_implantacao")
    def test_dossie_nao_expoe_caminhos_ou_segredos(self, prontidao, pdv, servidor):
        prontidao.return_value = {"pronto": True, "contrato": "deployment_readiness_v2"}
        pdv.return_value = _artefato("pdv_desktop")
        servidor.return_value = _artefato("servidor_local")

        dossie = gerar_dossie_implantacao(perfil="servidor-local", producao=True)
        serializado = json.dumps(dossie)

        self.assertEqual(dossie["contrato"], "deployment_evidence_v1")
        self.assertEqual(dossie["aplicacao"]["pdv_desktop"], "1.2.3")
        self.assertNotIn('\"caminho\":', serializado.casefold())
        self.assertNotIn("c:\\\\users", serializado.casefold())
        self.assertNotIn("password", serializado.casefold())
        self.assertFalse(dossie["seguranca"]["segredos_expostos"])

    @patch("apps.configuracoes.management.commands.gerar_dossie_implantacao.gerar_dossie_implantacao")
    def test_comando_grava_json_atomico_e_hash(self, gerar):
        gerar.return_value = {
            "contrato": "deployment_evidence_v1",
            "prontidao": {"pronto": False},
        }
        with TemporaryDirectory() as diretorio:
            destino = f"{diretorio}/dossie.json"
            call_command(
                "gerar_dossie_implantacao",
                "--perfil",
                "servidor-local",
                "--saida",
                destino,
                stdout=StringIO(),
            )
            with open(destino, encoding="utf-8") as arquivo:
                payload = json.load(arquivo)

            self.assertEqual(payload["contrato"], "deployment_evidence_v1")
            with open(destino + ".sha256", encoding="ascii") as arquivo:
                self.assertIn("dossie.json", arquivo.read())
            self.assertTrue(validar_dossie_implantacao(destino)["hash_valido"])

    @patch("apps.configuracoes.management.commands.gerar_dossie_implantacao.gerar_dossie_implantacao")
    def test_verificador_detecta_adulteracao(self, gerar):
        gerar.return_value = {
            "contrato": "deployment_evidence_v1",
            "perfil": "central",
            "alvo": "homologacao",
            "prontidao": {"contrato": "deployment_readiness_v2", "pronto": True},
            "artefatos": {},
        }
        with TemporaryDirectory() as diretorio:
            destino = f"{diretorio}/dossie.json"
            call_command("gerar_dossie_implantacao", "--saida", destino, stdout=StringIO())
            with open(destino, "a", encoding="utf-8") as arquivo:
                arquivo.write(" ")

            resultado = validar_dossie_implantacao(destino)

        self.assertFalse(resultado["valido"])
        self.assertFalse(resultado["hash_valido"])

    @patch("apps.configuracoes.management.commands.gerar_dossie_implantacao.gerar_dossie_implantacao")
    def test_modo_estrito_recusa_dossie_bloqueado(self, gerar):
        gerar.return_value = {
            "contrato": "deployment_evidence_v1",
            "perfil": "servidor-local",
            "alvo": "producao",
            "prontidao": {"contrato": "deployment_readiness_v2", "pronto": False},
            "artefatos": {
                "servidor_local": {"publicavel": False, "sha256": "a" * 64}
            },
        }
        with TemporaryDirectory() as diretorio:
            destino = f"{diretorio}/dossie.json"
            call_command("gerar_dossie_implantacao", "--saida", destino, stdout=StringIO())
            with self.assertRaises(CommandError):
                call_command(
                    "verificar_dossie_implantacao",
                    destino,
                    "--estrito",
                    stdout=StringIO(),
                )

