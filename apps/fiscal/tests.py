import hashlib
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from io import StringIO
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

from .forms import ConfiguracaoFiscalForm, HomologacaoFiscalForm
from .perfis_uf import endpoints_nfce_uf
from .models import (
    AmbienteFiscal,
    CodigoRegimeTributario,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    HomologacaoFiscal,
    InutilizacaoNumeracaoFiscal,
    ModoTransicaoIbsCbs,
    NaturezaOperacao,
    SerieFiscal,
    StatusDocumentoFiscal,
    StatusHomologacaoFiscal,
    StatusInutilizacaoFiscal,
    TipoDocumentoFiscal,
)
from .certificados import abrir_certificado_a1, salvar_certificado_a1
from .assinaturas import assinar_xml_documento, verificar_assinatura_xml
from .validacoes import diagnosticar_schemas_fiscais, validar_xml_schema
from .fila import diagnostico_fila_fiscal, processar_fila_fiscal, retomar_consultas_documento_fiscal
from .services import (
    _codigo_pagamento,
    ativar_contingencia_offline,
    cancelar_documento,
    consultar_situacao_documento,
    pendencias_produto_fiscal,
    preparar_documento_venda,
    solicitar_inutilizacao_numeracao,
    transmitir_documento_sefaz,
    transmitir_documento_simulado,
)


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
    last_cancel_request = None
    last_inutilization_request = None

    def transmitir(self, **kwargs):
        type(self).last_request = kwargs
        return {
            "status": "AUTORIZADO",
            "chave_acesso": kwargs["documento"].chave_acesso,
            "protocolo": "135260000000001",
            "mensagem": "Autorizado o uso da NF-e.",
        }

    def cancelar(self, **kwargs):
        type(self).last_cancel_request = kwargs
        return {
            "status": "CANCELADO",
            "protocolo": "135260000000099",
            "mensagem": "Cancelamento homologado.",
        }

    def inutilizar(self, **kwargs):
        type(self).last_inutilization_request = kwargs
        return {
            "status": "INUTILIZADA",
            "protocolo": "135260000000199",
            "mensagem": "Inutilização homologada.",
        }

    def consultar(self, **kwargs):
        type(self).last_query_request = kwargs
        return {
            "status": "AUTORIZADO",
            "protocolo": "135260000000299",
            "mensagem": "Autorizado o uso da NF-e.",
        }


class FakeSefazRejectedAdapter:
    assina_xml = True
    valida_schema = True

    def transmitir(self, **kwargs):
        return {"status": "REJEITADO", "mensagem": "Rejeicao: cadastro do emitente inválido."}


class FakeUnsignedSefazAdapter:
    valida_schema = True

    def transmitir(self, **kwargs):
        return {"status": "PENDENTE", "mensagem": "Lote recebido."}


class FakeSefazQueryCanceledAdapter(FakeUnsignedSefazAdapter):
    def consultar(self, **kwargs):
        return {
            "status": "CANCELADO",
            "protocolo": "135260000000300",
            "protocolo_cancelamento": "135260000000301",
            "mensagem": "Cancelamento homologado.",
        }


class FakeSefazQueryNotFoundAdapter(FakeUnsignedSefazAdapter):
    def consultar(self, **kwargs):
        return {
            "status": "NAO_LOCALIZADO",
            "mensagem": "Documento não localizado na base da SEFAZ.",
        }


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


class FakePendingThenAuthorizedAdapter:
    assina_xml = True
    valida_schema = True
    transmission_calls = 0
    query_calls = 0

    def transmitir(self, **kwargs):
        type(self).transmission_calls += 1
        return {
            "status": "PENDENTE",
            "mensagem": "Lote recebido e aguardando processamento.",
        }

    def consultar(self, **kwargs):
        type(self).query_calls += 1
        return {
            "status": "AUTORIZADO",
            "protocolo": "135260000000399",
            "mensagem": "Autorizado o uso da NF-e.",
        }


class FakePendingQueryAdapter(FakePendingThenAuthorizedAdapter):
    def consultar(self, **kwargs):
        type(self).query_calls += 1
        return {
            "status": "PENDENTE",
            "mensagem": "Documento ainda em processamento na SEFAZ.",
        }


