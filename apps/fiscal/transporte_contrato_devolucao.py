"""Contrato puro e não emissivo do transporte da devolução."""
from decimal import Decimal, InvalidOperation

from .transporte_devolucao import documento_numerico_valido


CONTRATO_TRANSPORTE = "supplier_return_transport_input_v1"
CONTRATO_VALIDACAO_TRANSPORTE = "supplier_return_transport_input_validation_v1"
_CAMPOS_DADOS = {
    "modalidade", "nome", "documento", "inscricao_estadual", "endereco",
    "municipio", "uf", "quantidade_volumes", "especie", "marca",
    "numeracao", "peso_liquido", "peso_bruto", "observacao",
}


def _peso(valor):
    if not isinstance(valor, str) or not valor or "," in valor:
        return None
    try:
        numero = Decimal(valor)
        normalizado = numero.quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() and numero >= 0 and numero == normalizado else None


def validar_transporte_devolucao(conteudo):
    erros = []
    pendencias = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    def pendencia(caminho, codigo):
        pendencias.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    campos = {
        "contrato", "operacao", "permite_emissao", "origem_atual",
        "ficha_id", "ficha_sha256", "memoria_id", "memoria_sha256",
        "revisao_memoria_sha256", "dados",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_TRANSPORTE:
        erro("contrato", "VALOR_NAO_SUPORTADO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")
    if conteudo.get("origem_atual") is not True:
        pendencia("origem_atual", "FICHA_TRANSPORTE_ATUAL_PENDENTE")
    for campo in ("ficha_id", "memoria_id"):
        if type(conteudo.get(campo)) is not int or conteudo.get(campo, 0) <= 0:
            pendencia(campo, "IDENTIFICADOR_ORIGEM_PENDENTE")
    for campo in ("ficha_sha256", "memoria_sha256", "revisao_memoria_sha256"):
        valor = conteudo.get(campo)
        if not isinstance(valor, str) or len(valor) != 64 or any(c not in "0123456789abcdef" for c in valor):
            pendencia(campo, "HASH_ORIGEM_PENDENTE")

    dados = conteudo.get("dados")
    if not isinstance(dados, dict) or set(dados) != _CAMPOS_DADOS:
        erro("dados", "CAMPOS_INVALIDOS")
        dados = {}
    modalidade = dados.get("modalidade")
    if modalidade not in {"0", "1", "2", "3", "4", "9"}:
        pendencia("dados.modalidade", "MODALIDADE_PENDENTE")
    for campo, limite in (
        ("nome", 60), ("inscricao_estadual", 14), ("endereco", 60),
        ("municipio", 60), ("especie", 60), ("marca", 60),
        ("numeracao", 60), ("observacao", 500),
    ):
        if not isinstance(dados.get(campo), str) or len(dados.get(campo, "")) > limite:
            erro(f"dados.{campo}", "TEXTO_INVALIDO")
    documento = dados.get("documento")
    if not isinstance(documento, str):
        erro("dados.documento", "DOCUMENTO_INVALIDO")
    elif documento and not documento_numerico_valido(documento):
        pendencia("dados.documento", "DOCUMENTO_TRANSPORTADOR_INVALIDO")
    elif documento and not dados.get("nome"):
        pendencia("dados.nome", "NOME_TRANSPORTADOR_PENDENTE")
    uf = dados.get("uf")
    if not isinstance(uf, str) or (uf and (len(uf) != 2 or uf != uf.upper())):
        erro("dados.uf", "UF_INVALIDA")
    quantidade = dados.get("quantidade_volumes")
    if type(quantidade) is not int or not 0 <= quantidade <= 999999999:
        pendencia("dados.quantidade_volumes", "QUANTIDADE_VOLUMES_PENDENTE")
    liquido = _peso(dados.get("peso_liquido"))
    bruto = _peso(dados.get("peso_bruto"))
    if liquido is None:
        pendencia("dados.peso_liquido", "PESO_LIQUIDO_PENDENTE")
    if bruto is None:
        pendencia("dados.peso_bruto", "PESO_BRUTO_PENDENTE")
    if liquido is not None and bruto is not None and liquido > bruto:
        pendencia("dados.peso_bruto", "PESO_BRUTO_INFERIOR_AO_LIQUIDO")
    transportador = any(dados.get(campo) for campo in ("nome", "documento", "inscricao_estadual", "endereco", "municipio", "uf"))
    if modalidade == "9" and transportador:
        pendencia("dados", "SEM_TRANSPORTE_NAO_PERMITE_TRANSPORTADOR")
    volumes = any(dados.get(campo) for campo in ("especie", "marca", "numeracao"))
    if quantidade == 0 and (volumes or (liquido is not None and liquido != 0) or (bruto is not None and bruto != 0)):
        pendencia("dados", "SEM_VOLUMES_EXIGE_PESOS_ZERO")

    bloqueios = [{"grupo": "transporte", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "transporte", "codigo": "MAPEAMENTO_XML_PENDENTE"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_TRANSPORTE,
        "estrutura_valida": not erros,
        "origem_completa": not erros and not pendencias,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
