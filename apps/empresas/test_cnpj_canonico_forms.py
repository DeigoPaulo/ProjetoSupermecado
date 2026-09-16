from django.test import TestCase, override_settings

from apps.fiscal.test_support_identidades_fiscais import obter_identidade_fiscal_teste

from .forms import EmpresaForm, FilialForm
from .models import Empresa, Filial, ModoImplantacao


@override_settings(ENVIRONMENT="test")
class CNPJCanonicoFormsTests(TestCase):
    def identidade(self, codigo, *, mascarado=False):
        return obter_identidade_fiscal_teste(
            codigo, finalidade="TESTE_UNITARIO", mascarado=mascarado
        )

    def dados_empresa(self, cnpj, *, nome="Empresa canônica"):
        return {
            "razao_social": nome,
            "nome_fantasia": nome,
            "cnpj": cnpj,
            "modo_implantacao": ModoImplantacao.LOCAL,
            "is_active": "on",
        }

    def dados_filial(self, empresa, cnpj, *, nome="Filial canônica"):
        return {
            "empresa": empresa.pk,
            "nome": nome,
            "cnpj": cnpj,
            "is_active": "on",
        }

    def test_empresa_nova_grava_representacao_canonica(self):
        canonico = self.identidade("EMPRESA_MATRIZ")
        form = EmpresaForm(data=self.dados_empresa(canonico.lower()))

        self.assertTrue(form.is_valid(), form.errors)
        empresa = form.save()
        self.assertEqual(empresa.cnpj, canonico)

    def test_empresa_rejeita_dv_invalido(self):
        cnpj = self.identidade("EMPRESA_MATRIZ")
        invalido = cnpj[:-1] + ("0" if cnpj[-1] != "0" else "1")
        form = EmpresaForm(data=self.dados_empresa(invalido))

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors.as_data()["cnpj"][0].code, "cnpj_invalido")
        self.assertFalse(Empresa.objects.exists())

    def test_empresa_rejeita_colisao_entre_mascara_e_canonico(self):
        Empresa.objects.create(
            razao_social="Existente",
            nome_fantasia="Existente",
            cnpj=self.identidade("EMPRESA_MATRIZ", mascarado=True),
        )
        form = EmpresaForm(data=self.dados_empresa(self.identidade("EMPRESA_MATRIZ")))

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors.as_data()["cnpj"][0].code, "cnpj_colisao_canonica")

    def test_atualizacao_equivalente_mantem_identidade_e_canonicaliza(self):
        empresa = Empresa.objects.create(
            razao_social="Existente",
            nome_fantasia="Existente",
            cnpj=self.identidade("EMPRESA_MATRIZ", mascarado=True),
        )
        form = EmpresaForm(
            data=self.dados_empresa(self.identidade("EMPRESA_MATRIZ"), nome="Atualizada"),
            instance=empresa,
        )

        self.assertTrue(form.is_valid(), form.errors)
        atualizada = form.save()
        self.assertEqual(atualizada.cnpj, self.identidade("EMPRESA_MATRIZ"))

    def test_legado_invalido_nao_e_corrigido_silenciosamente(self):
        empresa = Empresa.objects.create(
            razao_social="Legado",
            nome_fantasia="Legado",
            cnpj="11.111.111/0001-11",
        )
        form = EmpresaForm(
            data=self.dados_empresa(self.identidade("EMPRESA_MATRIZ"), nome="Legado"),
            instance=empresa,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors.as_data()["cnpj"][0].code, "cnpj_legado_invalido")
        empresa.refresh_from_db()
        self.assertEqual(empresa.cnpj, "11.111.111/0001-11")

    def test_troca_de_identidade_valida_continua_bloqueada(self):
        empresa = Empresa.objects.create(
            razao_social="Existente",
            nome_fantasia="Existente",
            cnpj=self.identidade("EMPRESA_MATRIZ"),
        )
        form = EmpresaForm(
            data=self.dados_empresa(self.identidade("FORNECEDOR"), nome="Existente"),
            instance=empresa,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors.as_data()["cnpj"][0].code, "cnpj_troca_identidade")

    def test_filial_canonicaliza_e_detecta_colisao_no_escopo_da_empresa(self):
        empresa = Empresa.objects.create(
            razao_social="Empresa",
            nome_fantasia="Empresa",
            cnpj=self.identidade("EMPRESA_MATRIZ"),
        )
        form = FilialForm(
            data=self.dados_filial(empresa, self.identidade("FILIAL", mascarado=True))
        )
        self.assertTrue(form.is_valid(), form.errors)
        filial = form.save()
        self.assertEqual(filial.cnpj, self.identidade("FILIAL"))

        duplicada = FilialForm(
            data=self.dados_filial(
                empresa, self.identidade("FILIAL"), nome="Filial duplicada"
            )
        )
        self.assertFalse(duplicada.is_valid())
        self.assertEqual(
            duplicada.errors.as_data()["cnpj"][0].code,
            "cnpj_colisao_canonica",
        )

    def test_filial_sem_cnpj_permanece_permitida(self):
        empresa = Empresa.objects.create(
            razao_social="Empresa",
            nome_fantasia="Empresa",
            cnpj=self.identidade("EMPRESA_MATRIZ"),
        )
        form = FilialForm(data=self.dados_filial(empresa, ""))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().cnpj, "")
