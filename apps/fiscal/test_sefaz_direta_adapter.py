from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from lxml import etree

from .assinaturas import assinar_xml_elemento_fiscal
from .sefaz_direta.resiliencia import (
    CircuitoSefazDiretaAberto,
    limpar_estado_resiliencia,
)
from .tests import _certificado_teste
from .sefaz_direta import (
    NFE_NS,
    SOAP_NS,
    SefazDiretaAdapter,
    SefazDiretaConnectionError,
    SefazDiretaError,
)


CHAVE = "52260812345678000199650010000000011000000010"
XML_NFE = f'''<NFe xmlns="{NFE_NS}"><infNFe Id="NFe{CHAVE}" versao="4.00"/></NFe>'''


def objeto_fiscal(pk=7):
    configuracao = SimpleNamespace()
    empresa = SimpleNamespace(cnpj="12345678000199")
    filial = SimpleNamespace(
        uf="GO",
        cnpj="12345678000199",
        empresa=empresa,
        configuracao_fiscal=configuracao,
    )
    return SimpleNamespace(
        pk=pk,
        filial=filial,
        xml_conteudo=XML_NFE,
    )


def resposta_autorizada():
    return f'''<retEnviNFe xmlns="{NFE_NS}" versao="4.00">
      <tpAmb>2</tpAmb><verAplic>GO</verAplic><cStat>104</cStat><xMotivo>Lote processado</xMotivo>
      <protNFe versao="4.00"><infProt>
        <tpAmb>2</tpAmb><chNFe>{CHAVE}</chNFe><dhRecbto>2026-08-20T10:00:00-03:00</dhRecbto>
        <nProt>152600000000001</nProt><digVal>abc=</digVal><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>
      </infProt></protNFe>
    </retEnviNFe>'''.encode()


