"""Contrato versionado dos cenários tributários do emissor local em Goiás."""

from collections import Counter


CONTRATO_CENARIOS_TRIBUTARIOS = "fiscal_tax_scenarios_go_v1"
CONTRATO_PERFIL_PROVISORIO = "fiscal_development_profile_go_v1"

SUPORTADO = "SUPORTADO"
PARCIAL = "PARCIAL"
BLOQUEADO = "BLOQUEADO"
DEPENDENCIA_EXTERNA = "DEPENDENCIA_EXTERNA"
STATUS_VALIDOS = {SUPORTADO, PARCIAL, BLOQUEADO, DEPENDENCIA_EXTERNA}


PERFIL_FISCAL_PROVISORIO_GO = {
    "contrato": CONTRATO_PERFIL_PROVISORIO,
    "codigo": "go_dev_sem_credenciais_v1",
    "uf": "GO",
    "regime_tributario": "PENDENTE_DEFINICAO_CONTADOR",
    "modelos_planejados": ("55", "65"),
    "ambiente": "DESENVOLVIMENTO_SEM_REDE",
    "permite_comunicacao_externa": False,
    "permite_producao": False,
    "exige_cnpj_ie_a1_csc_reais": False,
    "finalidade": (
        "Permitir testes locais do motor tributario sem inventar identidade fiscal "
        "nem liberar Focus ou SEFAZ."
    ),
}


CENARIOS_TRIBUTARIOS_GO = (
    {
        "codigo": "venda_interna_consumidor_final",
        "nome": "Venda interna a consumidor final",
        "modelos": ("55", "65"),
        "status": PARCIAL,
        "escopo_atual": (
            "idDest interno, consumidor final e sem frete; ICMS limitado aos "
            "CST 00/20/40/41/50 e CSOSN 102/103/300/400."
        ),
        "proxima_evidencia": "Testes por regime, produto e modelo, seguidos de homologacao real.",
    },
    {
        "codigo": "venda_interestadual",
        "nome": "Venda interestadual",
        "modelos": ("55",),
        "status": BLOQUEADO,
        "escopo_atual": "O XML atual fixa idDest como operacao interna.",
        "proxima_evidencia": "Destinatario, CFOP, partilha/DIFAL e testes por UF.",
    },
    {
        "codigo": "venda_contribuinte_b2b",
        "nome": "Venda para contribuinte",
        "modelos": ("55",),
        "status": BLOQUEADO,
        "escopo_atual": "O fluxo atual foi desenhado para consumidor final.",
        "proxima_evidencia": "Indicadores do destinatario e matriz CFOP/CST por operacao.",
    },
    {
        "codigo": "icms_st_retido",
        "nome": "ICMS-ST proprio ou retido anteriormente",
        "modelos": ("55", "65"),
        "status": BLOQUEADO,
        "escopo_atual": "Grupos XML de ICMS-ST ainda nao implementados.",
        "proxima_evidencia": "Calculo, campos por item, totalizadores, XML e testes.",
    },
    {
        "codigo": "tributacao_monofasica",
        "nome": "Tributacao monofasica",
        "modelos": ("55", "65"),
        "status": BLOQUEADO,
        "escopo_atual": "Nao ha contrato completo por produto e tributo no XML.",
        "proxima_evidencia": "Regras por NCM/CEST, vigencia, calculo e validacao contabil.",
    },
    {
        "codigo": "devolucao_fornecedor",
        "nome": "Devolucao fiscal a fornecedor",
        "modelos": ("55",),
        "status": BLOQUEADO,
        "escopo_atual": (
            "Rascunho operacional ligado à entrada, com seleção limitada, mapeamento ao nItem, "
            "snapshot tributário original, submissão íntegra e decisão segregada imutável por "
            "Administrador/Contabilidade. Parecer tributário global versionado exige CFOP de "
            "saída no catálogo oficial e tratamentos humanos explícitos. A ficha por nItem "
            "versiona CST/CSOSN e orientações complementares. A memória não emissiva vinculada "
            "à ficha preserva bases, alíquotas e valores informados e confere os totais; revisão segregada implementada. "
            "Finalidade no gerador, documento referenciado e impostos devolvidos ainda não implementados."
        ),
        "proxima_evidencia": (
            "Ficha logística e composição comercial estruturadas; obter revisão e "
            "definir reflexos tributários, mantendo a emissão bloqueada."
        ),
    },
    {
        "codigo": "transferencia_bonificacao_remessa",
        "nome": "Transferencia, bonificacao e remessa",
        "modelos": ("55",),
        "status": BLOQUEADO,
        "escopo_atual": "Naturezas nao possuem geracao XML completa por finalidade.",
        "proxima_evidencia": "Matriz de operacoes aprovada pelo contador.",
    },
    {
        "codigo": "frete_entrega",
        "nome": "Frete e entrega",
        "modelos": ("55", "65"),
        "status": BLOQUEADO,
        "escopo_atual": "O XML atual fixa modFrete como sem frete.",
        "proxima_evidencia": "Transportador, volumes, modalidade e reflexos nos totais.",
    },
    {
        "codigo": "cbenef_go",
        "nome": "Beneficio fiscal de Goiás",
        "modelos": ("55", "65"),
        "status": PARCIAL,
        "escopo_atual": "Formato GO + 6 digitos e obrigatoriedade na reducao de base.",
        "proxima_evidencia": "Tabela oficial versionada, vigencia e compatibilidade por CST.",
    },
    {
        "codigo": "pis_cofins_ipi",
        "nome": "PIS, COFINS e IPI",
        "modelos": ("55", "65"),
        "status": PARCIAL,
        "escopo_atual": "Somente os CST e grupos explicitamente aceitos pelo emissor.",
        "proxima_evidencia": "Matriz por produto, regime e natureza de operacao.",
    },
    {
        "codigo": "ibs_cbs_2026",
        "nome": "IBS/CBS conforme vigencia de 2026",
        "modelos": ("55", "65"),
        "status": PARCIAL,
        "escopo_atual": "Cadastro preparado; emissao XML permanece bloqueada.",
        "proxima_evidencia": "Schema, calculo, grupos XML, testes e aceite fiscal.",
    },
    {
        "codigo": "homologacao_go",
        "nome": "Homologacao real em Goiás",
        "modelos": ("55", "65"),
        "status": DEPENDENCIA_EXTERNA,
        "escopo_atual": "Rede e producao permanecem desligadas.",
        "proxima_evidencia": "CNPJ, IE, A1, CSC, credenciamento e aceite por filial.",
    },
)


