import hashlib
import io
import json
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from .auditoria_pacote_xsd import AuditoriaPacoteXSDErro, auditar_pacote_xsd


XSD_RAIZ = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
 targetNamespace="http://www.portalfiscal.inf.br/nfe"
 xmlns="http://www.portalfiscal.inf.br/nfe" elementFormDefault="qualified">
 <xs:include schemaLocation="tipos.xsd"/>
 <xs:element name="NFe" type="TNFe"/>
</xs:schema>
"""
XSD_TIPOS = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
 targetNamespace="http://www.portalfiscal.inf.br/nfe"
 xmlns="http://www.portalfiscal.inf.br/nfe" elementFormDefault="qualified">
 <xs:complexType name="TNFe"><xs:sequence/></xs:complexType>
</xs:schema>
"""


def _zip(membros):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        for nome, conteudo in membros.items():
            pacote.writestr(nome, conteudo)
    return saida.getvalue()


def _arquivo(diretorio, conteudo):
    caminho = Path(diretorio) / "schemas.zip"
    caminho.write_bytes(conteudo)
    return caminho


class AuditoriaPacoteXSDTests(SimpleTestCase):
    def test_audita_pacote_real_sem_promover(self):
        caminho = Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip"
        resultado = auditar_pacote_xsd(
            arquivo=caminho,
            sha256_esperado="b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998",
            versao="PL_010f_v1.04",
        )
        self.assertEqual(resultado["resultado"], "INTEGRO_TECNICAMENTE_SEM_PROMOCAO")
        self.assertEqual(len(resultado["schema"]["arquivos_xsd"]), 5)
        self.assertEqual(len(resultado["schema"]["dependencias"]), 4)
        self.assertEqual(
            resultado["schema"]["arquivo_raiz_sha256"],
            "adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df",
        )
        self.assertFalse(resultado["promocao_versionada"]["aplicabilidade_aprovada"])
        self.assertFalse(resultado["promocao_versionada"]["instalacao_executada"])
        self.assertTrue(all(
            valor is False
            for chave, valor in resultado["politica"].items()
            if chave not in {"somente_offline"}
        ))

    def test_comando_publica_json_sem_escrever_no_destino(self):
        conteudo = _zip({"PL/NFe/nfe_v4.00.xsd": XSD_RAIZ, "PL/NFe/tipos.xsd": XSD_TIPOS})
        with TemporaryDirectory() as diretorio:
            origem = _arquivo(diretorio, conteudo)
            destino = Path(diretorio) / "fiscal_schemas"
            saida = io.StringIO()
            with override_settings(FISCAL_SCHEMA_DIR=destino):
                call_command(
                    "auditar_pacote_xsd",
                    arquivo=str(origem),
                    sha256=hashlib.sha256(conteudo).hexdigest(),
                    versao="PL_TESTE_1",
                    stdout=saida,
                )
            resultado = json.loads(saida.getvalue())
            self.assertTrue(resultado["schema"]["compilacao_offline"])
            self.assertFalse(destino.exists())

    def test_rejeita_hash_divergente(self):
        conteudo = _zip({"PL/NFe/nfe_v4.00.xsd": XSD_RAIZ, "PL/NFe/tipos.xsd": XSD_TIPOS})
        with TemporaryDirectory() as diretorio:
            with self.assertRaisesMessage(AuditoriaPacoteXSDErro, "diverge do esperado"):
                auditar_pacote_xsd(
                    arquivo=_arquivo(diretorio, conteudo),
                    sha256_esperado="0" * 64,
                    versao="PL_TESTE_1",
                )

    def test_rejeita_dependencia_ausente(self):
        conteudo = _zip({"PL/NFe/nfe_v4.00.xsd": XSD_RAIZ})
        with TemporaryDirectory() as diretorio:
            with self.assertRaisesMessage(AuditoriaPacoteXSDErro, "Dependência XSD ausente"):
                auditar_pacote_xsd(
                    arquivo=_arquivo(diretorio, conteudo),
                    sha256_esperado=hashlib.sha256(conteudo).hexdigest(),
                    versao="PL_TESTE_1",
                )

    def test_rejeita_caminho_inseguro_sem_escrever(self):
        conteudo = _zip({"../nfe_v4.00.xsd": XSD_RAIZ})
        with TemporaryDirectory() as diretorio:
            with self.assertRaisesMessage(AuditoriaPacoteXSDErro, "caminho inseguro"):
                auditar_pacote_xsd(
                    arquivo=_arquivo(diretorio, conteudo),
                    sha256_esperado=hashlib.sha256(conteudo).hexdigest(),
                    versao="PL_TESTE_1",
                )
            self.assertEqual(sorted(item.name for item in Path(diretorio).iterdir()), ["schemas.zip"])

    def test_rejeita_duplicidade_por_caixa_no_windows(self):
        conteudo = _zip({"PL/NFe/nfe_v4.00.xsd": XSD_RAIZ, "pl/nfe/NFE_v4.00.xsd": XSD_RAIZ})
        with TemporaryDirectory() as diretorio:
            with self.assertRaisesMessage(AuditoriaPacoteXSDErro, "caminhos duplicados"):
                auditar_pacote_xsd(
                    arquivo=_arquivo(diretorio, conteudo),
                    sha256_esperado=hashlib.sha256(conteudo).hexdigest(),
                    versao="PL_TESTE_1",
                )
    def test_comando_converte_erro_controlado(self):
        with TemporaryDirectory() as diretorio:
            origem = _arquivo(diretorio, b"nao-e-zip")
            with self.assertRaises(CommandError):
                call_command(
                    "auditar_pacote_xsd",
                    arquivo=str(origem),
                    sha256=hashlib.sha256(b"nao-e-zip").hexdigest(),
                    versao="PL_TESTE_1",
                )