from copy import deepcopy
from django.test import SimpleTestCase
from .contrato_devolucao import CONTRATO, GRUPOS, validar_contrato_devolucao


class ContratoDevolucaoTests(SimpleTestCase):
    def setUp(self):
        self.conteudo = {"contrato": CONTRATO, "rascunho_id": 1, "empresa_id": 2,
                         "modelo": "55", "operacao": "DEVOLUCAO_COMPRA", "permite_emissao": False,
                         "grupos": {g: {"estado": "NAO_SUPORTADO", "referencias": []} for g in GRUPOS}}

    def test_envelope_valido_nao_libera_xml_ou_emissao(self):
        antes = deepcopy(self.conteudo)
        resultado = validar_contrato_devolucao(self.conteudo)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertFalse(resultado["permite_gerar_xml"])
        self.assertFalse(resultado["permite_emissao"])
        self.assertEqual(self.conteudo, antes)
        self.assertEqual(len(resultado["bloqueios"]), len(GRUPOS) + 4)

    def test_referencia_valida_ainda_exige_validacao_fiscal(self):
        self.conteudo["grupos"]["origem"] = {"estado": "REFERENCIADO", "referencias": [{"tipo": "rascunho", "id": 1, "sha256": "a" * 64}]}
        resultado = validar_contrato_devolucao(self.conteudo)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertEqual(resultado["bloqueios"][0]["codigo"], "VALIDACAO_FISCAL_NAO_IMPLEMENTADA")

    def test_grupo_desconhecido_ausente_e_campos_extras_bloqueiam(self):
        for alteracao in (lambda c: c["grupos"].pop("pagamento"), lambda c: c["grupos"].update(extra={}), lambda c: c.update(token="segredo")):
            conteudo = deepcopy(self.conteudo)
            alteracao(conteudo)
            resultado = validar_contrato_devolucao(conteudo)
            self.assertFalse(resultado["estrutura_valida"])
            self.assertNotIn("segredo", str(resultado))

    def test_identificadores_modelo_e_emissao_invalidos(self):
        for campo, valor in (("empresa_id", True), ("rascunho_id", 0), ("modelo", "65"), ("permite_emissao", 0), ("permite_emissao", True), ("operacao", "VENDA")):
            with self.subTest(campo=campo, valor=valor):
                self.assertFalse(validar_contrato_devolucao({**self.conteudo, campo: valor})["estrutura_valida"])

    def test_referencia_invalida_duplicada_e_ausente(self):
        ref = {"tipo": "memoria", "id": 1, "sha256": "b" * 64}
        for referencias in ([], [ref, ref], [{**ref, "sha256": "abc"}], [{**ref, "id": True}], [None], [{**ref, "tipo": []}]):
            self.conteudo["grupos"]["origem"] = {"estado": "REFERENCIADO", "referencias": referencias}
            self.assertFalse(validar_contrato_devolucao(self.conteudo)["estrutura_valida"])

    def test_tipos_malformados_nao_geram_excecao(self):
        for conteudo in (None, [], "", 1, {**self.conteudo, "grupos": []}):
            self.assertFalse(validar_contrato_devolucao(conteudo)["estrutura_valida"])

    def test_estados_diferenciados_e_evidencia_contraditoria(self):
        for estado in ("AUSENTE", "DIVERGENTE", "SUPERADO", "NAO_SUPORTADO"):
            self.conteudo["grupos"]["origem"] = {"estado": estado, "referencias": []}
            self.assertEqual(validar_contrato_devolucao(self.conteudo)["bloqueios"][0]["codigo"], estado)
        self.conteudo["grupos"]["origem"] = {"estado": "AUSENTE", "referencias": [{"tipo": "memoria", "id": 1, "sha256": "b" * 64}]}
        self.assertFalse(validar_contrato_devolucao(self.conteudo)["estrutura_valida"])
