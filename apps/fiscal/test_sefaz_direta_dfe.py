import base64
import gzip
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from lxml import etree

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial

from .dfe_adapters import normalizar_lote_dfe
from .models import ControleDistribuicaoDFeFilial, EventoDFeRecebido
from .services_dfe import consultar_distribuicao_dfe
from .sefaz_direta import NFE_NS, SefazDiretaDFeAdapter, SefazDiretaDFeError

CHAVE = "52260812345678000123550010000001231000001234"
CNPJ = "12345678000199"


def _doc_zip(xml, nsu="9", schema="resEvento_v1.01.xsd"):
    comprimido = gzip.compress(xml.encode("utf-8"))
    return (
        f'<docZip NSU="{nsu}" schema="{schema}">'
        f'{base64.b64encode(comprimido).decode("ascii")}</docZip>'
    )


def _retorno(*documentos, cstat="138", ultimo="9", maximo="9"):
    return (
        f'<retDistDFeInt xmlns="{NFE_NS}" versao="1.01">'
        f'<tpAmb>2</tpAmb><verAplic>1</verAplic><cStat>{cstat}</cStat>'
        f'<xMotivo>Documentos localizados</xMotivo><dhResp>2026-08-20T10:00:00-03:00</dhResp>'
        f'<ultNSU>{ultimo.zfill(15)}</ultNSU><maxNSU>{maximo.zfill(15)}</maxNSU>'
        f'<loteDistDFeInt>{"".join(documentos)}</loteDistDFeInt>'
        f'</retDistDFeInt>'
    ).encode("utf-8")


@override_settings(
    SEFAZ_DIRETA_DFE_NETWORK_ENABLED=True,
    SEFAZ_DIRETA_DFE_ALLOW_PRODUCTION=False,
    SEFAZ_DIRETA_DFE_TIMEOUT_SECONDS=12,
    SEFAZ_DIRETA_DFE_ENDPOINTS={},
)
class SefazDiretaDFeAdapterTests(SimpleTestCase):
    def _configuracao(self, ambiente="HOMOLOGACAO"):
        return SimpleNamespace(
            ambiente=ambiente,
            filial=SimpleNamespace(uf="GO"),
        )

    def test_consulta_evento_por_nsu_no_ambiente_nacional(self):
        chamadas = []
        evento = f'''<procEventoNFe xmlns="{NFE_NS}" versao="1.00"><evento><infEvento>
          <chNFe>{CHAVE}</chNFe><tpEvento>110111</tpEvento><nSeqEvento>1</nSeqEvento>
          <dhEvento>2026-08-20T09:00:00-03:00</dhEvento><detEvento><descEvento>Cancelamento</descEvento></detEvento>
        </infEvento></evento></procEventoNFe>'''

        def transporte(**kwargs):
            chamadas.append(kwargs)
            return _retorno(_doc_zip(evento))

        adaptador = SefazDiretaDFeAdapter(
            transport=transporte,
            configuracao_resolver=lambda cnpj: self._configuracao(),
        )
        lote = adaptador.consultar(cnpj=CNPJ, ultimo_nsu="8", limite=50)

        self.assertEqual(lote["ultimo_nsu"], "9")
        self.assertEqual(lote["aguardar_segundos"], 3600)
        self.assertEqual(lote["documentos"][0]["tipo_documento"], "EVENTO")
        self.assertEqual(lote["documentos"][0]["tipo_evento"], "110111")
        self.assertEqual(chamadas[0]["servico"], "distribuicao_dfe")
        self.assertEqual(
            chamadas[0]["endpoint"],
            "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
        )
        envelope = etree.fromstring(chamadas[0]["envelope"])
        self.assertEqual(envelope.xpath("string(.//*[local-name()='ultNSU'])"), "000000000000008")
        self.assertEqual(envelope.xpath("string(.//*[local-name()='CNPJ'])"), CNPJ)

    def test_sem_documentos_exige_intervalo_de_uma_hora(self):
        adaptador = SefazDiretaDFeAdapter(
            transport=lambda **kwargs: _retorno(cstat="137", ultimo="8", maximo="8"),
            configuracao_resolver=lambda cnpj: self._configuracao(),
        )
        lote = adaptador.consultar(cnpj=CNPJ, ultimo_nsu="8", limite=50)
        self.assertEqual(lote["documentos"], [])
        self.assertEqual(lote["aguardar_segundos"], 3600)

    def test_producao_permanece_bloqueada(self):
        adaptador = SefazDiretaDFeAdapter(
            transport=lambda **kwargs: b"",
            configuracao_resolver=lambda cnpj: self._configuracao("PRODUCAO"),
        )
        with self.assertRaisesMessage(SefazDiretaDFeError, "Produção"):
            adaptador.consultar(cnpj=CNPJ, ultimo_nsu="", limite=50)

    def test_contrato_rejeita_evento_sem_xml(self):
        with self.assertRaisesMessage(ValidationError, "Evento"):
            normalizar_lote_dfe({
                "contrato": "fiscal_dfe_distribution_v1",
                "ultimo_nsu": "1",
                "max_nsu": "1",
                "documentos": [{"tipo_documento": "EVENTO", "nsu": "1", "chave_acesso": CHAVE}],
            })


