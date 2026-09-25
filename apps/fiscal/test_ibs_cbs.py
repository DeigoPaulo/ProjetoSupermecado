from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from django.test import SimpleTestCase

from .focus_sefaz_adapter import FocusNFeSefazAdapter
from .ibs_cbs.calculo import calcular_base_operacao_padrao, calcular_ibs_cbs_padrao
from .ibs_cbs.catalogo import (
    METADADOS_CATALOGO,
    ClassificacaoIbsCbsInvalida,
    validar_classificacao,
)
from .ibs_cbs.contrato import emissao_ibs_cbs_obrigatoria
from .ibs_cbs.validacao import validar_paridade_xml
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

    def test_catalogo_congela_rastreabilidade_oficial_sem_hash_ficticio(self):
        self.assertEqual(METADADOS_CATALOGO["versao_it"], "IT 2025.002 v1.60")
        self.assertEqual(METADADOS_CATALOGO["data_oficial"], "2026-06-23")
        self.assertEqual(METADADOS_CATALOGO["data_consulta"], "2026-09-24")
        self.assertTrue(METADADOS_CATALOGO["url_oficial"].startswith("https://"))
        self.assertIsNone(METADADOS_CATALOGO["artefato_oficial_sha256"])
        self.assertIn("endpoint oficial", METADADOS_CATALOGO["evidencia"])

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
            prod = ET.SubElement(det, f"{{{NFE_NS}}}prod")
            ET.SubElement(prod, f"{{{NFE_NS}}}vProd").text = f"{base:.2f}"
            imposto = ET.SubElement(det, f"{{{NFE_NS}}}imposto")
            icms = ET.SubElement(imposto, f"{{{NFE_NS}}}ICMS")
            icms00 = ET.SubElement(icms, f"{{{NFE_NS}}}ICMS00")
            ET.SubElement(icms00, f"{{{NFE_NS}}}vICMS").text = "0.00"
            pis = ET.SubElement(imposto, f"{{{NFE_NS}}}PIS")
            pis_aliq = ET.SubElement(pis, f"{{{NFE_NS}}}PISAliq")
            ET.SubElement(pis_aliq, f"{{{NFE_NS}}}vPIS").text = "0.00"
            cofins = ET.SubElement(imposto, f"{{{NFE_NS}}}COFINS")
            cofins_aliq = ET.SubElement(cofins, f"{{{NFE_NS}}}COFINSAliq")
            ET.SubElement(cofins_aliq, f"{{{NFE_NS}}}vCOFINS").text = "0.00"
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

    @staticmethod
    def _duplicar(pai, elemento):
        duplicado = ET.fromstring(ET.tostring(elemento, encoding="unicode"))
        pai.append(duplicado)
        return duplicado

    def test_itens_e_total_reconciliam_e_projetam_no_payload_focus(self):
        nfe, inf_nfe = self._xml()
        self.assertTrue(reconciliar_xml(inf_nfe, namespace=NFE_NS))
        self.assertTrue(
            validar_paridade_xml(
                inf_nfe,
                namespace=NFE_NS,
                modelo="65",
                data_emissao=date(2026, 9, 25),
            )
        )
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

    def test_reconciliacao_reconhece_ibs_cbs_vazio_como_grupo_presente(self):
        _, inf_nfe = self._xml()
        grupo = inf_nfe.find(
            f"{{{NFE_NS}}}det/{{{NFE_NS}}}imposto/{{{NFE_NS}}}IBSCBS"
        )
        grupo.clear()

        with self.assertRaises(ValueError):
            reconciliar_xml(inf_nfe, namespace=NFE_NS)

    def test_paridade_bloqueia_ibs_cbs_vazio_e_campos_obrigatorios_ausentes(self):
        caminhos = (None, "CST", "cClassTrib", "gIBSCBS")
        for caminho in caminhos:
            with self.subTest(caminho=caminho or "IBSCBS vazio"):
                _, inf_nfe = self._xml()
                grupo = inf_nfe.find(
                    f"{{{NFE_NS}}}det/{{{NFE_NS}}}imposto/{{{NFE_NS}}}IBSCBS"
                )
                if caminho is None:
                    grupo.clear()
                else:
                    grupo.remove(grupo.find(f"{{{NFE_NS}}}{caminho}"))

                with self.assertRaises(ValueError):
                    validar_paridade_xml(
                        inf_nfe,
                        namespace=NFE_NS,
                        modelo="65",
                        data_emissao=date(2026, 9, 25),
                    )

    def test_paridade_bloqueia_ibs_cbs_presente_somente_em_parte_dos_itens(self):
        _, inf_nfe = self._xml()
        primeiro_imposto = inf_nfe.find(
            f"{{{NFE_NS}}}det/{{{NFE_NS}}}imposto"
        )
        primeiro_imposto.remove(primeiro_imposto.find(f"{{{NFE_NS}}}IBSCBS"))

        with self.assertRaisesRegex(ValueError, "item 1 IBSCBS ausente"):
            validar_paridade_xml(
                inf_nfe,
                namespace=NFE_NS,
                modelo="65",
                data_emissao=date(2026, 9, 25),
            )

    def test_paridade_bloqueia_cardinalidade_duplicada_do_item_ibs_cbs(self):
        cenarios = (
            ("IBSCBS", "imposto", "IBSCBS"),
            ("CST", "IBSCBS", "CST"),
            ("cClassTrib", "IBSCBS", "cClassTrib"),
            ("gIBSCBS", "IBSCBS", "gIBSCBS"),
            ("vBC", "gIBSCBS", "vBC"),
            ("gIBSUF", "gIBSCBS", "gIBSUF"),
            ("pIBSUF", "gIBSUF", "pIBSUF"),
            ("vIBSUF", "gIBSUF", "vIBSUF"),
            ("gIBSMun", "gIBSCBS", "gIBSMun"),
            ("pIBSMun", "gIBSMun", "pIBSMun"),
            ("vIBSMun", "gIBSMun", "vIBSMun"),
            ("vIBS", "gIBSCBS", "vIBS"),
            ("gCBS", "gIBSCBS", "gCBS"),
            ("pCBS", "gCBS", "pCBS"),
            ("vCBS", "gCBS", "vCBS"),
        )
        for nome, pai_nome, filho_nome in cenarios:
            with self.subTest(campo=nome):
                _, inf_nfe = self._xml()
                imposto = inf_nfe.find(
                    f"{{{NFE_NS}}}det/{{{NFE_NS}}}imposto"
                )
                ibs_cbs = imposto.find(f"{{{NFE_NS}}}IBSCBS")
                g_ibs_cbs = ibs_cbs.find(f"{{{NFE_NS}}}gIBSCBS")
                pais = {
                    "imposto": imposto,
                    "IBSCBS": ibs_cbs,
                    "gIBSCBS": g_ibs_cbs,
                    "gIBSUF": g_ibs_cbs.find(f"{{{NFE_NS}}}gIBSUF"),
                    "gIBSMun": g_ibs_cbs.find(f"{{{NFE_NS}}}gIBSMun"),
                    "gCBS": g_ibs_cbs.find(f"{{{NFE_NS}}}gCBS"),
                }
                pai = pais[pai_nome]
                self._duplicar(pai, pai.find(f"{{{NFE_NS}}}{filho_nome}"))

                with self.assertRaisesRegex(ValueError, "XML IBS/CBS ambiguo"):
                    validar_paridade_xml(
                        inf_nfe,
                        namespace=NFE_NS,
                        modelo="65",
                        data_emissao=date(2026, 9, 25),
                    )

    def test_reconciliacao_bloqueia_cardinalidade_duplicada_dos_totais(self):
        cenarios = (
            ("total", "IBSCBSTot"),
            ("IBSCBSTot", "vBCIBSCBS"),
            ("IBSCBSTot", "gIBS"),
            ("gIBS", "gIBSUF"),
            ("gIBSUF", "vIBSUF"),
            ("gIBS", "gIBSMun"),
            ("gIBSMun", "vIBSMun"),
            ("gIBS", "vIBS"),
            ("IBSCBSTot", "gCBS"),
            ("gCBS", "vCBS"),
        )
        for pai_nome, filho_nome in cenarios:
            with self.subTest(campo=f"{pai_nome}/{filho_nome}"):
                _, inf_nfe = self._xml()
                total = inf_nfe.find(f"{{{NFE_NS}}}total")
                ibs_cbs = total.find(f"{{{NFE_NS}}}IBSCBSTot")
                g_ibs = ibs_cbs.find(f"{{{NFE_NS}}}gIBS")
                pais = {
                    "total": total,
                    "IBSCBSTot": ibs_cbs,
                    "gIBS": g_ibs,
                    "gIBSUF": g_ibs.find(f"{{{NFE_NS}}}gIBSUF"),
                    "gIBSMun": g_ibs.find(f"{{{NFE_NS}}}gIBSMun"),
                    "gCBS": ibs_cbs.find(f"{{{NFE_NS}}}gCBS"),
                }
                pai = pais[pai_nome]
                self._duplicar(pai, pai.find(f"{{{NFE_NS}}}{filho_nome}"))

                with self.assertRaisesRegex(ValueError, "XML IBS/CBS ambiguo"):
                    reconciliar_xml(inf_nfe, namespace=NFE_NS)

    def test_paridade_bloqueia_ambiguidades_nos_grupos_legados(self):
        cenarios = (
            ("ICMS duplicado", "imposto", "ICMS", "grupo"),
            ("ICMS variantes", "ICMS", "ICMS20", "variante"),
            ("vICMS duplicado", "ICMS00", "vICMS", "campo"),
            ("vFCP duplicado", "ICMS00", "vFCP", "campo_novo_duplo"),
            ("PIS duplicado", "imposto", "PIS", "grupo"),
            ("PIS variantes", "PIS", "PISNT", "variante"),
            ("vPIS duplicado", "PISAliq", "vPIS", "campo"),
            ("COFINS duplicado", "imposto", "COFINS", "grupo"),
            ("COFINS variantes", "COFINS", "COFINSNT", "variante"),
            ("vCOFINS duplicado", "COFINSAliq", "vCOFINS", "campo"),
        )
        for nome, pai_nome, filho_nome, operacao in cenarios:
            with self.subTest(cenario=nome):
                _, inf_nfe = self._xml()
                imposto = inf_nfe.find(
                    f"{{{NFE_NS}}}det/{{{NFE_NS}}}imposto"
                )
                icms = imposto.find(f"{{{NFE_NS}}}ICMS")
                pis = imposto.find(f"{{{NFE_NS}}}PIS")
                cofins = imposto.find(f"{{{NFE_NS}}}COFINS")
                pais = {
                    "imposto": imposto,
                    "ICMS": icms,
                    "ICMS00": icms.find(f"{{{NFE_NS}}}ICMS00"),
                    "PIS": pis,
                    "PISAliq": pis.find(f"{{{NFE_NS}}}PISAliq"),
                    "COFINS": cofins,
                    "COFINSAliq": cofins.find(f"{{{NFE_NS}}}COFINSAliq"),
                }
                pai = pais[pai_nome]
                if operacao in {"grupo", "campo"}:
                    self._duplicar(pai, pai.find(f"{{{NFE_NS}}}{filho_nome}"))
                elif operacao == "campo_novo_duplo":
                    for _ in range(2):
                        ET.SubElement(pai, f"{{{NFE_NS}}}{filho_nome}").text = "0.00"
                else:
                    ET.SubElement(pai, f"{{{NFE_NS}}}{filho_nome}")

                with self.assertRaisesRegex(ValueError, "XML IBS/CBS ambiguo"):
                    validar_paridade_xml(
                        inf_nfe,
                        namespace=NFE_NS,
                        modelo="65",
                        data_emissao=date(2026, 9, 25),
                    )

    def test_paridade_bloqueia_adulteracao_de_cada_campo_do_item(self):
        caminhos = {
            "CST": ("CST", "999"),
            "cClassTrib": ("cClassTrib", "999999"),
            "vBC": ("gIBSCBS/vBC", "58.21"),
            "pIBSUF": ("gIBSCBS/gIBSUF/pIBSUF", "0.2000"),
            "vIBSUF": ("gIBSCBS/gIBSUF/vIBSUF", "0.07"),
            "pIBSMun": ("gIBSCBS/gIBSMun/pIBSMun", "0.1000"),
            "vIBSMun": ("gIBSCBS/gIBSMun/vIBSMun", "0.01"),
            "vIBS": ("gIBSCBS/vIBS", "0.07"),
            "pCBS": ("gIBSCBS/gCBS/pCBS", "1.0000"),
            "vCBS": ("gIBSCBS/gCBS/vCBS", "0.53"),
        }
        for campo, (caminho, valor) in caminhos.items():
            with self.subTest(campo=campo):
                _, inf_nfe = self._xml()
                grupo = inf_nfe.find(
                    f"{{{NFE_NS}}}det/{{{NFE_NS}}}imposto/{{{NFE_NS}}}IBSCBS"
                )
                elemento = grupo.find(
                    "/".join(f"{{{NFE_NS}}}{parte}" for parte in caminho.split("/"))
                )
                elemento.text = valor
                with self.assertRaises(ValueError):
                    validar_paridade_xml(
                        inf_nfe,
                        namespace=NFE_NS,
                        modelo="65",
                        data_emissao=date(2026, 9, 25),
                    )

    def test_paridade_bloqueia_item_e_total_adulterados_coerentemente(self):
        cenarios = (
            ("vBC", "58.21", "vBCIBSCBS", "68.21"),
            ("vIBS", "0.07", "gIBS/vIBS", "0.08"),
            ("gCBS/vCBS", "0.53", "gCBS/vCBS", "0.62"),
        )
        for caminho_item, valor_item, caminho_total, valor_total in cenarios:
            with self.subTest(campo=caminho_item):
                _, inf_nfe = self._xml()
                grupo = inf_nfe.find(
                    f"{{{NFE_NS}}}det/{{{NFE_NS}}}imposto/{{{NFE_NS}}}IBSCBS/"
                    f"{{{NFE_NS}}}gIBSCBS"
                )
                grupo.find(
                    "/".join(
                        f"{{{NFE_NS}}}{parte}" for parte in caminho_item.split("/")
                    )
                ).text = valor_item
                total = inf_nfe.find(
                    f"{{{NFE_NS}}}total/{{{NFE_NS}}}IBSCBSTot"
                )
                total.find(
                    "/".join(
                        f"{{{NFE_NS}}}{parte}" for parte in caminho_total.split("/")
                    )
                ).text = valor_total
                with self.assertRaisesRegex(ValueError, "Divergencia matematica"):
                    validar_paridade_xml(
                        inf_nfe,
                        namespace=NFE_NS,
                        modelo="65",
                        data_emissao=date(2026, 9, 25),
                    )

    def test_paridade_bloqueia_totais_adulterados(self):
        caminhos = ("vBCIBSCBS", "gIBS/vIBS", "gCBS/vCBS")
        for caminho in caminhos:
            with self.subTest(campo=caminho):
                _, inf_nfe = self._xml()
                total = inf_nfe.find(
                    f"{{{NFE_NS}}}total/{{{NFE_NS}}}IBSCBSTot"
                )
                total.find(
                    "/".join(f"{{{NFE_NS}}}{parte}" for parte in caminho.split("/"))
                ).text = "99.99"
                with self.assertRaisesRegex(ValueError, "SOMA_ITENS diverge de TOTAL_XML"):
                    validar_paridade_xml(
                        inf_nfe,
                        namespace=NFE_NS,
                        modelo="65",
                        data_emissao=date(2026, 9, 25),
                    )

    def test_paridade_bloqueia_componentes_fora_do_contrato_e_ano_futuro(self):
        for campo in ("vFrete", "vSeg", "vOutro"):
            with self.subTest(campo=campo):
                _, inf_nfe = self._xml()
                prod = inf_nfe.find(f"{{{NFE_NS}}}det/{{{NFE_NS}}}prod")
                ET.SubElement(prod, f"{{{NFE_NS}}}{campo}").text = "1.00"
                with self.assertRaisesRegex(ValueError, campo):
                    validar_paridade_xml(
                        inf_nfe,
                        namespace=NFE_NS,
                        modelo="65",
                        data_emissao=date(2026, 9, 25),
                    )

        for grupo_nome in (
            "II",
            "ICMSUFDest",
            "ISSQN",
            "IS",
            "PISST",
            "COFINSST",
            "ICMSMono",
        ):
            with self.subTest(grupo=grupo_nome):
                _, inf_nfe = self._xml()
                imposto = inf_nfe.find(
                    f"{{{NFE_NS}}}det/{{{NFE_NS}}}imposto"
                )
                ET.SubElement(imposto, f"{{{NFE_NS}}}{grupo_nome}")
                with self.assertRaises(ValueError):
                    validar_paridade_xml(
                        inf_nfe,
                        namespace=NFE_NS,
                        modelo="65",
                        data_emissao=date(2026, 9, 25),
                    )

        for campo in ("vFCPUFDest", "vICMSUFDest", "vICMSMono"):
            with self.subTest(campo=campo):
                _, inf_nfe = self._xml()
                imposto = inf_nfe.find(
                    f"{{{NFE_NS}}}det/{{{NFE_NS}}}imposto"
                )
                ET.SubElement(imposto, f"{{{NFE_NS}}}{campo}").text = "1.00"
                with self.assertRaisesRegex(ValueError, "ainda nao suportado"):
                    validar_paridade_xml(
                        inf_nfe,
                        namespace=NFE_NS,
                        modelo="65",
                        data_emissao=date(2026, 9, 25),
                    )

        _, inf_nfe = self._xml()
        with self.assertRaisesRegex(ValueError, "somente para 2026"):
            validar_paridade_xml(
                inf_nfe,
                namespace=NFE_NS,
                modelo="65",
                data_emissao=date(2027, 1, 1),
            )
