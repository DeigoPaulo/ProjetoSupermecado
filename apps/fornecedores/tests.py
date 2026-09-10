from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.compras.forms import EntradaCompraForm, PedidoCompraForm, RespostaCotacaoFornecedorForm
from apps.empresas.models import Empresa, Filial
from apps.financeiro.forms import ContaFinanceiraForm

from .forms import FornecedorForm
from .models import Fornecedor, IndicadorInscricaoEstadual


class FornecedorViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado dos testes Ltda",
            nome_fantasia="Mercado dos testes",
            cnpj="00.000.000/0001-00",
        )
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.fornecedor = Fornecedor.objects.create(
            empresa=self.empresa,
            razao_social="Fornecedor Teste Ltda",
            nome_fantasia="Fornecedor Teste",
            cnpj="11.111.111/0001-11",
            prazo_entrega_dias=3,
        )

    def test_form_fornecedor_exibe_secoes_operacionais(self):
        response = self.client.get(f"/fornecedores/{self.fornecedor.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identificação")
        self.assertContains(response, "Contato e entrega")
        self.assertContains(response, "Cadastro fiscal estruturado")
        self.assertContains(response, "não copia nem atualiza estes campos a partir do XML")
        self.assertContains(response, "consultar CNPJ automaticamente")
        self.assertContains(response, "previsão de recebimento")

    def test_dados_fiscais_sao_opcionais_e_nao_recebem_defaults(self):
        fornecedor = Fornecedor.objects.create(razao_social="Fornecedor sem dados fiscais")

        self.assertEqual(fornecedor.indicador_ie, "")
        self.assertEqual(fornecedor.inscricao_estadual, "")
        self.assertEqual(fornecedor.codigo_municipio_ibge, "")
        self.assertEqual(fornecedor.uf, "")
        self.assertEqual(fornecedor.cep, "")

    def test_formulario_persiste_cadastro_fiscal_estruturado_completo(self):
        dados = {
            "empresa": self.empresa.pk,
            "razao_social": "Fornecedor fiscal completo",
            "nome_fantasia": "",
            "cnpj": "",
            "telefone": "",
            "email": "",
            "endereco": "Endereço comercial preservado",
            "indicador_ie": IndicadorInscricaoEstadual.CONTRIBUINTE,
            "inscricao_estadual": "123456789",
            "logradouro": "Avenida Goiás",
            "numero": "100",
            "complemento": "Sala 2",
            "bairro": "Centro",
            "codigo_municipio_ibge": "5208707",
            "municipio": "Goiânia",
            "uf": "GO",
            "cep": "74000-000",
            "condicao_pagamento": "",
            "prazo_entrega_dias": 0,
            "is_active": True,
        }

        form = FornecedorForm(data=dados, user=self.user)

        self.assertTrue(form.is_valid(), form.errors)
        fornecedor = form.save()
        self.assertEqual(fornecedor.codigo_municipio_ibge, "5208707")
        self.assertEqual(fornecedor.inscricao_estadual, "123456789")
        self.assertEqual(fornecedor.endereco, "Endereço comercial preservado")

    def test_formulario_rejeita_ie_sem_indicador_contribuinte(self):
        form = FornecedorForm(
            data={
                "empresa": self.empresa.pk,
                "razao_social": "Fornecedor IE incoerente",
                "indicador_ie": IndicadorInscricaoEstadual.ISENTO,
                "inscricao_estadual": "123456789",
                "prazo_entrega_dias": 0,
                "is_active": True,
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("inscricao_estadual", form.errors)

    def test_formulario_rejeita_endereco_fiscal_parcial(self):
        form = FornecedorForm(
            data={
                "empresa": self.empresa.pk,
                "razao_social": "Fornecedor endereço incompleto",
                "logradouro": "Rua sem demais dados",
                "codigo_municipio_ibge": "123",
                "uf": "G",
                "cep": "7400",
                "prazo_entrega_dias": 0,
                "is_active": True,
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        for campo in ("numero", "bairro", "municipio", "codigo_municipio_ibge", "uf", "cep"):
            with self.subTest(campo=campo):
                self.assertIn(campo, form.errors)

    def test_busca_json_retorna_fornecedor_para_select2(self):
        response = self.client.get("/fornecedores/busca.json", {"q": "Teste"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["id"], self.fornecedor.id)
        self.assertIn("Fornecedor Teste", payload["results"][0]["text"])

    def test_busca_json_abre_com_fornecedores_sem_exigir_texto(self):
        payload = self.client.get("/fornecedores/busca.json").json()

        self.assertEqual(payload["results"][0]["id"], self.fornecedor.id)
        self.assertFalse(payload["pagination"]["more"])


class FornecedorIsolamentoEmpresaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.empresa_a = Empresa.objects.create(
            razao_social="Mercado A Ltda", nome_fantasia="Mercado A", cnpj="11.111.111/0001-11"
        )
        self.empresa_b = Empresa.objects.create(
            razao_social="Mercado B Ltda", nome_fantasia="Mercado B", cnpj="22.222.222/0001-22"
        )
        self.filial_a = Filial.objects.create(empresa=self.empresa_a, nome="Matriz A", cnpj=self.empresa_a.cnpj)
        self.filial_b = Filial.objects.create(empresa=self.empresa_b, nome="Matriz B", cnpj=self.empresa_b.cnpj)
        self.usuario_a = User.objects.create_user("compras_a", password="123")
        self.super_admin = User.objects.create_superuser("master_fornecedor", "master@example.com", "123")
        PerfilUsuario.objects.create(usuario=self.usuario_a, filial=self.filial_a, tipo=TipoPerfil.COMPRAS)
        self.fornecedor_a = Fornecedor.objects.create(
            empresa=self.empresa_a, razao_social="Fornecedor da empresa A", cnpj="11111111000111"
        )
        self.fornecedor_b = Fornecedor.objects.create(
            empresa=self.empresa_b, razao_social="Fornecedor da empresa B", cnpj="22222222000122"
        )
        self.client = Client(HTTP_HOST="localhost")

    def test_lista_busca_e_edicao_respeitam_empresa_do_usuario(self):
        self.client.force_login(self.usuario_a)

        lista = self.client.get("/fornecedores/")
        busca = self.client.get("/fornecedores/busca.json", {"q": "Fornecedor da empresa"})
        edicao_estrangeira = self.client.get(f"/fornecedores/{self.fornecedor_b.pk}/editar/")

        self.assertContains(lista, self.fornecedor_a.razao_social)
        self.assertNotContains(lista, self.fornecedor_b.razao_social)
        self.assertEqual([item["id"] for item in busca.json()["results"]], [self.fornecedor_a.pk])
        self.assertEqual(edicao_estrangeira.status_code, 404)

    def test_usuario_nao_consegue_forcar_empresa_de_outro_fornecedor(self):
        self.client.force_login(self.usuario_a)

        resposta = self.client.post(
            "/fornecedores/novo/",
            {
                "empresa": self.empresa_b.pk,
                "razao_social": "Fornecedor forjado",
                "nome_fantasia": "",
                "cnpj": "33333333000133",
                "telefone": "",
                "email": "",
                "endereco": "",
                "condicao_pagamento": "",
                "prazo_entrega_dias": 0,
                "is_active": "on",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Fornecedor.objects.filter(razao_social="Fornecedor forjado").exists())

    def test_formularios_operacionais_oferecem_somente_fornecedores_da_empresa(self):
        formularios = [
            PedidoCompraForm(user=self.usuario_a),
            EntradaCompraForm(user=self.usuario_a),
            RespostaCotacaoFornecedorForm(user=self.usuario_a, empresa_id=self.empresa_a.pk),
            ContaFinanceiraForm(user=self.usuario_a),
        ]

        for formulario in formularios:
            with self.subTest(formulario=formulario.__class__.__name__):
                self.assertEqual(list(formulario.fields["fornecedor"].queryset), [self.fornecedor_a])

    def test_formulario_rejeita_fornecedor_de_outra_empresa(self):
        form = PedidoCompraForm(
            data={
                "fornecedor": self.fornecedor_b.pk,
                "filial": self.filial_a.pk,
                "referencia": "FORJADO",
                "previsao_entrega": "",
                "observacoes": "",
            },
            user=self.super_admin,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("fornecedor", form.errors)

    def test_super_admin_mantem_visao_global(self):
        self.client.force_login(self.super_admin)

        lista = self.client.get("/fornecedores/")

        self.assertContains(lista, self.fornecedor_a.razao_social)
        self.assertContains(lista, self.fornecedor_b.razao_social)
