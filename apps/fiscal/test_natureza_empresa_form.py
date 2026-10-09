from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial

from .forms import NaturezaOperacaoForm
from .models import NaturezaOperacao, TipoDocumentoFiscal


class NaturezaEmpresaFormTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Empresa A Ltda", nome_fantasia="Empresa A", cnpj="11.111.111/0001-11"
        )
        self.outra_empresa = Empresa.objects.create(
            razao_social="Empresa B Ltda", nome_fantasia="Empresa B", cnpj="22.222.222/0001-22"
        )
        filial = Filial.objects.create(empresa=self.empresa, nome="Matriz")
        self.superusuario = get_user_model().objects.create_superuser("master_natureza", password="teste")
        self.administrador = get_user_model().objects.create_user("admin_natureza", password="teste")
        PerfilUsuario.objects.create(
            usuario=self.administrador, filial=filial, tipo=TipoPerfil.ADMINISTRADOR
        )
        self.dados = {
            "descricao": "VENDA DE MERCADORIAS",
            "cfop": "5102",
            "tipo_documento": TipoDocumentoFiscal.NFCE,
            "movimenta_estoque": "on",
            "ativo": "on",
        }

    def test_superusuario_ve_empresa_sem_selecao_automatica(self):
        self.outra_empresa.delete()
        self.client.force_login(self.superusuario)
        response = self.client.get("/fiscal/naturezas/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("empresa", response.context["form"].fields)
        self.assertIsNone(response.context["form"].initial.get("empresa"))
        self.assertContains(response, 'name="empresa"')
        self.assertContains(response, 'id="id_empresa"')

    def test_superusuario_sem_empresa_ve_erro_no_campo(self):
        self.client.force_login(self.superusuario)
        response = self.client.post("/fiscal/naturezas/nova/", self.dados)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].errors["empresa"], ["Este campo é obrigatório."])
        self.assertContains(response, "Este campo é obrigatório.")
        self.assertContains(response, 'form-field form-field-wide has-error')
        self.assertRegex(
            response.content.decode(),
            r'(?s)<label class="form-field form-field-wide has-error">.*?name="empresa".*?Este campo é obrigatório\.',
        )
        self.assertFalse(NaturezaOperacao.objects.exists())

    def test_superusuario_escolhe_empresa_e_salva_natureza(self):
        self.client.force_login(self.superusuario)
        dados = {**self.dados, "empresa": self.empresa.pk}
        form = NaturezaOperacaoForm(dados, user=self.superusuario)
        self.assertTrue(form.is_valid(), form.errors)

        response = self.client.post("/fiscal/naturezas/nova/", dados)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(NaturezaOperacao.objects.get().empresa, self.empresa)

    def test_usuario_vinculado_nao_ve_empresa_e_mantem_escopo(self):
        self.client.force_login(self.administrador)
        response = self.client.get("/fiscal/naturezas/nova/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("empresa", response.context["form"].fields)
        self.assertNotContains(response, 'name="empresa"')

        response = self.client.post(
            "/fiscal/naturezas/nova/", {**self.dados, "empresa": self.outra_empresa.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(NaturezaOperacao.objects.get().empresa, self.empresa)