@override_settings(
    SEFAZ_DIRETA_NETWORK_ENABLED=True,
    SEFAZ_DIRETA_ALLOW_PRODUCTION=False,
    SEFAZ_DIRETA_TIMEOUT_SECONDS=12,
    SEFAZ_DIRETA_ENDPOINTS={},
)
class SefazDiretaAdapterTests(SimpleTestCase):
    def setUp(self):
        limpar_estado_resiliencia()
    def test_assinatura_real_de_evento_com_certificado_a1(self):
        xml = f'''<envEvento xmlns="{NFE_NS}" versao="1.00">
          <evento versao="1.00"><infEvento Id="ID110111{CHAVE}01">
            <cOrgao>52</cOrgao><tpAmb>2</tpAmb><CNPJ>12345678000199</CNPJ>
          </infEvento></evento>
        </envEvento>'''
        certificado = _certificado_teste()
        with patch(
            "apps.fiscal.assinaturas.abrir_certificado_a1",
            return_value=(certificado.read(), "123456"),
        ):
            assinado = assinar_xml_elemento_fiscal(
                xml,
                SimpleNamespace(),
                nome_elemento="infEvento",
                prefixo_id="ID110111",
            )

        raiz = etree.fromstring(assinado.encode())
        self.assertEqual(
            raiz.xpath("count(.//*[local-name()='Signature'])"), 1.0
        )
        self.assertEqual(
            raiz.xpath("string(.//*[local-name()='Reference']/@URI)"),
            f"#ID110111{CHAVE}01",
        )
        self.assertTrue(
            raiz.xpath("string(.//*[local-name()='X509Certificate'])")
        )
    def test_transmitir_monta_soap_sincrono_e_retorna_nfe_proc(self):
        chamadas = []

        def transporte(**kwargs):
            chamadas.append(kwargs)
            return resposta_autorizada()

        resultado = SefazDiretaAdapter(transport=transporte).transmitir(
            documento=objeto_fiscal(),
            xml=XML_NFE,
            idempotency_key="teste-1",
            ambiente="HOMOLOGACAO",
        )

        self.assertEqual(resultado["status"], "AUTORIZADO")
        self.assertEqual(resultado["chave_acesso"], CHAVE)
        self.assertEqual(resultado["protocolo"], "152600000000001")
        self.assertIn("nfeProc", resultado["xml_autorizado"])
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0]["servico"], "autorizacao")
        self.assertEqual(chamadas[0]["timeout"], 12)
        self.assertEqual(
            chamadas[0]["endpoint"],
            "https://homolog.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
        )
        envelope = etree.fromstring(chamadas[0]["envelope"])
        self.assertEqual(etree.QName(envelope).namespace, SOAP_NS)
        self.assertEqual(
            envelope.xpath("string(.//*[local-name()='indSinc'])"), "1"
        )
        self.assertEqual(
            envelope.xpath("count(.//*[local-name()='NFe'])"), 1.0
        )

    def test_consultar_status_servico_operacional(self):
        chamadas = []

        def transporte(**kwargs):
            chamadas.append(kwargs)
            return f'''<retConsStatServ xmlns="{NFE_NS}" versao="4.00">
              <tpAmb>2</tpAmb><cStat>107</cStat><xMotivo>Servico em Operacao</xMotivo>
              <cUF>52</cUF><tMed>1</tMed>
            </retConsStatServ>'''.encode()

        resultado = SefazDiretaAdapter(transport=transporte).consultar_status_servico(
            documento=objeto_fiscal(),
            ambiente="HOMOLOGACAO",
        )

        self.assertTrue(resultado["disponivel"])
        self.assertEqual(resultado["status"], "DISPONIVEL")
        self.assertEqual(resultado["codigo"], "107")
        self.assertEqual(chamadas[0]["servico"], "status")
        self.assertEqual(
            chamadas[0]["endpoint"],
            "https://homolog.sefaz.go.gov.br/nfe/services/NFeStatusServico4",
        )
        envelope = etree.fromstring(chamadas[0]["envelope"])
        self.assertEqual(envelope.xpath("string(.//*[local-name()='xServ'])"), "STATUS")

    def test_matriz_de_capacidades_e_exposta_no_diagnostico(self):
        resultado = SefazDiretaAdapter(transport=lambda **kwargs: b"").diagnosticar()
        capacidades = resultado["capacidades"]
        self.assertEqual(capacidades["contrato"], "deigo_fiscal_capabilities_v1")
        self.assertGreater(capacidades["contagem"]["IMPLEMENTADO"], 0)
        self.assertGreater(capacidades["contagem"]["PLANEJADO"], 0)
    def test_consultar_documento_nao_localizado(self):
        def transporte(**kwargs):
            return f'''<retConsSitNFe xmlns="{NFE_NS}" versao="4.00">
              <tpAmb>2</tpAmb><cStat>217</cStat><xMotivo>NF-e nao consta na base</xMotivo>
            </retConsSitNFe>'''.encode()

        resultado = SefazDiretaAdapter(transport=transporte).consultar(
            documento=objeto_fiscal(),
            chave_acesso=CHAVE,
            idempotency_key="consulta-1",
            ambiente="HOMOLOGACAO",
        )
        self.assertEqual(resultado["status"], "NAO_LOCALIZADO")
        self.assertIn("217", resultado["mensagem"])

    @patch(
        "apps.fiscal.sefaz_direta.adapter.assinar_xml_elemento_fiscal",
        side_effect=lambda xml, *args, **kwargs: xml,
    )
    def test_cancelar_assina_evento_e_interpreta_registro(self, assinatura):
        chamadas = []

        def transporte(**kwargs):
            chamadas.append(kwargs)
            return f'''<retEnvEvento xmlns="{NFE_NS}" versao="1.00">
              <idLote>7</idLote><tpAmb>2</tpAmb><cOrgao>52</cOrgao><cStat>128</cStat><xMotivo>Lote processado</xMotivo>
              <retEvento versao="1.00"><infEvento><tpAmb>2</tpAmb><cOrgao>52</cOrgao>
                <cStat>135</cStat><xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
                <chNFe>{CHAVE}</chNFe><nProt>152600000000002</nProt>
              </infEvento></retEvento>
            </retEnvEvento>'''.encode()

        resultado = SefazDiretaAdapter(transport=transporte).cancelar(
            documento=objeto_fiscal(),
            chave_acesso=CHAVE,
            protocolo_autorizacao="152600000000001",
            justificativa="Cancelamento solicitado pelo contribuinte",
            idempotency_key="cancelar-1",
            ambiente="HOMOLOGACAO",
        )
        self.assertEqual(resultado["status"], "CANCELADO")
        self.assertEqual(resultado["protocolo"], "152600000000002")
        assinatura.assert_called_once()
        evento = etree.fromstring(chamadas[0]["envelope"])
        self.assertEqual(
            evento.xpath("string(.//*[local-name()='tpEvento'])"), "110111"
        )

    @patch(
        "apps.fiscal.sefaz_direta.adapter.assinar_xml_elemento_fiscal",
        side_effect=lambda xml, *args, **kwargs: xml,
    )
    def test_inutilizar_interpreta_protocolo(self, assinatura):
        def transporte(**kwargs):
            return f'''<retInutNFe xmlns="{NFE_NS}" versao="4.00">
              <infInut><tpAmb>2</tpAmb><cStat>102</cStat><xMotivo>Inutilizacao homologada</xMotivo>
                <nProt>152600000000003</nProt></infInut>
            </retInutNFe>'''.encode()

        resultado = SefazDiretaAdapter(transport=transporte).inutilizar(
            inutilizacao=objeto_fiscal(8),
            cnpj="12.345.678/0001-99",
            tipo_documento="NFCE",
            ano=2026,
            serie=1,
            numero_inicial=10,
            numero_final=12,
            justificativa="Falha de numeracao durante homologacao",
            idempotency_key="inut-1",
            ambiente="HOMOLOGACAO",
        )
        self.assertEqual(resultado["status"], "INUTILIZADA")
        self.assertEqual(resultado["protocolo"], "152600000000003")
        assinatura.assert_called_once()

    @override_settings(
        SEFAZ_DIRETA_MAX_ATTEMPTS=3,
        SEFAZ_DIRETA_RETRY_BASE_MS=10,
        SEFAZ_DIRETA_CIRCUIT_FAILURE_THRESHOLD=5,
    )
    def test_consulta_repete_falha_de_rede_e_se_recupera(self):
        chamadas = []
        esperas = []

        def transporte(**kwargs):
            chamadas.append(kwargs)
            if len(chamadas) == 1:
                raise TimeoutError("falha transitória")
            return f'''<retConsSitNFe xmlns="{NFE_NS}" versao="4.00">
              <tpAmb>2</tpAmb><cStat>217</cStat><xMotivo>NF-e nao consta na base</xMotivo>
            </retConsSitNFe>'''.encode()

        adapter = SefazDiretaAdapter(
            transport=transporte,
            sleeper=esperas.append,
        )
        resultado = adapter.consultar(
            documento=objeto_fiscal(),
            chave_acesso=CHAVE,
            idempotency_key="consulta-resiliente",
            ambiente="HOMOLOGACAO",
        )
        diagnostico = adapter.diagnosticar()["resiliencia"]

        self.assertEqual(resultado["status"], "NAO_LOCALIZADO")
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(esperas, [0.01])
        self.assertEqual(diagnostico["contagem"]["FALHA_REDE"], 1)
        self.assertEqual(diagnostico["contagem"]["NOVA_TENTATIVA"], 1)
        self.assertEqual(diagnostico["contagem"]["SUCESSO"], 1)

    @override_settings(
        SEFAZ_DIRETA_MAX_ATTEMPTS=3,
        SEFAZ_DIRETA_CIRCUIT_FAILURE_THRESHOLD=5,
    )
    def test_emissao_nao_repete_quando_resposta_e_incerta(self):
        chamadas = []

        def transporte(**kwargs):
            chamadas.append(kwargs)
            raise TimeoutError("resposta incerta")

        adapter = SefazDiretaAdapter(
            transport=transporte,
            sleeper=lambda segundos: self.fail("emissão não deve aguardar retry"),
        )
        with self.assertRaises(SefazDiretaConnectionError):
            adapter.transmitir(
                documento=objeto_fiscal(),
                xml=XML_NFE,
                idempotency_key="emissao-sem-retry",
                ambiente="HOMOLOGACAO",
            )

        self.assertEqual(len(chamadas), 1)
        self.assertNotIn(
            "NOVA_TENTATIVA",
            adapter.diagnosticar()["resiliencia"]["contagem"],
        )

    @override_settings(
        SEFAZ_DIRETA_MAX_ATTEMPTS=1,
        SEFAZ_DIRETA_CIRCUIT_FAILURE_THRESHOLD=2,
        SEFAZ_DIRETA_CIRCUIT_RESET_SECONDS=10,
    )
    def test_circuito_bloqueia_e_reabre_com_sonda_controlada(self):
        chamadas = []
        agora = [100.0]

        def transporte(**kwargs):
            chamadas.append(kwargs)
            if len(chamadas) <= 2:
                raise TimeoutError("indisponível")
            return f'''<retConsStatServ xmlns="{NFE_NS}" versao="4.00">
              <tpAmb>2</tpAmb><cStat>107</cStat><xMotivo>Servico em Operacao</xMotivo>
              <cUF>52</cUF><tMed>1</tMed>
            </retConsStatServ>'''.encode()

        adapter = SefazDiretaAdapter(
            transport=transporte,
            clock=lambda: agora[0],
            sleeper=lambda segundos: None,
        )
        for _ in range(2):
            with self.assertRaises(SefazDiretaConnectionError):
                adapter.consultar_status_servico(
                    documento=objeto_fiscal(), ambiente="HOMOLOGACAO"
                )
        with self.assertRaises(CircuitoSefazDiretaAberto):
            adapter.consultar_status_servico(
                documento=objeto_fiscal(), ambiente="HOMOLOGACAO"
            )
        self.assertEqual(len(chamadas), 2)

        agora[0] = 111.0
        resultado = adapter.consultar_status_servico(
            documento=objeto_fiscal(), ambiente="HOMOLOGACAO"
        )
        self.assertTrue(resultado["disponivel"])
        self.assertEqual(len(chamadas), 3)
        self.assertEqual(
            adapter.diagnosticar()["resiliencia"]["circuitos_abertos"], 0
        )

    @override_settings(
        SEFAZ_DIRETA_MAX_ATTEMPTS=1,
        SEFAZ_DIRETA_CIRCUIT_FAILURE_THRESHOLD=5,
    )
    def test_telemetria_nao_registra_documento_credencial_ou_mensagem_bruta(self):
        segredo = f"{CHAVE} 12345678000199 token-ultrassecreto"

        def transporte(**kwargs):
            raise TimeoutError(segredo)

        adapter = SefazDiretaAdapter(transport=transporte)
        with self.assertRaises(SefazDiretaConnectionError):
            adapter.consultar_status_servico(
                documento=objeto_fiscal(), ambiente="HOMOLOGACAO"
            )
        diagnostico = repr(adapter.diagnosticar()["resiliencia"])

        self.assertNotIn(CHAVE, diagnostico)
        self.assertNotIn("12345678000199", diagnostico)
        self.assertNotIn("ultrassecreto", diagnostico)
        self.assertIn("SefazDiretaConnectionError", diagnostico)
    @override_settings(
        SEFAZ_DIRETA_MAX_ATTEMPTS=1,
        SEFAZ_DIRETA_CIRCUIT_FAILURE_THRESHOLD=1,
    )
    def test_resposta_invalida_nao_deixa_circuito_preso(self):
        chamadas = []

        def transporte(**kwargs):
            chamadas.append(kwargs)
            return b"<resposta-invalida"

        adapter = SefazDiretaAdapter(transport=transporte)
        for _ in range(2):
            with self.assertRaises(SefazDiretaError):
                adapter.consultar_status_servico(
                    documento=objeto_fiscal(), ambiente="HOMOLOGACAO"
                )

        diagnostico = adapter.diagnosticar()["resiliencia"]
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(diagnostico["circuitos_abertos"], 0)
        self.assertEqual(diagnostico["contagem"]["FALHA_NAO_RETENTAVEL"], 2)
    @override_settings(SEFAZ_DIRETA_SVC_ENABLED=True)
    def test_nfe_marcada_em_svc_usa_endpoint_separado_da_svc_rs(self):
        chamadas = []

        def transporte(**kwargs):
            chamadas.append(kwargs)
            return resposta_autorizada()

        documento = objeto_fiscal()
        documento.tipo_documento = "NFE"
        documento.chave_acesso = CHAVE
        documento.contingencia_iniciada_em = object()
        documento.contingencia_justificativa = "Indisponibilidade do autorizador normal"

        SefazDiretaAdapter(transport=transporte).transmitir(
            documento=documento,
            xml=XML_NFE,
            idempotency_key="svc-rs-1",
            ambiente="HOMOLOGACAO",
        )

        self.assertEqual(
            chamadas[0]["endpoint"],
            "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        )

    @override_settings(SEFAZ_DIRETA_SVC_ENABLED=False)
    def test_nfe_marcada_em_svc_falha_fechada_quando_flag_desligada(self):
        documento = objeto_fiscal()
        documento.tipo_documento = "NFE"
        documento.chave_acesso = CHAVE
        documento.contingencia_iniciada_em = object()
        documento.contingencia_justificativa = "Indisponibilidade do autorizador normal"

        with self.assertRaisesMessage(
            SefazDiretaError, "contingência SVC permanece desligada"
        ):
            SefazDiretaAdapter(transport=lambda **kwargs: self.fail()).transmitir(
                documento=documento,
                xml=XML_NFE,
                idempotency_key="svc-rs-off",
                ambiente="HOMOLOGACAO",
            )
    def test_producao_permanece_bloqueada(self):
        adapter = SefazDiretaAdapter(transport=lambda **kwargs: b"")
        with self.assertRaisesMessage(
            SefazDiretaError, "Produção da SEFAZ direta permanece bloqueada"
        ):
            adapter.transmitir(
                documento=objeto_fiscal(),
                xml=XML_NFE,
                idempotency_key="prod-1",
                ambiente="PRODUCAO",
            )

    @override_settings(SEFAZ_DIRETA_NETWORK_ENABLED=False)
    def test_rede_permanece_bloqueada_por_padrao(self):
        adapter = SefazDiretaAdapter(transport=lambda **kwargs: self.fail())
        with self.assertRaisesMessage(
            SefazDiretaError, "Rede da SEFAZ direta está bloqueada"
        ):
            adapter.transmitir(
                documento=objeto_fiscal(),
                xml=XML_NFE,
                idempotency_key="off-1",
                ambiente="HOMOLOGACAO",
            )

    @override_settings(
        SEFAZ_DIRETA_ENDPOINTS={
            "GO": {
                "HOMOLOGACAO": {
                    "autorizacao": "https://exemplo.invalid/nfe"
                }
            }
        }
    )
    def test_endpoint_nao_oficial_e_rejeitado(self):
        adapter = SefazDiretaAdapter(transport=lambda **kwargs: self.fail())
        with self.assertRaisesMessage(SefazDiretaError, "host oficial"):
            adapter.transmitir(
                documento=objeto_fiscal(),
                xml=XML_NFE,
                idempotency_key="host-1",
                ambiente="HOMOLOGACAO",
            )

    @override_settings(SEFAZ_DIRETA_NETWORK_ENABLED=False)
    def test_diagnostico_explica_que_adaptador_esta_dormente(self):
        resultado = SefazDiretaAdapter().diagnosticar()
        self.assertFalse(resultado["pronto"])
        self.assertFalse(resultado["rede_habilitada"])
        self.assertIn("dormente", resultado["erro"].lower())