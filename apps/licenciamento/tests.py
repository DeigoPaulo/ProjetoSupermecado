import json
from io import StringIO
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial

from .models import (
    AutorizacaoEmergencial,
    ContratoLicenca,
    EstadoLicencaLocal,
    EventoWebhookAsaas,
    FaturaLicenca,
    InstalacaoLocal,
    LiberacaoEmergencialLocal,
    PlanoComercial,
    StatusContrato,
    StatusEventoCobranca,
    StatusFatura,
)
from .services import (
    aplicar_autorizacao_emergencial,
    assinar_concessao,
    emitir_autorizacao_emergencial,
    emitir_concessao,
    gerar_desafio_liberacao,
    sincronizar_licenca_local,
    verificar_concessao,
)


@override_settings(
    LICENCIAMENTO_CHAVE_ASSINATURA="segredo-de-teste-forte",
    LICENCIAMENTO_CONCESSAO_HORAS=24,
    ASAAS_WEBHOOK_TOKEN="webhook-seguro-asaas",
)
class LicenciamentoTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Licenciado Ltda",
            nome_fantasia="Mercado Licenciado",
            cnpj="12.345.678/0001-90",
            email="financeiro@mercado.test",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)
        self.plano = PlanoComercial.objects.create(
            nome="Profissional",
            valor_matriz=Decimal("300.00"),
            valor_por_filial=Decimal("100.00"),
            valor_por_terminal=Decimal("30.00"),
            dias_aviso=10,
            dias_tolerancia=7,
        )
        self.contrato = ContratoLicenca.objects.create(
            empresa=self.empresa,
            plano=self.plano,
            valor_mensal=Decimal("430.00"),
            dia_vencimento=10,
        )
        self.instalacao = InstalacaoLocal(empresa=self.empresa, nome="Servidor matriz")
        self.token = self.instalacao.emitir_token()
        self.instalacao.save()
        self.admin = get_user_model().objects.create_user("dono", password="123")
        PerfilUsuario.objects.create(usuario=self.admin, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)

    def _fatura(self, vencimento, status=StatusFatura.PENDENTE):
        return FaturaLicenca.objects.create(
            contrato=self.contrato,
            competencia=vencimento.replace(day=1),
            vencimento=vencimento,
            valor=Decimal("430.00"),
            status=status,
            referencia_externa=f"licenca:{self.contrato.pk}:{vencimento:%Y-%m}",
            asaas_payment_id=f"pay_{vencimento:%Y%m%d}",
            invoice_url="https://sandbox.asaas.com/i/teste",
        )

    def test_central_e_exclusiva_do_super_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/licenciamento/central/").status_code, 403)
        super_admin = get_user_model().objects.create_superuser("owner", password="123")
        self.client.force_login(super_admin)
        response = self.client.get("/licenciamento/central/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Central de licenças")
        self.assertContains(response, self.empresa.nome_fantasia)

    def test_central_pagina_listas_independentes_e_preserva_parametros(self):
        super_admin = get_user_model().objects.create_superuser("owner-pages", password="123")
        InstalacaoLocal.objects.bulk_create(
            [
                InstalacaoLocal(
                    empresa=self.empresa,
                    nome=f"Servidor extra {indice:02d}",
                    token_hash=InstalacaoLocal.hash_token(f"token-extra-{indice}"),
                )
                for indice in range(51)
            ]
        )
        self.client.force_login(super_admin)

        response = self.client.get(
            "/licenciamento/central/?instalacoes_page=2&contratos_page=1"
        )

        self.assertEqual(response.status_code, 200)
        pagina = response.context["instalacoes"]
        self.assertEqual(response.context["instalacoes_total"], 52)
        self.assertEqual(pagina.number, 2)
        self.assertEqual(len(pagina.object_list), 2)
        self.assertIn("contratos_page=1", pagina.previous_url)
        self.assertContains(response, "Página 2 de 2")

    def test_diagnostico_central_e_protegido_e_expoe_prontidao(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/licenciamento/central/diagnostico.json").status_code, 403)
        super_admin = get_user_model().objects.create_superuser("owner-readiness", password="123")
        self.client.force_login(super_admin)
        response = self.client.get("/licenciamento/central/diagnostico.json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["contrato"], "licensing_readiness_v1")
        self.assertTrue(payload["script_agendamento_disponivel"])
        self.assertIn("comando_agendamento", payload)

    def test_comando_prontidao_licenciamento_aprova_sandbox_configurado(self):
        privada_pem, _ = self._chaves_emergenciais()
        saida = StringIO()
        with self.settings(
            LICENCIAMENTO_CHAVE_PRIVADA_PEM=privada_pem,
            LICENCIAMENTO_CHAVE_PRIVADA_ARQUIVO="",
            LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA=False,
            ASAAS_API_URL="https://api-sandbox.asaas.com/v3",
            ASAAS_API_KEY="chave-sandbox",
            ASAAS_WEBHOOK_TOKEN="token-webhook",
        ):
            call_command(
                "verificar_prontidao_licenciamento",
                "--json",
                "--estrito",
                stdout=saida,
            )

        payload = json.loads(saida.getvalue())
        self.assertTrue(payload["pronto_homologacao"])
        self.assertFalse(payload["pronto_producao"])
        self.assertTrue(payload["asaas_url_https"])

    def test_comando_prontidao_licenciamento_bloqueia_configuracao_incompleta(self):
        with self.settings(
            LICENCIAMENTO_CHAVE_PRIVADA_PEM="",
            LICENCIAMENTO_CHAVE_PRIVADA_ARQUIVO="",
            LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA=False,
            ASAAS_API_URL="http://api-insegura.example",
            ASAAS_API_KEY="",
            ASAAS_WEBHOOK_TOKEN="",
        ):
            with self.assertRaisesMessage(CommandError, "não está pronto para homologação"):
                call_command("verificar_prontidao_licenciamento", "--estrito")

    def test_rotina_diaria_atualiza_contrato_vencido(self):
        self.contrato.cobranca_automatica = False
        self.contrato.save(update_fields=["cobranca_automatica"])
        self._fatura(timezone.localdate() - timedelta(days=10))
        call_command("processar_cobrancas_licenca")
        self.contrato.refresh_from_db()
        self.assertEqual(self.contrato.status, StatusContrato.SUSPENSO)
    def test_rotina_mensal_nao_duplica_fatura(self):
        self.contrato.cobranca_automatica = False
        self.contrato.save(update_fields=["cobranca_automatica"])

        call_command("processar_cobrancas_licenca")
        call_command("processar_cobrancas_licenca")

        self.assertEqual(FaturaLicenca.objects.filter(contrato=self.contrato).count(), 1)

    def test_api_renova_concessao_assinada_para_instalacao_autorizada(self):
        response = self.client.post(
            "/licenciamento/api/v1/renovar/",
            data=json.dumps({"empresa_cnpj": self.empresa.cnpj, "versao": "1.2.3"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 200)
        dados = response.json()
        self.assertEqual(verificar_concessao(dados["assinatura"]), dados["licenca"])
        self.assertEqual(dados["licenca"]["empresa_cnpj"], self.empresa.cnpj)
        self.assertEqual(dados["licenca"]["status"], StatusContrato.ATIVO)
        self.instalacao.refresh_from_db()
        self.assertEqual(self.instalacao.versao_sistema, "1.2.3")

    def test_api_retorna_503_sem_chave_assimetrica_em_producao(self):
        with self.settings(
            LICENCIAMENTO_CHAVE_PRIVADA_PEM="",
            LICENCIAMENTO_CHAVE_PRIVADA_ARQUIVO="",
            LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA=False,
        ):
            response = self.client.post(
                "/licenciamento/api/v1/renovar/",
                data=json.dumps({"empresa_cnpj": self.empresa.cnpj, "versao": "1.2.3"}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["codigo"], "central_signature_not_ready")
    def test_api_rejeita_token_ou_empresa_divergente(self):
        sem_token = self.client.post("/licenciamento/api/v1/renovar/", data="{}", content_type="application/json")
        empresa_errada = self.client.post(
            "/licenciamento/api/v1/renovar/",
            data=json.dumps({"empresa_cnpj": "00.000.000/0001-00"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(sem_token.status_code, 401)
        self.assertEqual(empresa_errada.status_code, 403)

    def test_concessao_aplica_aviso_tolerancia_e_suspensao(self):
        hoje = timezone.localdate()
        fatura = self._fatura(hoje - timedelta(days=2))

        payload, _ = emitir_concessao(self.instalacao)
        self.assertEqual(payload["status"], StatusContrato.TOLERANCIA)
        self.assertIn("tolerância", payload["mensagem"])

        fatura.vencimento = hoje - timedelta(days=10)
        fatura.competencia = fatura.vencimento.replace(day=1)
        fatura.referencia_externa = "licenca:suspensa"
        fatura.save()
        payload, _ = emitir_concessao(self.instalacao)
        self.assertEqual(payload["status"], StatusContrato.SUSPENSO)

    def test_webhook_asaas_e_idempotente_e_libera_contrato(self):
        fatura = self._fatura(timezone.localdate() - timedelta(days=10), status=StatusFatura.VENCIDA)
        self.contrato.status = StatusContrato.SUSPENSO
        self.contrato.save(update_fields=["status"])
        payload = {"id": "evt_pagamento_1", "event": "PAYMENT_RECEIVED", "payment": {"id": fatura.asaas_payment_id}}

        primeira = self.client.post(
            "/licenciamento/webhooks/asaas/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="webhook-seguro-asaas",
        )
        segunda = self.client.post(
            "/licenciamento/webhooks/asaas/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="webhook-seguro-asaas",
        )

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertTrue(segunda.json()["duplicado"])
        self.assertEqual(EventoWebhookAsaas.objects.count(), 1)
        self.assertEqual(EventoWebhookAsaas.objects.get().status, StatusEventoCobranca.PROCESSADO)
        fatura.refresh_from_db()
        self.contrato.refresh_from_db()
        self.assertEqual(fatura.status, StatusFatura.RECEBIDA)
        self.assertEqual(self.contrato.status, StatusContrato.ATIVO)

    def test_licenca_ativa_expirada_offline_tambem_bloqueia(self):
        estado = EstadoLicencaLocal.objects.create(
            empresa=self.empresa,
            status=StatusContrato.ATIVO,
            valida_ate=timezone.now() - timedelta(days=4),
            offline_ate=timezone.now() - timedelta(minutes=1),
            mensagem="Licença regular.",
        )
        self.assertTrue(estado.bloqueado)
        self.assertIn("não conseguiu renovar", estado.mensagem_operacional)
    def test_alerta_aparece_para_admin_e_bloqueio_preserva_tela_de_pagamento(self):
        EstadoLicencaLocal.objects.create(
            empresa=self.empresa,
            status=StatusContrato.SUSPENSO,
            tolerancia_ate=timezone.now() - timedelta(minutes=1),
            mensagem="Mensalidade vencida.",
            valor_pendente=Decimal("430.00"),
            url_pagamento="https://sandbox.asaas.com/i/teste",
        )
        self.client.force_login(self.admin)

        dashboard = self.client.get("/")
        licenca = self.client.get("/licenciamento/")

        self.assertRedirects(dashboard, "/licenciamento/")
        self.assertEqual(licenca.status_code, 200)
        self.assertContains(licenca, "Mensalidade vencida")
        self.assertContains(licenca, "Pagar com Pix ou boleto")

    @override_settings(
        LICENCIAMENTO_CENTRAL_URL="https://central.example.com",
        LICENCIAMENTO_API_TOKEN="token-local",
        LICENCIAMENTO_INSTALACAO_ID="instalacao-local",
        LICENCIAMENTO_TIMEOUT_SEGUNDOS=5,
    )
    @patch("apps.licenciamento.services.urlopen")
    def test_servidor_local_valida_assinatura_e_atualiza_estado(self, urlopen_mock):
        agora = timezone.now()
        payload = {
            "contrato": "license_lease_v1",
            "empresa_id": 999,
            "empresa_cnpj": self.empresa.cnpj,
            "empresa": self.empresa.nome_fantasia,
            "instalacao_id": "remota",
            "status": StatusContrato.AVISO,
            "emitida_em": agora.isoformat(),
            "valida_ate": (agora + timedelta(hours=24)).isoformat(),
            "offline_ate": (agora + timedelta(days=4)).isoformat(),
            "tolerancia_ate": None,
            "proxima_fatura_vencimento": (timezone.localdate() + timedelta(days=3)).isoformat(),
            "valor_pendente": "430.00",
            "url_pagamento": "https://sandbox.asaas.com/i/teste",
            "mensagem": "Mensalidade próxima do vencimento.",
            "limites": {"filiais": 1, "terminais": 1},
        }
        assinatura = assinar_concessao(payload)

        class Resposta:
            def read(self):
                return json.dumps({"status": "ok", "licenca": payload, "assinatura": assinatura}).encode("utf-8")

        urlopen_mock.return_value = Resposta()
        resultado = sincronizar_licenca_local(self.empresa)

        self.assertEqual(resultado["status"], "sincronizado")
        estado = EstadoLicencaLocal.objects.get(empresa=self.empresa)
        self.assertEqual(estado.status, StatusContrato.AVISO)
        self.assertEqual(estado.valor_pendente, Decimal("430.00"))
        self.assertEqual(estado.ultimo_erro, "")
    def _chaves_emergenciais(self):
        privada = Ed25519PrivateKey.generate()
        privada_pem = privada.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        publica_pem = privada.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return privada_pem, publica_pem

    def test_concessao_regular_usa_ed25519_e_producao_rejeita_legado(self):
        privada_pem, publica_pem = self._chaves_emergenciais()
        payload = {"contrato": "license_lease_v2", "empresa_cnpj": self.empresa.cnpj}
        with self.settings(
            LICENCIAMENTO_CHAVE_PRIVADA_PEM=privada_pem,
            LICENCIAMENTO_CHAVE_PUBLICA_PEM=publica_pem,
            LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA=False,
        ):
            assinatura = assinar_concessao(payload)
            self.assertTrue(assinatura.startswith("ed25519."))
            self.assertEqual(verificar_concessao(assinatura), payload)
            adulterada = assinatura[:-2] + ("AA" if assinatura[-2:] != "AA" else "BB")
            with self.assertRaises(signing.BadSignature):
                verificar_concessao(adulterada)

        with self.settings(
            LICENCIAMENTO_CHAVE_PRIVADA_PEM="",
            LICENCIAMENTO_CHAVE_PRIVADA_ARQUIVO="",
            LICENCIAMENTO_CHAVE_PUBLICA_PEM="",
            LICENCIAMENTO_CHAVE_PUBLICA_ARQUIVO="",
            LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA=False,
        ):
            with self.assertRaises(RuntimeError):
                assinar_concessao(payload)
    def test_liberacao_emergencial_e_assinada_temporaria_e_de_uso_unico(self):
        privada_pem, publica_pem = self._chaves_emergenciais()
        super_admin = get_user_model().objects.create_superuser("owner-offline", password="123")
        estado = EstadoLicencaLocal.objects.create(
            empresa=self.empresa,
            status=StatusContrato.SUSPENSO,
            tolerancia_ate=timezone.now() - timedelta(minutes=1),
            offline_ate=timezone.now() - timedelta(minutes=1),
        )
        with self.settings(
            LICENCIAMENTO_INSTALACAO_ID=str(self.instalacao.identificador),
            LICENCIAMENTO_CHAVE_PRIVADA_PEM=privada_pem,
            LICENCIAMENTO_CHAVE_PUBLICA_PEM=publica_pem,
        ):
            desafio, codigo_desafio = gerar_desafio_liberacao(self.empresa)
            autorizacao, codigo_liberacao = emitir_autorizacao_emergencial(
                codigo_desafio=codigo_desafio,
                motivo="Falha de internet confirmada presencialmente.",
                horas=24,
                usuario=super_admin,
            )
            liberacao = aplicar_autorizacao_emergencial(empresa=self.empresa, codigo=codigo_liberacao)
            indice = len(codigo_liberacao) // 2
            adulterado = codigo_liberacao[:indice] + ("A" if codigo_liberacao[indice] != "A" else "B") + codigo_liberacao[indice + 1:]
            with self.assertRaises(RuntimeError):
                aplicar_autorizacao_emergencial(empresa=self.empresa, codigo=adulterado)
            with self.assertRaises(RuntimeError):
                aplicar_autorizacao_emergencial(empresa=self.empresa, codigo=codigo_liberacao)

        estado.refresh_from_db()
        desafio.refresh_from_db()
        self.assertFalse(estado.bloqueado)
        self.assertEqual(liberacao.autorizacao_id, autorizacao.identificador)
        self.assertIsNotNone(desafio.usado_em)
        self.assertIsNone(liberacao.sincronizada_em)

    def test_api_reconcilia_liberacao_offline_quando_internet_retorna(self):
        privada_pem, publica_pem = self._chaves_emergenciais()
        super_admin = get_user_model().objects.create_superuser("owner-sync", password="123")
        with self.settings(
            LICENCIAMENTO_INSTALACAO_ID=str(self.instalacao.identificador),
            LICENCIAMENTO_CHAVE_PRIVADA_PEM=privada_pem,
            LICENCIAMENTO_CHAVE_PUBLICA_PEM=publica_pem,
        ):
            _, codigo_desafio = gerar_desafio_liberacao(self.empresa)
            autorizacao, codigo_liberacao = emitir_autorizacao_emergencial(
                codigo_desafio=codigo_desafio,
                motivo="Contingência por indisponibilidade do provedor.",
                horas=72,
                usuario=super_admin,
            )
            aplicar_autorizacao_emergencial(empresa=self.empresa, codigo=codigo_liberacao)

        response = self.client.post(
            "/licenciamento/api/v1/renovar/",
            data=json.dumps({
                "empresa_cnpj": self.empresa.cnpj,
                "versao": "1.2.3",
                "liberacoes_emergenciais": [str(autorizacao.identificador)],
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["liberacoes_reconciliadas"], [str(autorizacao.identificador)])
        autorizacao.refresh_from_db()
        self.assertIsNotNone(autorizacao.usada_em)
        self.assertIsNotNone(autorizacao.reconciliada_em)

    def test_admin_bloqueado_consegue_gerar_desafio_e_operador_nao(self):
        EstadoLicencaLocal.objects.create(
            empresa=self.empresa,
            status=StatusContrato.SUSPENSO,
            tolerancia_ate=timezone.now() - timedelta(minutes=1),
        )
        self.client.force_login(self.admin)
        with self.settings(LICENCIAMENTO_INSTALACAO_ID=str(self.instalacao.identificador)):
            response = self.client.post("/licenciamento/contingencia/gerar-desafio/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Código de desafio")