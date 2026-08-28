import hashlib
import json
from io import StringIO
from pathlib import Path
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



class PoliticaMidiaOfflineDossieTests(SimpleTestCase):
    def _validar(self, payload):
        conteudo = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        with TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "dossie.json"
            caminho.write_bytes(conteudo)
            digest = hashlib.sha256(conteudo).hexdigest()
            caminho.with_name(caminho.name + ".sha256").write_text(
                f"{digest}  {caminho.name}\n",
                encoding="ascii",
            )
            return validar_dossie_implantacao(caminho)

    def _payload(self, *, exigir, offline_publicavel):
        verificacao_offline = {
            "id": "midia_instalacao_offline",
            "obrigatoria": exigir,
            "pronta": offline_publicavel,
        }
        return {
            "contrato": "deployment_evidence_v1",
            "perfil": "servidor-local",
            "alvo": "producao",
            "politica_instalacao": {
                "contrato": "local_installation_media_policy_v1",
                "midia_offline_exigida": exigir,
            },
            "prontidao": {
                "contrato": "deployment_readiness_v2",
                "pronto": not exigir or offline_publicavel,
                "verificacoes": [verificacao_offline],
            },
            "artefatos": {
                "servidor_local": {"publicavel": True, "sha256": "a" * 64},
                "servidor_offline": {
                    "publicavel": offline_publicavel,
                    "sha256": "b" * 64,
                    "contrato_publicacao": "detech_server_offline_publication_validation_v1",
                },
            },
        }

    def test_dossie_com_rede_nao_exige_publicacao_offline(self):
        resultado = self._validar(self._payload(exigir=False, offline_publicavel=False))

        self.assertTrue(resultado["liberavel"])
        self.assertFalse(resultado["midia_offline_exigida"])

    def test_dossie_offline_bloqueia_publicacao_pendente(self):
        resultado = self._validar(self._payload(exigir=True, offline_publicavel=False))

        self.assertFalse(resultado["liberavel"])
        self.assertTrue(resultado["midia_offline_exigida"])
        self.assertTrue(any("servidor_offline" in item for item in resultado["avisos"]))

    def test_dossie_offline_integro_e_liberavel(self):
        resultado = self._validar(self._payload(exigir=True, offline_publicavel=True))

        self.assertTrue(resultado["liberavel"])
        self.assertTrue(resultado["midia_offline_exigida"])
