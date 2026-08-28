import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.configuracoes.readiness import (
    SERVIDOR_LOCAL_ARQUIVOS,
    diagnostico_prontidao_banco_dados,
    diagnostico_prontidao_https,
    diagnostico_prontidao_implantacao,
    diagnostico_prontidao_servidor_local,
)


def _https(pronto=True):
    return {
        "contrato": "https_deployment_readiness_v1",
        "pronto": pronto,
        "alertas": [] if pronto else ["HTTPS pendente."],
        "recomendacoes": [],
    }


def _banco(pronto=True, postgresql=True):
    return {
        "contrato": "database_deployment_readiness_v1",
        "pronto": pronto,
        "conectado": pronto,
        "backend": "postgresql" if postgresql else "outro",
        "postgresql": postgresql,
        "migracoes_pendentes": 0 if pronto else 1,
        "erro_tipo": "",
        "alertas": [] if pronto else ["Migrações pendentes."],
        "nao_expoe_credenciais": True,
    }


def _licenciamento(pronto_homologacao=True, pronto_producao=True):
    return {
        "contrato": "licensing_readiness_v1",
        "pronto_homologacao": pronto_homologacao,
        "pronto_producao": pronto_producao,
        "alertas": [] if pronto_homologacao else ["Licenciamento pendente."],
    }


def _senha(pronta=True):
    return {
        "prontidao": {
            "contrato": "password_reset_readiness_v1",
            "status": "ready_for_homologation" if pronta else "configuration_required",
            "configuracao_smtp_completa": pronta,
            "bloqueios": [] if pronta else ["SMTP pendente."],
        }
    }


def _consulta(pronta=False):
    return {
        "prontidao": {
            "contrato": "cadastro_lookup_readiness_v1",
            "status": "ready_for_provider_homologation" if pronta else "local_fallback_only",
            "pronto_homologacao": pronta,
            "bloqueios": [] if pronta else ["Provedores externos pendentes."],
        }
    }


