"""Auditoria somente leitura para preparar CNPJ e chaves alfanumericas."""

import hashlib
import re

from .estrategia_normalizacao_cnpj import canonicalizar_cnpj, validar_chave_acesso, validar_dv_cnpj


CONTRATO_AUDITORIA_CNPJ = "alphanumeric_cnpj_readonly_audit_v1"
PADRAO_CHAVE = re.compile(r"^[0-9]{6}[A-Z0-9]{12}[0-9]{26}$")
PADRAO_CPF_PURO = re.compile(r"^[0-9]{11}$")
PADRAO_CPF_MASCARADO = re.compile(r"^[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}$")


def _impressao_digital(valor):
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:16]


def _ocultar(valor):
    if len(valor) <= 4:
        return "*" * len(valor)
    return valor[:2] + ("*" * (len(valor) - 4)) + valor[-2:]


def _eh_cpf_em_campo_misto(valor):
    texto = str(valor or "").strip()
    return bool(PADRAO_CPF_PURO.fullmatch(texto) or PADRAO_CPF_MASCARADO.fullmatch(texto))


def _item_base(registro, status, *, canonico="", detalhe=""):
    item = {
        "origem": registro["origem"],
        "identificador": str(registro["identificador"]),
        "empresa_id": str(registro.get("empresa_id") or ""),
        "papel": registro["papel"],
        "status": status,
        "detalhe": detalhe,
        "valor_oculto": _ocultar(canonico) if canonico else "",
        "impressao_digital": _impressao_digital(canonico) if canonico else "",
    }
    return item


def auditar_identificadores(registros_cnpj, registros_chave):
    itens_cnpj = []
    grupos_cnpj = {}
    for registro in registros_cnpj:
        valor = registro.get("valor")
        if registro.get("campo_misto") and _eh_cpf_em_campo_misto(valor):
            itens_cnpj.append(_item_base(registro, "IGNORADO_CPF"))
            continue
        if not str(valor or "").strip():
            status = "AUSENTE_OBRIGATORIO" if registro.get("obrigatorio") else "VAZIO_PERMITIDO"
            itens_cnpj.append(_item_base(registro, status))
            continue
        try:
            canonico = canonicalizar_cnpj(valor)
        except ValueError as exc:
            itens_cnpj.append(_item_base(registro, "FORMATO_INVALIDO", detalhe=str(exc)))
            continue
        status = "VALIDO" if validar_dv_cnpj(canonico) else "DV_INVALIDO"
        item = _item_base(registro, status, canonico=canonico)
        item_interno = {**item, "_canonico": canonico, "_dominio": registro.get("dominio", "")}
        itens_cnpj.append(item)
        if registro["papel"] == "IDENTIDADE":
            grupos_cnpj.setdefault(canonico, []).append(item_interno)

    colisoes = []
    for canonico, grupo in sorted(grupos_cnpj.items()):
        if len(grupo) < 2:
            continue
        dominios = [item["_dominio"] for item in grupo if item["_dominio"]]
        mesmas_fronteiras = len(dominios) != len(set(dominios))
        origens = {item["origem"] for item in grupo}
        empresa = next((item for item in grupo if item["origem"] == "Empresa"), None)
        filiais = [item for item in grupo if item["origem"] == "Filial"]
        somente_empresa_e_filiais = origens.issubset({"Empresa", "Filial"}) and empresa is not None
        filiais_da_empresa = somente_empresa_e_filiais and all(
            filial["empresa_id"] == empresa["identificador"] for filial in filiais
        )
        if mesmas_fronteiras or (empresa and filiais and not filiais_da_empresa):
            classificacao = "BLOQUEANTE"
        elif somente_empresa_e_filiais and filiais_da_empresa:
            classificacao = "ESPERADA_EMPRESA_FILIAL"
        else:
            classificacao = "REVISAR_PAPEIS_DISTINTOS"
        colisoes.append({
            "impressao_digital": _impressao_digital(canonico),
            "valor_oculto": _ocultar(canonico),
            "classificacao": classificacao,
            "registros": [
                {chave: valor for chave, valor in item.items() if not chave.startswith("_")}
                for item in grupo
            ],
        })

    itens_chave = []
    for registro in registros_chave:
        valor = str(registro.get("valor") or "").strip().upper()
        if not valor:
            status = "AUSENTE_OBRIGATORIA" if registro.get("obrigatorio") else "VAZIA_PERMITIDA"
            itens_chave.append(_item_base(registro, status))
            continue
        if not PADRAO_CHAVE.fullmatch(valor):
            itens_chave.append(_item_base(registro, "FORMATO_INVALIDO", canonico=valor))
            continue
        status = "VALIDA" if validar_chave_acesso(valor) else "DV_INVALIDO"
        itens_chave.append(_item_base(registro, status, canonico=valor))

    contagens_cnpj = {}
    for item in itens_cnpj:
        contagens_cnpj[item["status"]] = contagens_cnpj.get(item["status"], 0) + 1
    contagens_chave = {}
    for item in itens_chave:
        contagens_chave[item["status"]] = contagens_chave.get(item["status"], 0) + 1
    contagens_colisoes = {}
    for item in colisoes:
        chave = item["classificacao"]
        contagens_colisoes[chave] = contagens_colisoes.get(chave, 0) + 1

    bloqueios = (
        contagens_cnpj.get("AUSENTE_OBRIGATORIO", 0)
        + contagens_cnpj.get("FORMATO_INVALIDO", 0)
        + contagens_cnpj.get("DV_INVALIDO", 0)
        + contagens_chave.get("AUSENTE_OBRIGATORIA", 0)
        + contagens_chave.get("FORMATO_INVALIDO", 0)
        + contagens_chave.get("DV_INVALIDO", 0)
        + contagens_colisoes.get("BLOQUEANTE", 0)
    )
    return {
        "contrato": CONTRATO_AUDITORIA_CNPJ,
        "data_corte": "2026-09-14",
        "base": "ENSAIO_LOCAL_NAO_ACEITE_PRODUCAO",
        "resumo": {
            "total_cnpj": len(itens_cnpj),
            "total_chaves": len(itens_chave),
            "cnpj_por_status": contagens_cnpj,
            "chaves_por_status": contagens_chave,
            "colisoes_por_classificacao": contagens_colisoes,
            "quantidade_bloqueios": bloqueios,
        },
        "cnpj": itens_cnpj,
        "chaves": itens_chave,
        "colisoes": colisoes,
        "seguranca": {
            "somente_select": True,
            "altera_dados": False,
            "identificadores_completos_expostos": False,
            "consulta_credenciais": False,
            "aceite_producao": False,
            "libera_migracao": False,
            "libera_emissao": False,
        },
        "proximo_passo": "REVISAR_RELATORIO_E_DEFINIR_PORTAO_DE_LEITURA_DUPLA",
    }


