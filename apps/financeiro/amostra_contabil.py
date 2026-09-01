import hashlib
import json
from datetime import date
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.auditoria.models import LogAuditoria

from .models import (
    AceiteAmostraContabil,
    FormatoEntregaContabil,
    StatusContratoIntegracaoContabil,
)


CONTRATO_VALIDACAO = "accounting_monthly_sample_validation_v1"
LIMITE_PACOTE_BYTES = 512 * 1024 * 1024
LIMITE_MANIFESTO_BYTES = 5 * 1024 * 1024
LIMITE_RECONCILIACAO_BYTES = 20 * 1024 * 1024
ARQUIVOS_OBRIGATORIOS = {
    "manifesto.json",
    "reconciliacao/resumo.json",
    "reconciliacao/vendas.csv",
    "reconciliacao/entradas.csv",
    "fiscal/documentos-saida.csv",
    "fiscal/documentos-entrada.csv",
    "fiscal/itens-fiscais.csv",
    "fiscal/eventos.csv",
    "estoque/inventario-valorizado.csv",
}


def _erro(erros, codigo, mensagem):
    erros.append({"codigo": codigo, "mensagem": mensagem})


def _aviso(avisos, codigo, mensagem):
    avisos.append({"codigo": codigo, "mensagem": mensagem})


def _hash_arquivo_zip(arquivo_zip, nome):
    digest = hashlib.sha256()
    with arquivo_zip.open(nome) as origem:
        while True:
            bloco = origem.read(1024 * 1024)
            if not bloco:
                break
            digest.update(bloco)
    return digest.hexdigest()


