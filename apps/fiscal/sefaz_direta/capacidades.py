"""Matriz versionada de capacidades do Deigo Fiscal/SEFAZ direta."""

CONTRATO_CAPACIDADES = "deigo_fiscal_capabilities_v1"

IMPLEMENTADO = "IMPLEMENTADO"
PARCIAL = "PARCIAL"
PLANEJADO = "PLANEJADO"
DEPENDENCIA_EXTERNA = "DEPENDENCIA_EXTERNA"

CAPACIDADES = (
    {"codigo": "emissao_nfe_nfce", "nome": "Emissão NF-e/NFC-e 4.00", "status": IMPLEMENTADO, "escopo": "SOAP síncrono, assinatura A1 e nfeProc."},
    {"codigo": "consulta_protocolo", "nome": "Consulta por chave", "status": IMPLEMENTADO, "escopo": "Autorizada, cancelada, denegada, pendente ou não localizada."},
    {"codigo": "cancelamento", "nome": "Cancelamento por evento", "status": IMPLEMENTADO, "escopo": "Evento 110111 assinado."},
    {"codigo": "inutilizacao", "nome": "Inutilização de numeração", "status": IMPLEMENTADO, "escopo": "Pedido assinado e protocolo preservado."},
    {"codigo": "status_servico", "nome": "Status do autorizador", "status": IMPLEMENTADO, "escopo": "Consulta NFeStatusServico4."},
    {"codigo": "armazenamento_xml", "nome": "Armazenamento de XML e protocolos", "status": PARCIAL, "escopo": "ERP persiste documentos; retenção externa e cópia imutável ainda pendentes."},
    {"codigo": "fila_retentativas", "nome": "Fila, consulta e retentativas", "status": PARCIAL, "escopo": "Fila do ERP disponível; circuit breaker e telemetria avançada pendentes."},
    {"codigo": "contingencia_nfce", "nome": "Contingência NFC-e offline", "status": PARCIAL, "escopo": "Fluxo do ERP existe; homologação completa e reconciliação direta pendentes."},
    {"codigo": "distribuicao_dfe", "nome": "Distribuição DF-e por CNPJ/NSU", "status": IMPLEMENTADO, "escopo": "Consulta distNSU, notas, resumos, eventos, cursor e cooldown; homologação real pendente."},
    {"codigo": "manifestacao_destinatario", "nome": "Manifestação do destinatário", "status": IMPLEMENTADO, "escopo": "Ciência, confirmação, desconhecimento e operação não realizada com histórico, XML, auditoria e travas; homologação real pendente."},
    {"codigo": "carta_correcao", "nome": "Carta de Correção Eletrônica", "status": IMPLEMENTADO, "escopo": "Evento 110110 assinado, sequencial 1-20, histórico, XML, auditoria e travas legais; homologação real pendente."},
    {"codigo": "consulta_cadastro", "nome": "Consulta cadastro do contribuinte", "status": IMPLEMENTADO, "escopo": "ConsCad 2.00 em Goiás, com histórico, XML, auditoria e bloqueio de produção; homologação real pendente."},
    {"codigo": "contingencia_nfe_svc", "nome": "Contingência NF-e SVC", "status": PLANEJADO, "escopo": "Catálogo, regras de ativação e reconciliação."},
    {"codigo": "multi_uf", "nome": "Catálogo multi-UF", "status": PLANEJADO, "escopo": "Goiás é o único perfil estrutural atual."},
    {"codigo": "ibs_cbs", "nome": "IBS/CBS no XML", "status": DEPENDENCIA_EXTERNA, "escopo": "Depende de schemas vigentes, cálculo homologado e aceite fiscal."},
    {"codigo": "homologacao_go", "nome": "Homologação real em Goiás", "status": DEPENDENCIA_EXTERNA, "escopo": "Exige credenciamento, A1/CSC válidos e testes com a SEFAZ."},
)


def matriz_capacidades():
    return [dict(item) for item in CAPACIDADES]


def resumo_capacidades():
    contagem = {status: 0 for status in (IMPLEMENTADO, PARCIAL, PLANEJADO, DEPENDENCIA_EXTERNA)}
    for item in CAPACIDADES:
        contagem[item["status"]] += 1
    return {
        "contrato": CONTRATO_CAPACIDADES,
        "total": len(CAPACIDADES),
        "contagem": contagem,
        "itens": matriz_capacidades(),
    }