def avaliar_cenario_fiscal_go(
    *,
    uf_emitente,
    modelo,
    cfop,
    finalidade="1",
    destinatario_contribuinte=False,
    possui_frete=False,
    uf_destinatario="",
):
    """Avalia somente as premissas que o XML local representa hoje."""
    uf = str(uf_emitente or "").strip().upper()
    modelo = str(modelo or "").strip()
    cfop = str(cfop or "").strip()
    finalidade = str(finalidade or "").strip()
    uf_destino = str(uf_destinatario or "").strip().upper()

    if uf != "GO":
        return {
            "contrato": CONTRATO_CENARIOS_TRIBUTARIOS,
            "aplicavel": False,
            "cenario": None,
            "status": DEPENDENCIA_EXTERNA,
            "permitido": True,
            "pendencias": [],
        }

    pendencias = []
    if modelo not in {"55", "65"}:
        pendencias.append(
            f"Cenário fiscal GO bloqueado: modelo {modelo or '-'} não pertence ao catálogo NF-e/NFC-e."
        )
    if len(cfop) == 4 and cfop.isdigit() and not cfop.startswith("5"):
        pendencias.append(
            "Cenário fiscal GO bloqueado: o XML atual suporta somente venda interna "
            "(CFOP iniciado por 5); operação interestadual ou exterior ainda não está implementada."
        )
    if uf_destino and uf_destino != uf:
        pendencias.append(
            "Cenário fiscal GO bloqueado: a UF do destinatário difere da UF emitente, "
            "mas o XML atual declara operação interna."
        )
    if finalidade != "1":
        pendencias.append(
            "Cenário fiscal GO bloqueado: o XML atual suporta somente finalidade normal de venda."
        )
    if destinatario_contribuinte:
        pendencias.append(
            "Cenário fiscal GO bloqueado: destinatário contribuinte exige IE, indicador e regras próprias."
        )
    if possui_frete:
        pendencias.append(
            "Cenário fiscal GO bloqueado: frete exige modalidade, transportador, volumes e totalização próprios."
        )

    return {
        "contrato": CONTRATO_CENARIOS_TRIBUTARIOS,
        "aplicavel": True,
        "cenario": "venda_interna_consumidor_final",
        "status": BLOQUEADO if pendencias else PARCIAL,
        "permitido": not pendencias,
        "pendencias": pendencias,
    }


def pendencias_cenario_fiscal_go(**dados):
    return avaliar_cenario_fiscal_go(**dados)["pendencias"]


def perfil_fiscal_provisorio_go():
    perfil = dict(PERFIL_FISCAL_PROVISORIO_GO)
    perfil["modelos_planejados"] = list(perfil["modelos_planejados"])
    return perfil


def catalogo_cenarios_tributarios_go():
    itens = []
    for cenario in CENARIOS_TRIBUTARIOS_GO:
        item = dict(cenario)
        item["modelos"] = list(item["modelos"])
        itens.append(item)
    return itens


def resumo_cenarios_tributarios_go():
    contagem = Counter(item["status"] for item in CENARIOS_TRIBUTARIOS_GO)
    return {
        "contrato": CONTRATO_CENARIOS_TRIBUTARIOS,
        "perfil": perfil_fiscal_provisorio_go(),
        "total": len(CENARIOS_TRIBUTARIOS_GO),
        "contagem": {status: contagem.get(status, 0) for status in sorted(STATUS_VALIDOS)},
        "itens": catalogo_cenarios_tributarios_go(),
    }
