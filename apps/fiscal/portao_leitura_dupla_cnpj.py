"""Portao puro para leitura textual/canonica de CNPJ, ainda sem consumidores."""

import hashlib

from .estrategia_normalizacao_cnpj import canonicalizar_cnpj, validar_dv_cnpj

CONTRATO_PORTAO_LEITURA_DUPLA_CNPJ = "alphanumeric_cnpj_dual_read_gate_v1"
FRONTEIRAS_PROTEGIDAS = frozenset({"EMPRESA", "FILIAL", "LICENCA", "CREDENCIAL"})


def _impressao_digital(valor):
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:16]


def _resposta(status, fronteira, *, consulta_canonica="", detalhes=None):
    return {
        "contrato": CONTRATO_PORTAO_LEITURA_DUPLA_CNPJ,
        "status": status,
        "fronteira": fronteira,
        "encontrou": status == "ENCONTRADO_UNICO",
        "identificador": "",
        "origem": "",
        "empresa_id": "",
        "consulta": {
            "foi_canonicalizada": False,
            "impressao_digital": _impressao_digital(consulta_canonica) if consulta_canonica else "",
        },
        "diagnostico": detalhes or {},
        "seguranca": {
            "altera_dados": False,
            "consulta_banco": False,
            "retorna_cnpj_completo": False,
            "prioriza_match_textual_em_ambiguidade": False,
            "libera_consumidor_operacional": False,
            "libera_licenca": False,
            "libera_credencial": False,
            "libera_emissao": False,
        },
    }


def resolver_cnpj_por_leitura_dupla(valor_consulta, registros, *, fronteira, empresa_id=None):
    """Resolve candidatos fornecidos sem banco, escrita ou preferencia pelo texto bruto."""
    if fronteira not in FRONTEIRAS_PROTEGIDAS:
        return _resposta(
            "FRONTEIRA_INVALIDA", fronteira,
            detalhes={"fronteiras_permitidas": sorted(FRONTEIRAS_PROTEGIDAS)},
        )
    if not isinstance(registros, (list, tuple)):
        return _resposta("CONJUNTO_INVALIDO", fronteira)
    try:
        consulta_canonica = canonicalizar_cnpj(valor_consulta)
    except ValueError:
        return _resposta("CONSULTA_INVALIDA", fronteira)
    if not consulta_canonica or not validar_dv_cnpj(consulta_canonica):
        return _resposta("CONSULTA_INVALIDA", fronteira, consulta_canonica=consulta_canonica)

    entradas_malformadas = sum(not isinstance(item, dict) for item in registros)
    candidatos = [
        item for item in registros
        if isinstance(item, dict) and item.get("fronteira") == fronteira
    ]
    exige_escopo = any(str(item.get("empresa_id") or "") for item in candidatos)
    empresa_escopo = str(empresa_id or "")
    if exige_escopo and not empresa_escopo:
        return _resposta(
            "ESCOPO_EMPRESA_OBRIGATORIO", fronteira, consulta_canonica=consulta_canonica
        )
    if exige_escopo:
        candidatos = [
            item for item in candidatos if str(item.get("empresa_id") or "") == empresa_escopo
        ]

    correspondencias = []
    cadastros_invalidos = 0
    for item in candidatos:
        if not str(item.get("identificador") or "") or not str(item.get("origem") or ""):
            cadastros_invalidos += 1
            continue
        valor_cadastrado = item.get("valor")
        try:
            cadastrado_canonico = canonicalizar_cnpj(valor_cadastrado)
        except ValueError:
            cadastros_invalidos += 1
            continue
        if not cadastrado_canonico or not validar_dv_cnpj(cadastrado_canonico):
            cadastros_invalidos += 1
            continue
        if cadastrado_canonico != consulta_canonica:
            continue
        correspondencias.append({
            "identificador": str(item.get("identificador") or ""),
            "origem": str(item.get("origem") or ""),
            "empresa_id": str(item.get("empresa_id") or ""),
            "match_textual_exato": isinstance(valor_consulta, str) and valor_cadastrado == valor_consulta,
            "cadastro_diverge_do_canonico": valor_cadastrado != cadastrado_canonico,
        })

    detalhes = {
        "quantidade_correspondencias": len(correspondencias),
        "quantidade_matches_textuais": sum(item["match_textual_exato"] for item in correspondencias),
        "quantidade_matches_canonicos": len(correspondencias),
        "quantidade_cadastros_invalidos_ignorados": cadastros_invalidos + entradas_malformadas,
        "identidade_ambigua": len(correspondencias) > 1,
    }
    status = "AMBIGUO" if len(correspondencias) > 1 else (
        "ENCONTRADO_UNICO" if correspondencias else "NAO_ENCONTRADO"
    )
    resultado = _resposta(
        status, fronteira, consulta_canonica=consulta_canonica, detalhes=detalhes
    )
    resultado["consulta"]["foi_canonicalizada"] = valor_consulta != consulta_canonica
    if len(correspondencias) == 1:
        selecionado = correspondencias[0]
        resultado["identificador"] = selecionado["identificador"]
        resultado["origem"] = selecionado["origem"]
        resultado["empresa_id"] = selecionado["empresa_id"]
        resultado["diagnostico"]["match_textual_exato"] = selecionado["match_textual_exato"]
        resultado["diagnostico"]["cadastro_diverge_do_canonico"] = selecionado[
            "cadastro_diverge_do_canonico"
        ]
    return resultado


def descrever_portao_leitura_dupla_cnpj():
    """Contrato verificavel da fase, sem ativar qualquer fronteira real."""
    return {
        "contrato": CONTRATO_PORTAO_LEITURA_DUPLA_CNPJ,
        "fronteiras": sorted(FRONTEIRAS_PROTEGIDAS),
        "comparacoes": ["TEXTUAL_EXATA", "CANONICA"],
        "regras": {
            "cnpj_e_dv_validos_obrigatorios": True,
            "fronteira_explicita_obrigatoria": True,
            "escopo_empresa_quando_presente_obrigatorio": True,
            "match_textual_nao_desambigua": True,
            "mais_de_um_match_recusa_identidade": True,
            "cadastro_invalido_nao_e_selecionado": True,
            "retorno_protegido_sem_cnpj_completo": True,
        },
        "estado": {
            "funcao_pura_isolada": True,
            "consumidor_operacional_alterado": False,
            "banco_consultado": False,
            "banco_alterado": False,
            "focus_ativado": False,
            "sefaz_direta_ativada": False,
            "emissao_liberada": False,
        },
        "proximo_passo": "VERIFICAR_EXCLUSAO_DO_CATALOGO_NO_EMPACOTAMENTO",
    }