class FakeEventoDFeAdapter:
    chamadas = 0

    def consultar(self, *, cnpj, ultimo_nsu, limite):
        type(self).chamadas += 1
        xml = f'''<procEventoNFe xmlns="{NFE_NS}"><evento><infEvento><chNFe>{CHAVE}</chNFe></infEvento></evento></procEventoNFe>'''
        return {
            "contrato": "fiscal_dfe_distribution_v1",
            "ultimo_nsu": "9",
            "max_nsu": "9",
            "aguardar_segundos": 3600,
            "mensagem": "Sem documentos pendentes.",
            "documentos": [{
                "tipo_documento": "EVENTO", "nsu": "9", "chave_acesso": CHAVE,
                "destinatario_cnpj": cnpj, "schema": "procEventoNFe_v1.00.xsd",
                "tipo_evento": "110111", "sequencia": 1,
                "data_evento": "2026-08-20T09:00:00-03:00", "descricao": "Cancelamento",
                "xml": xml,
            }],
        }


@override_settings(FISCAL_DFE_ADAPTER="apps.fiscal.test_sefaz_direta_dfe.FakeEventoDFeAdapter")
class SefazDiretaDFeServiceTests(TestCase):
    def setUp(self):
        FakeEventoDFeAdapter.chamadas = 0
        self.usuario = get_user_model().objects.create_superuser("dfe_direta", "dfe-direta@example.com", "123")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Direto", nome_fantasia="Mercado Direto", cnpj=CNPJ
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz Direta", cnpj=CNPJ, uf="GO"
        )

    def test_evento_e_cooldown_sao_atomicos_por_filial(self):
        resultado = consultar_distribuicao_dfe(filial=self.filial, usuario=self.usuario)
        controle = ControleDistribuicaoDFeFilial.objects.get(filial=self.filial)

        self.assertEqual(resultado["eventos"], 1)
        self.assertEqual(EventoDFeRecebido.objects.count(), 1)
        self.assertEqual(controle.ultimo_nsu, "9")
        self.assertGreater(controle.proxima_consulta_em, timezone.now())

        with self.assertRaisesMessage(ValidationError, "intervalo entre consultas"):
            consultar_distribuicao_dfe(filial=self.filial, usuario=self.usuario)
        self.assertEqual(FakeEventoDFeAdapter.chamadas, 1)

        evento = EventoDFeRecebido.objects.get()
        self.client.force_login(self.usuario)
        tela = self.client.get("/fiscal/dfe-recebidos/")
        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, "Eventos fiscais recebidos")
        self.assertContains(tela, "Cancelamento")
        download = self.client.get(f"/fiscal/dfe-recebidos/eventos/{evento.pk}/xml/")
        self.assertEqual(download.status_code, 200)
        self.assertIn(CHAVE.encode(), download.content)

        outra_empresa = Empresa.objects.create(
            razao_social="Outro Mercado", nome_fantasia="Outro Mercado", cnpj="98765432000110"
        )
        outra_filial = Filial.objects.create(
            empresa=outra_empresa, nome="Outra Matriz", cnpj="98765432000110", uf="GO"
        )
        outro_usuario = get_user_model().objects.create_user("outro_dfe", password="123")
        PerfilUsuario.objects.create(
            usuario=outro_usuario, filial=outra_filial, tipo=TipoPerfil.ADMINISTRADOR
        )
        self.client.force_login(outro_usuario)
        negado = self.client.get(f"/fiscal/dfe-recebidos/eventos/{evento.pk}/xml/")
        self.assertEqual(negado.status_code, 404)