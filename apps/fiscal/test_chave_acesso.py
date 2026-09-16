from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.utils import timezone

from .chave_acesso import (
    CONTRATO_CHAVE_ACESSO,
    construir_chave_acesso,
    normalizar_chave_acesso,
    normalizar_cnpj_emitente,
)
from .adapters import (
    SefazAdapterError,
    normalizar_retorno_consulta,
    normalizar_retorno_transmissao,
)
from .estrategia_normalizacao_cnpj import calcular_dv_cnpj
from .models import TipoDocumentoFiscal
from .services import _chave_acesso_documento
from .validacoes import validar_xml_pre_transmissao


def _dv_numerico_legado(base):
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(
        int(digito) * pesos[indice % len(pesos)]
        for indice, digito in enumerate(reversed(base))
    )
    resultado = 11 - (soma % 11)
    return "0" if resultado >= 10 else str(resultado)


class ChaveAcessoCentralTests(SimpleTestCase):
    def argumentos(self, cnpj):
        return {
            "codigo_uf": "52",
            "aamm": "2609",
            "cnpj_emitente": cnpj,
            "modelo": "55",
            "serie": "001",
            "numero": "000000123",
            "tipo_emissao": "1",
            "codigo_numerico": "12345678",
        }

    def test_contrato_e_chave_numerica_preservam_resultado_legado(self):
        self.assertEqual(CONTRATO_CHAVE_ACESSO, "fiscal_access_key_alphanumeric_v1")
        cnpj = "04252011000110"
        chave = construir_chave_acesso(**self.argumentos(cnpj))
        base = "522609" + cnpj + "55001000000123112345678"

        self.assertEqual(chave, base + _dv_numerico_legado(base))
        self.assertEqual(normalizar_chave_acesso(chave), chave)

    def test_forma_chave_alfanumerica_mascarada_ou_canonica(self):
        base_cnpj = "12ABC34501DE"
        cnpj = base_cnpj + calcular_dv_cnpj(base_cnpj)
        mascarado = (
            f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/"
            f"{cnpj[8:12]}-{cnpj[12:]}"
        )

        canonica = construir_chave_acesso(**self.argumentos(cnpj.lower()))
        com_mascara = construir_chave_acesso(**self.argumentos(mascarado.lower()))

        self.assertEqual(canonica, com_mascara)
        self.assertEqual(canonica[6:20], cnpj)
        self.assertEqual(normalizar_chave_acesso(canonica.lower()), canonica)

    def test_recusa_campos_fora_da_estrutura_oficial(self):
        cenarios = (
            ("codigo_uf", "5"),
            ("aamm", "26A9"),
            ("modelo", "5"),
            ("serie", "1"),
            ("numero", "123"),
            ("tipo_emissao", "X"),
            ("codigo_numerico", "123"),
        )
        for campo, valor in cenarios:
            argumentos = self.argumentos("04252011000110")
            argumentos[campo] = valor
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                construir_chave_acesso(**argumentos)

    def test_normalizador_recusa_tamanho_posicoes_e_dv_invalidos(self):
        chave = construir_chave_acesso(**self.argumentos("04252011000110"))
        self.assertEqual(normalizar_chave_acesso(chave[:-1]), "")
        self.assertEqual(normalizar_chave_acesso(chave[:5] + "A" + chave[6:]), "")
        self.assertEqual(
            normalizar_chave_acesso(
                chave[:-1] + ("0" if chave[-1] != "0" else "1")
            ),
            "",
        )

    def test_servico_usa_nucleo_para_cnpj_numerico_e_alfanumerico(self):
        documento = SimpleNamespace(
            pk=7,
            serie=1,
            numero=123,
            criado_em=timezone.now(),
        )
        empresa = SimpleNamespace(cnpj="04.252.011/0001-10")
        filial = SimpleNamespace(cnpj="", empresa=empresa, uf="GO")

        chave, codigo = _chave_acesso_documento(documento, filial, "65", "1")

        self.assertEqual(codigo, "00000007")
        self.assertEqual(normalizar_chave_acesso(chave), chave)

        base_cnpj = "12ABC34501DE"
        filial.cnpj = base_cnpj + calcular_dv_cnpj(base_cnpj)
        chave_alfa, _ = _chave_acesso_documento(documento, filial, "65", "1")

        self.assertEqual(chave_alfa[6:20], filial.cnpj)
        self.assertEqual(normalizar_chave_acesso(chave_alfa), chave_alfa)

    def test_normaliza_cnpj_emitente_uma_vez_para_chave_e_xml(self):
        base_cnpj = "12ABC34501DE"
        cnpj = base_cnpj + calcular_dv_cnpj(base_cnpj)
        mascarado = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

        self.assertEqual(normalizar_cnpj_emitente(mascarado.lower()), cnpj)

    def test_validacao_pre_transmissao_reconhece_chave_alfa_offline(self):
        base_cnpj = "12ABC34501DE"
        cnpj = base_cnpj + calcular_dv_cnpj(base_cnpj)
        chave = construir_chave_acesso(**self.argumentos(cnpj))
        xml = (
            '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
            f'<infNFe Id="NFe{chave}"><ide><mod>55</mod><cDV>{chave[-1]}</cDV>'
            f"</ide><emit><CNPJ>{cnpj}</CNPJ></emit></infNFe></NFe>"
        )
        documento = SimpleNamespace(
            chave_acesso=chave.lower(),
            xml_conteudo=xml,
            tipo_documento=TipoDocumentoFiscal.NFE,
        )
        adapter = SimpleNamespace(valida_schema=True, assina_xml=True)

        resultado = validar_xml_pre_transmissao(documento, adapter)

        self.assertEqual(resultado["chave_acesso"], chave)
        self.assertEqual(resultado["modelo"], "55")
        self.assertTrue(resultado["assinatura_pelo_adaptador"])

    def test_validacao_recusa_divergencia_entre_emitente_e_chave(self):
        cnpj = "04252011000110"
        chave = construir_chave_acesso(**self.argumentos(cnpj))
        xml = (
            '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
            f'<infNFe Id="NFe{chave}"><ide><mod>55</mod><cDV>{chave[-1]}</cDV>'
            "</ide><emit><CNPJ>12345678000190</CNPJ></emit></infNFe></NFe>"
        )
        documento = SimpleNamespace(
            chave_acesso=chave,
            xml_conteudo=xml,
            tipo_documento=TipoDocumentoFiscal.NFE,
        )
        adapter = SimpleNamespace(valida_schema=True, assina_xml=True)

        with self.assertRaisesMessage(
            ValidationError, "CNPJ do emitente no XML não corresponde a chave de acesso"
        ):
            validar_xml_pre_transmissao(documento, adapter)

    def test_retornos_de_transmissao_e_consulta_aceitam_chave_alfanumerica(self):
        base_cnpj = "12ABC34501DE"
        cnpj = base_cnpj + calcular_dv_cnpj(base_cnpj)
        chave = construir_chave_acesso(**self.argumentos(cnpj))

        transmissao = normalizar_retorno_transmissao({
            "status": "AUTORIZADO",
            "chave_acesso": chave.lower(),
            "protocolo": "135260000000001",
        })
        consulta = normalizar_retorno_consulta({
            "status": "AUTORIZADO",
            "chave_acesso": chave.lower(),
            "protocolo": "135260000000001",
        })

        self.assertEqual(transmissao.chave_acesso, chave)
        self.assertEqual(consulta.chave_acesso, chave)

    def test_retornos_continuam_recusando_chave_com_dv_invalido(self):
        chave = construir_chave_acesso(**self.argumentos("04252011000110"))
        invalida = chave[:-1] + ("0" if chave[-1] != "0" else "1")

        with self.assertRaises(SefazAdapterError):
            normalizar_retorno_transmissao({
                "status": "AUTORIZADO",
                "chave_acesso": invalida,
                "protocolo": "135260000000001",
            })
        with self.assertRaises(SefazAdapterError):
            normalizar_retorno_consulta({
                "status": "AUTORIZADO",
                "chave_acesso": invalida,
                "protocolo": "135260000000001",
            })
