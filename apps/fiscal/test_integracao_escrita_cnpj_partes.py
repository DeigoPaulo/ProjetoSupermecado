from django.test import TestCase, override_settings

from apps.clientes.forms import ClienteForm
from apps.clientes.models import Cliente
from apps.empresas.models import Empresa
from apps.fornecedores.forms import FornecedorForm
from apps.fornecedores.models import Fornecedor

from .test_support_identidades_fiscais import obter_identidade_fiscal_teste


@override_settings(ENVIRONMENT="test")
class IntegracaoEscritaCNPJPartesTests(TestCase):
    def identidade(self, codigo, *, mascarado=False):
        return obter_identidade_fiscal_teste(
            codigo, finalidade="TESTE_UNITARIO", mascarado=mascarado
        )

    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Empresa partes integradas",
            nome_fantasia="Empresa partes integradas",
            cnpj=self.identidade("EMPRESA_MATRIZ"),
        )

    def cliente(self, documento, *, nome="Cliente integrado"):
        return ClienteForm(
            data={"empresa": self.empresa.pk, "nome": nome, "cpf_cnpj": documento, "is_active": "on"}
        )

    def fornecedor(self, cnpj, *, nome="Fornecedor integrado"):
        return FornecedorForm(
            data={
                "empresa": self.empresa.pk,
                "razao_social": nome,
                "nome_fantasia": nome,
                "cnpj": cnpj,
                "prazo_entrega_dias": 0,
                "is_active": "on",
            }
        )

    def test_cliente_pj_e_fornecedor_gravam_cnpj_canonico(self):
        cliente = self.cliente(self.identidade("CLIENTE_PJ", mascarado=True))
        fornecedor = self.fornecedor(self.identidade("FORNECEDOR", mascarado=True))

        self.assertTrue(cliente.is_valid(), cliente.errors)
        self.assertTrue(fornecedor.is_valid(), fornecedor.errors)
        self.assertEqual(cliente.save().cpf_cnpj, self.identidade("CLIENTE_PJ"))
        self.assertEqual(fornecedor.save().cnpj, self.identidade("FORNECEDOR"))

    def test_dv_invalido_e_rejeitado_nas_duas_fronteiras(self):
        cnpj = self.identidade("FORNECEDOR")
        invalido = cnpj[:-1] + ("0" if cnpj[-1] != "0" else "1")
        cliente = self.cliente(invalido)
        fornecedor = self.fornecedor(invalido)

        self.assertFalse(cliente.is_valid())
        self.assertFalse(fornecedor.is_valid())
        self.assertEqual(cliente.errors.as_data()["cpf_cnpj"][0].code, "cnpj_invalido")
        self.assertEqual(fornecedor.errors.as_data()["cnpj"][0].code, "cnpj_invalido")

    def test_colisao_canonica_e_rejeitada_no_escopo_da_empresa(self):
        Cliente.objects.create(
            empresa=self.empresa,
            nome="Cliente existente",
            cpf_cnpj=self.identidade("CLIENTE_PJ", mascarado=True),
        )
        Fornecedor.objects.create(
            empresa=self.empresa,
            razao_social="Fornecedor existente",
            cnpj=self.identidade("FORNECEDOR", mascarado=True),
        )
        cliente = self.cliente(self.identidade("CLIENTE_PJ"), nome="Duplicado")
        fornecedor = self.fornecedor(self.identidade("FORNECEDOR"), nome="Duplicado")

        self.assertFalse(cliente.is_valid())
        self.assertFalse(fornecedor.is_valid())
        self.assertEqual(cliente.errors.as_data()["cpf_cnpj"][0].code, "cnpj_colisao_canonica")
        self.assertEqual(fornecedor.errors.as_data()["cnpj"][0].code, "cnpj_colisao_canonica")

    def test_cpf_e_campos_vazios_permanecem_preservados(self):
        cpf = self.cliente("529.982.247-25", nome="Cliente CPF")
        cliente_vazio = self.cliente("", nome="Cliente vazio")
        fornecedor_vazio = self.fornecedor("", nome="Fornecedor vazio")

        self.assertTrue(cpf.is_valid(), cpf.errors)
        self.assertTrue(cliente_vazio.is_valid(), cliente_vazio.errors)
        self.assertTrue(fornecedor_vazio.is_valid(), fornecedor_vazio.errors)
        self.assertEqual(cpf.save().cpf_cnpj, "529.982.247-25")
        self.assertEqual(cliente_vazio.save().cpf_cnpj, "")
        self.assertEqual(fornecedor_vazio.save().cnpj, "")

    def test_troca_entre_cpf_e_cnpj_e_bloqueada(self):
        cliente = Cliente.objects.create(
            empresa=self.empresa, nome="Cliente CPF", cpf_cnpj="529.982.247-25"
        )
        form = ClienteForm(
            data={
                "empresa": self.empresa.pk,
                "nome": cliente.nome,
                "cpf_cnpj": self.identidade("CLIENTE_PJ"),
                "is_active": "on",
            },
            instance=cliente,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors.as_data()["cpf_cnpj"][0].code, "cnpj_legado_invalido")

    def test_legado_invalido_nao_e_corrigido_silenciosamente(self):
        fornecedor = Fornecedor.objects.create(
            empresa=self.empresa,
            razao_social="Fornecedor legado",
            cnpj="11.111.111/0001-11",
        )
        form = FornecedorForm(
            data={
                "empresa": self.empresa.pk,
                "razao_social": fornecedor.razao_social,
                "cnpj": self.identidade("FORNECEDOR"),
                "prazo_entrega_dias": 0,
                "is_active": "on",
            },
            instance=fornecedor,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors.as_data()["cnpj"][0].code, "cnpj_legado_invalido")
        fornecedor.refresh_from_db()
        self.assertEqual(fornecedor.cnpj, "11.111.111/0001-11")
