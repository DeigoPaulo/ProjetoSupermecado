from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.clientes.models import Cliente
from apps.empresas.models import Empresa
from apps.fornecedores.models import Fornecedor

from .adaptador_sombra_escrita_cnpj_partes import (
    observar_escrita_cliente,
    observar_escrita_fornecedor,
)
from .test_support_identidades_fiscais import obter_identidade_fiscal_teste


@override_settings(ENVIRONMENT="test")
class AdaptadorSombraEscritaCNPJPartesTests(TestCase):
    def identidade(self, codigo, *, mascarado=False):
        return obter_identidade_fiscal_teste(
            codigo, finalidade="TESTE_UNITARIO", mascarado=mascarado
        )

    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Empresa partes",
            nome_fantasia="Empresa partes",
            cnpj=self.identidade("EMPRESA_MATRIZ"),
        )

    def dados_cliente(self, documento, *, nome="Cliente observado"):
        return {"empresa": self.empresa.pk, "nome": nome, "cpf_cnpj": documento, "is_active": "on"}

    def dados_fornecedor(self, cnpj, *, nome="Fornecedor observado"):
        return {
            "empresa": self.empresa.pk,
            "razao_social": nome,
            "nome_fantasia": nome,
            "cnpj": cnpj,
            "prazo_entrega_dias": 0,
            "is_active": "on",
        }

    def test_cliente_preserva_cpf_fora_do_escopo_cnpj(self):
        resultado = observar_escrita_cliente(self.dados_cliente("529.982.247-25"))

        self.assertEqual(resultado["classificacao"], "CPF_PRESERVADO_FORA_ESCOPO_CNPJ")
        self.assertEqual(resultado["documento_tipo"], "CPF")
        self.assertTrue(resultado["formulario_atual"]["valido"])

    def test_campos_vazios_opcionais_sao_preservados(self):
        cliente = observar_escrita_cliente(self.dados_cliente(""))
        fornecedor = observar_escrita_fornecedor(self.dados_fornecedor(""))

        self.assertEqual(cliente["classificacao"], "VAZIO_OPCIONAL_PRESERVADO")
        self.assertEqual(fornecedor["classificacao"], "VAZIO_OPCIONAL_PRESERVADO")

    def test_cliente_pj_e_fornecedor_validos_concordam_sem_gravar(self):
        with CaptureQueriesContext(connection) as consultas:
            cliente = observar_escrita_cliente(
                self.dados_cliente(self.identidade("CLIENTE_PJ", mascarado=True))
            )
            fornecedor = observar_escrita_fornecedor(
                self.dados_fornecedor(self.identidade("FORNECEDOR", mascarado=True))
            )

        self.assertEqual(cliente["classificacao"], "CONCORDAM_ESTRUTURALMENTE")
        self.assertEqual(fornecedor["classificacao"], "CONCORDAM_ESTRUTURALMENTE")
        self.assertFalse(Cliente.objects.exists())
        self.assertFalse(Fornecedor.objects.exists())
        self.assertTrue(consultas.captured_queries)
        self.assertTrue(
            all(item["sql"].lstrip().upper().startswith("SELECT") for item in consultas.captured_queries)
        )

    def test_formularios_atuais_aceitam_dv_invalido(self):
        cnpj = self.identidade("FORNECEDOR")
        invalido = cnpj[:-1] + ("0" if cnpj[-1] != "0" else "1")

        cliente = observar_escrita_cliente(self.dados_cliente(invalido))
        fornecedor = observar_escrita_fornecedor(self.dados_fornecedor(invalido))

        self.assertEqual(cliente["classificacao"], "FORMULARIO_ATUAL_ACEITA_PORTAO_RECUSA")
        self.assertEqual(fornecedor["classificacao"], "FORMULARIO_ATUAL_ACEITA_PORTAO_RECUSA")

    def test_detecta_colisoes_canonicas_no_escopo_da_empresa(self):
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

        cliente = observar_escrita_cliente(
            self.dados_cliente(self.identidade("CLIENTE_PJ"), nome="Outro cliente")
        )
        fornecedor = observar_escrita_fornecedor(
            self.dados_fornecedor(self.identidade("FORNECEDOR"), nome="Outro fornecedor")
        )

        self.assertEqual(cliente["classificacao"], "COLISAO_CANONICA_DETECTADA")
        self.assertEqual(fornecedor["classificacao"], "COLISAO_CANONICA_DETECTADA")
        self.assertEqual(cliente["proposta_canonica"]["quantidade_colisoes"], 1)
        self.assertEqual(fornecedor["proposta_canonica"]["quantidade_colisoes"], 1)

    def test_diagnostico_nao_expoe_documentos_ou_ids(self):
        cnpj = self.identidade("CLIENTE_PJ")
        resultado = observar_escrita_cliente(self.dados_cliente(cnpj))

        self.assertNotIn(cnpj, repr(resultado))
        self.assertFalse(resultado["seguranca"]["cnpj_ou_cpf_exposto"])
        self.assertFalse(resultado["seguranca"]["identificador_interno_exposto"])
        self.assertFalse(resultado["seguranca"]["chama_save"])
