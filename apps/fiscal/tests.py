import hashlib
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone as django_timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento, ItemVenda, PagamentoVenda, StatusVenda, TipoDocumentoConsumidor, Venda

from .models import (
    AmbienteFiscal,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    NaturezaOperacao,
    SerieFiscal,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
)
from .certificados import abrir_certificado_a1, salvar_certificado_a1
from .assinaturas import assinar_xml_documento, verificar_assinatura_xml
from .validacoes import diagnosticar_schemas_fiscais, validar_xml_schema
from .fila import diagnostico_fila_fiscal, processar_fila_fiscal
from .services import (_codigo_pagamento, ativar_contingencia_offline, cancelar_documento, preparar_documento_venda, transmitir_documento_sefaz, transmitir_documento_simulado)


def _certificado_teste(nome="certificado-teste.pfx", senha="123456", dias_validade=365):
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assunto = emissor = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Mercado Teste"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Mercado Teste A1"),
        ]
    )
    agora = datetime.now(timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(assunto)
        .issuer_name(emissor)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=1))
        .not_valid_after(agora + timedelta(days=dias_validade))
        .sign(chave, hashes.SHA256())
    )
    conteudo = pkcs12.serialize_key_and_certificates(
        name=b"mercado-teste",
        key=chave,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode("utf-8")),
    )
    return SimpleUploadedFile(nome, conteudo, content_type="application/x-pkcs12")


class FakeSefazAdapter:
    assina_xml = True
    valida_schema = True
    last_request = None

    def transmitir(self, **kwargs):
        type(self).last_request = kwargs
        return {
            "status": "AUTORIZADO",
            "chave_acesso": kwargs["documento"].chave_acesso,
            "protocolo": "135260000000001",
            "mensagem": "Autorizado o uso da NF-e.",
        }


class FakeSefazRejectedAdapter:
    assina_xml = True
    valida_schema = True

    def transmitir(self, **kwargs):
        return {"status": "REJEITADO", "mensagem": "Rejeicao: cadastro do emitente invalido."}


class FakeUnsignedSefazAdapter:
    valida_schema = True

    def transmitir(self, **kwargs):
        return {"status": "PENDENTE", "mensagem": "Lote recebido."}


class FakeFailingSefazAdapter:
    assina_xml = True
    valida_schema = True

    def transmitir(self, **kwargs):
        raise RuntimeError("SEFAZ temporariamente indisponivel")


class FakeWrongKeySefazAdapter:
    assina_xml = True
    valida_schema = True

    def transmitir(self, **kwargs):
        return {
            "status": "AUTORIZADO",
            "chave_acesso": "35" * 22,
            "protocolo": "135260000000002",
            "mensagem": "Autorizado o uso da NF-e.",
        }


class FakeLocalSchemaAdapter:
    assina_xml = True
    valida_schema = False

    def transmitir(self, **kwargs):
        return {"status": "PENDENTE", "mensagem": "Lote recebido e aguardando processamento."}


XSD_NFE_MINIMO = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="http://www.portalfiscal.inf.br/nfe"
           xmlns="http://www.portalfiscal.inf.br/nfe"
           elementFormDefault="qualified">
  <xs:element name="NFe">
    <xs:complexType>
      <xs:sequence>
        <xs:any minOccurs="1" maxOccurs="unbounded" processContents="skip"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

class CodigoPagamentoFiscalTests(TestCase):
    def test_vales_possuem_codigos_fiscais_proprios(self):
        self.assertEqual(_codigo_pagamento("VALE_ALIMENTACAO"), "10")
        self.assertEqual(_codigo_pagamento("VALE_REFEICAO"), "11")
        self.assertEqual(_codigo_pagamento("DEBITO"), "04")

class FiscalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(razao_social="Mercado Teste", nome_fantasia="Mercado", cnpj="44.444.444/0001-44")
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz",
            cnpj=self.empresa.cnpj,
            municipio="Sao Paulo",
            uf="SP",
            codigo_municipio_ibge="3550308",
        )
        self.caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.user, valor_inicial=Decimal("50.00"))
        self.venda = Venda.objects.create(
            filial=self.filial,
            caixa=self.caixa,
            usuario=self.user,
            total_bruto=Decimal("82.70"),
            total_liquido=Decimal("82.70"),
            status=StatusVenda.FINALIZADA,
        )
        self.categoria = Categoria.objects.create(nome="Mercearia")
        self.produto = Produto.objects.create(
            codigo_barras="7891234567001",
            nome="Arroz Branco 5kg",
            categoria=self.categoria,
            preco_custo=Decimal("15.00"),
            preco_venda=Decimal("82.70"),
            ncm="10063021",
            origem_mercadoria="0",
            cst_icms="00",
            aliquota_icms=Decimal("18.00"),
        )
        ItemVenda.objects.create(
            venda=self.venda,
            produto=self.produto,
            quantidade=Decimal("1.000"),
            preco_unitario_venda=Decimal("82.70"),
            total=Decimal("82.70"),
            custo_unitario_no_momento=Decimal("15.00"),
        )
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        PagamentoVenda.objects.create(venda=self.venda, forma_pagamento=forma, valor=Decimal("82.70"))
        self.configuracao = ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            inscricao_estadual="123456789",
            csc_id="1",
            csc_token="token-homologacao",
            url_qrcode_nfce="https://nfce-homologacao.example.com/qrcode",
            url_consulta_nfce="https://nfce-homologacao.example.com/consulta",
            regime_tributario="Regime normal",
        )
        salvar_certificado_a1(self.configuracao, _certificado_teste(), "123456")
        SerieFiscal.objects.create(filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE, serie=1, proximo_numero=100)
        NaturezaOperacao.objects.create(descricao="Venda ao consumidor", cfop="5102", tipo_documento=TipoDocumentoFiscal.NFCE)

    def test_tela_fiscal_abre_com_parametros(self):
        response = self.client.get("/fiscal/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fiscal")
        self.assertContains(response, "Vendas aguardando NFC-e")
        self.assertContains(response, f"#{self.venda.id}")
        self.assertContains(response, "Venda ao consumidor")
        self.assertContains(response, "Homologacao")
        self.assertContains(response, "Produção fiscal")
        self.assertContains(response, "Situacao fiscal")
        self.assertContains(response, "Pronta")
        self.assertContains(response, "Valido ate")
        self.assertContains(response, "Produtos fiscais")
        self.assertContains(response, "Pendências automáticas")
        self.assertContains(response, "Prontidão fiscal")
        self.assertContains(response, "Prontidão por filial")
        self.assertContains(response, "Diagnóstico JSON")
        self.assertContains(response, "fiscal_transmission_queue_v1")

    def test_diagnostico_json_fiscal_resume_prontidao_por_filial(self):
        response = self.client.get("/fiscal/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["resumo"]["filiais"], 1)
        self.assertEqual(payload["resumo"]["filiais_prontas"], 0)
        self.assertEqual(payload["resumo"]["vendas_pendentes"], 1)
        self.assertEqual(payload["filiais"][0]["serie_nfce"], 1)
        self.assertIn("venda(s) aguardando NFC-e", " ".join(payload["filiais"][0]["pendencias"]))
        self.assertEqual(payload["contrato"], "fiscal_readiness_v1")
        self.assertEqual(payload["producao"]["contrato"], "fiscal_production_readiness_v1")
        self.assertEqual(payload["producao"]["filiais_em_producao"], 0)
        self.assertFalse(payload["producao"]["transmissao_real_disponivel"])
        self.assertTrue(payload["producao"]["homologacao_simulada_disponivel"])
        self.assertEqual(payload["fila_transmissao"]["contrato"], "fiscal_transmission_queue_v1")
        self.assertFalse(payload["fila_transmissao"]["habilitada"])


    def test_diagnostico_json_fiscal_alerta_producao_sem_adaptador_sefaz(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])

        response = self.client.get("/fiscal/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["producao"]["filiais_em_producao"], 1)
        self.assertFalse(payload["producao"]["sefaz_adapter_configurado"])
        self.assertFalse(payload["producao"]["transmissao_real_disponivel"])
        self.assertIn("adaptador SEFAZ oficial", " ".join(payload["producao"]["alertas"]))

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter")
    def test_diagnostico_json_fiscal_marca_producao_pronta_com_adaptador(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])

        response = self.client.get("/fiscal/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["producao"]["sefaz_adapter_configurado"])
        self.assertTrue(payload["producao"]["sefaz_adapter_carregavel"])
        self.assertTrue(payload["producao"]["sefaz_adapter_assina_xml"])
        self.assertTrue(payload["producao"]["sefaz_adapter_valida_schema"])
        self.assertTrue(payload["producao"]["transmissao_real_disponivel"])
        self.assertEqual(payload["producao"]["alertas"], [])

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeUnsignedSefazAdapter")
    def test_diagnostico_producao_aceita_assinatura_local_a1(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])

        payload = self.client.get("/fiscal/diagnostico.json").json()

        self.assertFalse(payload["producao"]["sefaz_adapter_assina_xml"])
        self.assertTrue(payload["producao"]["assinatura_local_pronta"])
        self.assertTrue(payload["producao"]["assinatura_xml_disponivel"])
        self.assertTrue(payload["producao"]["transmissao_real_disponivel"])
        self.assertEqual(payload["producao"]["alertas"], [])
    @override_settings(FISCAL_SEFAZ_ADAPTER="integracao.inexistente.Adapter")
    def test_diagnostico_rejeita_adaptador_sefaz_inexistente(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])

        payload = self.client.get("/fiscal/diagnostico.json").json()

        self.assertTrue(payload["producao"]["sefaz_adapter_configurado"])
        self.assertFalse(payload["producao"]["sefaz_adapter_carregavel"])
        self.assertFalse(payload["producao"]["sefaz_adapter_assina_xml"])
        self.assertFalse(payload["producao"]["sefaz_adapter_valida_schema"])
        self.assertFalse(payload["producao"]["transmissao_real_disponivel"])
        self.assertIn("não pôde ser carregado", " ".join(payload["producao"]["alertas"]))
    def test_contingencia_json_exporta_documentos_prontos_com_xml_e_auditoria(self):
        documento = preparar_documento_venda(self.venda, self.user)

        response = self.client.get("/fiscal/contingencia.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["contrato"], "fiscal_contingencia_v1")
        self.assertEqual(payload["status"], StatusDocumentoFiscal.PRONTO)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["documentos"][0]["id"], documento.id)
        self.assertEqual(payload["documentos"][0]["origem"], {"tipo": "venda", "id": self.venda.id})
        self.assertIn("<NFe", payload["documentos"][0]["xml"])
        self.assertIn("Nao substitui assinatura", payload["observacao"])
        self.assertTrue(LogAuditoria.objects.filter(modulo="fiscal", acao="EXPORTA_CONTINGENCIA_FISCAL").exists())

    def test_tela_produtos_fiscais_mostra_pendencias_e_prontos(self):
        Produto.objects.create(
            codigo_barras="7890000000001",
            nome="Produto sem fiscal",
            categoria=self.categoria,
            preco_custo=Decimal("1.00"),
            preco_venda=Decimal("2.00"),
        )

        response = self.client.get("/fiscal/produtos/")
        response_todos = self.client.get("/fiscal/produtos/?filtro=todos")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produtos fiscais")
        self.assertContains(response, "Produto sem fiscal")
        self.assertContains(response, "NCM com 8 digitos")
        self.assertContains(response, "CST ICMS com 2 digitos")
        self.assertContains(response_todos, "Arroz Branco 5kg")
        self.assertContains(response_todos, "Pronto")

    def test_preparar_documento_venda_numera_e_audita(self):
        documento = preparar_documento_venda(self.venda, self.user)

        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.numero, 100)
        self.assertEqual(documento.valor_total, Decimal("82.70"))
        self.assertEqual(documento.natureza_operacao.descricao, "Venda ao consumidor")
        self.assertIn("<NFe", documento.xml_conteudo)
        self.assertIn("<cUF>35</cUF>", documento.xml_conteudo)
        self.assertIn("<cMunFG>3550308</cMunFG>", documento.xml_conteudo)
        self.assertIn("<mod>65</mod>", documento.xml_conteudo)
        self.assertEqual(len(documento.chave_acesso), 44)
        self.assertTrue(documento.chave_acesso.isdigit())
        self.assertIn(f'Id="NFe{documento.chave_acesso}"', documento.xml_conteudo)
        self.assertIn(f"<cDV>{documento.chave_acesso[-1]}</cDV>", documento.xml_conteudo)
        self.assertEqual(documento.chave_acesso[34], "1")
        self.assertNotIn("NFeLOCAL", documento.xml_conteudo)
        self.assertIn("<tpEmis>1</tpEmis>", documento.xml_conteudo)
        self.assertNotIn("<dhCont>", documento.xml_conteudo)
        self.assertNotIn("<xJust>", documento.xml_conteudo)
        self.assertIn("<xProd>Arroz Branco 5kg</xProd>", documento.xml_conteudo)
        self.assertIsNotNone(documento.xml_gerado_em)
        self.assertTrue(LogAuditoria.objects.filter(modulo="fiscal", acao="PREPARA_DOCUMENTO").exists())
        self.assertEqual(SerieFiscal.objects.get(filial=self.filial).proximo_numero, 101)

    def test_preparar_nfce_inclui_cpf_do_consumidor_quando_solicitado(self):
        self.venda.documento_consumidor_tipo = TipoDocumentoConsumidor.CPF
        self.venda.documento_consumidor = "12345678909"
        self.venda.save(update_fields=["documento_consumidor_tipo", "documento_consumidor"])

        documento = preparar_documento_venda(self.venda, self.user)

        self.assertIn("<dest>", documento.xml_conteudo)
        self.assertIn("<CPF>12345678909</CPF>", documento.xml_conteudo)
        self.assertIn("<indIEDest>9</indIEDest>", documento.xml_conteudo)

    def test_preparar_nfce_recusa_cnpj_e_preserva_numero_da_serie(self):
        self.venda.documento_consumidor_tipo = TipoDocumentoConsumidor.CNPJ
        self.venda.documento_consumidor = "12345678000190"
        self.venda.save(update_fields=["documento_consumidor_tipo", "documento_consumidor"])

        with self.assertRaisesMessage(ValidationError, "NF-e modelo 55"):
            preparar_documento_venda(self.venda, self.user)

        self.assertFalse(DocumentoFiscal.objects.exists())
        self.assertEqual(SerieFiscal.objects.get(filial=self.filial).proximo_numero, 100)

    def test_nao_prepara_documento_duplicado_para_mesma_venda(self):
        preparar_documento_venda(self.venda, self.user)

        with self.assertRaisesMessage(Exception, "ja possui documento fiscal"):
            preparar_documento_venda(self.venda, self.user)

        self.assertEqual(DocumentoFiscal.objects.filter(venda=self.venda).count(), 1)

    def test_bloqueia_nfce_quando_produto_esta_sem_dados_tributarios(self):
        self.produto.ncm = ""
        self.produto.origem_mercadoria = ""
        self.produto.cst_icms = ""
        self.produto.aliquota_icms = None
        self.produto.save(update_fields=["ncm", "origem_mercadoria", "cst_icms", "aliquota_icms"])

        with self.assertRaises(ValidationError) as contexto:
            preparar_documento_venda(self.venda, self.user)

        mensagem = " ".join(contexto.exception.messages)
        self.assertIn("NCM com 8 digitos", mensagem)
        self.assertIn("origem da mercadoria", mensagem)
        self.assertIn("CST ICMS", mensagem)
        self.assertIn("aliquota de ICMS", mensagem)
        self.assertFalse(DocumentoFiscal.objects.exists())
        self.assertEqual(SerieFiscal.objects.get(filial=self.filial).proximo_numero, 100)

        response = self.client.get("/fiscal/")
        self.assertContains(response, "4 pendencias")
        self.assertContains(response, "Corrija as pendencias fiscais antes de preparar")

    def test_tela_fiscal_exibe_tentativa_automatica_auditada(self):
        self.produto.ncm = ""
        self.produto.save(update_fields=["ncm"])
        LogAuditoria.objects.create(
            usuario=self.user,
            modulo="fiscal",
            acao="PREPARA_DOCUMENTO_PENDENTE",
            descricao=f"Venda {self.venda.id} finalizada sem NFC-e preparada automaticamente: Produto sem NCM.",
            objeto_tipo="Venda",
            objeto_id=str(self.venda.id),
        )

        response = self.client.get("/fiscal/")

        self.assertContains(response, "Pendências automáticas")
        self.assertContains(response, "Tentativa automatica em")
        self.assertContains(response, "1 pendencia")

    def test_cancelar_documento_pronto(self):
        documento = preparar_documento_venda(self.venda, self.user)

        cancelar_documento(documento, self.user, "Venda cancelada antes da transmissao")
        documento.refresh_from_db()

        self.assertEqual(documento.status, StatusDocumentoFiscal.CANCELADO)
        self.assertIn("Venda cancelada", documento.motivo_cancelamento)
        self.assertTrue(LogAuditoria.objects.filter(modulo="fiscal", acao="CANCELA_DOCUMENTO").exists())

    def test_rota_preparar_venda(self):
        response = self.client.post(f"/fiscal/vendas/{self.venda.pk}/preparar/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(DocumentoFiscal.objects.filter(venda=self.venda, status=StatusDocumentoFiscal.PRONTO).exists())

    @override_settings(FISCAL_AUTO_TRANSMIT_ENABLED=False)
    def test_fila_fiscal_desligada_nao_transmite_documento(self):
        documento = preparar_documento_venda(self.venda, self.user)

        resumo = processar_fila_fiscal()

        documento.refresh_from_db()
        self.assertEqual(resumo["processados"], 0)
        self.assertIn("desabilitada", resumo["motivo"])
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.tentativas_transmissao, 0)

    @override_settings(FISCAL_AUTO_TRANSMIT_ENABLED=True, FISCAL_SEFAZ_ADAPTER="")
    def test_fila_fiscal_so_simula_homologacao_quando_solicitado(self):
        documento = preparar_documento_venda(self.venda, self.user)

        ignorado = processar_fila_fiscal()
        documento.refresh_from_db()

        self.assertEqual(ignorado["processados"], 0)
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.tentativas_transmissao, 0)

        simulado = processar_fila_fiscal(simular_homologacao=True)
        documento.refresh_from_db()

        self.assertEqual(simulado["emitidos"], 1)
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)
        self.assertEqual(documento.tentativas_transmissao, 1)

    @override_settings(
        FISCAL_AUTO_TRANSMIT_ENABLED=True,
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter",
    )
    def test_fila_fiscal_transmite_producao_com_lease(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)

        resumo = processar_fila_fiscal()

        documento.refresh_from_db()
        self.assertEqual(resumo["emitidos"], 1)
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)
        self.assertEqual(documento.tentativas_transmissao, 1)
        self.assertIsNone(documento.transmissao_reservada_em)
        self.assertIsNone(documento.proxima_tentativa_em)

    @override_settings(
        FISCAL_AUTO_TRANSMIT_ENABLED=True,
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter",
    )
    def test_fila_fiscal_ignora_documento_com_lease_ativo(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)
        documento.transmissao_reservada_em = django_timezone.now()
        documento.save(update_fields=["transmissao_reservada_em"])

        resumo = processar_fila_fiscal()

        documento.refresh_from_db()
        self.assertEqual(resumo["processados"], 0)
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.tentativas_transmissao, 0)

    @override_settings(
        FISCAL_AUTO_TRANSMIT_ENABLED=True,
        FISCAL_AUTO_TRANSMIT_RETRY_BASE_SECONDS=60,
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeFailingSefazAdapter",
    )
    def test_fila_fiscal_reagenda_falha_e_libera_lease(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)
        inicio = django_timezone.now()

        resumo = processar_fila_fiscal()

        documento.refresh_from_db()
        self.assertEqual(resumo["reagendados"], 1)
        self.assertEqual(len(resumo["erros"]), 1)
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.tentativas_transmissao, 1)
        self.assertIsNone(documento.transmissao_reservada_em)
        self.assertGreaterEqual(documento.proxima_tentativa_em, inicio + timedelta(seconds=60))
        diagnostico = diagnostico_fila_fiscal()
        self.assertEqual(diagnostico["contrato"], "fiscal_transmission_queue_v1")
        self.assertTrue(diagnostico["habilitada"])

    def test_reprocessamento_manual_regenera_xml_reinicia_fila_e_audita(self):
        documento = preparar_documento_venda(self.venda, self.user)
        documento.status = StatusDocumentoFiscal.REJEITADO
        documento.tentativas_transmissao = 8
        documento.proxima_tentativa_em = django_timezone.now() + timedelta(hours=2)
        documento.transmissao_reservada_em = django_timezone.now()
        documento.xml_assinado_em = django_timezone.now()
        documento.certificado_serial_assinatura = "SERIAL-ANTERIOR"
        documento.mensagem_retorno = "Rejeicao fiscal de teste"
        documento.save(
            update_fields=[
                "status",
                "tentativas_transmissao",
                "proxima_tentativa_em",
                "transmissao_reservada_em",
                "xml_assinado_em",
                "certificado_serial_assinatura",
                "mensagem_retorno",
            ]
        )
        gerado_antes = documento.xml_gerado_em
        detalhe_antes = self.client.get(f"/fiscal/documentos/{documento.pk}/")
        self.assertContains(detalhe_antes, "Reprocessamento fiscal controlado")
        self.assertContains(detalhe_antes, "Recolocar na fila")

        resposta = self.client.post(
            f"/fiscal/documentos/{documento.pk}/reagendar/",
            {"motivo": "Cadastro tributario do produto corrigido."},
        )

        documento.refresh_from_db()
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.tentativas_transmissao, 0)
        self.assertIsNone(documento.transmissao_reservada_em)
        self.assertIsNone(documento.xml_assinado_em)
        self.assertEqual(documento.certificado_serial_assinatura, "")
        self.assertLessEqual(documento.proxima_tentativa_em, django_timezone.now())
        self.assertGreaterEqual(documento.xml_gerado_em, gerado_antes)
        auditoria = LogAuditoria.objects.get(acao="REAGENDA_TRANSMISSAO_FISCAL")
        self.assertIn("tentativas anteriores: 8", auditoria.descricao)
        self.assertIn("Cadastro tributario", auditoria.descricao)
        detalhe_depois = self.client.get(f"/fiscal/documentos/{documento.pk}/")
        self.assertNotContains(detalhe_depois, "Reprocessamento fiscal controlado")

    def test_reprocessamento_manual_recusa_documento_ja_emitido(self):
        documento = preparar_documento_venda(self.venda, self.user)
        documento.status = StatusDocumentoFiscal.EMITIDO
        documento.protocolo = "PROTOCOLO-AUTORIZADO"
        documento.save(update_fields=["status", "protocolo"])

        resposta = self.client.post(
            f"/fiscal/documentos/{documento.pk}/reagendar/",
            {"motivo": "Tentativa indevida de reabrir documento."},
        )

        documento.refresh_from_db()
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)
        self.assertEqual(documento.protocolo, "PROTOCOLO-AUTORIZADO")
        self.assertFalse(LogAuditoria.objects.filter(acao="REAGENDA_TRANSMISSAO_FISCAL").exists())

    def test_contingencia_offline_exige_autorizacao_da_filial(self):
        documento = preparar_documento_venda(self.venda, self.user)

        with self.assertRaisesMessage(ValidationError, "nao esta autorizada"):
            ativar_contingencia_offline(
                documento, self.user, "Indisponibilidade de comunicacao com a SEFAZ."
            )

        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertFalse(documento.contingencia_iniciada_em)

    def test_contingencia_offline_gera_xml_prazo_auditoria_e_fila(self):
        self.configuracao.permite_contingencia_offline = True
        self.configuracao.save(update_fields=["permite_contingencia_offline"])
        documento = preparar_documento_venda(self.venda, self.user)
        chave_normal = documento.chave_acesso
        justificativa = "Indisponibilidade de comunicacao com a SEFAZ."
        inicio = django_timezone.now()

        ativado = ativar_contingencia_offline(documento, self.user, justificativa)

        self.assertEqual(ativado.status, StatusDocumentoFiscal.CONTINGENCIA)
        self.assertNotEqual(ativado.chave_acesso, chave_normal)
        self.assertEqual(ativado.chave_acesso[34], "9")
        self.assertIn(f'Id="NFe{ativado.chave_acesso}"', ativado.xml_conteudo)
        self.assertEqual(ativado.contingencia_justificativa, justificativa)
        self.assertFalse(ativado.protocolo)
        self.assertGreaterEqual(ativado.transmissao_limite_em, inicio + timedelta(hours=24))
        self.assertLess(ativado.transmissao_limite_em, inicio + timedelta(hours=24, seconds=5))
        self.assertIn("<tpEmis>9</tpEmis>", ativado.xml_conteudo)
        self.assertIn("<dhCont>", ativado.xml_conteudo)
        self.assertIn(f"<xJust>{justificativa}</xJust>", ativado.xml_conteudo)
        self.assertTrue(LogAuditoria.objects.filter(modulo="fiscal", acao="ATIVA_CONTINGENCIA_OFFLINE").exists())

        detalhe = self.client.get(f"/fiscal/documentos/{ativado.pk}/")
        fila = self.client.get("/fiscal/contingencia.json", {"status": StatusDocumentoFiscal.CONTINGENCIA})
        diagnostico = self.client.get("/fiscal/diagnostico.json").json()
        payload = fila.json()

        self.assertContains(detalhe, "Documento sem autorizacao da SEFAZ")
        self.assertContains(detalhe, justificativa)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(diagnostico["resumo"]["documentos_em_contingencia"], 1)
        self.assertEqual(diagnostico["resumo"]["contingencias_com_prazo_vencido"], 0)
        self.assertEqual(payload["documentos"][0]["contingencia"]["justificativa"], justificativa)
        self.assertIsNotNone(payload["documentos"][0]["contingencia"]["transmissao_limite_em"])

    def test_contingencia_offline_regulariza_em_homologacao(self):
        self.configuracao.permite_contingencia_offline = True
        self.configuracao.save(update_fields=["permite_contingencia_offline"])
        documento = preparar_documento_venda(self.venda, self.user)
        ativar_contingencia_offline(
            documento, self.user, "Falha temporaria de acesso ao autorizador da SEFAZ."
        )

        transmitido = transmitir_documento_simulado(documento, self.user)

        self.assertEqual(transmitido.status, StatusDocumentoFiscal.EMITIDO)
        self.assertEqual(transmitido.tentativas_transmissao, 1)
        self.assertIsNotNone(transmitido.ultima_tentativa_em)
        self.assertTrue(transmitido.protocolo.startswith("HOM"))
        self.assertIn("<tpEmis>9</tpEmis>", transmitido.xml_conteudo)

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter")
    def test_adaptador_sefaz_autoriza_com_idempotencia_e_auditoria(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)
        FakeSefazAdapter.last_request = None

        transmitido = transmitir_documento_sefaz(documento, self.user)

        self.assertEqual(transmitido.status, StatusDocumentoFiscal.EMITIDO)
        self.assertEqual(transmitido.chave_acesso, documento.chave_acesso)
        self.assertEqual(transmitido.protocolo, "135260000000001")
        self.assertEqual(transmitido.tentativas_transmissao, 1)
        self.assertTrue(FakeSefazAdapter.last_request["idempotency_key"].startswith(f"fiscal:{documento.pk}:"))
        self.assertEqual(FakeSefazAdapter.last_request["ambiente"], AmbienteFiscal.PRODUCAO)
        self.assertNotIn("token-homologacao", str(FakeSefazAdapter.last_request))
        self.assertTrue(LogAuditoria.objects.filter(acao="TRANSMISSAO_SEFAZ_AUTORIZADA").exists())

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazRejectedAdapter")
    def test_adaptador_sefaz_preserva_rejeicao_e_motivo(self):
        documento = preparar_documento_venda(self.venda, self.user)

        transmitido = transmitir_documento_sefaz(documento, self.user)

        self.assertEqual(transmitido.status, StatusDocumentoFiscal.REJEITADO)
        self.assertIn("cadastro do emitente", transmitido.mensagem_retorno)
        self.assertFalse(transmitido.protocolo)
        self.assertTrue(LogAuditoria.objects.filter(acao="TRANSMISSAO_SEFAZ_REJEITADA").exists())

    @override_settings(FISCAL_SEFAZ_ADAPTER="")
    def test_transmissao_real_sem_adaptador_falha_sem_autorizar(self):
        documento = preparar_documento_venda(self.venda, self.user)

        with self.assertRaisesMessage(ValidationError, "Falha na comunicacao"):
            transmitir_documento_sefaz(documento, self.user)

        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.tentativas_transmissao, 1)
        self.assertFalse(documento.protocolo)
        self.assertTrue(LogAuditoria.objects.filter(acao="TRANSMISSAO_SEFAZ_FALHA").exists())

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeUnsignedSefazAdapter",
        FISCAL_LOCAL_XML_SIGNATURE_ENABLED=False,
    )
    def test_pre_transmissao_bloqueia_xml_sem_assinatura(self):
        documento = preparar_documento_venda(self.venda, self.user)

        with self.assertRaisesMessage(ValidationError, "nao esta assinado"):
            transmitir_documento_sefaz(documento, self.user)

        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertFalse(documento.protocolo)
        self.assertTrue(LogAuditoria.objects.filter(acao="TRANSMISSAO_SEFAZ_FALHA").exists())

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeUnsignedSefazAdapter")
    def test_transmissao_assina_xml_localmente_quando_adaptador_nao_assina(self):
        documento = preparar_documento_venda(self.venda, self.user)

        transmitido = transmitir_documento_sefaz(documento, self.user)

        transmitido.refresh_from_db()
        verificacao = verificar_assinatura_xml(transmitido.xml_conteudo)
        self.assertEqual(transmitido.status, StatusDocumentoFiscal.PRONTO)
        self.assertIsNotNone(transmitido.xml_assinado_em)
        self.assertTrue(transmitido.certificado_serial_assinatura)
        self.assertEqual(verificacao["certificado_serial"], transmitido.certificado_serial_assinatura)
        self.assertEqual(verificacao["referencia"], f"#NFe{transmitido.chave_acesso}")
        self.assertIn("Signature", transmitido.xml_conteudo)
        self.assertNotIn("PRIVATE KEY", transmitido.xml_conteudo)

    def test_verificacao_rejeita_xml_alterado_depois_da_assinatura(self):
        documento = preparar_documento_venda(self.venda, self.user)
        assinar_xml_documento(documento)
        xml_adulterado = documento.xml_conteudo.replace("Arroz Branco 5kg", "Arroz adulterado", 1)

        with self.assertRaisesMessage(ValidationError, "Digest da assinatura fiscal invalido"):
            verificar_assinatura_xml(xml_adulterado)

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeWrongKeySefazAdapter")
    def test_pre_transmissao_rejeita_autorizacao_de_outra_chave(self):
        documento = preparar_documento_venda(self.venda, self.user)

        with self.assertRaisesMessage(ValidationError, "chave diferente"):
            transmitir_documento_sefaz(documento, self.user)

        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.chave_acesso[34], "1")
        self.assertFalse(documento.protocolo)
    def test_schema_local_valido_libera_pre_transmissao(self):
        documento = preparar_documento_venda(self.venda, self.user)
        with tempfile.TemporaryDirectory() as diretorio:
            arquivo = Path(diretorio) / "nfe_v4.00.xsd"
            arquivo.write_text(XSD_NFE_MINIMO, encoding="utf-8")
            sha256 = hashlib.sha256(arquivo.read_bytes()).hexdigest()
            with override_settings(
                FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeLocalSchemaAdapter",
                FISCAL_SCHEMA_DIR=diretorio,
                FISCAL_NFE_SCHEMA_FILE=arquivo.name,
                FISCAL_SCHEMA_SHA256=sha256,
            ):
                diagnostico = diagnosticar_schemas_fiscais()
                validacao = validar_xml_schema(documento)
                transmitido = transmitir_documento_sefaz(documento, self.user)

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(validacao["sha256"], sha256)
        self.assertEqual(transmitido.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(transmitido.tentativas_transmissao, 1)
        self.assertIn("aguardando processamento", transmitido.mensagem_retorno)
        self.assertTrue(LogAuditoria.objects.filter(acao="TRANSMISSAO_SEFAZ_PENDENTE").exists())

    def test_schema_local_com_hash_divergente_bloqueia_prontidao(self):
        with tempfile.TemporaryDirectory() as diretorio:
            arquivo = Path(diretorio) / "nfe_v4.00.xsd"
            arquivo.write_text(XSD_NFE_MINIMO, encoding="utf-8")
            with override_settings(
                FISCAL_SCHEMA_DIR=diretorio,
                FISCAL_NFE_SCHEMA_FILE=arquivo.name,
                FISCAL_SCHEMA_SHA256="0" * 64,
            ):
                diagnostico = diagnosticar_schemas_fiscais()

        self.assertTrue(diagnostico["configurado"])
        self.assertFalse(diagnostico["pronto"])
        self.assertIn("SHA-256", diagnostico["erro"])
    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter")
    def test_detalhe_de_producao_exibe_transmissao_sefaz(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)

        response = self.client.get(f"/fiscal/documentos/{documento.pk}/")

        self.assertContains(response, "Transmitir SEFAZ")
        self.assertContains(response, f"/fiscal/documentos/{documento.pk}/transmitir-sefaz/")


    def test_transmissao_simulada_em_homologacao_emite_com_protocolo(self):
        documento = preparar_documento_venda(self.venda, self.user)

        transmitido = transmitir_documento_simulado(documento, self.user)

        self.assertEqual(transmitido.status, StatusDocumentoFiscal.EMITIDO)
        self.assertTrue(transmitido.chave_acesso)
        self.assertTrue(transmitido.protocolo.startswith("HOM"))
        self.assertIn("Transmissao simulada em homologacao", transmitido.mensagem_retorno)
        self.assertTrue(LogAuditoria.objects.filter(modulo="fiscal", acao="TRANSMISSAO_SIMULADA").exists())

    def test_rota_transmissao_simulada_aparece_e_emite_documento(self):
        documento = preparar_documento_venda(self.venda, self.user)

        detalhe = self.client.get(f"/fiscal/documentos/{documento.pk}/")
        response = self.client.post(f"/fiscal/documentos/{documento.pk}/transmitir-simulado/", follow=True)

        self.assertContains(detalhe, "Transmitir homologacao")
        self.assertRedirects(response, f"/fiscal/documentos/{documento.pk}/")
        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)
        self.assertContains(response, "Emitido", status_code=200)

    def test_transmissao_simulada_bloqueia_producao(self):
        documento = preparar_documento_venda(self.venda, self.user)
        documento.ambiente = AmbienteFiscal.PRODUCAO
        documento.save(update_fields=["ambiente"])

        with self.assertRaisesMessage(ValidationError, "somente em homologacao"):
            transmitir_documento_simulado(documento, self.user)

        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)

    def test_detalhe_e_impressao_mostram_espelho_do_documento(self):
        documento = preparar_documento_venda(self.venda, self.user)

        response = self.client.get(f"/fiscal/documentos/{documento.pk}/")
        response_print = self.client.get(f"/fiscal/documentos/{documento.pk}/imprimir/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Espelho de conferencia")
        self.assertContains(response, "Arroz Branco 5kg")
        self.assertContains(response, "Dinheiro")
        self.assertContains(response, "Cliente avulso")
        self.assertContains(response, "Baixar XML")
        self.assertEqual(response_print.status_code, 200)
        self.assertContains(response_print, "window.print")

        response_xml = self.client.get(f"/fiscal/documentos/{documento.pk}/xml/")
        self.assertEqual(response_xml.status_code, 200)
        self.assertEqual(response_xml["Content-Type"], "application/xml; charset=utf-8")
        self.assertIn(b"<NFe", response_xml.content)
        self.assertIn(b"<tPag>01</tPag>", response_xml.content)
        self.assertIn(b"<infNFeSupl>", response_xml.content)
        self.assertIn(b"<qrCode>https://nfce-homologacao.example.com/qrcode?p=", response_xml.content)
        self.assertIn(b"|3|2", response_xml.content)
        self.assertIn(b"<urlChave>https://nfce-homologacao.example.com/consulta</urlChave>", response_xml.content)
        self.assertContains(response_print, "DOCUMENTO NAO AUTORIZADO")
        self.assertNotContains(response_print, "data:image/png;base64,")

    def test_danfe_nfce_emitida_exibe_qrcode_oficial(self):
        documento = preparar_documento_venda(self.venda, self.user)
        transmitir_documento_simulado(documento, self.user)
        self.configuracao.url_qrcode_nfce = ""
        self.configuracao.save(update_fields=["url_qrcode_nfce", "atualizado_em"])

        response = self.client.get(f"/fiscal/documentos/{documento.pk}/imprimir/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DOCUMENTO AUXILIAR DA NOTA FISCAL")
        self.assertContains(response, "data:image/png;base64,")
        self.assertContains(response, documento.chave_acesso)
        self.assertContains(response, "R$ 82,70")
        self.assertNotContains(response, "DOCUMENTO NAO AUTORIZADO")

    def test_upload_certificado_a1_criptografa_e_le_validade(self):
        nova_filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Loja 2",
            cnpj="55.555.555/0001-55",
            municipio="Sao Paulo",
            uf="SP",
            codigo_municipio_ibge="3550308",
        )
        arquivo = _certificado_teste(nome="loja2.p12", senha="segredo", dias_validade=90)

        response = self.client.post(
            "/fiscal/configuracoes/nova/",
            {
                "filial": nova_filial.pk,
                "ambiente": AmbienteFiscal.HOMOLOGACAO,
                "regime_tributario": "Regime normal",
                "inscricao_estadual": "987654321",
                "csc_id": "2",
                "csc_token": "token",
                "certificado_nome": "",
                "certificado_validade": "",
                "certificado_senha": "segredo",
                "ativo": "on",
                "certificado_arquivo": arquivo,
            },
        )

        self.assertEqual(response.status_code, 302)
        configuracao = ConfiguracaoFiscal.objects.get(filial=nova_filial)
        self.assertTrue(configuracao.certificado_configurado)
        self.assertEqual(configuracao.certificado_nome, "loja2.p12")
        self.assertGreaterEqual(configuracao.certificado_validade, django_timezone.localdate())
        conteudo, senha = abrir_certificado_a1(configuracao)
        self.assertEqual(senha, "segredo")
        self.assertIsInstance(conteudo, bytes)
        self.assertNotIn(b"segredo", bytes(configuracao.certificado_senha_criptografada))

    def test_form_configuracao_fiscal_exibe_secoes_operacionais(self):
        response = self.client.get(f"/fiscal/configuracoes/{self.configuracao.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Loja e ambiente")
        self.assertContains(response, "NFC-e")
        self.assertContains(response, "Certificado digital")
        self.assertContains(response, "Certificado A1")
        self.assertContains(response, "O arquivo sera armazenado criptografado")

    def test_forms_serie_e_natureza_exibem_secoes_operacionais(self):
        serie = SerieFiscal.objects.get(filial=self.filial)
        natureza = NaturezaOperacao.objects.get(descricao="Venda ao consumidor")

        response_serie = self.client.get(f"/fiscal/series/{serie.pk}/editar/")
        response_natureza = self.client.get(f"/fiscal/naturezas/{natureza.pk}/editar/")

        self.assertEqual(response_serie.status_code, 200)
        self.assertContains(response_serie, "Numeracao fiscal")
        self.assertContains(response_serie, "O numero e reservado")
        self.assertEqual(response_natureza.status_code, 200)
        self.assertContains(response_natureza, "Operacao fiscal")
        self.assertContains(response_natureza, "Use CFOP com 4 digitos")

    def test_edicao_de_serie_e_natureza_fiscal_gera_auditoria(self):
        serie = SerieFiscal.objects.get(filial=self.filial)
        natureza = NaturezaOperacao.objects.get(descricao="Venda ao consumidor")

        response_serie = self.client.post(
            f"/fiscal/series/{serie.pk}/editar/",
            {
                "filial": self.filial.pk,
                "tipo_documento": TipoDocumentoFiscal.NFCE,
                "serie": 2,
                "proximo_numero": 150,
                "ativo": "on",
            },
            REMOTE_ADDR="127.0.0.10",
        )
        response_natureza = self.client.post(
            f"/fiscal/naturezas/{natureza.pk}/editar/",
            {
                "descricao": "Venda presencial",
                "cfop": "5102",
                "tipo_documento": TipoDocumentoFiscal.NFCE,
                "movimenta_estoque": "on",
                "ativo": "on",
            },
            REMOTE_ADDR="127.0.0.11",
        )

        self.assertRedirects(response_serie, "/fiscal/")
        self.assertRedirects(response_natureza, "/fiscal/")
        log_serie = LogAuditoria.objects.get(acao="ATUALIZA_SERIE_FISCAL", objeto_id=str(serie.pk))
        log_natureza = LogAuditoria.objects.get(
            acao="ATUALIZA_NATUREZA_OPERACAO",
            objeto_id=str(natureza.pk),
        )
        self.assertEqual(log_serie.usuario, self.user)
        self.assertEqual(log_serie.ip, "127.0.0.10")
        self.assertIn("Serie fiscal 2", log_serie.descricao)
        self.assertEqual(log_natureza.usuario, self.user)
        self.assertEqual(log_natureza.ip, "127.0.0.11")
        self.assertIn("Venda presencial", log_natureza.descricao)

    def test_bloqueia_nfce_sem_certificado_a1(self):
        self.configuracao.certificado_a1_criptografado = None
        self.configuracao.certificado_senha_criptografada = None
        self.configuracao.certificado_validade = None
        self.configuracao.save(
            update_fields=["certificado_a1_criptografado", "certificado_senha_criptografada", "certificado_validade"]
        )

        with self.assertRaises(ValidationError) as contexto:
            preparar_documento_venda(self.venda, self.user)

        self.assertIn("Envie o certificado A1", " ".join(contexto.exception.messages))

    def test_bloqueia_nfce_sem_uf_e_codigo_ibge_da_filial(self):
        self.filial.uf = ""
        self.filial.codigo_municipio_ibge = ""
        self.filial.save(update_fields=["uf", "codigo_municipio_ibge"])

        with self.assertRaises(ValidationError) as contexto:
            preparar_documento_venda(self.venda, self.user)

        mensagem = " ".join(contexto.exception.messages)
        self.assertIn("UF da filial", mensagem)
        self.assertIn("codigo IBGE", mensagem)