class ProntidaoImplantacaoTests(SimpleTestCase):
    def _patches(self, *, https=None, banco=None, licenca=None, senha=None, consulta=None):
        return (
            patch(
                "apps.configuracoes.readiness.diagnostico_prontidao_https",
                return_value=https or _https(),
            ),
            patch(
                "apps.configuracoes.readiness.diagnostico_prontidao_banco_dados",
                return_value=banco or _banco(),
            ),
            patch(
                "apps.configuracoes.readiness.diagnostico_prontidao_licenciamento",
                return_value=licenca or _licenciamento(),
            ),
            patch(
                "apps.configuracoes.readiness.diagnostico_prontidao_recuperacao_senha",
                return_value=senha or _senha(),
            ),
            patch(
                "apps.configuracoes.readiness.diagnostico_prontidao_consulta_cadastro",
                return_value=consulta or _consulta(),
            ),
        )

    @override_settings(SECRET_KEY="segredo-unico-de-homologacao", ALLOWED_HOSTS=["erp.exemplo.test"], DEBUG=True)
    def test_recurso_recomendado_nao_bloqueia_homologacao(self):
        ph, p0, p1, p2, p3 = self._patches(https=_https(False))
        with ph, p0, p1, p2, p3:
            diagnostico = diagnostico_prontidao_implantacao()
        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["resumo"]["obrigatorias_prontas"], 4)
        self.assertEqual(diagnostico["resumo"]["recomendadas_prontas"], 0)
        self.assertTrue(any("consulta_cnpj_cep" in item for item in diagnostico["recomendacoes"]))
        self.assertTrue(any("seguranca_https" in item for item in diagnostico["recomendacoes"]))

    @override_settings(SECRET_KEY="django-insecure-dev", ALLOWED_HOSTS=["*"], DEBUG=True)
    def test_producao_bloqueia_configuracao_django_insegura(self):
        ph, p0, p1, p2, p3 = self._patches()
        with ph, p0, p1, p2, p3:
            diagnostico = diagnostico_prontidao_implantacao(producao=True)
        self.assertFalse(diagnostico["pronto"])
        self.assertTrue(any("SECRET_KEY" in item for item in diagnostico["bloqueios"]))
        self.assertTrue(any("DEBUG" in item for item in diagnostico["bloqueios"]))

    @override_settings(SECRET_KEY="segredo-unico", ALLOWED_HOSTS=["erp.exemplo.test"], DEBUG=False)
    def test_comando_json_nao_expoe_segredo(self):
        ph, p0, p1, p2, p3 = self._patches(consulta=_consulta(True))
        saida = StringIO()
        with ph, p0, p1, p2, p3:
            call_command("verificar_prontidao_implantacao", "--json", "--producao", stdout=saida)
        payload = json.loads(saida.getvalue())
        self.assertEqual(payload["contrato"], "deployment_readiness_v2")
        self.assertTrue(payload["pronto"])
        self.assertNotIn("segredo-unico", saida.getvalue())

    @override_settings(SECRET_KEY="segredo-unico", ALLOWED_HOSTS=["erp.exemplo.test"], DEBUG=False)
    def test_modo_estrito_falha_quando_obrigatoria_esta_pendente(self):
        ph, p0, p1, p2, p3 = self._patches(senha=_senha(False))
        with ph, p0, p1, p2, p3, self.assertRaises(CommandError):
            call_command("verificar_prontidao_implantacao", "--estrito", stdout=StringIO())


    @override_settings(SECRET_KEY="segredo-unico", ALLOWED_HOSTS=["erp.local.test"], DEBUG=False)
    def test_perfil_local_nao_valida_segredos_da_central(self):
        ph, p0, p1, p2, p3 = self._patches()
        local = {
            "contrato": "local_admin_readiness_v1",
            "pronto": True,
            "bloqueios": [],
            "recomendacoes": [],
        }
        with ph, p0, p1, p2, p3, patch(
            "apps.configuracoes.readiness.diagnostico_prontidao_servidor_local",
            return_value=local,
        ), patch(
            "apps.configuracoes.readiness.diagnostico_prontidao_licenciamento"
        ) as licenciamento:
            diagnostico = diagnostico_prontidao_implantacao(perfil="servidor-local")

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["perfil"], "servidor-local")
        self.assertNotIn("licenciamento_central", {item["id"] for item in diagnostico["verificacoes"]})
        licenciamento.assert_not_called()

    @override_settings(SECRET_KEY="segredo-unico", ALLOWED_HOSTS=["erp.local.test"], DEBUG=False)
    def test_comando_aceita_perfil_servidor_local(self):
        ph, p0, p1, p2, p3 = self._patches()
        local = {
            "contrato": "local_admin_readiness_v1",
            "pronto": True,
            "bloqueios": [],
            "recomendacoes": [],
        }
        saida = StringIO()
        with ph, p0, p1, p2, p3, patch(
            "apps.configuracoes.readiness.diagnostico_prontidao_servidor_local",
            return_value=local,
        ):
            call_command(
                "verificar_prontidao_implantacao",
                "--perfil",
                "servidor-local",
                "--json",
                stdout=saida,
            )

        payload = json.loads(saida.getvalue())
        self.assertEqual(payload["perfil"], "servidor-local")