def auditar_base_identificadores():
    """Executa apenas SELECTs nos campos persistidos relevantes."""
    from apps.clientes.models import Cliente
    from apps.compras.models import EntradaCompra
    from apps.empresas.models import DocumentoFiscalSincronizado, Empresa, Filial
    from apps.fornecedores.models import Fornecedor

    from .models import DocumentoDFeRecebido, DocumentoFiscal, EventoDFeRecebido, EvidenciaFiscal

    registros_cnpj = []
    registros_cnpj.extend(
        {"origem": "Empresa", "identificador": pk, "empresa_id": pk, "valor": cnpj,
         "papel": "IDENTIDADE", "dominio": "EMPRESA_GLOBAL", "obrigatorio": True}
        for pk, cnpj in Empresa.objects.order_by("pk").values_list("pk", "cnpj")
    )
    registros_cnpj.extend(
        {"origem": "Filial", "identificador": pk, "empresa_id": empresa_id, "valor": cnpj,
         "papel": "IDENTIDADE", "dominio": "FILIAL_GLOBAL", "obrigatorio": False}
        for pk, empresa_id, cnpj in Filial.objects.order_by("pk").values_list("pk", "empresa_id", "cnpj")
    )
    registros_cnpj.extend(
        {"origem": "Fornecedor", "identificador": pk, "empresa_id": empresa_id, "valor": cnpj,
         "papel": "IDENTIDADE", "dominio": f"FORNECEDOR_EMPRESA_{empresa_id or 'GLOBAL'}", "obrigatorio": False}
        for pk, empresa_id, cnpj in Fornecedor.objects.order_by("pk").values_list("pk", "empresa_id", "cnpj")
    )
    registros_cnpj.extend(
        {"origem": "Cliente", "identificador": pk, "empresa_id": empresa_id, "valor": documento,
         "papel": "IDENTIDADE", "dominio": f"CLIENTE_EMPRESA_{empresa_id or 'GLOBAL'}",
         "obrigatorio": False, "campo_misto": True}
        for pk, empresa_id, documento in Cliente.objects.order_by("pk").values_list("pk", "empresa_id", "cpf_cnpj")
    )
    registros_cnpj.extend(
        {"origem": "DocumentoDFeRecebido.emitente", "identificador": pk, "empresa_id": empresa_id,
         "valor": cnpj, "papel": "REFERENCIA", "obrigatorio": False}
        for pk, empresa_id, cnpj in DocumentoDFeRecebido.objects.order_by("pk").values_list("pk", "empresa_id", "emitente_cnpj")
    )

    registros_chave = []
    fontes_chave = (
        ("DocumentoFiscal", DocumentoFiscal, "chave_acesso", False),
        ("DocumentoFiscalSincronizado", DocumentoFiscalSincronizado, "chave_acesso", False),
        ("EntradaCompra", EntradaCompra, "chave_acesso_xml", False),
        ("EvidenciaFiscal", EvidenciaFiscal, "chave_acesso", False),
        ("DocumentoDFeRecebido", DocumentoDFeRecebido, "chave_acesso", True),
        ("EventoDFeRecebido", EventoDFeRecebido, "chave_acesso", False),
    )
    for origem, modelo, campo, obrigatorio in fontes_chave:
        registros_chave.extend(
            {"origem": origem, "identificador": pk, "empresa_id": "", "valor": valor,
             "papel": "REFERENCIA", "obrigatorio": obrigatorio}
            for pk, valor in modelo.objects.order_by("pk").values_list("pk", campo)
        )
    return auditar_identificadores(registros_cnpj, registros_chave)