class FiscalMultiempresaTests(TestCase):
    def setUp(self):
        self.empresa_a = Empresa.objects.create(
            razao_social="Empresa Fiscal A",
            nome_fantasia="Fiscal A",
            cnpj="11.111.111/0001-11",
        )
        self.empresa_b = Empresa.objects.create(
            razao_social="Empresa Fiscal B",
            nome_fantasia="Fiscal B",
            cnpj="22.222.222/0001-22",
        )
        self.filial_a = Filial.objects.create(empresa=self.empresa_a, nome="Matriz A", cnpj=self.empresa_a.cnpj)
        self.filial_a_sem_config = Filial.objects.create(
            empresa=self.empresa_a,
            nome="Loja A2",
            cnpj="11.111.111/0002-00",
        )
        self.filial_b = Filial.objects.create(empresa=self.empresa_b, nome="Matriz B", cnpj=self.empresa_b.cnpj)
        self.usuario_a = get_user_model().objects.create_user("fiscal_a", password="123")
        PerfilUsuario.objects.create(
            usuario=self.usuario_a,
            filial=self.filial_a,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.usuario_b = get_user_model().objects.create_user("fiscal_b", password="123")
        PerfilUsuario.objects.create(
            usuario=self.usuario_b,
            filial=self.filial_b,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.config_a = ConfiguracaoFiscal.objects.create(filial=self.filial_a, inscricao_estadual="IE-A")
        self.config_b = ConfiguracaoFiscal.objects.create(filial=self.filial_b, inscricao_estadual="IE-B")
        self.serie_a = SerieFiscal.objects.create(filial=self.filial_a, serie=1)
        self.serie_b = SerieFiscal.objects.create(filial=self.filial_b, serie=2)
        self.documento_a = DocumentoFiscal.objects.create(
            filial=self.filial_a,
            usuario=self.usuario_a,
            status=StatusDocumentoFiscal.PRONTO,
            numero=101,
            xml_conteudo="<NFe>EMPRESA-A</NFe>",
        )
        self.documento_b = DocumentoFiscal.objects.create(
            filial=self.filial_b,
            usuario=self.usuario_b,
            status=StatusDocumentoFiscal.PRONTO,
            numero=202,
            xml_conteudo="<NFe>EMPRESA-B</NFe>",
        )
        self.caixa_b = Caixa.objects.create(
            filial=self.filial_b,
            usuario_abertura=self.usuario_b,
            valor_inicial=Decimal("0.00"),
        )
        self.venda_b = Venda.objects.create(
            filial=self.filial_b,
            caixa=self.caixa_b,
            usuario=self.usuario_b,
            total_bruto=Decimal("10.00"),
            total_liquido=Decimal("10.00"),
            status=StatusVenda.FINALIZADA,
        )
        self.client.force_login(self.usuario_a)

    def test_listagem_diagnostico_e_contingencia_mostram_apenas_empresa_do_usuario(self):
        pagina = self.client.get("/fiscal/")
        diagnostico = self.client.get("/fiscal/diagnostico.json").json()
        contingencia = self.client.get("/fiscal/contingencia.json").json()

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Matriz A")
        self.assertNotContains(pagina, "Matriz B")
        self.assertEqual(diagnostico["resumo"]["filiais"], 2)
        self.assertEqual({item["id"] for item in diagnostico["filiais"]}, {self.filial_a.id, self.filial_a_sem_config.id})
        self.assertEqual(diagnostico["fila_transmissao"]["pendentes"], 1)
        self.assertEqual(contingencia["total"], 1)
        self.assertEqual(contingencia["documentos"][0]["id"], self.documento_a.id)

    def test_documento_de_outra_empresa_nao_pode_ser_consultado_exportado_ou_alterado(self):
        rotas_get = [
            f"/fiscal/documentos/{self.documento_b.pk}/",
            f"/fiscal/documentos/{self.documento_b.pk}/imprimir/",
            f"/fiscal/documentos/{self.documento_b.pk}/xml/",
        ]
        rotas_post = [
            f"/fiscal/documentos/{self.documento_b.pk}/reagendar/",
            f"/fiscal/documentos/{self.documento_b.pk}/transmitir-simulado/",
            f"/fiscal/documentos/{self.documento_b.pk}/transmitir-sefaz/",
            f"/fiscal/documentos/{self.documento_b.pk}/contingencia/",
            f"/fiscal/documentos/{self.documento_b.pk}/cancelar/",
        ]

        for rota in rotas_get:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 404)
        for rota in rotas_post:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.post(rota).status_code, 404)
        self.documento_b.refresh_from_db()
        self.assertEqual(self.documento_b.status, StatusDocumentoFiscal.PRONTO)

    def test_configuracao_serie_e_venda_de_outra_empresa_nao_podem_ser_acessadas(self):
        self.assertEqual(self.client.get(f"/fiscal/configuracoes/{self.config_b.pk}/editar/").status_code, 404)
        self.assertEqual(self.client.get(f"/fiscal/series/{self.serie_b.pk}/editar/").status_code, 404)
        self.assertEqual(self.client.post(f"/fiscal/vendas/{self.venda_b.pk}/preparar/").status_code, 404)
        self.assertFalse(DocumentoFiscal.objects.filter(venda=self.venda_b).exists())

    def test_formularios_rejeitam_filial_de_outra_empresa(self):
        resposta_config = self.client.post(
            "/fiscal/configuracoes/nova/",
            {
                "filial": self.filial_b.pk,
                "ambiente": AmbienteFiscal.HOMOLOGACAO,
                "regime_tributario": "Simples Nacional",
                "inscricao_estadual": "FORJADA",
                "ativo": "on",
            },
        )
        resposta_serie = self.client.post(
            "/fiscal/series/nova/",
            {
                "filial": self.filial_b.pk,
                "tipo_documento": TipoDocumentoFiscal.NFCE,
                "serie": 99,
                "proximo_numero": 1,
                "ativo": "on",
            },
        )

        self.assertEqual(resposta_config.status_code, 200)
        self.assertIn("filial", resposta_config.context["form"].errors)
        self.assertEqual(resposta_serie.status_code, 200)
        self.assertIn("filial", resposta_serie.context["form"].errors)
        self.assertFalse(ConfiguracaoFiscal.objects.filter(filial=self.filial_a_sem_config).exists())
        self.assertFalse(SerieFiscal.objects.filter(filial=self.filial_b, serie=99).exists())

    def test_superadmin_mantem_visao_global(self):
        superadmin = get_user_model().objects.create_superuser("fiscal_master", "master@example.com", "123")
        self.client.force_login(superadmin)

        diagnostico = self.client.get("/fiscal/diagnostico.json").json()
        detalhe = self.client.get(f"/fiscal/documentos/{self.documento_b.pk}/")

        self.assertEqual(diagnostico["resumo"]["filiais"], 3)
        self.assertEqual(detalhe.status_code, 200)
