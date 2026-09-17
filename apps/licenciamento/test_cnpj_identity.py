from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from apps.empresas.models import Empresa
from apps.fiscal.estrategia_normalizacao_cnpj import calcular_dv_cnpj

from .models import ContratoLicenca, InstalacaoLocal, PlanoComercial
from .services import (
    emitir_concessao,
    garantir_cliente_asaas,
    gerar_desafio_liberacao,
    ler_desafio_liberacao,
)


def _cnpj(base):
    return base + calcular_dv_cnpj(base)


def _mascarar(valor):
    return f"{valor[:2]}.{valor[2:5]}.{valor[5:8]}/{valor[8:12]}-{valor[12:]}"


@override_settings(LICENCIAMENTO_CHAVE_ASSINATURA="segredo-cnpj-alfa")
class IdentidadeCnpjLicenciamentoTests(TestCase):
    def setUp(self):
        self.cnpj = _cnpj("12ABC34501DE")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Alfa Licenciado Ltda",
            nome_fantasia="Mercado Alfa Licenciado",
            cnpj=self.cnpj,
            email="alfa@example.test",
        )
        plano = PlanoComercial.objects.create(
            nome="Plano Alfa",
            valor_matriz=Decimal("100.00"),
            valor_por_filial=Decimal("0.00"),
            valor_por_terminal=Decimal("0.00"),
        )
        self.contrato = ContratoLicenca.objects.create(
            empresa=self.empresa,
            plano=plano,
            valor_mensal=Decimal("100.00"),
        )
        self.instalacao = InstalacaoLocal(empresa=self.empresa, nome="Servidor Alfa")
        self.token = self.instalacao.emitir_token()
        self.instalacao.save()
        self.client = Client(HTTP_HOST="localhost")

    def test_concessao_desafio_e_api_preservam_identidade_alfanumerica(self):
        payload, _ = emitir_concessao(self.instalacao)
        with self.settings(LICENCIAMENTO_INSTALACAO_ID=str(self.instalacao.identificador)):
            _, codigo = gerar_desafio_liberacao(self.empresa)
        desafio = ler_desafio_liberacao(codigo)
        response = self.client.post(
            "/licenciamento/api/v1/renovar/",
            data={"empresa_cnpj": _mascarar(self.cnpj).lower(), "versao": "alfa"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(payload["empresa_cnpj"], self.cnpj)
        self.assertEqual(desafio["empresa_cnpj"], self.cnpj)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["licenca"]["empresa_cnpj"], self.cnpj)

    @patch("apps.licenciamento.services._asaas_request")
    def test_asaas_bloqueia_sem_capacidade_e_preserva_letras_quando_habilitado(self, request_mock):
        with self.settings(ASAAS_SUPORTA_CNPJ_ALFANUMERICO=False):
            with self.assertRaisesMessage(RuntimeError, "não declara suporte"):
                garantir_cliente_asaas(self.contrato)
        request_mock.assert_not_called()

        request_mock.return_value = {"id": "cus_alfa"}
        with self.settings(ASAAS_SUPORTA_CNPJ_ALFANUMERICO=True):
            customer_id = garantir_cliente_asaas(self.contrato)

        self.assertEqual(customer_id, "cus_alfa")
        self.assertEqual(request_mock.call_args.args[2]["cpfCnpj"], self.cnpj)

