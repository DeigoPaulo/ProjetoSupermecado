import json
from unittest.mock import patch

from django.test import Client, TestCase

from apps.fiscal.estrategia_normalizacao_cnpj import calcular_dv_cnpj

from .credenciais_sincronizacao import token_sincronizacao_para_cnpj
from .models import Empresa, EventoSincronizacao, Filial, ModoImplantacao
from .services_eventos_entrada import _filial_por_cnpj
from .services_sincronizacao import enviar_evento_http


def _cnpj(base):
    return base + calcular_dv_cnpj(base)


def _mascarar(valor):
    return f"{valor[:2]}.{valor[2:5]}.{valor[5:8]}/{valor[8:12]}-{valor[12:]}"


class IdentidadeCnpjSincronizacaoTests(TestCase):
    def setUp(self):
        self.cnpj = _cnpj("12ABC34501DE")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Alfa Ltda",
            nome_fantasia="Mercado Alfa",
            cnpj=self.cnpj,
            modo_implantacao=ModoImplantacao.HIBRIDO,
            sincronizacao_automatica=True,
            url_sincronizacao="https://nuvem.example/api/",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Alfa",
            cnpj=self.cnpj,
        )
        self.client = Client(HTTP_HOST="localhost")

    def test_credencial_e_receptor_preservam_cnpj_alfanumerico_mascarado(self):
        mascarado = _mascarar(self.cnpj).lower()
        with self.settings(
            SINCRONIZACAO_API_TOKEN="",
            SINCRONIZACAO_TOKENS_EMPRESA={mascarado: "token-alfa"},
            SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=False,
        ):
            token, origem = token_sincronizacao_para_cnpj(self.cnpj)
            response = self.client.post(
                "/empresas/api/sincronizacao/eventos/",
                data={
                    "id": "470f8f5d-72b7-4a03-9009-07f5998585d1",
                    "tipo": "sistema.ping",
                    "empresa_cnpj": mascarado,
                    "payload": {},
                },
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer token-alfa",
                HTTP_IDEMPOTENCY_KEY="alfa:ping:1",
            )

        self.assertEqual((token, origem), ("token-alfa", "empresa"))
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "recebido")

    def test_resolucao_de_filial_compara_identidade_canonica(self):
        filial = _filial_por_cnpj(self.empresa.filiais.all(), _mascarar(self.cnpj).lower())
        self.assertEqual(filial, self.filial)

    def test_emissor_serializa_empresa_e_filial_sem_descartar_letras(self):
        evento = EventoSincronizacao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            tipo="sistema.ping",
            objeto_tipo="Empresa",
            objeto_id=str(self.empresa.pk),
            payload={},
            chave_idempotencia="alfa:saida:1",
        )

        class Resposta:
            status = 202

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with self.settings(
            SINCRONIZACAO_TOKENS_EMPRESA={self.cnpj: "token-alfa"},
            SINCRONIZACAO_PERMITE_TOKEN_GLOBAL=False,
        ), patch("apps.empresas.services_sincronizacao.urlopen", return_value=Resposta()) as chamada:
            enviar_evento_http(evento)

        payload = json.loads(chamada.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["empresa_cnpj"], self.cnpj)
        self.assertEqual(payload["filial_cnpj"], self.cnpj)