class ProntidaoServidorLocalTests(SimpleTestCase):
    def test_arquivos_ausentes_bloqueiam_servidor_local(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as diretorio:
            diagnostico = diagnostico_prontidao_servidor_local(base_dir=diretorio)

        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(len(diagnostico["arquivos"]), len(SERVIDOR_LOCAL_ARQUIVOS))
        self.assertTrue(diagnostico["bloqueios"])



class ProntidaoBancoDadosTests(TestCase):
    def test_sqlite_e_aceito_em_homologacao_mas_bloqueado_em_producao(self):
        homologacao = diagnostico_prontidao_banco_dados(producao=False)
        producao = diagnostico_prontidao_banco_dados(producao=True)

        self.assertTrue(homologacao["conectado"])
        self.assertEqual(homologacao["migracoes_pendentes"], 0)
        self.assertTrue(homologacao["pronto"])
        self.assertFalse(producao["pronto"])
        self.assertFalse(producao["postgresql"])
        self.assertTrue(producao["nao_expoe_credenciais"])
        self.assertNotIn("NAME", producao)
        self.assertNotIn("PASSWORD", producao)



class ProntidaoHttpsTests(SimpleTestCase):
    @override_settings(
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_SSL_REDIRECT=True,
        SECURE_HSTS_SECONDS=3600,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        CSRF_TRUSTED_ORIGINS=["https://erp.exemplo.test"],
    )
    def test_https_completo_fica_pronto_sem_expor_origem(self):
        diagnostico = diagnostico_prontidao_https()

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["origens_csrf_configuradas"], 1)
        self.assertTrue(diagnostico["nao_expoe_origens"])
        self.assertNotIn("https://erp.exemplo.test", str(diagnostico))

    @override_settings(
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        SECURE_SSL_REDIRECT=False,
        SECURE_HSTS_SECONDS=0,
        SECURE_PROXY_SSL_HEADER=None,
        CSRF_TRUSTED_ORIGINS=["http://erp.exemplo.test"],
    )
    def test_http_inseguro_e_bloqueado_para_producao(self):
        diagnostico = diagnostico_prontidao_https()

        self.assertFalse(diagnostico["pronto"])
        self.assertFalse(diagnostico["origens_csrf_https"])
        self.assertGreaterEqual(len(diagnostico["alertas"]), 6)


class PoliticaMidiaOfflineTests(SimpleTestCase):
    def _diagnostico(self, *, exigir, pronta):
        local = {
            "contrato": "local_admin_readiness_v1",
            "pronto": True,
            "bloqueios": [],
            "recomendacoes": [],
        }
        midia = {
            "contrato": "offline_installation_media_readiness_v1",
            "pronto": pronta,
            "alertas": [] if pronta else ["Publicação offline pendente."],
        }
        with patch(
            "apps.configuracoes.readiness._diagnostico_seguranca_django",
            return_value={"contrato": "django_deployment_security_v1", "pronto": True, "alertas": []},
        ), patch(
            "apps.configuracoes.readiness.diagnostico_prontidao_https",
            return_value=_https(),
        ), patch(
            "apps.configuracoes.readiness.diagnostico_prontidao_banco_dados",
            return_value=_banco(),
        ), patch(
            "apps.configuracoes.readiness.diagnostico_prontidao_recuperacao_senha",
            return_value=_senha(),
        ), patch(
            "apps.configuracoes.readiness.diagnostico_prontidao_consulta_cadastro",
            return_value=_consulta(),
        ), patch(
            "apps.configuracoes.readiness.diagnostico_prontidao_servidor_local",
            return_value=local,
        ), patch(
            "apps.configuracoes.readiness.diagnostico_prontidao_midia_offline",
            return_value=midia,
        ):
            return diagnostico_prontidao_implantacao(
                perfil="servidor-local",
                exigir_midia_offline=exigir,
            )

    def test_midia_ausente_e_recomendacao_quando_instalacao_tem_rede(self):
        diagnostico = self._diagnostico(exigir=False, pronta=False)
        verificacao = next(
            item
            for item in diagnostico["verificacoes"]
            if item["id"] == "midia_instalacao_offline"
        )

        self.assertTrue(diagnostico["pronto"])
        self.assertFalse(verificacao["obrigatoria"])
        self.assertFalse(diagnostico["politica_instalacao"]["midia_offline_exigida"])
        self.assertTrue(
            any("midia_instalacao_offline" in item for item in diagnostico["recomendacoes"])
        )

    def test_midia_ausente_bloqueia_quando_instalacao_e_offline(self):
        diagnostico = self._diagnostico(exigir=True, pronta=False)

        self.assertFalse(diagnostico["pronto"])
        self.assertTrue(diagnostico["politica_instalacao"]["midia_offline_exigida"])
        self.assertTrue(
            any("midia_instalacao_offline" in item for item in diagnostico["bloqueios"])
        )

    def test_midia_integra_libera_prontidao_offline(self):
        diagnostico = self._diagnostico(exigir=True, pronta=True)

        self.assertTrue(diagnostico["pronto"])
        verificacao = next(
            item
            for item in diagnostico["verificacoes"]
            if item["id"] == "midia_instalacao_offline"
        )
        self.assertTrue(verificacao["obrigatoria"])
        self.assertTrue(verificacao["pronta"])
