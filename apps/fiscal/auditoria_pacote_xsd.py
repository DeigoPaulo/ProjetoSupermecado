"""Auditoria offline e sem promoção de pacotes XSD NF-e/NFC-e."""

import hashlib
import io
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from lxml import etree


CONTRATO_AUDITORIA_XSD = "fiscal_schema_package_audit_v1"
LIMITE_PACOTE = 25 * 1024 * 1024
LIMITE_EXTRAIDO = 100 * 1024 * 1024
LIMITE_ARQUIVOS = 500
COMPRESSOES_PERMITIDAS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
XSD_NS = "http://www.w3.org/2001/XMLSchema"


class AuditoriaPacoteXSDErro(ValueError):
    pass


def _sha256(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def _validar_sha256(valor):
    esperado = (valor or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", esperado):
        raise AuditoriaPacoteXSDErro("O SHA-256 esperado deve possuir 64 caracteres hexadecimais.")
    return esperado


def _validar_versao(valor):
    versao = (valor or "").strip()
    if not versao or re.sub(r"[^A-Za-z0-9._-]+", "-", versao).strip(".-") != versao:
        raise AuditoriaPacoteXSDErro("A versão do pacote deve usar somente letras, números, ponto, hífen ou sublinhado.")
    return versao


def _nome_seguro(info):
    nome = PurePosixPath(info.filename.replace("\\", "/"))
    if nome.is_absolute() or not nome.parts or ".." in nome.parts or re.match(r"^[A-Za-z]:", str(nome)):
        raise AuditoriaPacoteXSDErro("O pacote XSD contém caminho inseguro.")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise AuditoriaPacoteXSDErro("O pacote XSD não pode conter link simbólico.")
    return nome


def _resolver_relativo(base, referencia):
    parsed = urlparse(referencia)
    if parsed.scheme or parsed.netloc or referencia.startswith(("/", "\\")):
        raise AuditoriaPacoteXSDErro("Dependência XSD externa ou absoluta não é permitida.")
    partes = list(base.parent.parts)
    for parte in PurePosixPath(referencia.replace("\\", "/")).parts:
        if parte in {"", "."}:
            continue
        if parte == "..":
            if not partes:
                raise AuditoriaPacoteXSDErro("Dependência XSD escapa da raiz do pacote.")
            partes.pop()
        else:
            partes.append(parte)
    return PurePosixPath(*partes)


def _dependencias_xsd(arquivos):
    caminhos = set(arquivos)
    dependencias = []
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    for caminho in sorted(caminhos, key=str):
        try:
            raiz = etree.fromstring(arquivos[caminho], parser)
        except etree.XMLSyntaxError as exc:
            raise AuditoriaPacoteXSDErro(f"XSD malformado: {caminho}.") from exc
        for elemento in raiz.xpath(
            "//xs:include[@schemaLocation] | //xs:import[@schemaLocation] | //xs:redefine[@schemaLocation]",
            namespaces={"xs": XSD_NS},
        ):
            referencia = elemento.get("schemaLocation", "").strip()
            resolvido = _resolver_relativo(caminho, referencia)
            if resolvido not in caminhos:
                raise AuditoriaPacoteXSDErro(
                    f"Dependência XSD ausente: {referencia} referenciada por {caminho}."
                )
            dependencias.append(
                {
                    "arquivo": str(caminho),
                    "referencia": referencia,
                    "resolvido": str(resolvido),
                }
            )
    return sorted(dependencias, key=lambda item: (item["arquivo"], item["referencia"]))


def _compilar_raiz(arquivos, raiz):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        with tempfile.TemporaryDirectory(prefix="auditoria-xsd-") as temporario:
            base = Path(temporario)
            for nome, conteudo in arquivos.items():
                alvo = base.joinpath(*nome.parts)
                alvo.parent.mkdir(parents=True, exist_ok=True)
                alvo.write_bytes(conteudo)
            etree.XMLSchema(etree.parse(str(base.joinpath(*raiz.parts)), parser))
    except (OSError, etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        raise AuditoriaPacoteXSDErro("O schema raiz ou suas dependências não compilam offline.") from exc


def auditar_pacote_xsd(*, arquivo, sha256_esperado, versao, arquivo_raiz="nfe_v4.00.xsd"):
    esperado = _validar_sha256(sha256_esperado)
    versao = _validar_versao(versao)
    origem = Path(arquivo).expanduser()
    if origem.is_symlink():
        raise AuditoriaPacoteXSDErro("Arquivo ZIP local, regular e existente é obrigatório.")
    caminho = origem.resolve()
    if not caminho.is_file():
        raise AuditoriaPacoteXSDErro("Arquivo ZIP local, regular e existente é obrigatório.")
    if caminho.stat().st_size > LIMITE_PACOTE:
        raise AuditoriaPacoteXSDErro("O pacote XSD excede o limite de tamanho.")
    conteudo = caminho.read_bytes()
    if len(conteudo) > LIMITE_PACOTE:
        raise AuditoriaPacoteXSDErro("O pacote XSD excede o limite de tamanho.")
    calculado = _sha256(conteudo)
    if calculado != esperado:
        raise AuditoriaPacoteXSDErro(f"SHA-256 do pacote diverge do esperado: {calculado}.")

    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            infos = [info for info in pacote.infolist() if not info.is_dir()]
            if not infos or len(infos) > LIMITE_ARQUIVOS:
                raise AuditoriaPacoteXSDErro("A quantidade de arquivos do pacote XSD é inválida.")
            if sum(info.file_size for info in infos) > LIMITE_EXTRAIDO:
                raise AuditoriaPacoteXSDErro("O conteúdo descompactado excede o limite permitido.")
            nomes = []
            for info in infos:
                nome = _nome_seguro(info)
                if nome.suffix.lower() != ".xsd":
                    raise AuditoriaPacoteXSDErro("O pacote de schemas contém arquivo não XSD.")
                if info.flag_bits & 0x1:
                    raise AuditoriaPacoteXSDErro("O pacote XSD não pode conter arquivo criptografado.")
                if info.compress_type not in COMPRESSOES_PERMITIDAS:
                    raise AuditoriaPacoteXSDErro("O pacote XSD usa compressão não permitida.")
                nomes.append(nome)
            chaves_nomes = [str(nome).casefold() for nome in nomes]
            if len(chaves_nomes) != len(set(chaves_nomes)):
                raise AuditoriaPacoteXSDErro("O pacote XSD contém caminhos duplicados.")
            membro_corrompido = pacote.testzip()
            if membro_corrompido:
                raise AuditoriaPacoteXSDErro(f"Falha de CRC no membro {membro_corrompido}.")
            arquivos = {nome: pacote.read(str(nome)) for nome in nomes}
    except zipfile.BadZipFile as exc:
        raise AuditoriaPacoteXSDErro("O arquivo informado não é um ZIP XSD íntegro.") from exc

    candidatos = [nome for nome in arquivos if nome.name == arquivo_raiz]
    if len(candidatos) != 1:
        raise AuditoriaPacoteXSDErro(
            f"O pacote deve conter exatamente um {arquivo_raiz}; encontrados: {len(candidatos)}."
        )
    raiz = candidatos[0]
    dependencias = _dependencias_xsd(arquivos)
    _compilar_raiz(arquivos, raiz)
    inventario = [
        {
            "caminho": str(nome),
            "tamanho": len(arquivos[nome]),
            "sha256": _sha256(arquivos[nome]),
        }
        for nome in sorted(arquivos, key=str)
    ]
    return {
        "contrato": CONTRATO_AUDITORIA_XSD,
        "resultado": "INTEGRO_TECNICAMENTE_SEM_PROMOCAO",
        "versao": versao,
        "pacote": {
            "nome": caminho.name,
            "tamanho": len(conteudo),
            "sha256": calculado,
            "crc_integro": True,
        },
        "schema": {
            "arquivo_raiz": str(raiz),
            "arquivo_raiz_sha256": _sha256(arquivos[raiz]),
            "arquivos_xsd": inventario,
            "dependencias": dependencias,
            "compilacao_offline": True,
        },
        "promocao_versionada": {
            "destino_relativo_candidato": f"pacotes/{versao}",
            "integridade_tecnica_confirmada": True,
            "aplicabilidade_aprovada": False,
            "instalacao_executada": False,
            "ativacao_executada": False,
            "bloqueios": [
                "APLICABILIDADE_NORMATIVA_PENDENTE",
                "APROVACAO_FISCAL_PENDENTE",
                "HOMOLOGACAO_SEPARADA_PENDENTE",
                "CONFIGURACAO_EXPLICITA_PENDENTE",
            ],
        },
        "politica": {
            "somente_offline": True,
            "extracao_persistente": False,
            "acessou_rede": False,
            "alterou_fiscal_schemas": False,
            "alterou_configuracao": False,
            "aprovou_pacote": False,
            "gerou_xml": False,
            "assinou": False,
            "transmitiu": False,
        },
    }