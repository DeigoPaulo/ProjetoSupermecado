"""Inventario protegido de candidatos a identidade fiscal em fontes locais."""

import hashlib
import re
from pathlib import Path


CONTRATO_INVENTARIO_ESTATICO = "static_fiscal_identity_candidate_inventory_v1"
EXTENSOES = frozenset({".py", ".md", ".json", ".yaml", ".yml"})
PADRAO_CHAVE = re.compile(r"(?<=[\"'>`])[0-9]{6}[A-Z0-9]{12}[0-9]{26}(?=[\"'<`])", re.I)
PADRAO_MASCARADO = re.compile(
    r"(?<=[\"'>`])[A-Z0-9]{2}\.[A-Z0-9]{3}\.[A-Z0-9]{3}/[A-Z0-9]{4}-[0-9]{2}(?=[\"'<`])",
    re.I,
)
PADRAO_BLOCO_14 = re.compile(r"(?<=[\"'>`])[A-Z0-9]{12}[0-9]{2}(?=[\"'<`])", re.I)
INDICADORES_IDENTIDADE = (
    "cnpj", "documento", "emitente", "destinatario", "destinatário",
    "remetente", "fornecedor", "empresa", "filial",
)


def _impressao(valor):
    return hashlib.sha256(("inventario-estatico:" + valor.upper()).encode("utf-8")).hexdigest()[:16]


def _arquivo_teste(caminho):
    nome = Path(caminho).name.lower()
    return nome == "tests.py" or nome.startswith("test_") or "/tests/" in caminho.lower()


def classificar_candidato(caminho, linha, tipo):
    caminho_normalizado = caminho.replace("\\", "/")
    contexto = linha.lower()
    if caminho_normalizado.endswith("apps/fiscal/test_support_identidades_fiscais.py"):
        return "CATALOGO_CENTRAL_TESTE"
    if caminho_normalizado.endswith("apps/fiscal/inventario_estatico_identidades_fiscais.py"):
        return "REGRA_CLASSIFICADOR"
    if caminho_normalizado.endswith("apps/empresas/services_lookup.py") and "00.000.000/0000-00" in linha:
        return "MASCARA_VISUAL"
    if "/management/commands/popular_demo.py" in caminho_normalizado or "/management/commands/criar_dados_iniciais.py" in caminho_normalizado:
        return "DEMONSTRACAO_LOCAL"
    if caminho_normalizado.startswith("docs/"):
        if "evidencias/" in caminho_normalizado or "exemplo oficial" in contexto or "normativ" in contexto:
            return "EXEMPLO_NORMATIVO_DOCUMENTADO"
        if "token" in contexto or "_json" in contexto or "configura" in contexto:
            return "DOCUMENTACAO_CONFIGURACAO"
        return "DOCUMENTACAO_REVISAR"
    if _arquivo_teste(caminho_normalizado):
        if caminho_normalizado.endswith("apps/fiscal/test_inventario_estatico_identidades_fiscais.py"):
            return "REGRA_CLASSIFICADOR_TESTE"
        if tipo == "CHAVE_44":
            return "CHAVE_FISCAL_TESTE"
        if "<cnpj>" in contexto or "infnfe" in contexto or "nfeproc" in contexto:
            return "XML_FISCAL_TESTE"
        if any(termo in caminho_normalizado for termo in (
            "test_portao_leitura_dupla_cnpj.py", "test_estrategia_normalizacao_cnpj.py",
            "test_auditoria_cnpj_alfanumerico.py",
        )) or any(termo in contexto for termo in ("valida", "invalido", "dv_", "transporte", "documento")):
            return "VALIDACAO_DOCUMENTO_TESTE"
        if caminho_normalizado.startswith("apps/empresas/") or any(
            termo in contexto for termo in (
                "cnpj", "empresa", "filial", "fornecedor", "emitente", "destinatario",
                "destinatário", "remetente",
            )
        ):
            return "IDENTIDADE_MODELO_TESTE"
        return "OUTRO_TESTE_REVISAR"
    if tipo == "CHAVE_44":
        return "CHAVE_RUNTIME_REVISAR"
    if "<cnpj>" in contexto or "infnfe" in contexto:
        return "XML_RUNTIME_REVISAR"
    if "cnpj" in contexto:
        return "IDENTIDADE_RUNTIME_REVISAR"
    return "OUTRO_RUNTIME_REVISAR"


def _ocorrencias_linha(caminho, numero_linha, linha, contexto=None):
    encontradas = []
    contexto_normalizado = (contexto or linha).lower()
    intervalos_chave = []
    for match in PADRAO_CHAVE.finditer(linha):
        intervalos_chave.append(match.span())
        encontradas.append((match.start(), "CHAVE_44", match.group(0)))
    for tipo, padrao in (("CNPJ_MASCARADO", PADRAO_MASCARADO), ("BLOCO_14", PADRAO_BLOCO_14)):
        for match in padrao.finditer(linha):
            if any(inicio <= match.start() < fim for inicio, fim in intervalos_chave):
                continue
            if tipo == "BLOCO_14" and not any(
                indicador in contexto_normalizado for indicador in INDICADORES_IDENTIDADE
            ):
                continue
            valor = match.group(0)
            encontradas.append((match.start(), tipo, valor))
    return [
        {
            "arquivo": caminho,
            "linha": numero_linha,
            "tipo": tipo,
            "finalidade": classificar_candidato(caminho, linha, tipo),
            "impressao_digital": _impressao(valor),
            "valor_exposto": False,
        }
        for _, tipo, valor in sorted(encontradas)
    ]


def inventariar_identidades_fiscais_estaticas(base_dir, *, incluir_ocorrencias=False):
    raiz = Path(base_dir).resolve()
    ocorrencias = []
    arquivos_lidos = 0
    for nome_raiz in ("apps", "docs"):
        pasta = raiz / nome_raiz
        if not pasta.is_dir():
            continue
        for arquivo in sorted(item for item in pasta.rglob("*") if item.is_file() and item.suffix.lower() in EXTENSOES):
            relativo = arquivo.relative_to(raiz).as_posix()
            try:
                linhas = arquivo.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                continue
            arquivos_lidos += 1
            for numero, linha in enumerate(linhas, 1):
                ocorrencias.extend(_ocorrencias_linha(relativo, numero, linha))

    por_finalidade = {}
    por_tipo = {}
    arquivos_com_candidatos = set()
    for item in ocorrencias:
        por_finalidade[item["finalidade"]] = por_finalidade.get(item["finalidade"], 0) + 1
        por_tipo[item["tipo"]] = por_tipo.get(item["tipo"], 0) + 1
        arquivos_com_candidatos.add(item["arquivo"])
    quantidade_revisao = sum(
        quantidade for finalidade, quantidade in por_finalidade.items() if finalidade.endswith("_REVISAR")
    )
    resultado = {
        "contrato": CONTRATO_INVENTARIO_ESTATICO,
        "data_corte": "2026-09-14",
        "resumo": {
            "arquivos_lidos": arquivos_lidos,
            "arquivos_com_candidatos": len(arquivos_com_candidatos),
            "total_candidatos": len(ocorrencias),
            "por_tipo": dict(sorted(por_tipo.items())),
            "por_finalidade": dict(sorted(por_finalidade.items())),
            "quantidade_revisao": quantidade_revisao,
        },
        "seguranca": {
            "somente_leitura_de_fontes": True,
            "consulta_banco": False,
            "altera_arquivos": False,
            "reescreve_fixtures": False,
            "valores_completos_expostos": False,
            "libera_homologacao": False,
            "libera_producao": False,
            "libera_emissao": False,
        },
        "proximo_passo": "ESPECIFICAR_ADAPTADOR_SOMBRA_DE_ESCRITA_SEM_PERSISTENCIA",
    }
    if incluir_ocorrencias:
        resultado["ocorrencias"] = ocorrencias
    return resultado