def validar_amostra_contabil(*, pacote_bytes, empresa, contrato_integracao):
    erros = []
    avisos = []
    pacote_sha256 = hashlib.sha256(pacote_bytes).hexdigest()
    relatorio = {
        "contrato": CONTRATO_VALIDACAO,
        "aprovado": False,
        "empresa_id": empresa.pk,
        "pacote_sha256": pacote_sha256,
        "contrato_integracao_versao": getattr(contrato_integracao, "versao", None),
        "erros": erros,
        "avisos": avisos,
        "contagens": {},
    }
    if not contrato_integracao or contrato_integracao.empresa_id != empresa.pk:
        _erro(erros, "CONTRATO_EMPRESA_INVALIDO", "Não existe contrato contábil da empresa selecionada.")
        return relatorio
    if contrato_integracao.status != StatusContratoIntegracaoContabil.VALIDADO:
        _erro(erros, "CONTRATO_NAO_VALIDADO", "A amostra exige uma versão validada do contrato contábil.")
    if contrato_integracao.formato_entrega != FormatoEntregaContabil.PACOTE_ZIP_V2:
        _erro(erros, "FORMATO_INCOMPATIVEL", "A amostra mensal exige contrato para o pacote ZIP v2.")
    if len(pacote_bytes) > LIMITE_PACOTE_BYTES:
        _erro(erros, "LIMITE_PACOTE", "O arquivo ZIP excede o limite de tamanho da validação.")
        return relatorio
    try:
        arquivo_zip = ZipFile(BytesIO(pacote_bytes))
    except BadZipFile:
        _erro(erros, "ZIP_INVALIDO", "O pacote mensal não é um ZIP válido.")
        return relatorio
    with arquivo_zip:
        informacoes = arquivo_zip.infolist()
        nomes = [info.filename for info in informacoes]
        if len(nomes) != len(set(nomes)):
            _erro(erros, "ARQUIVO_DUPLICADO", "O ZIP contém caminhos duplicados.")
        if len(nomes) > 5000:
            _erro(erros, "LIMITE_ARQUIVOS", "O ZIP excede o limite de arquivos da validação.")
        if sum(info.file_size for info in informacoes) > 2 * 1024 * 1024 * 1024:
            _erro(erros, "LIMITE_CONTEUDO", "O conteúdo descompactado excede o limite da validação.")
        for nome in nomes:
            caminho = PurePosixPath(nome)
            if not nome or "\\" in nome or caminho.is_absolute() or ".." in caminho.parts:
                _erro(erros, "CAMINHO_INSEGURO", "O ZIP contém caminho interno inseguro.")
                break
        ausentes = sorted(ARQUIVOS_OBRIGATORIOS - set(nomes))
        if ausentes:
            _erro(erros, "ARQUIVOS_OBRIGATORIOS_AUSENTES", "Faltam arquivos obrigatórios na amostra.")
        if "manifesto.json" not in nomes:
            return relatorio
        if arquivo_zip.getinfo("manifesto.json").file_size > LIMITE_MANIFESTO_BYTES:
            _erro(erros, "LIMITE_MANIFESTO", "O manifesto excede o limite de tamanho da validação.")
            return relatorio
        try:
            manifesto = json.loads(arquivo_zip.read("manifesto.json"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            _erro(erros, "MANIFESTO_INVALIDO", "O manifesto do pacote não é JSON válido.")
            return relatorio
        if manifesto.get("contrato") != "accounting_monthly_package_v2":
            _erro(erros, "CONTRATO_PACOTE_INVALIDO", "O pacote não segue accounting_monthly_package_v2.")
        empresa_manifesto = manifesto.get("empresa") or {}
        if empresa_manifesto.get("id") != empresa.pk:
            _erro(erros, "EMPRESA_DIVERGENTE", "O manifesto pertence a outra empresa.")
        contrato_manifesto = manifesto.get("contrato_integracao_contabil") or {}
        if not contrato_manifesto.get("validado"):
            _erro(erros, "CONTRATO_AUSENTE_NO_PACOTE", "O pacote não declara contrato contábil validado.")
        if contrato_manifesto.get("versao_validada") != contrato_integracao.versao:
            _erro(erros, "VERSAO_CONTRATO_DIVERGENTE", "O pacote não corresponde à versão de contrato selecionada.")
        declarados = manifesto.get("arquivos")
        if not isinstance(declarados, list):
            _erro(erros, "INTEGRIDADE_AUSENTE", "O manifesto não contém a lista de integridade.")
            declarados = []
        caminhos_declarados = set()
        for item in declarados:
            if not isinstance(item, dict):
                _erro(erros, "INTEGRIDADE_INVALIDA", "A lista de integridade possui item inválido.")
                continue
            nome = item.get("caminho")
            if not nome or nome in caminhos_declarados:
                _erro(erros, "INTEGRIDADE_DUPLICADA", "A lista de integridade possui caminho ausente ou duplicado.")
                continue
            caminhos_declarados.add(nome)
            if nome not in nomes:
                _erro(erros, "ARQUIVO_DECLARADO_AUSENTE", "Um arquivo declarado não existe no ZIP.")
                continue
            info = arquivo_zip.getinfo(nome)
            if item.get("bytes") != info.file_size or item.get("sha256") != _hash_arquivo_zip(arquivo_zip, nome):
                _erro(erros, "HASH_DIVERGENTE", "Tamanho ou SHA-256 de arquivo diverge do manifesto.")
        extras = set(nomes) - caminhos_declarados - {"manifesto.json"}
        if extras:
            _erro(erros, "ARQUIVO_NAO_DECLARADO", "O ZIP contém arquivo não declarado no manifesto.")
        contagens = manifesto.get("contagens") or {}
        relatorio["contagens"] = {
            chave: int(contagens.get(chave) or 0)
            for chave in (
                "documentos_saida", "documentos_entrada", "itens_fiscais", "eventos",
                "itens_inventario", "vendas_reconciliadas", "vendas_divergentes",
                "entradas_reconciliadas", "entradas_divergentes",
            )
        }
        if relatorio["contagens"]["documentos_saida"] <= 0:
            _erro(erros, "SEM_DOCUMENTOS_SAIDA", "A amostra mensal não possui documento fiscal de saída.")
        xml_saida = sum(1 for nome in nomes if nome.startswith("fiscal/xml/saida/") and nome.endswith(".xml"))
        if xml_saida < relatorio["contagens"]["documentos_saida"]:
            _erro(erros, "XML_SAIDA_INCOMPLETO", "Nem todos os documentos de saída possuem XML no pacote.")
        documentos_entrada = relatorio["contagens"]["documentos_entrada"]
        xml_entrada = sum(1 for nome in nomes if nome.startswith("fiscal/xml/entrada/") and nome.endswith(".xml"))
        if documentos_entrada and xml_entrada < documentos_entrada:
            _erro(erros, "XML_ENTRADA_INCOMPLETO", "Nem todos os documentos de entrada possuem XML no pacote.")
        if not documentos_entrada:
            _aviso(avisos, "SEM_DOCUMENTOS_ENTRADA", "A competência não contém documento fiscal de entrada.")
        if relatorio["contagens"]["vendas_divergentes"]:
            _erro(erros, "VENDAS_DIVERGENTES", "Existem vendas divergentes na reconciliação operacional.")
        if relatorio["contagens"]["entradas_divergentes"]:
            _erro(erros, "ENTRADAS_DIVERGENTES", "Existem entradas divergentes na reconciliação operacional.")
        inventario = manifesto.get("inventario") or {}
        if not inventario.get("snapshot_completo"):
            _erro(erros, "INVENTARIO_SEM_FECHAMENTO", "O inventário não possui fechamento imutável completo.")
        if "reconciliacao/resumo.json" in nomes:
            if arquivo_zip.getinfo("reconciliacao/resumo.json").file_size > LIMITE_RECONCILIACAO_BYTES:
                _erro(erros, "LIMITE_RECONCILIACAO", "O resumo da reconciliação excede o limite de tamanho.")
                return relatorio
            try:
                reconciliacao = json.loads(arquivo_zip.read("reconciliacao/resumo.json"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                _erro(erros, "RECONCILIACAO_INVALIDA", "O resumo da reconciliação não é JSON válido.")
            else:
                if reconciliacao.get("contrato") != "accounting_operational_reconciliation_v1":
                    _erro(erros, "CONTRATO_RECONCILIACAO_INVALIDO", "O resumo usa contrato de reconciliação incompatível.")
    relatorio["aprovado"] = not erros
    return relatorio


@transaction.atomic
def registrar_aceite_amostra(
    *, empresa, competencia, contrato_integracao, pacote_bytes,
    relatorio_validacao, referencia_aceite, usuario, ip=None,
):
    if not usuario or not usuario.is_active or not usuario.is_superuser:
        raise PermissionDenied("Somente o Master pode registrar o aceite da amostra contábil.")
    if isinstance(competencia, str):
        try:
            ano, mes = (int(parte) for parte in competencia.split("-", 1))
            competencia = date(ano, mes, 1)
        except (TypeError, ValueError):
            raise ValidationError("Competência inválida. Informe AAAA-MM.")
    pacote_sha256 = hashlib.sha256(pacote_bytes).hexdigest()
    if relatorio_validacao.get("contrato") != CONTRATO_VALIDACAO:
        raise ValidationError("Relatório de validação incompatível.")
    if relatorio_validacao.get("pacote_sha256") != pacote_sha256:
        raise ValidationError("O pacote não corresponde ao relatório validado.")
    if relatorio_validacao.get("contrato_integracao_versao") != contrato_integracao.versao:
        raise ValidationError("A versão do contrato diverge do relatório validado.")
    existente = AceiteAmostraContabil.objects.filter(
        empresa=empresa, competencia=competencia, pacote_sha256=pacote_sha256
    ).first()
    if existente:
        if existente.contrato_integracao_id != contrato_integracao.pk:
            raise ValidationError("A amostra já foi aceita com outra versão de contrato.")
        return existente, False
    aceite = AceiteAmostraContabil(
        empresa=empresa,
        competencia=competencia,
        contrato_integracao=contrato_integracao,
        pacote_sha256=pacote_sha256,
        relatorio_validacao=relatorio_validacao,
        referencia_aceite=(referencia_aceite or "").strip(),
        registrado_por=usuario,
    )
    aceite.save()
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="REGISTRAR_ACEITE_AMOSTRA_CONTABIL",
        descricao=(
            f"Amostra contábil {competencia:%Y-%m} aceita para {empresa.nome_fantasia}; "
            f"contrato v{contrato_integracao.versao}."
        ),
        objeto_tipo="AceiteAmostraContabil",
        objeto_id=str(aceite.pk),
        ip=ip,
    )
    return aceite, True