class FakePendingWithoutQueryAdapter:
    assina_xml = True
    valida_schema = True
    transmission_calls = 0

    def transmitir(self, **kwargs):
        type(self).transmission_calls += 1
        return {
            "status": "PENDENTE",
            "mensagem": "Lote recebido e aguardando processamento.",
        }


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
            cst_pis="01",
            aliquota_pis=Decimal("1.6500"),
            cst_cofins="01",
            aliquota_cofins=Decimal("7.6000"),
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
            crt=CodigoRegimeTributario.REGIME_NORMAL,
        )
        salvar_certificado_a1(self.configuracao, _certificado_teste(), "123456")
        SerieFiscal.objects.create(filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE, serie=1, proximo_numero=100)
        NaturezaOperacao.objects.create(empresa=self.filial.empresa, descricao="Venda ao consumidor", cfop="5102", tipo_documento=TipoDocumentoFiscal.NFCE)

    def test_emissao_rejeita_natureza_de_operacao_de_outra_empresa(self):
        empresa_externa = Empresa.objects.create(
            razao_social="Fiscal Externa Ltda",
            nome_fantasia="Fiscal Externa",
            cnpj="55.555.555/0001-55",
        )
        natureza_externa = NaturezaOperacao.objects.create(
            empresa=empresa_externa,
            descricao="Venda externa",
            cfop="5102",
            tipo_documento=TipoDocumentoFiscal.NFCE,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "nao pertence a empresa da venda",
        ):
            preparar_documento_venda(
                self.venda,
                self.user,
                natureza_operacao=natureza_externa,
            )

        self.assertFalse(self.venda.documentos_fiscais.exists())

    def test_promocao_de_natureza_padrao_define_emissao_e_auditoria(self):
        natureza_anterior = NaturezaOperacao.objects.get(descricao="Venda ao consumidor")
        natureza_nova = NaturezaOperacao.objects.create(
            empresa=self.filial.empresa,
            descricao="Venda presencial promocional",
            cfop="5101",
            tipo_documento=TipoDocumentoFiscal.NFCE,
        )
        self.assertTrue(natureza_anterior.padrao)
        self.assertFalse(natureza_nova.padrao)
        pagina = self.client.get("/fiscal/")
        self.assertContains(pagina, "Tornar padrão")
        self.assertContains(pagina, "Padrão")

        resposta = self.client.post(
            f"/fiscal/naturezas/{natureza_nova.pk}/definir-padrao/",
            REMOTE_ADDR="127.0.0.21",
        )

        self.assertRedirects(resposta, "/fiscal/")
        natureza_anterior.refresh_from_db()
        natureza_nova.refresh_from_db()
        self.assertFalse(natureza_anterior.padrao)
        self.assertTrue(natureza_nova.padrao)
        documento = preparar_documento_venda(self.venda, self.user)
        self.assertEqual(documento.natureza_operacao, natureza_nova)
        log = LogAuditoria.objects.get(
            acao="DEFINE_NATUREZA_PADRAO",
            objeto_id=str(natureza_nova.pk),
        )
        self.assertEqual(log.usuario, self.user)
        self.assertEqual(log.ip, "127.0.0.21")

    def test_formulario_natureza_expoe_politica_segura_de_ipi(self):
        natureza = NaturezaOperacao.objects.get(descricao="Venda ao consumidor")

        response = self.client.get(f"/fiscal/naturezas/{natureza.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tratamento do IPI tributado")
        self.assertContains(response, "IPI tributado já incluído no preço")
        self.assertContains(response, "IPI compõe a base do ICMS")
        self.assertContains(response, "IPI compõe a base de PIS/COFINS")

    def test_tela_fiscal_abre_com_parametros(self):
        response = self.client.get("/fiscal/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fiscal")
        self.assertContains(response, "Vendas aguardando NFC-e")
        self.assertContains(response, f"#{self.venda.id}")
        self.assertContains(response, "Venda ao consumidor")
        self.assertContains(response, "Homologacao")
        self.assertContains(response, "Produção fiscal")
        self.assertContains(response, "Situação fiscal")
        self.assertContains(response, "Pronta")
        self.assertContains(response, "Válido até")
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
        self.assertEqual(
            payload["capacidade_tributaria"]["contrato"],
            "fiscal_tax_capability_v1",
        )
        self.assertEqual(
            payload["capacidade_tributaria"]["regime_normal"]["cst_suportados"],
            ["00", "20", "40", "41", "50"],
        )
        self.assertEqual(
            payload["capacidade_tributaria"]["simples_nacional"]["csosn_suportados"],
            ["102", "103", "300", "400"],
        )
        self.assertTrue(payload["capacidade_tributaria"]["ibs_cbs"]["cadastro_produto_disponivel"])
        self.assertFalse(payload["capacidade_tributaria"]["ibs_cbs"]["emissao_xml_habilitada"])
        self.assertEqual(payload["producao"]["filiais_em_producao"], 0)
        self.assertFalse(payload["producao"]["transmissao_real_disponivel"])
        self.assertTrue(payload["producao"]["homologacao_simulada_disponivel"])
        self.assertEqual(payload["fila_transmissao"]["contrato"], "fiscal_transmission_queue_v1")
        self.assertFalse(payload["fila_transmissao"]["habilitada"])


    def test_diagnostico_fiscal_conta_pendencias_apos_quinhentos_produtos(self):
        Produto.objects.bulk_create(
            [
                Produto(
                    codigo_barras=f"CATALOGO-{indice:04d}",
                    nome=f"Produto pendente {indice}",
                    categoria=self.categoria,
                    preco_custo=Decimal("1.00"),
                    preco_venda=Decimal("2.00"),
                )
                for indice in range(501)
            ]
        )

        payload = self.client.get("/fiscal/diagnostico.json").json()

        self.assertEqual(payload["resumo"]["produtos_pendentes"], 501)

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter")
    def test_comando_valida_contrato_completo_do_adaptador(self):
        saida = StringIO()

        call_command("validar_adaptador_sefaz", "--exigir-eventos", "--estrito", stdout=saida)

        resultado = __import__("json").loads(saida.getvalue())
        self.assertEqual(resultado["contrato"], "sefaz_adapter_validation_v1")
        self.assertTrue(resultado["adaptador"]["carregavel"])
        self.assertTrue(resultado["adaptador"]["requisitos"]["consulta"])
        self.assertTrue(resultado["pronto"])
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
        self.assertTrue(payload["producao"]["sefaz_adapter_consulta_documento"])
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
        self.assertIn("Não substitui assinatura", payload["observacao"])
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

    def test_exportacao_csv_fiscal_respeita_filtro_e_gera_modelo_reimportavel(self):
        produto_pendente = Produto.objects.create(
            codigo_barras="7890000000991",
            nome="Produto fiscal pendente",
            categoria=self.categoria,
            preco_custo=Decimal("1.00"),
            preco_venda=Decimal("2.50"),
        )

        response = self.client.get(
            "/fiscal/produtos/exportar.csv",
            {"filtro": "pendentes", "q": "fiscal pendente"},
        )
        conteudo = b"".join(response.streaming_content).decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("produtos-fiscais-pendentes-", response["Content-Disposition"])
        self.assertIn("codigo_barras;codigo_interno;nome;categoria;preco_venda", conteudo)
        self.assertIn("classificacao_tributaria_ibs_cbs;_modo_importacao", conteudo)
        self.assertIn(";fiscal\r\n", conteudo)
        self.assertIn(produto_pendente.codigo_barras, conteudo)
        self.assertIn("2,50", conteudo)
        self.assertNotIn(self.produto.codigo_barras, conteudo)
        self.assertTrue(
            LogAuditoria.objects.filter(
                modulo="fiscal", acao="EXPORTA_PRODUTOS_FISCAIS_CSV"
            ).exists()
        )

    def test_filtro_prontos_aplica_pis_cofins_e_ipi_como_validacao_da_linha(self):
        self.produto.cst_pis = ""
        self.produto.save(update_fields=["cst_pis"])

        response_pendentes = self.client.get("/fiscal/produtos/?filtro=pendentes")
        response_prontos = self.client.get("/fiscal/produtos/?filtro=prontos")

        self.assertContains(response_pendentes, self.produto.nome)
        self.assertContains(response_pendentes, "CST PIS ausente ou ainda nao suportado")
        self.assertNotContains(response_prontos, self.produto.nome)

    def test_produto_cst40_aparece_pronto_e_exibe_matriz_de_capacidade(self):
        self.produto.cst_icms = "40"
        self.produto.aliquota_icms = Decimal("0.00")
        self.produto.save(update_fields=["cst_icms", "aliquota_icms"])

        response = self.client.get("/fiscal/produtos/?filtro=prontos")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Capacidade tributária do emissor local")
        self.assertContains(response, "CST 40")
        self.assertContains(response, "CSOSN 102")
        self.assertContains(response, self.produto.nome)
        self.assertContains(response, "Pronto")

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

    def test_xml_usa_crt_estruturado_para_regime_normal(self):
        documento = preparar_documento_venda(self.venda, self.user)

        self.assertIn("<CRT>3</CRT>", documento.xml_conteudo)
        self.assertIn("<ICMS00>", documento.xml_conteudo)
        self.assertNotIn("<ICMSSN102>", documento.xml_conteudo)

    def test_icms00_calcula_base_imposto_e_totais(self):
        documento = preparar_documento_venda(self.venda, self.user)

        self.assertIn("<vBC>82.70</vBC>", documento.xml_conteudo)
        self.assertIn("<pICMS>18.00</pICMS>", documento.xml_conteudo)
        self.assertIn("<vICMS>14.89</vICMS>", documento.xml_conteudo)

    def test_icms40_gera_csts_nao_tributados_sem_debito_na_nfce(self):
        for cst in ("40", "41", "50"):
            with self.subTest(cst=cst):
                self.produto.cst_icms = cst
                self.produto.aliquota_icms = Decimal("0.00")
                self.produto.reducao_base_icms = Decimal("0.00")
                self.produto.save(
                    update_fields=["cst_icms", "aliquota_icms", "reducao_base_icms"]
                )

                documento = preparar_documento_venda(self.venda, self.user)

                self.assertIn(
                    f"<ICMS40><orig>0</orig><CST>{cst}</CST></ICMS40>",
                    documento.xml_conteudo,
                )
                self.assertIn("<vBC>0.00</vBC>", documento.xml_conteudo)
                self.assertIn("<vICMS>0.00</vICMS>", documento.xml_conteudo)
                documento.delete()

    def test_pis_cofins_calculam_item_e_totais(self):
        documento = preparar_documento_venda(self.venda, self.user)

        self.assertIn("<PISAliq>", documento.xml_conteudo)
        self.assertIn("<pPIS>1.6500</pPIS>", documento.xml_conteudo)
        self.assertIn("<vPIS>1.36</vPIS>", documento.xml_conteudo)
        self.assertIn("<COFINSAliq>", documento.xml_conteudo)
        self.assertIn("<pCOFINS>7.6000</pCOFINS>", documento.xml_conteudo)
        self.assertIn("<vCOFINS>6.29</vCOFINS>", documento.xml_conteudo)

    def test_contribuicoes_nao_tributadas_e_ipi_opcional(self):
        self.produto.cst_pis = "06"
        self.produto.aliquota_pis = None
        self.produto.cst_cofins = "06"
        self.produto.aliquota_cofins = None
        self.produto.cst_ipi = "53"
        self.produto.codigo_enquadramento_ipi = "999"
        self.produto.save(
            update_fields=[
                "cst_pis",
                "aliquota_pis",
                "cst_cofins",
                "aliquota_cofins",
                "cst_ipi",
                "codigo_enquadramento_ipi",
            ]
        )

        documento = preparar_documento_venda(self.venda, self.user)

        self.assertIn("<PISNT><CST>06</CST></PISNT>", documento.xml_conteudo)
        self.assertIn("<COFINSNT><CST>06</CST></COFINSNT>", documento.xml_conteudo)
        self.assertIn("<IPI><cEnq>999</cEnq><IPINT><CST>53</CST></IPINT></IPI>", documento.xml_conteudo)
    def test_ipi_tributado_exige_politica_explicita_na_natureza(self):
        self.produto.cst_ipi = "50"
        self.produto.codigo_enquadramento_ipi = "999"
        self.produto.aliquota_ipi = Decimal("10.0000")
        self.produto.save(update_fields=["cst_ipi", "codigo_enquadramento_ipi", "aliquota_ipi"])

        with self.assertRaisesRegex(ValidationError, "IPI tributado esta incluido no preco"):
            preparar_documento_venda(self.venda, self.user)

        self.assertFalse(self.venda.documentos_fiscais.exists())

    def test_ipi_tributado_destaca_imposto_sem_aumentar_total_pago(self):
        natureza = NaturezaOperacao.objects.get(descricao="Venda ao consumidor")
        natureza.ipi_incluso_preco = True
        natureza.ipi_compoe_base_icms = False
        natureza.ipi_compoe_base_pis_cofins = False
        natureza.save(
            update_fields=[
                "ipi_incluso_preco",
                "ipi_compoe_base_icms",
                "ipi_compoe_base_pis_cofins",
            ]
        )
        self.produto.cst_ipi = "50"
        self.produto.codigo_enquadramento_ipi = "999"
        self.produto.aliquota_ipi = Decimal("10.0000")
        self.produto.save(update_fields=["cst_ipi", "codigo_enquadramento_ipi", "aliquota_ipi"])

        documento = preparar_documento_venda(self.venda, self.user)

        self.assertEqual(documento.valor_total, Decimal("82.70"))
        self.assertIn("<vProd>75.18</vProd>", documento.xml_conteudo)
        self.assertIn(
            "<IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>75.18</vBC>"
            "<pIPI>10.0000</pIPI><vIPI>7.52</vIPI></IPITrib></IPI>",
            documento.xml_conteudo,
        )
        self.assertIn("<vIPI>7.52</vIPI>", documento.xml_conteudo)
        self.assertIn("<vNF>82.70</vNF>", documento.xml_conteudo)
        self.assertIn("<vBC>75.18</vBC>", documento.xml_conteudo)

    def test_cst20_aplica_reducao_fcp_cbenef_e_totais_em_goias(self):
        self.filial.uf = "GO"
        self.filial.municipio = "Goiânia"
        self.filial.codigo_municipio_ibge = "5208707"
        self.filial.save(update_fields=["uf", "municipio", "codigo_municipio_ibge"])
        self.configuracao.url_qrcode_nfce = "https://nfewebhomolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"
        self.configuracao.url_consulta_nfce = "https://nfewebhomolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"
        self.configuracao.save(update_fields=["url_qrcode_nfce", "url_consulta_nfce", "atualizado_em"])
        self.produto.cst_icms = "20"
        self.produto.reducao_base_icms = Decimal("10.00")
        self.produto.aliquota_fcp = Decimal("2.00")
        self.produto.codigo_beneficio_fiscal = "GO821019"
        self.produto.save(
            update_fields=[
                "cst_icms",
                "reducao_base_icms",
                "aliquota_fcp",
                "codigo_beneficio_fiscal",
            ]
        )

        documento = preparar_documento_venda(self.venda, self.user)

        self.assertIn("<cBenef>GO821019</cBenef>", documento.xml_conteudo)
        self.assertIn("<ICMS20>", documento.xml_conteudo)
        self.assertIn("<pRedBC>10.00</pRedBC>", documento.xml_conteudo)
        self.assertIn("<vBC>74.43</vBC>", documento.xml_conteudo)
        self.assertIn("<vICMS>13.40</vICMS>", documento.xml_conteudo)
        self.assertIn("<vFCP>1.49</vFCP>", documento.xml_conteudo)

    def test_desconto_da_venda_e_rateado_na_base_e_no_xml(self):
        self.venda.desconto = Decimal("2.70")
        self.venda.total_liquido = Decimal("80.00")
        self.venda.save(update_fields=["desconto", "total_liquido"])
        pagamento = self.venda.pagamentos.get()
        pagamento.valor = Decimal("80.00")
        pagamento.save(update_fields=["valor"])

        documento = preparar_documento_venda(self.venda, self.user)

        self.assertIn("<vDesc>2.70</vDesc>", documento.xml_conteudo)
        self.assertIn("<vBC>80.00</vBC>", documento.xml_conteudo)
        self.assertIn("<vICMS>14.40</vICMS>", documento.xml_conteudo)
        self.assertIn("<vNF>80.00</vNF>", documento.xml_conteudo)
    def test_crt_simples_exige_csosn_e_gera_grupo_proprio(self):
        self.configuracao.crt = CodigoRegimeTributario.SIMPLES_NACIONAL
        self.configuracao.regime_tributario = "Simples Nacional"
        self.configuracao.save(update_fields=["crt", "regime_tributario", "atualizado_em"])
        self.produto.cst_icms = ""
        self.produto.csosn = "102"
        self.produto.save(update_fields=["cst_icms", "csosn"])

        documento = preparar_documento_venda(self.venda, self.user)

        self.assertIn("<CRT>1</CRT>", documento.xml_conteudo)
        self.assertIn("<ICMSSN102>", documento.xml_conteudo)
        self.assertNotIn("<ICMS00>", documento.xml_conteudo)

    def test_preparacao_bloqueia_cst_ainda_nao_suportado(self):
        self.produto.cst_icms = "60"
        self.produto.save(update_fields=["cst_icms"])

        with self.assertRaises(ValidationError) as contexto:
            preparar_documento_venda(self.venda, self.user)

        self.assertIn("CST ICMS 60 ainda nao e suportado", " ".join(contexto.exception.messages))

    def test_preparacao_bloqueia_csosn_ainda_nao_suportado(self):
        self.configuracao.crt = CodigoRegimeTributario.SIMPLES_NACIONAL
        self.configuracao.save(update_fields=["crt", "atualizado_em"])
        self.produto.csosn = "500"
        self.produto.save(update_fields=["csosn"])

        with self.assertRaises(ValidationError) as contexto:
            preparar_documento_venda(self.venda, self.user)

        self.assertIn("CSOSN 500 ainda nao e suportado", " ".join(contexto.exception.messages))
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
        self.assertContains(response, "Tentativa automática em")
        self.assertContains(response, "1 pendencia")

    def test_cancelar_documento_pronto(self):
        documento = preparar_documento_venda(self.venda, self.user)

        cancelar_documento(documento, self.user, "Venda cancelada antes da transmissao")
        documento.refresh_from_db()

        self.assertEqual(documento.status, StatusDocumentoFiscal.CANCELADO)
        self.assertIn("Venda cancelada", documento.motivo_cancelamento)
        self.assertTrue(LogAuditoria.objects.filter(modulo="fiscal", acao="CANCELA_DOCUMENTO").exists())

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter")
    def test_cancelar_documento_emitido_exige_autorizacao_sefaz(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)
        transmitir_documento_sefaz(documento, self.user)
        FakeSefazAdapter.last_cancel_request = None

        cancelado = cancelar_documento(
            documento,
            self.user,
            "Venda cancelada integralmente antes da saída da mercadoria.",
        )

        self.assertEqual(cancelado.status, StatusDocumentoFiscal.CANCELADO)
        self.assertEqual(cancelado.protocolo_cancelamento, "135260000000099")
        self.assertIsNotNone(cancelado.cancelamento_em)
        self.assertEqual(
            FakeSefazAdapter.last_cancel_request["protocolo_autorizacao"],
            "135260000000001",
        )
        self.assertEqual(
            FakeSefazAdapter.last_cancel_request["chave_acesso"],
            documento.chave_acesso,
        )
        self.assertTrue(
            FakeSefazAdapter.last_cancel_request["idempotency_key"].startswith(
                f"fiscal-cancelamento:{documento.pk}:"
            )
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CANCELAMENTO_SEFAZ_AUTORIZADO"
            ).exists()
        )

    def test_cancelamento_emitido_recusa_justificativa_curta(self):
        documento = preparar_documento_venda(self.venda, self.user)
        transmitir_documento_simulado(documento, self.user)

        with self.assertRaisesMessage(ValidationError, "entre 15 e 255"):
            cancelar_documento(documento, self.user, "Erro")

        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter")
    def test_cancelamento_emitido_sem_suporte_do_adaptador_preserva_emissao(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)
        transmitir_documento_sefaz(documento, self.user)

        with override_settings(
            FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeUnsignedSefazAdapter"
        ):
            with self.assertRaisesMessage(
                ValidationError,
                "não implementa cancelamento autorizado",
            ):
                cancelar_documento(
                    documento,
                    self.user,
                    "Cancelamento solicitado antes da saída da mercadoria.",
                )

        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)
        self.assertFalse(documento.protocolo_cancelamento)
        self.assertIn(
            "não implementa cancelamento",
            documento.mensagem_cancelamento,
        )
        self.assertTrue(
            LogAuditoria.objects.filter(acao="CANCELAMENTO_SEFAZ_FALHA").exists()
        )

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
        FISCAL_AUTO_TRANSMIT_MAX_ATTEMPTS=1,
        FISCAL_AUTO_TRANSMIT_RETRY_BASE_SECONDS=1,
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakePendingThenAuthorizedAdapter",
    )
    def test_fila_reconcilia_pendente_antes_de_retransmitir(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)
        FakePendingThenAuthorizedAdapter.transmission_calls = 0
        FakePendingThenAuthorizedAdapter.query_calls = 0

        primeira = processar_fila_fiscal()
        documento.refresh_from_db()
        self.assertEqual(primeira["reagendados"], 1)
        self.assertTrue(documento.aguardando_consulta_sefaz)
        self.assertEqual(documento.tentativas_transmissao, 1)
        self.assertEqual(documento.tentativas_consulta_sefaz, 0)
        self.assertEqual(FakePendingThenAuthorizedAdapter.transmission_calls, 1)
        self.assertEqual(FakePendingThenAuthorizedAdapter.query_calls, 0)

        documento.proxima_tentativa_em = django_timezone.now()
        documento.save(update_fields=["proxima_tentativa_em"])
        segunda = processar_fila_fiscal()
        documento.refresh_from_db()

        self.assertEqual(segunda["consultados"], 1)
        self.assertEqual(segunda["reconciliados"], 1)
        self.assertEqual(segunda["emitidos"], 1)
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)
        self.assertFalse(documento.aguardando_consulta_sefaz)
        self.assertEqual(documento.protocolo, "135260000000399")
        self.assertEqual(documento.tentativas_consulta_sefaz, 1)
        self.assertEqual(FakePendingThenAuthorizedAdapter.transmission_calls, 1)
        self.assertEqual(FakePendingThenAuthorizedAdapter.query_calls, 1)

    @override_settings(
        FISCAL_AUTO_TRANSMIT_ENABLED=True,
        FISCAL_AUTO_TRANSMIT_RETRY_BASE_SECONDS=1,
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakePendingQueryAdapter",
    )
    def test_fila_mantem_consulta_pendente_sem_retransmitir(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)
        FakePendingQueryAdapter.transmission_calls = 0
        FakePendingQueryAdapter.query_calls = 0

        processar_fila_fiscal()
        documento.refresh_from_db()
        documento.proxima_tentativa_em = django_timezone.now()
        documento.save(update_fields=["proxima_tentativa_em"])
        resumo = processar_fila_fiscal()
        documento.refresh_from_db()

        self.assertEqual(resumo["consultados"], 1)
        self.assertEqual(resumo["reagendados"], 1)
        self.assertTrue(documento.aguardando_consulta_sefaz)
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(FakePendingQueryAdapter.transmission_calls, 1)
        self.assertEqual(FakePendingQueryAdapter.query_calls, 1)

    @override_settings(
        FISCAL_AUTO_TRANSMIT_ENABLED=True,
        FISCAL_AUTO_QUERY_MAX_ATTEMPTS=1,
        FISCAL_AUTO_TRANSMIT_RETRY_BASE_SECONDS=1,
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakePendingQueryAdapter",
    )
    def test_fila_interrompe_consultas_automaticas_ao_esgotar_limite(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)
        FakePendingQueryAdapter.transmission_calls = 0
        FakePendingQueryAdapter.query_calls = 0

        processar_fila_fiscal()
        documento.refresh_from_db()
        documento.proxima_tentativa_em = django_timezone.now()
        documento.save(update_fields=["proxima_tentativa_em"])
        segunda = processar_fila_fiscal()
        documento.refresh_from_db()

        self.assertEqual(segunda["consultados"], 1)
        self.assertEqual(segunda["consultas_esgotadas"], 1)
        self.assertEqual(segunda["reagendados"], 0)
        self.assertEqual(documento.tentativas_consulta_sefaz, 1)
        self.assertTrue(documento.aguardando_consulta_sefaz)
        self.assertIsNone(documento.transmissao_reservada_em)
        self.assertIsNone(documento.proxima_tentativa_em)

        documento.proxima_tentativa_em = django_timezone.now()
        documento.save(update_fields=["proxima_tentativa_em"])
        terceira = processar_fila_fiscal()
        diagnostico = diagnostico_fila_fiscal()

        self.assertEqual(terceira["processados"], 0)
        self.assertEqual(FakePendingQueryAdapter.transmission_calls, 1)
        self.assertEqual(FakePendingQueryAdapter.query_calls, 1)
        self.assertEqual(diagnostico["aguardando_consulta_sefaz"], 1)
        self.assertEqual(diagnostico["consultas_esgotadas"], 1)
        self.assertEqual(diagnostico["elegiveis_producao"], 0)
        self.assertEqual(diagnostico["max_consultas"], 1)

        detalhe = self.client.get(f"/fiscal/documentos/{documento.pk}/")
        self.assertContains(detalhe, "Reconciliação automática pausada")
        self.assertContains(detalhe, "Retomar consultas automáticas")

        resposta = self.client.post(
            f"/fiscal/documentos/{documento.pk}/retomar-consultas-sefaz/",
            {"motivo": "Comunicação com a SEFAZ normalizada após análise técnica."},
        )
        documento.refresh_from_db()

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(documento.aguardando_consulta_sefaz)
        self.assertEqual(documento.tentativas_consulta_sefaz, 0)
        self.assertIsNone(documento.transmissao_reservada_em)
        self.assertLessEqual(documento.proxima_tentativa_em, django_timezone.now())
        self.assertTrue(LogAuditoria.objects.filter(acao="RETOMA_CONSULTAS_SEFAZ", objeto_id=str(documento.pk), usuario=self.user).exists())

    @override_settings(
        FISCAL_AUTO_QUERY_MAX_ATTEMPTS=1,
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakePendingQueryAdapter",
    )
    def test_retomada_consulta_exige_estado_esgotado_e_motivo(self):
        documento = preparar_documento_venda(self.venda, self.user)
        with self.assertRaisesMessage(ValidationError, "não está aguardando"):
            retomar_consultas_documento_fiscal(documento, self.user, "Análise técnica concluída com segurança.")

        documento.aguardando_consulta_sefaz = True
        documento.tentativas_consulta_sefaz = 1
        documento.save(update_fields=["aguardando_consulta_sefaz", "tentativas_consulta_sefaz"])
        with self.assertRaisesMessage(ValidationError, "motivo entre 10 e 255"):
            retomar_consultas_documento_fiscal(documento, self.user, "curto")

    @override_settings(
        FISCAL_AUTO_TRANSMIT_ENABLED=True,
        FISCAL_AUTO_TRANSMIT_RETRY_BASE_SECONDS=1,
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakePendingWithoutQueryAdapter",
    )
    def test_fila_sem_consulta_falha_fechada_sem_retransmitir(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente"])
        documento = preparar_documento_venda(self.venda, self.user)
        FakePendingWithoutQueryAdapter.transmission_calls = 0

        processar_fila_fiscal()
        documento.refresh_from_db()
        documento.proxima_tentativa_em = django_timezone.now()
        documento.save(update_fields=["proxima_tentativa_em"])
        resumo = processar_fila_fiscal()
        documento.refresh_from_db()

        self.assertEqual(resumo["consultados"], 0)
        self.assertEqual(resumo["reagendados"], 1)
        self.assertEqual(len(resumo["erros"]), 1)
        self.assertTrue(documento.aguardando_consulta_sefaz)
        self.assertEqual(FakePendingWithoutQueryAdapter.transmission_calls, 1)

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

    def test_estado_pendente_bloqueia_cancelamento_e_contingencia(self):
        self.configuracao.permite_contingencia_offline = True
        self.configuracao.save(update_fields=["permite_contingencia_offline"])
        documento = preparar_documento_venda(self.venda, self.user)
        documento.aguardando_consulta_sefaz = True
        documento.save(update_fields=["aguardando_consulta_sefaz"])

        with self.assertRaisesMessage(ValidationError, "Consulte a situação"):
            cancelar_documento(
                documento,
                self.user,
                "Cancelamento solicitado por falha operacional confirmada.",
            )
        with self.assertRaisesMessage(ValidationError, "Consulte a situação"):
            ativar_contingencia_offline(
                documento,
                self.user,
                "Falha temporária de comunicação com o autorizador.",
            )

        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)

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

        with self.assertRaisesMessage(ValidationError, "não está autorizada"):
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

        self.assertContains(detalhe, "Documento sem autorização da SEFAZ")
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

        with self.assertRaisesMessage(ValidationError, "não está assinado"):
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

        with self.assertRaisesMessage(ValidationError, "Digest da assinatura fiscal inválido"):
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
        self.assertTrue(transmitido.aguardando_consulta_sefaz)
        with self.assertRaisesMessage(ValidationError, "Consulte a situação"):
            transmitir_documento_sefaz(transmitido, self.user)
        transmitido.refresh_from_db()
        self.assertEqual(transmitido.tentativas_transmissao, 1)
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
        self.assertIn("Transmissao simulada em homologação", transmitido.mensagem_retorno)
        self.assertTrue(LogAuditoria.objects.filter(modulo="fiscal", acao="TRANSMISSAO_SIMULADA").exists())

    def test_rota_transmissao_simulada_aparece_e_emite_documento(self):
        documento = preparar_documento_venda(self.venda, self.user)

        detalhe = self.client.get(f"/fiscal/documentos/{documento.pk}/")
        response = self.client.post(f"/fiscal/documentos/{documento.pk}/transmitir-simulado/", follow=True)

        self.assertContains(detalhe, "Transmitir homologação")
        self.assertRedirects(response, f"/fiscal/documentos/{documento.pk}/")
        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)
        self.assertContains(response, "Emitido", status_code=200)

    def test_transmissao_simulada_bloqueia_producao(self):
        documento = preparar_documento_venda(self.venda, self.user)
        documento.ambiente = AmbienteFiscal.PRODUCAO
        documento.save(update_fields=["ambiente"])

        with self.assertRaisesMessage(ValidationError, "somente em homologação"):
            transmitir_documento_simulado(documento, self.user)

        documento.refresh_from_db()
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)

    def test_detalhe_e_impressao_mostram_espelho_do_documento(self):
        documento = preparar_documento_venda(self.venda, self.user)

        response = self.client.get(f"/fiscal/documentos/{documento.pk}/")
        response_print = self.client.get(f"/fiscal/documentos/{documento.pk}/imprimir/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Espelho de conferência")
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
                "crt": CodigoRegimeTributario.REGIME_NORMAL,
                "inscricao_estadual": "987654321",
                "csc_id": "2",
                "csc_token": "token",
                "certificado_nome": "",
                "certificado_validade": "",
                "certificado_senha": "segredo",
                "ativo": "on",
            "modo_transicao_ibs_cbs": ModoTransicaoIbsCbs.LEGADO,
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

    def _dados_formulario_fiscal_go(self, **overrides):
        dados = {
            "filial": self.filial.pk,
            "ambiente": AmbienteFiscal.HOMOLOGACAO,
            "regime_tributario": "Regime normal",
            "crt": CodigoRegimeTributario.REGIME_NORMAL,
            "inscricao_estadual": "123456789",
            "csc_id": "1",
            "csc_token": "token-homologacao",
            "url_qrcode_nfce": "",
            "url_consulta_nfce": "",
            "certificado_nome": self.configuracao.certificado_nome,
            "certificado_validade": self.configuracao.certificado_validade,
            "ativo": "on",
            "modo_transicao_ibs_cbs": ModoTransicaoIbsCbs.LEGADO,
        }
        dados.update(overrides)
        return dados

    def test_perfil_go_preenche_endpoints_oficiais_por_ambiente(self):
        self.filial.uf = "GO"
        self.filial.municipio = "Goiânia"
        self.filial.codigo_municipio_ibge = "5208707"
        self.filial.save(update_fields=["uf", "municipio", "codigo_municipio_ibge"])
        self.configuracao.url_qrcode_nfce = "https://nfewebhomolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"
        self.configuracao.url_consulta_nfce = "https://nfewebhomolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"
        self.configuracao.save(update_fields=["url_qrcode_nfce", "url_consulta_nfce", "atualizado_em"])

        form = ConfiguracaoFiscalForm(
            data=self._dados_formulario_fiscal_go(),
            instance=self.configuracao,
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        configuracao = form.save()
        esperado = endpoints_nfce_uf("GO", AmbienteFiscal.HOMOLOGACAO)
        self.assertEqual(configuracao.url_qrcode_nfce, esperado["qrcode"])
        self.assertEqual(configuracao.url_consulta_nfce, esperado["consulta"])
        self.assertEqual(form.perfil_fiscal["nome"], "Goiás")

        response = self.client.get(f"/fiscal/configuracoes/{configuracao.pk}/editar/")
        self.assertContains(response, "Perfil estadual detectado: Goiás")
        self.assertContains(response, "Informe Técnico 2025.003")

    def test_perfil_go_rejeita_endpoint_antigo_e_separa_producao(self):
        self.filial.uf = "GO"
        self.filial.save(update_fields=["uf"])
        form = ConfiguracaoFiscalForm(
            data=self._dados_formulario_fiscal_go(
                url_qrcode_nfce="http://homolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe",
                url_consulta_nfce="http://homolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe",
            ),
            instance=self.configuracao,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("url_qrcode_nfce", form.errors)
        self.assertIn("url_consulta_nfce", form.errors)
        self.assertIn("nfewebhomolog.sefaz.go.gov.br", form.errors["url_qrcode_nfce"][0])
        self.assertIn("nfeweb.sefaz.go.gov.br", endpoints_nfce_uf("GO", AmbienteFiscal.PRODUCAO)["qrcode"])

    def test_perfil_go_valida_cbenef_para_reducao_de_base(self):
        self.produto.reducao_base_icms = Decimal("10.00")
        self.produto.codigo_beneficio_fiscal = ""
        self.produto.save(update_fields=["reducao_base_icms", "codigo_beneficio_fiscal"])

        pendencias = pendencias_produto_fiscal(self.produto, ["Regime normal"], ["GO"])
        self.assertIn("cBenef obrigatório em Goiás para redução de base do ICMS", pendencias)

        self.produto.codigo_beneficio_fiscal = "GO-INVALIDO"
        self.produto.save(update_fields=["codigo_beneficio_fiscal"])
        pendencias = pendencias_produto_fiscal(self.produto, ["Regime normal"], ["GO"])
        self.assertIn("cBenef de Goiás no formato GO + 6 dígitos", pendencias)

        self.produto.codigo_beneficio_fiscal = "GO821019"
        self.produto.save(update_fields=["codigo_beneficio_fiscal"])
        pendencias = pendencias_produto_fiscal(self.produto, ["Regime normal"], ["GO"])
        self.assertFalse(any("cBenef" in pendencia for pendencia in pendencias))

    def test_preparacao_ibs_cbs_exige_codigos_no_produto_apos_vigencia(self):
        self.configuracao.modo_transicao_ibs_cbs = ModoTransicaoIbsCbs.PREPARACAO
        self.configuracao.ibs_cbs_vigencia_inicio = django_timezone.localdate()
        self.configuracao.ibs_cbs_versao_leiaute = "NT 2025.002"
        self.configuracao.save()

        pendencias = pendencias_produto_fiscal(
            self.produto,
            ["Regime normal"],
            ["SP"],
            exigir_ibs_cbs=self.configuracao.ibs_cbs_exigido_em(),
        )

        self.assertIn("CST IBS/CBS com 3 dígitos", pendencias)
        self.assertIn("cClassTrib IBS/CBS com 6 dígitos", pendencias)

        self.produto.cst_ibs_cbs = "000"
        self.produto.classificacao_tributaria_ibs_cbs = "000000"
        self.produto.save(update_fields=["cst_ibs_cbs", "classificacao_tributaria_ibs_cbs"])
        pendencias = pendencias_produto_fiscal(
            self.produto,
            ["Regime normal"],
            ["SP"],
            exigir_ibs_cbs=self.configuracao.ibs_cbs_exigido_em(),
        )
        self.assertFalse(any("IBS/CBS" in pendencia or "cClassTrib" in pendencia for pendencia in pendencias))

    def test_form_ibs_cbs_requer_vigencia_e_leiaute_na_preparacao(self):
        form = ConfiguracaoFiscalForm(
            data=self._dados_formulario_fiscal_go(
                modo_transicao_ibs_cbs=ModoTransicaoIbsCbs.PREPARACAO,
                ibs_cbs_vigencia_inicio="",
                ibs_cbs_versao_leiaute="",
            ),
            instance=self.configuracao,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("ibs_cbs_vigencia_inicio", form.errors)
        self.assertIn("ibs_cbs_versao_leiaute", form.errors)

    def test_form_bloqueia_emissao_ibs_cbs_sem_homologacao_xml(self):
        form = ConfiguracaoFiscalForm(
            data=self._dados_formulario_fiscal_go(
                modo_transicao_ibs_cbs=ModoTransicaoIbsCbs.EMISSAO_HOMOLOGADA,
                ibs_cbs_vigencia_inicio=django_timezone.localdate().isoformat(),
                ibs_cbs_versao_leiaute="NT 2025.002",
            ),
            instance=self.configuracao,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("modo_transicao_ibs_cbs", form.errors)
    def test_form_homologacao_exige_responsavel_e_evidencia_na_conclusao(self):
        form = HomologacaoFiscalForm(
            data={"status": StatusHomologacaoFiscal.CONCLUIDA},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("responsavel_tecnico", form.errors)
        self.assertIn("evidencia_referencia", form.errors)

    def test_roteiro_homologacao_goias_registra_andamento_e_auditoria(self):
        self.filial.uf = "GO"
        self.filial.codigo_municipio_ibge = "5208707"
        self.filial.save(update_fields=["uf", "codigo_municipio_ibge"])

        response = self.client.post(
            f"/fiscal/configuracoes/{self.configuracao.pk}/homologacao-goias/",
            {
                "status": StatusHomologacaoFiscal.EM_ANDAMENTO,
                "responsavel_tecnico": "Equipe Deigo Tecnologia",
                "evidencia_referencia": "CHAMADO-123",
                "observacoes": "Aguardando credenciamento e validação externa.",
            },
        )

        self.assertRedirects(response, f"/fiscal/configuracoes/{self.configuracao.pk}/homologacao-goias/")
        homologacao = HomologacaoFiscal.objects.get(configuracao=self.configuracao)
        self.assertEqual(homologacao.status, StatusHomologacaoFiscal.EM_ANDAMENTO)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="ATUALIZA_HOMOLOGACAO_GOIAS",
                objeto_id=str(homologacao.pk),
            ).exists()
        )
    def test_form_configuracao_fiscal_exibe_secoes_operacionais(self):
        response = self.client.get(f"/fiscal/configuracoes/{self.configuracao.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Loja e ambiente")
        self.assertContains(response, "NFC-e")
        self.assertContains(response, "Certificado digital")
        self.assertContains(response, "Certificado A1")
        self.assertContains(response, "O arquivo será armazenado criptografado")
        self.assertContains(response, "Transição tributária IBS/CBS")

    def test_forms_serie_e_natureza_exibem_secoes_operacionais(self):
        serie = SerieFiscal.objects.get(filial=self.filial)
        natureza = NaturezaOperacao.objects.get(descricao="Venda ao consumidor")

        response_serie = self.client.get(f"/fiscal/series/{serie.pk}/editar/")
        response_natureza = self.client.get(f"/fiscal/naturezas/{natureza.pk}/editar/")

        self.assertEqual(response_serie.status_code, 200)
        self.assertContains(response_serie, "Numeracao fiscal")
        self.assertContains(response_serie, "O número é reservado")
        self.assertEqual(response_natureza.status_code, 200)
        self.assertContains(response_natureza, "Operação fiscal")
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
            "modo_transicao_ibs_cbs": ModoTransicaoIbsCbs.LEGADO,
            },
            REMOTE_ADDR="127.0.0.10",
        )
        response_natureza = self.client.post(
            f"/fiscal/naturezas/{natureza.pk}/editar/",
            {
                "empresa": self.empresa.pk,
                "descricao": "Venda presencial",
                "cfop": "5102",
                "tipo_documento": TipoDocumentoFiscal.NFCE,
                "movimenta_estoque": "on",
                "ativo": "on",
            "modo_transicao_ibs_cbs": ModoTransicaoIbsCbs.LEGADO,
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
        self.assertIn("código IBGE", mensagem)


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
            f"/fiscal/documentos/{self.documento_b.pk}/consultar-sefaz/",
            f"/fiscal/documentos/{self.documento_b.pk}/retomar-consultas-sefaz/",
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
                "crt": CodigoRegimeTributario.SIMPLES_NACIONAL,
                "inscricao_estadual": "FORJADA",
                "ativo": "on",
            "modo_transicao_ibs_cbs": ModoTransicaoIbsCbs.LEGADO,
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
            "modo_transicao_ibs_cbs": ModoTransicaoIbsCbs.LEGADO,
            },
        )

        self.assertEqual(resposta_config.status_code, 200)
        self.assertIn("filial", resposta_config.context["form"].errors)
        self.assertEqual(resposta_serie.status_code, 200)
        self.assertIn("filial", resposta_serie.context["form"].errors)
        self.assertFalse(ConfiguracaoFiscal.objects.filter(filial=self.filial_a_sem_config).exists())
        self.assertFalse(SerieFiscal.objects.filter(filial=self.filial_b, serie=99).exists())

    def test_natureza_operacao_fica_isolada_por_empresa(self):
        natureza_a = NaturezaOperacao.objects.create(
            empresa=self.empresa_a,
            descricao="Venda presencial A",
            cfop="5102",
            tipo_documento=TipoDocumentoFiscal.NFCE,
        )
        natureza_b = NaturezaOperacao.objects.create(
            empresa=self.empresa_b,
            descricao="Venda presencial B",
            cfop="5102",
            tipo_documento=TipoDocumentoFiscal.NFCE,
        )

        pagina = self.client.get("/fiscal/")

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, natureza_a.descricao)
        self.assertNotContains(pagina, natureza_b.descricao)
        self.assertTrue(natureza_a.padrao)
        self.assertTrue(natureza_b.padrao)
        self.assertEqual(
            self.client.get(f"/fiscal/naturezas/{natureza_b.pk}/editar/").status_code,
            404,
        )
        self.assertEqual(
            self.client.post(f"/fiscal/naturezas/{natureza_b.pk}/definir-padrao/").status_code,
            404,
        )

    def test_admin_cria_natureza_vinculada_a_propria_empresa(self):
        resposta = self.client.post(
            "/fiscal/naturezas/nova/",
            {
                "descricao": "Venda NFC-e da empresa A",
                "cfop": "5102",
                "tipo_documento": TipoDocumentoFiscal.NFCE,
                "movimenta_estoque": "on",
                "ativo": "on",
            "modo_transicao_ibs_cbs": ModoTransicaoIbsCbs.LEGADO,
            },
        )

        self.assertRedirects(resposta, "/fiscal/")
        natureza = NaturezaOperacao.objects.get(descricao="Venda NFC-e da empresa A")
        self.assertEqual(natureza.empresa, self.empresa_a)

    def test_superadmin_mantem_visao_global(self):
        superadmin = get_user_model().objects.create_superuser("fiscal_master", "master@example.com", "123")
        self.client.force_login(superadmin)

        diagnostico = self.client.get("/fiscal/diagnostico.json").json()
        detalhe = self.client.get(f"/fiscal/documentos/{self.documento_b.pk}/")

        self.assertEqual(diagnostico["resumo"]["filiais"], 3)
        self.assertEqual(detalhe.status_code, 200)


class InutilizacaoFiscalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "fiscal-inutilizacao", "inut@example.com", "123"
        )
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Inutilizacao",
            nome_fantasia="Mercado Inutilizacao",
            cnpj="11.222.333/0001-81",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Inutilizacao",
            cnpj=self.empresa.cnpj,
            municipio="Goiania",
            uf="GO",
            codigo_municipio_ibge="5208707",
        )
        self.configuracao = ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            ativo=True,
        )
        SerieFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            serie=1,
            proximo_numero=20,
            ativo=True,
        )

    def solicitar(self, **overrides):
        dados = {
            "filial": self.filial,
            "tipo_documento": TipoDocumentoFiscal.NFCE,
            "ano": django_timezone.localdate().year,
            "serie": 1,
            "numero_inicial": 10,
            "numero_final": 12,
            "justificativa": "Quebra de sequência causada por falha técnica.",
            "usuario": self.user,
            "ip": "127.0.0.1",
        }
        dados.update(overrides)
        return solicitar_inutilizacao_numeracao(**dados)

    def test_homologacao_sem_adaptador_gera_protocolo_simulado_e_auditoria(self):
        inutilizacao = self.solicitar()

        self.assertEqual(inutilizacao.status, StatusInutilizacaoFiscal.AUTORIZADA)
        self.assertTrue(inutilizacao.protocolo.startswith("HOMI"))
        self.assertIn("simulada", inutilizacao.mensagem_retorno.lower())
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="INUTILIZACAO_SEFAZ_AUTORIZADA",
                objeto_id=str(inutilizacao.pk),
            ).exists()
        )

    def test_numero_ja_usado_bloqueia_a_faixa(self):
        DocumentoFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            serie=1,
            numero=11,
            status=StatusDocumentoFiscal.CANCELADO,
            usuario=self.user,
        )

        with self.assertRaisesMessage(ValidationError, "número 11 já foi usado"):
            self.solicitar()
        self.assertFalse(InutilizacaoNumeracaoFiscal.objects.exists())

    def test_faixa_sobreposta_bloqueia_nova_solicitacao(self):
        self.solicitar(numero_inicial=10, numero_final=15)

        with self.assertRaisesMessage(ValidationError, "cruza uma inutilização"):
            self.solicitar(numero_inicial=14, numero_final=18)

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter")
    def test_producao_exige_e_registra_protocolo_do_adaptador(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente", "atualizado_em"])
        FakeSefazAdapter.last_inutilization_request = None

        inutilizacao = self.solicitar(numero_inicial=30, numero_final=31)

        self.assertEqual(inutilizacao.status, StatusInutilizacaoFiscal.AUTORIZADA)
        self.assertEqual(inutilizacao.protocolo, "135260000000199")
        self.assertEqual(
            FakeSefazAdapter.last_inutilization_request["idempotency_key"],
            (
                f"fiscal-inutilizacao:{self.filial.pk}:NFCE:"
                f"{django_timezone.localdate().year}:1:30:31:PRODUCAO"
            ),
        )

    @override_settings(FISCAL_SEFAZ_ADAPTER="")
    def test_producao_sem_adaptador_falha_fechada_e_preserva_pendente(self):
        self.configuracao.ambiente = AmbienteFiscal.PRODUCAO
        self.configuracao.save(update_fields=["ambiente", "atualizado_em"])

        with self.assertRaisesMessage(ValidationError, "Nenhum adaptador SEFAZ"):
            self.solicitar(numero_inicial=40, numero_final=40)

        inutilizacao = InutilizacaoNumeracaoFiscal.objects.get()
        self.assertEqual(inutilizacao.status, StatusInutilizacaoFiscal.PENDENTE)
        self.assertFalse(inutilizacao.protocolo)

    def test_tela_isola_registros_por_empresa(self):
        admin_empresa = get_user_model().objects.create_user("admin-empresa", password="123")
        PerfilUsuario.objects.create(
            usuario=admin_empresa,
            filial=self.filial,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.solicitar(numero_inicial=50, numero_final=50)

        empresa_externa = Empresa.objects.create(
            razao_social="Mercado Fiscal Externo",
            nome_fantasia="Mercado Fiscal Externo",
            cnpj="77.777.777/0001-77",
        )
        filial_externa = Filial.objects.create(
            empresa=empresa_externa,
            nome="Filial Fiscal Externa",
            cnpj=empresa_externa.cnpj,
        )
        InutilizacaoNumeracaoFiscal.objects.create(
            filial=filial_externa,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            ano=django_timezone.localdate().year,
            serie=1,
            numero_inicial=99,
            numero_final=99,
            justificativa="Quebra externa válida para teste de isolamento.",
            status=StatusInutilizacaoFiscal.AUTORIZADA,
            protocolo="EXTERNO",
            usuario=self.user,
        )

        self.client.force_login(admin_empresa)
        response = self.client.get("/fiscal/inutilizacoes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Matriz Inutilizacao")
        self.assertNotContains(response, "Filial Fiscal Externa")


    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeUnsignedSefazAdapter")
    def test_homologacao_nao_mascara_adaptador_configurado_sem_inutilizacao(self):
        with self.assertRaisesMessage(ValidationError, "não implementa inutilização"):
            self.solicitar(numero_inicial=60, numero_final=60)

        inutilizacao = InutilizacaoNumeracaoFiscal.objects.get()
        self.assertEqual(inutilizacao.status, StatusInutilizacaoFiscal.PENDENTE)
        self.assertFalse(inutilizacao.protocolo)


class ConsultaSituacaoFiscalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "consulta-fiscal", "consulta@example.com", "123"
        )
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Consulta",
            nome_fantasia="Mercado Consulta",
            cnpj="22.333.444/0001-06",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Consulta",
            cnpj=self.empresa.cnpj,
            municipio="Goiania",
            uf="GO",
            codigo_municipio_ibge="5208707",
        )
        self.documento = DocumentoFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.PRODUCAO,
            serie=1,
            numero=77,
            chave_acesso="52" + "0" * 42,
            status=StatusDocumentoFiscal.REJEITADO,
            usuario=self.user,
        )

    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter")
    def test_consulta_autorizada_reconcilia_documento_e_audita(self):
        FakeSefazAdapter.last_query_request = None

        documento, resultado = consultar_situacao_documento(
            self.documento,
            self.user,
            ip="127.0.0.1",
        )

        self.assertEqual(resultado.status, "AUTORIZADO")
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)
        self.assertEqual(documento.protocolo, "135260000000299")
        self.assertFalse(documento.aguardando_consulta_sefaz)
        self.assertIsNotNone(documento.consulta_sefaz_em)
        self.assertEqual(
            FakeSefazAdapter.last_query_request["idempotency_key"],
            f"fiscal-consulta:{documento.pk}:{documento.chave_acesso}",
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CONSULTA_SEFAZ_AUTORIZADO",
                objeto_id=str(documento.pk),
            ).exists()
        )

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazQueryCanceledAdapter"
    )
    def test_consulta_cancelada_exige_e_registra_protocolo_do_evento(self):
        self.documento.status = StatusDocumentoFiscal.EMITIDO
        self.documento.protocolo = "135260000000300"
        self.documento.save(update_fields=["status", "protocolo", "atualizado_em"])

        documento, resultado = consultar_situacao_documento(self.documento, self.user)

        self.assertEqual(resultado.status, "CANCELADO")
        self.assertEqual(documento.status, StatusDocumentoFiscal.CANCELADO)
        self.assertEqual(documento.protocolo_cancelamento, "135260000000301")

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazQueryNotFoundAdapter"
    )
    def test_nao_localizado_preserva_estado_local(self):
        status_anterior = self.documento.status
        self.documento.aguardando_consulta_sefaz = True
        self.documento.save(update_fields=["aguardando_consulta_sefaz"])

        documento, resultado = consultar_situacao_documento(self.documento, self.user)

        self.assertEqual(resultado.status, "NAO_LOCALIZADO")
        self.assertEqual(documento.status, status_anterior)
        self.assertFalse(documento.aguardando_consulta_sefaz)
        self.assertEqual(documento.tentativas_transmissao, 0)
        self.assertIn("não localizado", documento.mensagem_consulta_sefaz)

    @override_settings(FISCAL_SEFAZ_ADAPTER="")
    def test_sem_adaptador_falha_fechada_e_preserva_estado(self):
        with self.assertRaisesMessage(ValidationError, "Nenhum adaptador SEFAZ"):
            consultar_situacao_documento(self.documento, self.user)

        self.documento.refresh_from_db()
        self.assertEqual(self.documento.status, StatusDocumentoFiscal.REJEITADO)
        self.assertFalse(self.documento.protocolo)
        self.assertIsNotNone(self.documento.consulta_sefaz_em)
        self.assertEqual(self.documento.tentativas_consulta_sefaz, 1)


    @override_settings(FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter")
    def test_rota_post_consulta_e_redireciona_para_detalhe(self):
        response = self.client.post(
            f"/fiscal/documentos/{self.documento.pk}/consultar-sefaz/"
        )

        self.assertRedirects(
            response,
            f"/fiscal/documentos/{self.documento.pk}/",
            fetch_redirect_response=False,
        )
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.status, StatusDocumentoFiscal.EMITIDO)
