from datetime import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from .pacote_contabil import analisar_xml_nfe, data_competencia_documento


XML_COMPLETO = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe52260812345678000199650010000000011000000010" versao="4.00">
    <ide><mod>65</mod><dhEmi>2026-08-20T10:00:00-03:00</dhEmi></ide>
    <det nItem="1">
      <prod><cProd>10</cProd><xProd>Arroz</xProd><NCM>10063021</NCM><CEST>1704900</CEST><CFOP>5102</CFOP><uCom>UN</uCom><qCom>2.000</qCom><vUnCom>10.0000</vUnCom><vProd>20.00</vProd></prod>
      <imposto>
        <ICMS><ICMS20><orig>0</orig><CST>20</CST><pRedBC>10.0000</pRedBC><vBC>18.00</vBC><pICMS>17.0000</pICMS><vICMS>3.06</vICMS><vBCFCP>18.00</vBCFCP><pFCP>2.0000</pFCP><vFCP>0.36</vFCP><cBenef>GO123456</cBenef></ICMS20></ICMS>
        <PIS><PISAliq><CST>01</CST><vBC>20.00</vBC><pPIS>1.6500</pPIS><vPIS>0.33</vPIS></PISAliq></PIS>
        <COFINS><COFINSAliq><CST>01</CST><vBC>20.00</vBC><pCOFINS>7.6000</pCOFINS><vCOFINS>1.52</vCOFINS></COFINSAliq></COFINS>
        <IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>20.00</vBC><pIPI>5.0000</pIPI><vIPI>1.00</vIPI></IPITrib></IPI>
      </imposto>
    </det>
  </infNFe></NFe><protNFe><infProt><dhRecbto>2026-08-20T10:00:02-03:00</dhRecbto></infProt></protNFe>
</nfeProc>"""


class PacoteContabilFiscalTests(SimpleTestCase):
    def test_extrai_classificacao_e_tributos_do_xml_armazenado(self):
        analise = analisar_xml_nfe(XML_COMPLETO)

        self.assertEqual(analise["data_emissao"].isoformat(), "2026-08-20")
        self.assertEqual(analise["modelo"], "65")
        self.assertEqual(analise["data_autorizacao"].isoformat(), "2026-08-20")
        self.assertEqual(analise["erro"], "")
        item = analise["itens"][0]
        self.assertEqual(item["ncm"], "10063021")
        self.assertEqual(item["cest"], "1704900")
        self.assertEqual(item["cfop"], "5102")
        self.assertEqual(item["cst_icms"], "20")
        self.assertEqual(item["cbenef"], "GO123456")
        self.assertEqual(item["valor_icms"], "3.06")
        self.assertEqual(item["valor_fcp"], "0.36")
        self.assertEqual(item["valor_pis"], "0.33")
        self.assertEqual(item["valor_cofins"], "1.52")
        self.assertEqual(item["valor_ipi"], "1.00")

    def test_competencia_prioriza_data_do_xml_e_explicita_fallback(self):
        documento = SimpleNamespace(
            xml_conteudo=XML_COMPLETO,
            xml_gerado_em=timezone.make_aware(datetime(2026, 8, 21, 8, 0)),
            criado_em=timezone.make_aware(datetime(2026, 8, 22, 8, 0)),
        )
        data_emissao, fonte = data_competencia_documento(documento)
        self.assertEqual(data_emissao.isoformat(), "2026-08-20")
        self.assertEqual(fonte, "XML_DHEMI")

        documento.xml_conteudo = "<NFe><infNFe/></NFe>"
        data_emissao, fonte = data_competencia_documento(documento)
        self.assertEqual(data_emissao.isoformat(), "2026-08-21")
        self.assertEqual(fonte, "XML_GERADO_EM")

    def test_xml_invalido_vira_pendencia_sem_interromper_exportacao(self):
        analise = analisar_xml_nfe("<NFe>")
        self.assertEqual(analise["itens"], [])
        self.assertIn("XML inválido", analise["erro"])

