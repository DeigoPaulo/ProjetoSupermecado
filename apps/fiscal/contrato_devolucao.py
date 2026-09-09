"""Contrato estrutural preliminar. Não valida tributação, gera XML ou acessa provedores."""
import re


CONTRATO = "supplier_return_nfe_input_v1"
GRUPOS = (
    "origem", "identificacao", "emitente", "destinatario", "produtos",
    "classificacao", "bases_valores", "ajustes_comerciais", "ipi_devolvido",
    "icms_st_fcp", "ibs_cbs", "transporte", "total_fiscal", "pagamento", "observacoes",
)
ESTADOS = ("AUSENTE", "DIVERGENTE", "SUPERADO", "NAO_SUPORTADO", "REFERENCIADO")


def validar_contrato_devolucao(conteudo):
    """Valida somente envelope e referências; REFERENCIADO não significa aprovado.

    Não aceita dados tributários livres: cada grupo carrega apenas identificadores
    e hashes das evidências. A extração autenticada do dossiê é uma etapa posterior.
    Não deve ser usado como autorização, mesmo se estrutura_valida for True.
    """
    erros = []
    bloqueios = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    permitidos = {"contrato", "rascunho_id", "empresa_id", "modelo", "operacao", "permite_emissao", "grupos"}
    for chave in conteudo.keys() - permitidos:
        erro("$", "CAMPO_DESCONHECIDO")
    for campo, esperado in (("contrato", CONTRATO), ("modelo", "55"), ("operacao", "DEVOLUCAO_COMPRA")):
        if conteudo.get(campo) != esperado:
            erro(campo, "VALOR_NAO_SUPORTADO")
    for campo in ("rascunho_id", "empresa_id"):
        if type(conteudo.get(campo)) is not int or conteudo[campo] <= 0:
            erro(campo, "IDENTIFICADOR_INVALIDO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")
    grupos = conteudo.get("grupos")
    if not isinstance(grupos, dict):
        erro("grupos", "OBJETO_OBRIGATORIO")
        grupos = {}
    if grupos.keys() - set(GRUPOS):
        erro("grupos", "GRUPO_DESCONHECIDO")
    for grupo in GRUPOS:
        caminho = f"grupos.{grupo}"
        valor = grupos.get(grupo)
        if not isinstance(valor, dict):
            erro(caminho, "GRUPO_OBRIGATORIO")
            bloqueios.append({"grupo": grupo, "codigo": "AUSENTE"})
            continue
        if set(valor) != {"estado", "referencias"}:
            erro(caminho, "CAMPOS_INVALIDOS")
        estado = valor.get("estado")
        if estado not in ESTADOS:
            erro(caminho + ".estado", "ESTADO_INVALIDO")
        referencias = valor.get("referencias")
        if not isinstance(referencias, list):
            erro(caminho + ".referencias", "LISTA_OBRIGATORIA")
            referencias = []
        vistos = set()
        for referencia in referencias:
            if not isinstance(referencia, dict) or set(referencia) != {"tipo", "id", "sha256"}:
                erro(caminho + ".referencias", "REFERENCIA_INVALIDA")
                continue
            tipo, pk, sha = referencia["tipo"], referencia["id"], referencia["sha256"]
            if not isinstance(tipo, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", tipo):
                erro(caminho + ".referencias", "TIPO_INVALIDO")
            elif type(pk) is not int or pk <= 0:
                erro(caminho + ".referencias", "IDENTIFICADOR_INVALIDO")
            else:
                if (tipo, pk) in vistos:
                    erro(caminho + ".referencias", "REFERENCIA_DUPLICADA")
                vistos.add((tipo, pk))
            if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha):
                erro(caminho + ".referencias", "HASH_INVALIDO")
        if estado == "REFERENCIADO" and not referencias:
            erro(caminho, "EVIDENCIA_OBRIGATORIA")
        if estado == "AUSENTE" and referencias:
            erro(caminho, "ESTADO_DIVERGE_DAS_REFERENCIAS")
        bloqueios.append({"grupo": grupo, "codigo": "VALIDACAO_FISCAL_NAO_IMPLEMENTADA" if estado == "REFERENCIADO" else estado if estado in ESTADOS else "ESTADO_INVALIDO"})
    bloqueios.extend({"grupo": grupo, "codigo": codigo} for grupo, codigo in (
        ("fontes", "LEITURA_INTEGRAL_E_XSD_PENDENTES"),
        ("origem", "AUTENTICIDADE_E_ATUALIDADE_NAO_VERIFICADAS"),
        ("xml", "GERACAO_NAO_IMPLEMENTADA"),
        ("transmissao", "HOMOLOGACAO_PENDENTE"),
    ))
    return {"contrato": "supplier_return_nfe_input_validation_v1", "estrutura_valida": not erros,
            "erros": erros, "bloqueios": bloqueios, "permite_gerar_xml": False, "permite_emissao": False}
