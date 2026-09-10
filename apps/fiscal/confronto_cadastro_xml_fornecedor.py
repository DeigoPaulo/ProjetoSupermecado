"""Confronto não emissivo entre cadastro atual e emitente histórico da NF-e."""

import re
import unicodedata


CONTRATO_CONFRONTO_FORNECEDOR_XML = "supplier_return_supplier_registration_xml_comparison_v1"
CONTRATO_VALIDACAO_CONFRONTO_FORNECEDOR_XML = "supplier_return_supplier_registration_xml_comparison_validation_v1"

CAMPOS_CONFRONTO = (
    ("cnpj", "CNPJ", "cnpj", "cnpj", "DIGITOS", "OBRIGATORIO"),
    ("razao_social", "Razão social", "razao_social", "razao_social", "TEXTO", "OBRIGATORIO"),
    ("nome_fantasia", "Nome fantasia", "nome_fantasia", "nome_fantasia", "TEXTO", "OPCIONAL"),
    ("indicador_ie", "Indicador de IE", "indicador_ie", None, "CODIGO", "OBRIGATORIO"),
    ("inscricao_estadual", "Inscrição estadual", "inscricao_estadual", "inscricao_estadual", "ALFANUMERICO", "CONDICIONAL"),
    ("logradouro", "Logradouro", "logradouro", "logradouro", "TEXTO", "OBRIGATORIO"),
    ("numero", "Número", "numero", "numero", "ALFANUMERICO", "OBRIGATORIO"),
    ("complemento", "Complemento", "complemento", "complemento", "TEXTO", "OPCIONAL"),
    ("bairro", "Bairro", "bairro", "bairro", "TEXTO", "OBRIGATORIO"),
    ("codigo_municipio_ibge", "Código IBGE do município", "codigo_municipio_ibge", "codigo_municipio", "DIGITOS", "OBRIGATORIO"),
    ("municipio", "Município", "municipio", "municipio", "TEXTO", "OBRIGATORIO"),
    ("uf", "UF", "uf", "uf", "ALFANUMERICO", "OBRIGATORIO"),
    ("cep", "CEP", "cep", "cep", "DIGITOS", "OBRIGATORIO"),
)

ESTADOS = {
    "COINCIDENTE": "Coincidente",
    "DIVERGENTE": "Divergente",
    "AUSENTE_NO_CADASTRO": "Ausente no cadastro atual",
    "AUSENTE_NO_XML": "Ausente no XML histórico",
    "AUSENTE_EM_AMBOS": "Ausente nas duas fontes",
    "INFORMADO_SOMENTE_NO_CADASTRO": "Informado no cadastro; sem equivalente no emitente histórico",
}


def _valor(origem, chave):
    valor = origem.get(chave, "") if isinstance(origem, dict) and chave else ""
    return str(valor or "").strip()


def _normalizar(valor, tipo):
    valor = str(valor or "").strip()
    if tipo == "DIGITOS":
        return "".join(caractere for caractere in valor if caractere.isdigit())
    if tipo in {"ALFANUMERICO", "CODIGO"}:
        return "".join(caractere for caractere in valor.upper() if caractere.isalnum())
    sem_acentos = "".join(
        caractere for caractere in unicodedata.normalize("NFKD", valor)
        if not unicodedata.combining(caractere)
    )
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", sem_acentos).upper().split())


def _documento_numerico_formatado(valor, tamanho, padrao):
    valor = str(valor or "").strip()
    return bool(re.fullmatch(padrao, valor)) and len(_normalizar(valor, "DIGITOS")) == tamanho


def _estado(valor_cadastro, valor_xml, tipo, possui_equivalente_xml):
    cadastro_normalizado = _normalizar(valor_cadastro, tipo)
    if not possui_equivalente_xml:
        return "INFORMADO_SOMENTE_NO_CADASTRO" if cadastro_normalizado else "AUSENTE_NO_CADASTRO"
    xml_normalizado = _normalizar(valor_xml, tipo)
    if cadastro_normalizado and xml_normalizado:
        return "COINCIDENTE" if cadastro_normalizado == xml_normalizado else "DIVERGENTE"
    if cadastro_normalizado:
        return "AUSENTE_NO_XML"
    if xml_normalizado:
        return "AUSENTE_NO_CADASTRO"
    return "AUSENTE_EM_AMBOS"


