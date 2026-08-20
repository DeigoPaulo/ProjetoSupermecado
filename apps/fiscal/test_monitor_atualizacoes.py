from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.auditoria.models import LogAuditoria

from .models import (
    AlertaAtualizacaoFiscal,
    FonteAtualizacaoFiscal,
    StatusAlertaAtualizacaoFiscal,
    StatusFonteAtualizacaoFiscal,
)
from .monitor_atualizacoes import (
    MonitorAtualizacaoFiscalError,
    monitorar_atualizacoes_fiscais,
)


FONTE = {
    "codigo": "portal-nfe-teste",
    "nome": "Portal Nacional NF-e - Teste",
    "url": "https://www.nfe.fazenda.gov.br/portal/teste",
}
HTML_BASE = b"<html><body><a>Nota Tecnica 2025.001 versao 1.00</a></body></html>"
HTML_NOVO = b"""<html><body>
<a>Nota Tecnica 2025.001 versao 1.00</a>
<a>Nota Tecnica 2026.005 versao 1.00 publicada</a>
</body></html>"""


def resposta(conteudo):
    return {
        "status": 200,
        "conteudo": conteudo,
        "etag": '"teste"',
        "ultima_modificacao": "Thu, 20 Aug 2026 12:00:00 GMT",
        "url_final": FONTE["url"],
    }


class MonitorAtualizacoesFiscaisTests(TestCase):
    @override_settings(FISCAL_UPDATE_MONITOR_ENABLED=False)
    def test_desabilitado_nao_consulta_rede(self):
        chamado = False

        def fetcher(*args):
            nonlocal chamado
            chamado = True

        resultado = monitorar_atualizacoes_fiscais(fetcher=fetcher, fontes=[FONTE])

        self.assertFalse(resultado["habilitado"])
        self.assertFalse(chamado)
        self.assertFalse(FonteAtualizacaoFiscal.objects.exists())

    @override_settings(FISCAL_UPDATE_MONITOR_ENABLED=True)
    def test_primeira_consulta_registra_baseline_sem_alerta(self):
        resultado = monitorar_atualizacoes_fiscais(
            fetcher=lambda fonte, estado: resposta(HTML_BASE),
            fontes=[FONTE],
        )

        estado = FonteAtualizacaoFiscal.objects.get(codigo=FONTE["codigo"])
        self.assertEqual(estado.status, StatusFonteAtualizacaoFiscal.OK)
        self.assertTrue(estado.conteudo_sha256)
        self.assertEqual(resultado["alertas_criados"], 0)
        self.assertFalse(AlertaAtualizacaoFiscal.objects.exists())

    @override_settings(FISCAL_UPDATE_MONITOR_ENABLED=True)
    def test_novidade_cria_um_alerta_idempotente_e_audita(self):
        monitorar_atualizacoes_fiscais(
            fetcher=lambda fonte, estado: resposta(HTML_BASE),
            fontes=[FONTE],
        )
        primeiro = monitorar_atualizacoes_fiscais(
            fetcher=lambda fonte, estado: resposta(HTML_NOVO),
            fontes=[FONTE],
        )
        segundo = monitorar_atualizacoes_fiscais(
            fetcher=lambda fonte, estado: resposta(HTML_NOVO),
            fontes=[FONTE],
        )

        self.assertEqual(primeiro["alertas_criados"], 1)
        self.assertEqual(segundo["alertas_criados"], 0)
        self.assertEqual(AlertaAtualizacaoFiscal.objects.count(), 1)
        self.assertTrue(
            LogAuditoria.objects.filter(acao="ATUALIZACOES_FISCAIS_DETECTADAS").exists()
        )

    @override_settings(FISCAL_UPDATE_MONITOR_ENABLED=True)
    def test_falha_fica_registrada_sem_interromper_as_demais_fontes(self):
        def fetcher(fonte, estado):
            raise MonitorAtualizacaoFiscalError("Falha controlada de teste.")

        resultado = monitorar_atualizacoes_fiscais(fetcher=fetcher, fontes=[FONTE])

        estado = FonteAtualizacaoFiscal.objects.get(codigo=FONTE["codigo"])
        self.assertEqual(estado.status, StatusFonteAtualizacaoFiscal.ERRO)
        self.assertEqual(len(resultado["falhas"]), 1)

    @override_settings(FISCAL_UPDATE_MONITOR_ENABLED=True)
    def test_rejeita_fonte_fora_da_lista_oficial(self):
        fonte = {**FONTE, "url": "https://exemplo.com/fiscal"}
        with self.assertRaises(MonitorAtualizacaoFiscalError):
            monitorar_atualizacoes_fiscais(fontes=[fonte])

    @override_settings(FISCAL_UPDATE_MONITOR_ENABLED=False)
    def test_comando_informa_monitor_desabilitado(self):
        saida = StringIO()
        call_command("monitorar_atualizacoes_fiscais", stdout=saida)
        self.assertIn("Monitor fiscal desabilitado", saida.getvalue())


class TelaAtualizacoesFiscaisTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="admin_monitor_fiscal",
            email="admin@example.com",
            password="senha-forte-teste",
        )
        self.comum = User.objects.create_user(
            username="usuario_monitor_fiscal",
            password="senha-forte-teste",
        )
        self.fonte = FonteAtualizacaoFiscal.objects.create(
            codigo=FONTE["codigo"],
            nome=FONTE["nome"],
            url=FONTE["url"],
        )
        self.alerta = AlertaAtualizacaoFiscal.objects.create(
            fonte=self.fonte,
            fingerprint="a" * 64,
            titulo="Nota Técnica fiscal publicada",
            url_referencia=FONTE["url"],
        )

    def test_apenas_administrador_acessa_tela(self):
        self.client.force_login(self.comum)
        resposta_http = self.client.get(reverse("fiscal:atualizacoes"))
        self.assertEqual(resposta_http.status_code, 403)

        self.client.force_login(self.admin)
        resposta_http = self.client.get(reverse("fiscal:atualizacoes"))
        self.assertEqual(resposta_http.status_code, 200)
        self.assertContains(resposta_http, "Nota Técnica fiscal publicada")

    def test_admin_revisa_alerta_com_auditoria(self):
        self.client.force_login(self.admin)
        resposta_http = self.client.post(
            reverse("fiscal:revisar_atualizacao", args=[self.alerta.pk]),
            {"status": StatusAlertaAtualizacaoFiscal.REVISADO},
        )

        self.assertRedirects(resposta_http, reverse("fiscal:atualizacoes"))
        self.alerta.refresh_from_db()
        self.assertEqual(self.alerta.status, StatusAlertaAtualizacaoFiscal.REVISADO)
        self.assertEqual(self.alerta.revisado_por, self.admin)
        self.assertTrue(
            LogAuditoria.objects.filter(acao="REVISA_ATUALIZACAO_FISCAL").exists()
        )
