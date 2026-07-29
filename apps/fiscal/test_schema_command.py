import hashlib
import io
import json
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


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


def _pacote_zip(membros=None):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as pacote:
        for nome, conteudo in (
            membros
            or {
                "PL_TESTE/NFe/nfe_v4.00.xsd": XSD_RAIZ,
                "PL_TESTE/NFe/tipos.xsd": XSD_TIPOS,
            }
        ).items():
            pacote.writestr(nome, conteudo)
    return saida.getvalue()


class InstalarSchemasFiscaisTests(SimpleTestCase):
    def test_instala_pacote_valido_e_grava_manifesto(self):
        conteudo = _pacote_zip()
        with TemporaryDirectory() as diretorio:
            origem = Path(diretorio) / "oficial.zip"
            origem.write_bytes(conteudo)
            destino = Path(diretorio) / "schemas"
            with override_settings(FISCAL_SCHEMA_DIR=destino):
                call_command(
                    "instalar_schemas_fiscais",
                    arquivo=str(origem),
                    sha256=hashlib.sha256(conteudo).hexdigest(),
                    versao="PL_TESTE_1",
                    verbosity=0,
                )

            manifesto = json.loads(
                (destino / "pacotes" / "PL_TESTE_1" / "manifesto.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifesto["contrato"], "fiscal_schema_package_v1")
            self.assertEqual(manifesto["versao"], "PL_TESTE_1")
            self.assertEqual(len(manifesto["arquivo_raiz_sha256"]), 64)
            self.assertEqual(len(manifesto["arquivos_xsd"]), 2)

    def test_rejeita_hash_divergente_sem_extrair(self):
        conteudo = _pacote_zip()
        with TemporaryDirectory() as diretorio:
            origem = Path(diretorio) / "oficial.zip"
            origem.write_bytes(conteudo)
            destino = Path(diretorio) / "schemas"
            with override_settings(FISCAL_SCHEMA_DIR=destino):
                with self.assertRaisesMessage(CommandError, "diverge do esperado"):
                    call_command(
                        "instalar_schemas_fiscais",
                        arquivo=str(origem),
                        sha256="0" * 64,
                        versao="PL_TESTE_1",
                    )
            self.assertFalse((destino / "pacotes").exists())

    def test_rejeita_url_fora_do_portal_nacional(self):
        with TemporaryDirectory() as diretorio:
            with override_settings(FISCAL_SCHEMA_DIR=Path(diretorio) / "schemas"):
                with self.assertRaisesMessage(CommandError, "Portal Nacional"):
                    call_command(
                        "instalar_schemas_fiscais",
                        url="https://example.com/schemas.zip",
                        sha256="0" * 64,
                        versao="PL_TESTE_1",
                    )
    def test_rejeita_zip_com_travessia_de_diretorio(self):
        conteudo = _pacote_zip({"../nfe_v4.00.xsd": XSD_RAIZ})
        with TemporaryDirectory() as diretorio:
            origem = Path(diretorio) / "malicioso.zip"
            origem.write_bytes(conteudo)
            with override_settings(FISCAL_SCHEMA_DIR=Path(diretorio) / "schemas"):
                with self.assertRaisesMessage(CommandError, "caminho inseguro"):
                    call_command(
                        "instalar_schemas_fiscais",
                        arquivo=str(origem),
                        sha256=hashlib.sha256(conteudo).hexdigest(),
                        versao="PL_TESTE_1",
                    )