def _cadastro_completo(cadastro):
    obrigatorios = (
        "cnpj", "razao_social", "indicador_ie", "logradouro", "numero", "bairro",
        "codigo_municipio_ibge", "municipio", "uf", "cep",
    )
    if not all(_valor(cadastro, campo) for campo in obrigatorios):
        return False
    indicador = _valor(cadastro, "indicador_ie")
    inscricao_estadual = _valor(cadastro, "inscricao_estadual")
    formatos_validos = (
        _documento_numerico_formatado(_valor(cadastro, "cnpj"), 14, r"[0-9./-]+")
        and _documento_numerico_formatado(_valor(cadastro, "codigo_municipio_ibge"), 7, r"[0-9]+")
        and _documento_numerico_formatado(_valor(cadastro, "cep"), 8, r"[0-9-]+")
        and bool(re.fullmatch(r"[A-Za-z]{2}", _valor(cadastro, "uf")))
        and indicador in {"1", "2", "9"}
    )
    coerencia_ie = bool(inscricao_estadual) if indicador == "1" else not inscricao_estadual
    return formatos_validos and coerencia_ie


def _xml_completo(xml_historico):
    obrigatorios = (
        "cnpj", "razao_social", "inscricao_estadual", "logradouro", "numero", "bairro",
        "codigo_municipio", "municipio", "uf", "cep",
    )
    return (
        all(_valor(xml_historico, campo) for campo in obrigatorios)
        and _documento_numerico_formatado(_valor(xml_historico, "cnpj"), 14, r"[0-9./-]+")
        and _documento_numerico_formatado(_valor(xml_historico, "codigo_municipio"), 7, r"[0-9]+")
        and _documento_numerico_formatado(_valor(xml_historico, "cep"), 8, r"[0-9-]+")
        and bool(re.fullmatch(r"[A-Za-z]{2}", _valor(xml_historico, "uf")))
    )


