from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.financeiro.forms import ContaFinanceiraForm
from apps.marketplace.forms import PedidoOnlineForm
from apps.pdv.forms import FinalizarVendaForm, PreVendaForm
from apps.pdv.models import Caixa

from .models import Cliente


class ClienteViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(nome="Cliente Teste", cpf_cnpj="123.456.789-09", telefone="11999999999")

    def test_form_cliente_exibe_secoes_operacionais(self):
        response = self.client.get(f"/clientes/{self.cliente.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identificação")
        self.assertContains(response, "Endereço principal")
        self.assertContains(response, "Dados fiscais")
        self.assertNotContains(response, 'name="endereco"')
        self.assertContains(response, "Opcional para venda presencial avulsa.")
        self.assertContains(response, "Consultar CEP")

    def test_cliente_legado_preserva_endereco_ao_editar(self):
        empresa = Empresa.objects.create(
            razao_social="Cliente legado Ltda", nome_fantasia="Cliente legado", cnpj="12.345.678/0001-90",
        )
        self.cliente.empresa = empresa
        self.cliente.endereco = "Rua Legada, 20"
        self.cliente.save(update_fields=["empresa", "endereco"])

        response = self.client.get(f"/clientes/{self.cliente.pk}/editar/")
        self.assertContains(response, "Endereço legado cadastrado: Rua Legada, 20")
        self.assertNotContains(response, 'name="endereco"')

        response = self.client.post(f"/clientes/{self.cliente.pk}/editar/", {
            "empresa": empresa.pk,
            "nome": self.cliente.nome,
            "cpf_cnpj": self.cliente.cpf_cnpj,
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.endereco, "Rua Legada, 20")

    def test_busca_prioriza_endereco_estruturado_e_informa_documento(self):
        self.cliente.endereco = "Rua Legada"
        self.cliente.logradouro = "Rua Atual"
        self.cliente.numero = "42"
        self.cliente.bairro = "Centro"
        self.cliente.municipio = "Goiânia"
        self.cliente.uf = "GO"
        self.cliente.cep = "74000-000"
        self.cliente.codigo_municipio_ibge = "5208707"
        self.cliente.save()

        payload = self.client.get("/clientes/busca.json", {"q": "Teste"}).json()["results"][0]
        self.assertIn("Rua Atual, 42", payload["endereco"])
        self.assertNotIn("Rua Legada", payload["endereco"])
        self.assertFalse(payload["endereco_legado"])
        self.assertEqual(payload["documento_fiscal_tipo"], "CPF")

    def test_busca_json_retorna_cliente_para_select2(self):
        response = self.client.get("/clientes/busca.json", {"q": "Teste"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["id"], self.cliente.id)
        self.assertIn("Cliente Teste", payload["results"][0]["text"])
        self.assertEqual(payload["results"][0]["endereco"], self.cliente.endereco)

    def test_busca_json_abre_com_lista_e_pagina_sem_exigir_texto(self):
        for indice in range(21):
            Cliente.objects.create(nome=f"Cliente Lista {indice:02d}")

        primeira = self.client.get("/clientes/busca.json", {"page": 1}).json()
        segunda = self.client.get("/clientes/busca.json", {"page": 2}).json()

        self.assertEqual(len(primeira["results"]), 20)
        self.assertTrue(primeira["pagination"]["more"])
        self.assertGreaterEqual(len(segunda["results"]), 1)
        self.assertFalse(segunda["pagination"]["more"])


class ClienteIsolamentoEmpresaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.empresa_a = Empresa.objects.create(
            razao_social="Mercado A Ltda",
            nome_fantasia="Mercado A",
            cnpj="11.111.111/0001-11",
        )
        self.empresa_b = Empresa.objects.create(
            razao_social="Mercado B Ltda",
            nome_fantasia="Mercado B",
            cnpj="22.222.222/0001-22",
        )
        self.filial_a = Filial.objects.create(empresa=self.empresa_a, nome="Matriz A", cnpj=self.empresa_a.cnpj)
        self.filial_b = Filial.objects.create(empresa=self.empresa_b, nome="Matriz B", cnpj=self.empresa_b.cnpj)
        self.usuario_a = User.objects.create_user("gerente_a", password="123")
        self.super_admin = User.objects.create_superuser("master", "master@example.com", "123")
        PerfilUsuario.objects.create(usuario=self.usuario_a, filial=self.filial_a, tipo=TipoPerfil.GERENTE)
        self.cliente_a = Cliente.objects.create(empresa=self.empresa_a, nome="Cliente da empresa A", cpf_cnpj="11111111111")
        self.cliente_b = Cliente.objects.create(empresa=self.empresa_b, nome="Cliente da empresa B", cpf_cnpj="22222222222")
        self.client = Client(HTTP_HOST="localhost")

    def test_lista_busca_e_edicao_respeitam_empresa_do_usuario(self):
        self.client.force_login(self.usuario_a)

        lista = self.client.get("/clientes/")
        busca = self.client.get("/clientes/busca.json", {"q": "Cliente da empresa"})
        edicao_estrangeira = self.client.get(f"/clientes/{self.cliente_b.pk}/editar/")

        self.assertContains(lista, self.cliente_a.nome)
        self.assertNotContains(lista, self.cliente_b.nome)
        self.assertEqual([item["id"] for item in busca.json()["results"]], [self.cliente_a.pk])
        self.assertEqual(edicao_estrangeira.status_code, 404)

    def test_usuario_cria_cliente_na_empresa_do_perfil_sem_enviar_empresa(self):
        self.client.force_login(self.usuario_a)

        resposta = self.client.post(
            "/clientes/novo/",
            {
                "nome": "Cliente criado no caixa",
                "cpf_cnpj": "",
                "telefone": "62999990000",
                "email": "",
                "endereco": "Rua do Cliente, 10",
                "is_active": "on",
            },
        )

        self.assertRedirects(resposta, "/clientes/")
        cliente = Cliente.objects.get(nome="Cliente criado no caixa")
        self.assertEqual(cliente.empresa, self.empresa_a)

    def test_cadastro_rapido_pdv_reutiliza_formulario_e_empresa_do_perfil(self):
        self.client.force_login(self.usuario_a)

        resposta = self.client.post("/clientes/novo-pdv.json", {
            "nome": "Cliente do PDV", "cpf_cnpj": "", "telefone": "62999990000",
            "email": "", "endereco": "Rua do Cliente, 10", "is_active": "on",
        })

        self.assertEqual(resposta.status_code, 200)
        cliente = Cliente.objects.get(pk=resposta.json()["id"])
        self.assertEqual(cliente.empresa, self.empresa_a)
        self.assertEqual(resposta.json()["nome"], cliente.nome)

    def test_cadastro_rapido_pdv_nao_aceita_empresa_de_outra_filial(self):
        self.client.force_login(self.usuario_a)

        resposta = self.client.post("/clientes/novo-pdv.json", {
            "empresa": self.empresa_b.pk, "nome": "Cliente forjado",
            "cpf_cnpj": "", "is_active": "on",
        })

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(Cliente.objects.filter(nome="Cliente forjado").exists())

    def test_cadastro_rapido_pdv_exige_empresa_explicita_para_superusuario(self):
        self.client.force_login(self.super_admin)

        resposta = self.client.post("/clientes/novo-pdv.json", {
            "nome": "Cliente sem empresa", "cpf_cnpj": "", "is_active": "on",
        })

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("empresa", resposta.json()["errors"])
        self.assertFalse(Cliente.objects.filter(nome="Cliente sem empresa").exists())

    def test_superusuario_com_caixa_usa_empresa_operacional_sem_filial_artificial(self):
        Caixa.objects.create(filial=self.filial_a, usuario_abertura=self.super_admin)
        self.client.force_login(self.super_admin)

        resposta = self.client.post("/clientes/novo-pdv.json", {
            "nome": "Cliente do caixa A", "email": "caixa@example.com",
            "logradouro": "Rua A", "numero": "12", "bairro": "Centro",
            "municipio": "Goiânia", "codigo_municipio_ibge": "5208707",
            "uf": "GO", "cep": "74000000", "is_active": "on",
        })
        self.assertEqual(resposta.status_code, 200, resposta.content)
        cliente = Cliente.objects.get(pk=resposta.json()["id"])
        self.assertEqual(cliente.empresa_id, self.empresa_a.pk)
        self.assertEqual(cliente.email, "caixa@example.com")
        self.assertEqual(cliente.logradouro, "Rua A")
        self.assertFalse(hasattr(cliente, "filial_id"))

        forjada = self.client.post("/clientes/novo-pdv.json", {
            "empresa": self.empresa_b.pk, "nome": "Cliente de outra empresa", "is_active": "on",
        })
        self.assertEqual(forjada.status_code, 400)
        self.assertFalse(Cliente.objects.filter(nome="Cliente de outra empresa").exists())

    def test_cadastro_pdv_informa_bairro_ausente_sem_gravar_cliente(self):
        Caixa.objects.create(filial=self.filial_a, usuario_abertura=self.super_admin)
        self.client.force_login(self.super_admin)

        resposta = self.client.post("/clientes/novo-pdv.json", {
            "nome": "Cliente sem bairro", "logradouro": "Avenida de Teste",
            "numero": "115", "municipio": "Goiânia",
            "codigo_municipio_ibge": "5208707", "uf": "GO",
            "cep": "74423-020", "is_active": "on",
        })

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("bairro", resposta.json()["errors"])
        self.assertFalse(Cliente.objects.filter(nome="Cliente sem bairro").exists())

    def test_usuario_nao_consegue_forcar_empresa_de_outro_cliente(self):
        self.client.force_login(self.usuario_a)

        resposta = self.client.post(
            "/clientes/novo/",
            {
                "empresa": self.empresa_b.pk,
                "nome": "Cliente forjado",
                "cpf_cnpj": "33333333333",
                "telefone": "",
                "email": "",
                "endereco": "",
                "is_active": "on",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Cliente.objects.filter(nome="Cliente forjado").exists())

    def test_formularios_operacionais_oferecem_somente_clientes_da_empresa(self):
        formularios = [
            FinalizarVendaForm(user=self.usuario_a),
            PreVendaForm(user=self.usuario_a),
            PedidoOnlineForm(user=self.usuario_a),
            ContaFinanceiraForm(user=self.usuario_a),
        ]

        for formulario in formularios:
            with self.subTest(formulario=formulario.__class__.__name__):
                self.assertEqual(list(formulario.fields["cliente"].queryset), [self.cliente_a])

    def test_super_admin_mantem_visao_global(self):
        self.client.force_login(self.super_admin)

        lista = self.client.get("/clientes/")

        self.assertContains(lista, self.cliente_a.nome)
        self.assertContains(lista, self.cliente_b.nome)
