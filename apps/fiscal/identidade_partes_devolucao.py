"""Contrato puro e não emissivo de identificação e partes da devolução."""


CONTRATO_IDENTIDADE_PARTES = "supplier_return_identity_parties_v1"
CONTRATO_VALIDACAO_IDENTIDADE_PARTES = "supplier_return_identity_parties_validation_v1"

_CAMPOS_IDENTIFICACAO = {
    "modelo", "finalidade", "tipo_operacao", "natureza_operacao",
    "codigo_municipio_fato_gerador", "destino_operacao",
    "consumidor_final", "presenca_comprador",
}
_CAMPOS_EMITENTE = {
    "fonte", "filial_id", "cnpj", "razao_social", "nome_fantasia",
    "inscricao_estadual", "crt", "logradouro", "numero", "complemento",
    "bairro", "codigo_municipio", "municipio", "uf", "cep",
}
_CAMPOS_DESTINATARIO = {
    "fonte", "fornecedor_id", "cnpj", "razao_social", "nome_fantasia",
    "inscricao_estadual", "logradouro", "numero", "complemento", "bairro",
    "codigo_municipio", "municipio", "uf", "cep",
}


def _texto(valor, limite):
    return isinstance(valor, str) and bool(valor.strip()) and len(valor.strip()) <= limite


def _digitos(valor, tamanho):
    return isinstance(valor, str) and valor.isascii() and valor.isdigit() and len(valor) == tamanho


def validar_identidade_partes_devolucao(conteudo):
    """Valida o contrato sem banco, certificado, XML ou decisão tributária."""
    erros = []
    pendencias = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    def pendencia(caminho, codigo):
        pendencias.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    campos = {"contrato", "operacao", "permite_emissao", "identificacao", "emitente", "destinatario"}
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_IDENTIDADE_PARTES:
        erro("contrato", "VALOR_NAO_SUPORTADO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")

    identificacao = conteudo.get("identificacao")
    if not isinstance(identificacao, dict) or set(identificacao) != _CAMPOS_IDENTIFICACAO:
        erro("identificacao", "CAMPOS_INVALIDOS")
        identificacao = {}
    for campo, esperado in (("modelo", "55"), ("finalidade", "4"), ("tipo_operacao", "1")):
        if identificacao.get(campo) != esperado:
            erro(f"identificacao.{campo}", "VALOR_NAO_SUPORTADO")
    if not _texto(identificacao.get("natureza_operacao"), 60):
        pendencia("identificacao.natureza_operacao", "NATUREZA_OPERACAO_PENDENTE")
    if not _digitos(identificacao.get("codigo_municipio_fato_gerador"), 7):
        pendencia("identificacao.codigo_municipio_fato_gerador", "MUNICIPIO_FATO_GERADOR_PENDENTE")
    if identificacao.get("destino_operacao") not in {"1", "2", "3"}:
        pendencia("identificacao.destino_operacao", "DESTINO_OPERACAO_PENDENTE")
    if identificacao.get("consumidor_final") not in {"0", "1"}:
        pendencia("identificacao.consumidor_final", "CONSUMIDOR_FINAL_PENDENTE")
    if identificacao.get("presenca_comprador") not in {"0", "1", "2", "3", "4", "5", "9"}:
        pendencia("identificacao.presenca_comprador", "PRESENCA_COMPRADOR_PENDENTE")

    emitente = conteudo.get("emitente")
    if not isinstance(emitente, dict) or set(emitente) != _CAMPOS_EMITENTE:
        erro("emitente", "CAMPOS_INVALIDOS")
        emitente = {}
    if emitente.get("fonte") != "FILIAL_E_CONFIGURACAO_FISCAL":
        erro("emitente.fonte", "FONTE_INVALIDA")
    if type(emitente.get("filial_id")) is not int or emitente.get("filial_id", 0) <= 0:
        erro("emitente.filial_id", "IDENTIFICADOR_INVALIDO")
    _validar_parte(emitente, "emitente", pendencia, exige_crt=True)

    destinatario = conteudo.get("destinatario")
    if not isinstance(destinatario, dict) or set(destinatario) != _CAMPOS_DESTINATARIO:
        erro("destinatario", "CAMPOS_INVALIDOS")
        destinatario = {}
    if destinatario.get("fonte") != "XML_ORIGINAL_E_CADASTRO_FORNECEDOR":
        erro("destinatario.fonte", "FONTE_INVALIDA")
    if type(destinatario.get("fornecedor_id")) is not int or destinatario.get("fornecedor_id", 0) <= 0:
        erro("destinatario.fornecedor_id", "IDENTIFICADOR_INVALIDO")
    _validar_parte(destinatario, "destinatario", pendencia, exige_crt=False)

    bloqueios = [{"grupo": item["caminho"].split(".", 1)[0], "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "partes", "codigo": "CNPJ_ALFANUMERICO_NAO_SUPORTADO"},
        {"grupo": "vigencia", "codigo": "REGRAS_E_VIGENCIAS_PENDENTES"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_IDENTIDADE_PARTES,
        "estrutura_valida": not erros,
        "dados_completos": not erros and not pendencias,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }


def _validar_parte(parte, caminho, pendencia, *, exige_crt):
    if not _digitos(parte.get("cnpj"), 14):
        pendencia(f"{caminho}.cnpj", "CNPJ_NUMERICO_14_PENDENTE")
    for campo, limite, codigo in (
        ("razao_social", 60, "RAZAO_SOCIAL_PENDENTE"),
        ("logradouro", 60, "LOGRADOURO_PENDENTE"),
        ("numero", 60, "NUMERO_ENDERECO_PENDENTE"),
        ("bairro", 60, "BAIRRO_PENDENTE"),
        ("municipio", 60, "MUNICIPIO_PENDENTE"),
    ):
        if not _texto(parte.get(campo), limite):
            pendencia(f"{caminho}.{campo}", codigo)
    if not _texto(parte.get("inscricao_estadual"), 30):
        pendencia(f"{caminho}.inscricao_estadual", "INSCRICAO_ESTADUAL_PENDENTE")
    if not _digitos(parte.get("codigo_municipio"), 7):
        pendencia(f"{caminho}.codigo_municipio", "CODIGO_MUNICIPIO_PENDENTE")
    if not isinstance(parte.get("uf"), str) or len(parte["uf"]) != 2 or parte["uf"] != parte["uf"].upper():
        pendencia(f"{caminho}.uf", "UF_PENDENTE")
    if not _digitos(parte.get("cep"), 8):
        pendencia(f"{caminho}.cep", "CEP_PENDENTE")
    if exige_crt and parte.get("crt") not in {"1", "2", "3", "4"}:
        pendencia(f"{caminho}.crt", "CRT_PENDENTE")
