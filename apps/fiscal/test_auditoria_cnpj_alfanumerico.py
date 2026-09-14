import io
import json

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.clientes.models import Cliente
from apps.empresas.models import Empresa, Filial
from apps.fornecedores.models import Fornecedor

from .auditoria_cnpj_alfanumerico import auditar_base_identificadores, auditar_identificadores
from .estrategia_normalizacao_cnpj import calcular_dv_chave_acesso
from .models import DocumentoFiscal


class AuditoriaCNPJAlfanumericoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="auditoria-cnpj", password="senha-teste"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Empresa Auditada", nome_fantasia="Empresa Auditada",
            cnpj="04.252.011/0001-10",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz", cnpj="04252011000110"
        )

    def test_classifica_equivalencia_esperada_e_colisao_bloqueante(self):
        registros = [
            {"origem": "Empresa", "identificador": 1, "empresa_id": 1, "valor": "04.252.011/0001-10", "papel": "IDENTIDADE", "dominio": "EMPRESA_GLOBAL", "obrigatorio": True},
            {"origem": "Filial", "identificador": 2, "empresa_id": 1, "valor": "04252011000110", "papel": "IDENTIDADE", "dominio": "FILIAL_GLOBAL", "obrigatorio": False},
            {"origem": "Fornecedor", "identificador": 3, "empresa_id": 1, "valor": "12.ABC.345/01DE-35", "papel": "IDENTIDADE", "dominio": "FORNECEDOR_EMPRESA_1", "obrigatorio": False},
            {"origem": "Fornecedor", "identificador": 4, "empresa_id": 1, "valor": "12ABC34501DE35", "papel": "IDENTIDADE", "dominio": "FORNECEDOR_EMPRESA_1", "obrigatorio": False},
        ]
        resultado = auditar_identificadores(registros, [])
        classificacoes = {item["classificacao"] for item in resultado["colisoes"]}
        self.assertEqual(classificacoes, {"ESPERADA_EMPRESA_FILIAL", "BLOQUEANTE"})
        self.assertEqual(resultado["resumo"]["quantidade_bloqueios"], 1)

    def test_campo_misto_ignora_cpf_e_relatorio_oculta_identificadores(self):
        registros = [
            {"origem": "Cliente", "identificador": 1, "empresa_id": 1, "valor": "123.456.789-00", "papel": "IDENTIDADE", "dominio": "CLIENTE_EMPRESA_1", "obrigatorio": False, "campo_misto": True},
            {"origem": "Cliente", "identificador": 2, "empresa_id": 1, "valor": "12.ABC.345/01DE-35", "papel": "IDENTIDADE", "dominio": "CLIENTE_EMPRESA_1", "obrigatorio": False, "campo_misto": True},
        ]
        resultado = auditar_identificadores(registros, [])
        self.assertEqual(resultado["resumo"]["cnpj_por_status"], {"IGNORADO_CPF": 1, "VALIDO": 1})
        serializado = json.dumps(resultado)
        self.assertNotIn("123.456.789-00", serializado)
        self.assertNotIn("12ABC34501DE35", serializado)
        self.assertFalse(resultado["seguranca"]["identificadores_completos_expostos"])

    def test_classifica_formato_e_dv_de_chave_separadamente(self):
        base = "52260912ABC34501DE3555001000000001112345678"
        valida = base + calcular_dv_chave_acesso(base)
        registros = [
            {"origem": "DFe", "identificador": 1, "valor": valida, "papel": "REFERENCIA", "obrigatorio": True},
            {"origem": "DFe", "identificador": 2, "valor": valida[:-1] + str((int(valida[-1]) + 1) % 10), "papel": "REFERENCIA", "obrigatorio": True},
            {"origem": "DFe", "identificador": 3, "valor": "CHAVE", "papel": "REFERENCIA", "obrigatorio": True},
            {"origem": "DFe", "identificador": 4, "valor": "", "papel": "REFERENCIA", "obrigatorio": True},
        ]
        resultado = auditar_identificadores([], registros)
        self.assertEqual(resultado["resumo"]["chaves_por_status"], {
            "VALIDA": 1, "DV_INVALIDO": 1, "FORMATO_INVALIDO": 1, "AUSENTE_OBRIGATORIA": 1,
        })
        self.assertEqual(resultado["resumo"]["quantidade_bloqueios"], 3)

    def test_auditoria_do_banco_executa_apenas_select_e_nao_e_aceite(self):
        Fornecedor.objects.create(
            empresa=self.empresa, razao_social="Fornecedor", cnpj="12.ABC.345/01DE-35"
        )
        Cliente.objects.create(empresa=self.empresa, nome="Pessoa", cpf_cnpj="123.456.789-00")
        DocumentoFiscal.objects.create(filial=self.filial, usuario=self.usuario)
        with CaptureQueriesContext(connection) as consultas:
            resultado = auditar_base_identificadores()
        self.assertTrue(consultas)
        self.assertTrue(all(item["sql"].lstrip().upper().startswith("SELECT") for item in consultas))
        self.assertTrue(resultado["seguranca"]["somente_select"])
        self.assertFalse(resultado["seguranca"]["altera_dados"])
        self.assertFalse(resultado["seguranca"]["aceite_producao"])
        self.assertEqual(Empresa.objects.get(pk=self.empresa.pk).cnpj, "04.252.011/0001-10")

    def test_comando_emite_json_protegido_sem_escrita(self):
        saida = io.StringIO()
        with CaptureQueriesContext(connection) as consultas:
            call_command("auditar_cnpj_alfanumerico", stdout=saida)
        resultado = json.loads(saida.getvalue())
        self.assertEqual(resultado["contrato"], "alphanumeric_cnpj_readonly_audit_v1")
        self.assertNotIn(self.empresa.cnpj, saida.getvalue())
        self.assertTrue(all(item["sql"].lstrip().upper().startswith("SELECT") for item in consultas))
