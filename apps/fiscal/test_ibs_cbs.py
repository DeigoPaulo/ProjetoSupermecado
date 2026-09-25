from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from django.test import SimpleTestCase

from .focus_sefaz_adapter import FocusNFeSefazAdapter
from .ibs_cbs.calculo import calcular_base_operacao_padrao, calcular_ibs_cbs_padrao
from .ibs_cbs.catalogo import ClassificacaoIbsCbsInvalida, validar_classificacao
from .ibs_cbs.contrato import emissao_ibs_cbs_obrigatoria
from .ibs_cbs.xml import adicionar_grupo_item, adicionar_totais, reconciliar_xml
from .models import ModoTransicaoIbsCbs
from .services import _pendencias_emissao_ibs_cbs


NFE_NS = "http://www.portalfiscal.inf.br/nfe"


class ContratoIbsCbsTests(SimpleTestCase):
    def test_recorte_temporal_abrange_apenas_go_crt3_modelos_55_e_65(self):
        base = {
            "uf": "GO",
            "crt": "3",
            "modelo": "65",
            "ambiente": "HOMOLOGACAO",
        }
        self.assertFalse(
            emissao_ibs_cbs_obrigatoria(**base, data_emissao=date(2026, 6, 30))
        )
        self.assertTrue(
            emissao_ibs_cbs_obrigatoria(**base, data_emissao=date(2026, 7, 1))
        )
        self.assertFalse(
            emissao_ibs_cbs_obrigatoria(
                **{**base, "ambiente": "PRODUCAO"},
                data_emissao=date(2026, 8, 2),
            )
        )
        self.assertTrue(
            emissao_ibs_cbs_obrigatoria(
                **{**base, "ambiente": "PRODUCAO", "modelo": "55"},
                data_emissao=date(2026, 8, 3),
            )
        )
        for alteracao in ({"uf": "SP"}, {"crt": "1"}, {"modelo": "57"}):
            with self.subTest(alteracao=alteracao):
                self.assertFalse(
                    emissao_ibs_cbs_obrigatoria(
                        **{**base, **alteracao}, data_emissao=date(2026, 9, 1)
                    )
                )

    def test_catalogo_falha_fechado_para_classificacao_desconhecida_especial_e_monofasica(self):
        self.assertEqual(validar_classificacao("000", "000001", "65").cclass_trib, "000001")
        cenarios = (
            ("000", "999999", "65", "nao catalogados"),
            ("000", "000003", "65", "incompativel com o modelo 65"),
            ("000", "000003", "55", "regime automotivo especial"),
            ("620", "620001", "55", "monofasica"),
        )
        for cst, cclass_trib, modelo, mensagem in cenarios:
            with self.subTest(cst=cst, cclass_trib=cclass_trib, modelo=modelo):
                with self.assertRaisesRegex(ClassificacaoIbsCbsInvalida, mensagem):
                    validar_classificacao(cst, cclass_trib, modelo)

    def test_calculo_padrao_aplica_exclusoes_aliquotas_e_arredondamento(self):
        base = calcular_base_operacao_padrao(
            valor_produtos=Decimal("82.70"),
            desconto=Decimal("2.70"),
            valor_pis=Decimal("1.32"),
            valor_cofins=Decimal("6.08"),
            valor_icms=Decimal("14.40"),
            valor_fcp=Decimal("0.00"),
        )
        calculo = calcular_ibs_cbs_padrao(
            valor_operacao=base,
            cst="000",
            cclass_trib="000001",
            modelo="65",
        )
        self.assertEqual(calculo.base, Decimal("58.20"))
        self.assertEqual(calculo.valor_ibs_uf, Decimal("0.06"))
        self.assertEqual(calculo.valor_ibs_municipio, Decimal("0.00"))
        self.assertEqual(calculo.valor_ibs, Decimal("0.06"))
        self.assertEqual(calculo.valor_cbs, Decimal("0.52"))

    def test_modo_emissao_homologada_nao_libera_cenario_fora_do_recorte(self):
        configuracao = SimpleNamespace(
            modo_transicao_ibs_cbs=ModoTransicaoIbsCbs.EMISSAO_HOMOLOGADA,
            crt="3",
            regime_tributario="Regime normal",
            ambiente="HOMOLOGACAO",
        )
        self.assertEqual(
            _pendencias_emissao_ibs_cbs(
                configuracao, SimpleNamespace(uf="GO"), "65"
            ),
            [],
        )
        self.assertIn(
            "fora do recorte GO CRT 3 padrão",
            _pendencias_emissao_ibs_cbs(
                configuracao, SimpleNamespace(uf="SP"), "65"
            )[0],
        )


class XmlIbsCbsTests(SimpleTestCase):
    def _xml(self):
        ET.register_namespace("", NFE_NS)
        nfe = ET.Element(f"{{{NFE_NS}}}NFe")
        inf_nfe = ET.SubElement(nfe, f"{{{NFE_NS}}}infNFe")
        calculos = []
        for numero, base in enumerate((Decimal("58.20"), Decimal("10.00")), start=1):
            det = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}det", {"nItem": str(numero)})
            imposto = ET.SubElement(det, f"{{{NFE_NS}}}imposto")
            calculo = calcular_ibs_cbs_padrao(
                valor_operacao=base,
                cst="000",
                cclass_trib="000001",
                modelo="65",
            )
            adicionar_grupo_item(imposto, calculo, namespace=NFE_NS)
            calculos.append(calculo)
        total = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}total")
        adicionar_totais(total, calculos, namespace=NFE_NS)
        return nfe, inf_nfe

    def test_itens_e_total_reconciliam_e_projetam_no_payload_focus(self):
        nfe, inf_nfe = self._xml()
        self.assertTrue(reconciliar_xml(inf_nfe, namespace=NFE_NS))
        total = inf_nfe.findtext(
            f"{{{NFE_NS}}}total/{{{NFE_NS}}}IBSCBSTot/{{{NFE_NS}}}vBCIBSCBS"
        )
        self.assertEqual(total, "68.20")

        det = inf_nfe.find(f"{{{NFE_NS}}}det")
        item = FocusNFeSefazAdapter()._item(det)
        self.assertEqual(item["ibs_cbs_situacao_tributaria"], "000")
        self.assertEqual(item["ibs_cbs_classificacao_tributaria"], "000001")
        self.assertEqual(item["ibs_cbs_base_calculo"], "58.20")
        self.assertEqual(item["ibs_uf_aliquota"], "0.1000")
        self.assertEqual(item["cbs_aliquota"], "0.9000")
        self.assertIsNotNone(nfe)

    def test_reconciliacao_bloqueia_total_adulterado(self):
        _, inf_nfe = self._xml()
        total_cbs = inf_nfe.find(
            f"{{{NFE_NS}}}total/{{{NFE_NS}}}IBSCBSTot/"
            f"{{{NFE_NS}}}gCBS/{{{NFE_NS}}}vCBS"
        )
        total_cbs.text = "99.99"
        with self.assertRaisesRegex(ValueError, "SOMA_ITENS diverge de TOTAL_XML"):
            reconciliar_xml(inf_nfe, namespace=NFE_NS)
