import hashlib
import json
from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.financeiro.amostra_contabil import registrar_aceite_amostra, validar_amostra_contabil
from apps.financeiro.contrato_contabil import registrar_contrato_contabil
from apps.financeiro.models import (
    AceiteAmostraContabil,
    FormatoEntregaContabil,
    ResponsavelEFDICMSIPI,
)


class AmostraContabilTests(TestCase):
    def setUp(self):
        self.master = get_user_model().objects.create_superuser(
            "master-amostra", "master-amostra@example.com", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Amostra LTDA",
            nome_fantasia="Mercado Amostra",
            cnpj="34.567.890/0001-20",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz Amostra", cnpj=self.empresa.cnpj
        )
        self.contrato = registrar_contrato_contabil(
            empresa=self.empresa,
            usuario=self.master,
            software_contabil="Escritorio da amostra",
            formato_entrega=FormatoEntregaContabil.PACOTE_ZIP_V2,
            responsavel_efd_icms_ipi=ResponsavelEFDICMSIPI.ESCRITORIO_CONTABIL,
            responsavel_efd_nome="Escritorio responsavel",
            aceite_referencia="ACEITE-CONTRATO-AMOSTRA",
            validar=True,
        )

    def _pacote(self, *, vendas_divergentes=0, adulterar=False):
        reconciliacao = {
            "contrato": "accounting_operational_reconciliation_v1",
            "resumo": {
                "vendas": 1,
                "vendas_ok": 1 - vendas_divergentes,
                "vendas_divergentes": vendas_divergentes,
                "vendas_revisao": 0,
                "entradas": 0,
                "entradas_ok": 0,
                "entradas_divergentes": 0,
                "entradas_revisao": 0,
            },
            "vendas": [],
            "entradas": [],
        }
        arquivos = {
            "reconciliacao/resumo.json": json.dumps(reconciliacao).encode("utf-8"),
            "reconciliacao/vendas.csv": b"venda;situacao\n1;OK\n",
            "reconciliacao/entradas.csv": b"entrada;situacao\n",
            "fiscal/documentos-saida.csv": b"documento;status\n1;Emitido\n",
            "fiscal/documentos-entrada.csv": b"documento;status\n",
            "fiscal/itens-fiscais.csv": b"item;cfop\n1;5102\n",
            "fiscal/eventos.csv": b"evento;status\n",
            "fiscal/xml/saida/NFCE-1.xml": b"<nfeProc><NFe/></nfeProc>",
            "estoque/inventario-valorizado.csv": b"produto;quantidade;valor\n1;1;10\n",
        }
        integridade = [
            {
                "caminho": nome,
                "bytes": len(conteudo),
                "sha256": hashlib.sha256(conteudo).hexdigest(),
            }
            for nome, conteudo in arquivos.items()
        ]
        manifesto = {
            "contrato": "accounting_monthly_package_v2",
            "competencia": timezone.localdate().strftime("%Y-%m"),
            "empresa": {"id": self.empresa.pk, "cnpj": self.empresa.cnpj},
            "filial": None,
            "contrato_integracao_contabil": {
                "validado": True,
                "versao_validada": self.contrato.versao,
                "formato_entrega": FormatoEntregaContabil.PACOTE_ZIP_V2,
            },
            "contagens": {
                "documentos_saida": 1,
                "documentos_entrada": 0,
                "itens_fiscais": 1,
                "eventos": 0,
                "itens_inventario": 1,
                "vendas_reconciliadas": 1,
                "vendas_divergentes": vendas_divergentes,
                "entradas_reconciliadas": 0,
                "entradas_divergentes": 0,
            },
            "inventario": {"snapshot_completo": True},
            "arquivos": integridade,
        }
        if adulterar:
            arquivos["fiscal/documentos-saida.csv"] = b"conteudo adulterado"
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as destino:
            destino.writestr("manifesto.json", json.dumps(manifesto).encode("utf-8"))
            for nome, conteudo in arquivos.items():
                destino.writestr(nome, conteudo)
        return buffer.getvalue()

    def test_valida_e_registra_aceite_imutavel_e_idempotente(self):
        pacote = self._pacote()
        relatorio = validar_amostra_contabil(
            pacote_bytes=pacote, empresa=self.empresa, contrato_integracao=self.contrato
        )
        aceite, criado = registrar_aceite_amostra(
            empresa=self.empresa,
            competencia=timezone.localdate().strftime("%Y-%m"),
            contrato_integracao=self.contrato,
            pacote_bytes=pacote,
            relatorio_validacao=relatorio,
            referencia_aceite="ACEITE-AMOSTRA-001",
            usuario=self.master,
            ip="127.0.0.52",
        )
        repetido, criado_novamente = registrar_aceite_amostra(
            empresa=self.empresa,
            competencia=timezone.localdate().strftime("%Y-%m"),
            contrato_integracao=self.contrato,
            pacote_bytes=pacote,
            relatorio_validacao=relatorio,
            referencia_aceite="ACEITE-AMOSTRA-001",
            usuario=self.master,
        )

        self.assertTrue(relatorio["aprovado"])
        self.assertTrue(criado)
        self.assertFalse(criado_novamente)
        self.assertEqual(repetido.pk, aceite.pk)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="REGISTRAR_ACEITE_AMOSTRA_CONTABIL", objeto_id=str(aceite.pk), ip="127.0.0.52"
            ).exists()
        )
        aceite.referencia_aceite = "alteracao"
        with self.assertRaises(ValidationError):
            aceite.save()
        with self.assertRaises(ValidationError):
            AceiteAmostraContabil.objects.filter(pk=aceite.pk).update(referencia_aceite="alteracao")
        with self.assertRaises(ValidationError):
            aceite.delete()

    def test_bloqueia_hash_adulterado_e_divergencia_operacional(self):
        adulterado = validar_amostra_contabil(
            pacote_bytes=self._pacote(adulterar=True),
            empresa=self.empresa,
            contrato_integracao=self.contrato,
        )
        divergente = validar_amostra_contabil(
            pacote_bytes=self._pacote(vendas_divergentes=1),
            empresa=self.empresa,
            contrato_integracao=self.contrato,
        )

        self.assertFalse(adulterado["aprovado"])
        self.assertIn("HASH_DIVERGENTE", {item["codigo"] for item in adulterado["erros"]})
        self.assertFalse(divergente["aprovado"])
        self.assertIn("VENDAS_DIVERGENTES", {item["codigo"] for item in divergente["erros"]})

    def test_aceite_recusa_relatorio_reprovado_e_usuario_nao_master(self):
        pacote = self._pacote(vendas_divergentes=1)
        relatorio = validar_amostra_contabil(
            pacote_bytes=pacote, empresa=self.empresa, contrato_integracao=self.contrato
        )
        with self.assertRaises(ValidationError):
            registrar_aceite_amostra(
                empresa=self.empresa,
                competencia=timezone.localdate().strftime("%Y-%m"),
                contrato_integracao=self.contrato,
                pacote_bytes=pacote,
                relatorio_validacao=relatorio,
                referencia_aceite="ACEITE-INVALIDO",
                usuario=self.master,
            )
        administrador = get_user_model().objects.create_user("admin-amostra", password="123")
        PerfilUsuario.objects.create(
            usuario=administrador, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR
        )
        with self.assertRaises(PermissionDenied):
            registrar_aceite_amostra(
                empresa=self.empresa,
                competencia=timezone.localdate().strftime("%Y-%m"),
                contrato_integracao=self.contrato,
                pacote_bytes=self._pacote(),
                relatorio_validacao=validar_amostra_contabil(
                    pacote_bytes=self._pacote(), empresa=self.empresa,
                    contrato_integracao=self.contrato,
                ),
                referencia_aceite="ACEITE-SEM-PERMISSAO",
                usuario=administrador,
            )

    @patch("apps.financeiro.views._pacote_contabil_zip")
    def test_tela_master_registra_e_administrador_nao_acessa(self, gerar_pacote):
        pacote = self._pacote()
        gerar_pacote.return_value = (pacote, {}, 1, 1)
        cliente = Client(HTTP_HOST="localhost")
        cliente.force_login(self.master)
        competencia = timezone.localdate().strftime("%Y-%m")
        resposta = cliente.post(
            "/financeiro/contabilidade/validar-amostra/",
            {
                "empresa": self.empresa.pk,
                "competencia": competencia,
                "referencia_aceite": "ACEITE-TELA-001",
                "registrar_aceite": "on",
            },
            REMOTE_ADDR="127.0.0.53",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Amostra aprovada")
        self.assertEqual(AceiteAmostraContabil.objects.count(), 1)

        administrador = get_user_model().objects.create_user("admin-tela-amostra", password="123")
        PerfilUsuario.objects.create(
            usuario=administrador, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR
        )
        cliente.force_login(administrador)
        self.assertEqual(cliente.get("/financeiro/contabilidade/validar-amostra/").status_code, 403)