def construir_confronto_cadastro_xml_fornecedor(*, fornecedor_id, cadastro, xml_historico, erro_xml=""):
    campos = []
    for campo, rotulo, chave_cadastro, chave_xml, tipo, obrigatoriedade in CAMPOS_CONFRONTO:
        valor_cadastro = _valor(cadastro, chave_cadastro)
        valor_xml = _valor(xml_historico, chave_xml)
        estado = _estado(valor_cadastro, valor_xml, tipo, chave_xml is not None)
        campos.append({
            "campo": campo,
            "rotulo": rotulo,
            "obrigatoriedade": obrigatoriedade,
            "valor_cadastro": valor_cadastro,
            "valor_xml_historico": valor_xml,
            "estado": estado,
            "estado_rotulo": ESTADOS[estado],
        })
    resumo = {estado: sum(item["estado"] == estado for item in campos) for estado in ESTADOS}
    conteudo = {
        "contrato": CONTRATO_CONFRONTO_FORNECEDOR_XML,
        "operacao": "DEVOLUCAO_COMPRA",
        "fornecedor_id": fornecedor_id,
        "erro_xml": str(erro_xml or ""),
        "campos": campos,
        "resumo": resumo,
        "politica": {
            "fonte_preferencial_automatica": "",
            "sobrescrever_cadastro": False,
            "sobrescrever_xml_historico": False,
            "usar_resultado_na_emissao": False,
            "exige_decisao_humana": True,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_confronto_cadastro_xml_fornecedor(conteudo)}


def validar_confronto_cadastro_xml_fornecedor(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    campos_raiz = {"contrato", "operacao", "fornecedor_id", "erro_xml", "campos", "resumo", "politica"}
    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    if set(conteudo) != campos_raiz:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_CONFRONTO_FORNECEDOR_XML:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_INVALIDA")
    if type(conteudo.get("fornecedor_id")) is not int or conteudo.get("fornecedor_id", 0) <= 0:
        erro("fornecedor_id", "IDENTIFICADOR_INVALIDO")
    erro_xml = conteudo.get("erro_xml")
    erro_xml_valido = isinstance(erro_xml, str) and len(erro_xml) <= 80
    if not erro_xml_valido:
        erro("erro_xml", "DIAGNOSTICO_XML_INVALIDO")

    campos = conteudo.get("campos")
    if not isinstance(campos, list) or len(campos) != len(CAMPOS_CONFRONTO):
        erro("campos", "CONFRONTO_INCOMPLETO")
        campos = []
    elif [item.get("campo") if isinstance(item, dict) else None for item in campos] != [
        definicao[0] for definicao in CAMPOS_CONFRONTO
    ]:
        erro("campos", "CAMPOS_CONFRONTO_DIVERGENTES")
    esperados = {item[0]: item for item in CAMPOS_CONFRONTO}
    for indice, item in enumerate(campos):
        caminho = f"campos.{indice}"
        chaves = {
            "campo", "rotulo", "obrigatoriedade", "valor_cadastro",
            "valor_xml_historico", "estado", "estado_rotulo",
        }
        if not isinstance(item, dict) or set(item) != chaves:
            erro(caminho, "ITEM_INVALIDO")
            continue
        definicao = esperados.get(item["campo"])
        if not definicao or (item["rotulo"], item["obrigatoriedade"]) != (definicao[1], definicao[5]):
            erro(caminho, "DEFINICAO_DIVERGENTE")
            continue
        if not isinstance(item["valor_cadastro"], str) or not isinstance(item["valor_xml_historico"], str):
            erro(caminho, "VALOR_INVALIDO")
            continue
        estado_esperado = _estado(
            item["valor_cadastro"], item["valor_xml_historico"], definicao[4], definicao[3] is not None
        )
        if item["estado"] != estado_esperado or item["estado_rotulo"] != ESTADOS[estado_esperado]:
            erro(caminho, "ESTADO_DIVERGENTE")

    resumo_esperado = {
        estado: sum(isinstance(item, dict) and item.get("estado") == estado for item in campos)
        for estado in ESTADOS
    }
    if conteudo.get("resumo") != resumo_esperado:
        erro("resumo", "RESUMO_DIVERGENTE")
    politica = {
        "fonte_preferencial_automatica": "",
        "sobrescrever_cadastro": False,
        "sobrescrever_xml_historico": False,
        "usar_resultado_na_emissao": False,
        "exige_decisao_humana": True,
    }
    if conteudo.get("politica") != politica:
        erro("politica", "POLITICA_INVALIDA")

    por_campo = {item.get("campo"): item for item in campos if isinstance(item, dict)}
    cadastro = {campo: por_campo.get(campo, {}).get("valor_cadastro", "") for campo, *_ in CAMPOS_CONFRONTO}
    xml_historico = {
        definicao[3]: por_campo.get(definicao[0], {}).get("valor_xml_historico", "")
        for definicao in CAMPOS_CONFRONTO if definicao[3] is not None
    }
    cadastro_completo = _cadastro_completo(cadastro)
    codigo_erro_xml = erro_xml if erro_xml_valido else "DIAGNOSTICO_XML_INVALIDO"
    xml_completo = not codigo_erro_xml and _xml_completo(xml_historico)
    divergencias = resumo_esperado["DIVERGENTE"]
    bloqueios = [{"grupo": "confronto_fornecedor_xml", "codigo": "DECISAO_HUMANA_OBRIGATORIA"}]
    if codigo_erro_xml:
        bloqueios.append({"grupo": "xml_historico", "codigo": codigo_erro_xml})
    if not cadastro_completo:
        bloqueios.append({"grupo": "cadastro_fornecedor", "codigo": "CADASTRO_FISCAL_INCOMPLETO"})
    if not xml_completo:
        bloqueios.append({"grupo": "xml_historico", "codigo": "XML_HISTORICO_INCOMPLETO"})
    if divergencias:
        bloqueios.append({"grupo": "confronto_fornecedor_xml", "codigo": "DIVERGENCIAS_CADASTRO_XML"})
    bloqueios.append({"grupo": "destinatario", "codigo": "IND_IE_DESTINATARIO_NAO_INTEGRADO"})
    return {
        "contrato": CONTRATO_VALIDACAO_CONFRONTO_FORNECEDOR_XML,
        "estrutura_valida": not erros,
        "cadastro_completo": cadastro_completo,
        "xml_historico_completo": xml_completo,
        "sem_divergencias": divergencias == 0,
        "erros": erros,
        "bloqueios": bloqueios,
        "permite_sobrescrever": False,
        "permite_gerar_xml": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }
