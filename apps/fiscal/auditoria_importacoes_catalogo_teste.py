"""Portao estatico contra uso do catalogo fiscal de teste em runtime."""

import ast
from pathlib import Path


CONTRATO_AUDITORIA_IMPORTACOES_CATALOGO = "fiscal_test_catalog_import_gate_v1"
MODULO_PROTEGIDO = "test_support_identidades_fiscais"


def _arquivo_teste(caminho):
    normalizado = caminho.replace("\\", "/").lower()
    nome = Path(normalizado).name
    return nome == "tests.py" or nome.startswith("test_") or "/tests/" in normalizado


def _referencia_modulo_protegido(nome):
    partes = str(nome or "").split(".")
    return MODULO_PROTEGIDO in partes


def _importacoes_protegidas(arvore):
    importacoes = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                if _referencia_modulo_protegido(alias.name):
                    importacoes.append((no.lineno, "IMPORT", alias.name))
        elif isinstance(no, ast.ImportFrom):
            modulo = no.module or ""
            for alias in no.names:
                if _referencia_modulo_protegido(modulo) or alias.name == MODULO_PROTEGIDO:
                    referencia = ".".join(parte for parte in (modulo, alias.name) if parte)
                    importacoes.append((no.lineno, "IMPORT_FROM", referencia))
        elif isinstance(no, ast.Call) and no.args:
            funcao = no.func
            importacao_dinamica = (
                isinstance(funcao, ast.Name)
                and funcao.id in {"__import__", "import_module"}
            ) or (
                isinstance(funcao, ast.Attribute) and funcao.attr == "import_module"
            )
            primeiro_argumento = no.args[0]
            if (
                importacao_dinamica
                and isinstance(primeiro_argumento, ast.Constant)
                and isinstance(primeiro_argumento.value, str)
                and _referencia_modulo_protegido(primeiro_argumento.value)
            ):
                importacoes.append(
                    (no.lineno, "IMPORT_DINAMICO", primeiro_argumento.value)
                )
    return sorted(set(importacoes))


def auditar_importacoes_catalogo_teste(base_dir, *, incluir_detalhes=False):
    """Analisa ASTs sob apps sem importar modulos nem consultar o banco."""
    raiz = Path(base_dir).resolve()
    pasta_apps = raiz / "apps"
    violacoes = []
    erros = []
    arquivos_lidos = 0
    importacoes_permitidas = 0

    if pasta_apps.is_dir():
        for arquivo in sorted(pasta_apps.rglob("*.py")):
            if not arquivo.is_file():
                continue
            relativo = arquivo.relative_to(raiz).as_posix()
            try:
                conteudo = arquivo.read_text(encoding="utf-8")
                arvore = ast.parse(conteudo, filename=relativo)
            except (OSError, UnicodeError, SyntaxError) as exc:
                erros.append({
                    "arquivo": relativo,
                    "tipo": type(exc).__name__,
                    "linha": int(getattr(exc, "lineno", 0) or 0),
                })
                continue
            arquivos_lidos += 1
            importacoes = _importacoes_protegidas(arvore)
            if _arquivo_teste(relativo):
                importacoes_permitidas += len(importacoes)
                continue
            for linha, mecanismo, modulo in importacoes:
                violacoes.append({
                    "arquivo": relativo,
                    "linha": linha,
                    "mecanismo": mecanismo,
                    "modulo": modulo,
                })

    conforme = not violacoes and not erros
    resultado = {
        "contrato": CONTRATO_AUDITORIA_IMPORTACOES_CATALOGO,
        "conforme": conforme,
        "resumo": {
            "arquivos_python_lidos": arquivos_lidos,
            "importacoes_permitidas_em_testes": importacoes_permitidas,
            "importacoes_runtime_bloqueadas": len(violacoes),
            "erros_leitura_ou_sintaxe": len(erros),
        },
        "seguranca": {
            "analise_ast_sem_importar_modulos": True,
            "consulta_banco": False,
            "altera_arquivos": False,
            "altera_configuracao": False,
            "libera_homologacao": False,
            "libera_producao": False,
            "libera_emissao": False,
        },
        "proximo_passo": "INTEGRAR_PORTAO_A_ROTINA_PADRAO_DE_VERIFICACAO",
    }
    if incluir_detalhes or not conforme:
        resultado["violacoes"] = violacoes
        resultado["erros"] = erros
    return resultado
