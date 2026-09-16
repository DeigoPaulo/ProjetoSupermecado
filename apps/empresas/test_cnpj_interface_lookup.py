import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.clientes.forms import ClienteForm
from apps.fiscal.estrategia_normalizacao_cnpj import calcular_dv_cnpj
from apps.fornecedores.forms import FornecedorForm

from .forms import EmpresaForm, FilialForm
from .models import Empresa


class CNPJInterfaceContractTests(SimpleTestCase):
    def test_widgets_separam_cnpj_dedicado_do_campo_misto(self):
        self.assertIn("mask-cnpj", EmpresaForm().fields["cnpj"].widget.attrs["class"])
        self.assertIn("mask-cnpj", FilialForm().fields["cnpj"].widget.attrs["class"])
        self.assertIn("mask-cnpj", FornecedorForm().fields["cnpj"].widget.attrs["class"])
        self.assertIn(
            "mask-cpf-cnpj", ClienteForm().fields["cpf_cnpj"].widget.attrs["class"]
        )

    def test_formatador_javascript_preserva_cpf_e_cnpj_alfanumerico(self):
        if not shutil.which("node"):
            self.skipTest("Node.js não disponível para o contrato da interface.")
        modulo = Path(settings.BASE_DIR) / "static/js/cnpj-documento.js"
        roteiro = (
            f"const d=require({json.dumps(str(modulo))});"
            "const r={"
            "cpf:d.formatarCpfCnpjEntrada('52998224725'),"
            "numerico:d.formatarCpfCnpjEntrada('04252011000110'),"
            "alfa:d.formatarCpfCnpjEntrada('12AB3456CD7890'),"
            "minusculo:d.formatarCpfCnpjEntrada('12ab3456cd7890'),"
            "mascarado:d.normalizarCnpjEntrada('12.AB3.456/CD78-90'),"
            "canonico:d.normalizarCnpjEntrada('12AB3456CD7890')"
            "};process.stdout.write(JSON.stringify(r));"
        )
        resultado = subprocess.run(
            ["node", "-e", roteiro],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        valores = json.loads(resultado.stdout)
        self.assertEqual(valores["cpf"], "529.982.247-25")
        self.assertEqual(valores["numerico"], "04.252.011/0001-10")
        self.assertEqual(valores["alfa"], "12.AB3.456/CD78-90")
        self.assertEqual(valores["minusculo"], "12.AB3.456/CD78-90")
        self.assertEqual(valores["mascarado"], "12AB3456CD7890")
        self.assertEqual(valores["canonico"], "12AB3456CD7890")


@override_settings(ENVIRONMENT="test")
class CNPJLookupAlfanumericoTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")
        self.user = get_user_model().objects.create_superuser(
            "lookup_cnpj_alfa", "lookup@example.com", "123"
        )
        self.client.force_login(self.user)

    @staticmethod
    def identidade(base):
        return base + calcular_dv_cnpj(base)

    def test_lookup_local_aceita_mascara_minusculas_e_compara_canonico(self):
        canonico = self.identidade("12ABC34501DE")
        empresa = Empresa.objects.create(
            razao_social="Empresa Alfa",
            nome_fantasia="Empresa Alfa",
            cnpj=f"{canonico[:2]}.{canonico[2:5]}.{canonico[5:8]}/{canonico[8:12]}-{canonico[12:]}",
        )

        resposta = self.client.get(
            "/empresas/consulta-cadastro.json",
            {"cnpj": f"{canonico[:2]}.{canonico[2:5].lower()}.{canonico[5:8]}/{canonico[8:12].lower()}-{canonico[12:]}"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["status"], "local_match")
        self.assertEqual(resposta.json()["dados"]["id"], empresa.pk)

    @override_settings(
        CADASTRO_CNPJ_PROVIDER_URL="https://cadastro.example/cnpj/{cnpj}",
        CADASTRO_CNPJ_PROVIDER_SUPORTA_ALFANUMERICO=False,
    )
    @patch("apps.empresas.views.urlopen")
    def test_provider_sem_suporte_alfa_nao_recebe_identificador_mutilado(self, urlopen_mock):
        canonico = self.identidade("ABCDEF123456")

        resposta = self.client.get("/empresas/consulta-cadastro.json", {"cnpj": canonico.lower()})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["status"], "external_provider_unsupported")
        self.assertEqual(resposta.json()["consulta"]["valor"], canonico)
        self.assertIn("cadastro manualmente", resposta.json()["mensagem"])
        urlopen_mock.assert_not_called()

    def test_lookup_invalido_nao_remove_letras_para_fingir_cnpj_numerico(self):
        resposta = self.client.get(
            "/empresas/consulta-cadastro.json", {"cnpj": "12-ABC-345-01DE-35"}
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json()["status"], "invalid")
        self.assertEqual(resposta.json()["consulta"]["valor"], "12-ABC-345-01DE-35")
