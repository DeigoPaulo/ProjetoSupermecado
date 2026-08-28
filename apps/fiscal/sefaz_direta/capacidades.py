"""Matriz versionada de capacidades do Deigo Fiscal/SEFAZ direta."""

CONTRATO_CAPACIDADES = "deigo_fiscal_capabilities_v1"

IMPLEMENTADO = "IMPLEMENTADO"
PARCIAL = "PARCIAL"
PLANEJADO = "PLANEJADO"
DEPENDENCIA_EXTERNA = "DEPENDENCIA_EXTERNA"

CAPACIDADES = (
    {"codigo": "emissao_nfe_nfce", "nome": "Emissão NF-e/NFC-e 4.00", "status": PARCIAL, "escopo": "Transporte SOAP, assinatura A1 e nfeProc estruturais; cobertura tributária e homologação real ainda pendentes."},
    {"codigo": "consulta_protocolo", "nome": "Consulta por chave", "status": IMPLEMENTADO, "escopo": "Autorizada, cancelada, denegada, pendente ou não localizada."},
    {"codigo": "cancelamento", "nome": "Cancelamento por evento", "status": IMPLEMENTADO, "escopo": "Evento 110111 assinado."},
    {"codigo": "inutilizacao", "nome": "Inutilização de numeração", "status": IMPLEMENTADO, "escopo": "Pedido assinado e protocolo preservado."},
    {"codigo": "status_servico", "nome": "Status do autorizador", "status": IMPLEMENTADO, "escopo": "Consulta NFeStatusServico4."},
    {"codigo": "armazenamento_xml", "nome": "Armazenamento de XML e protocolos", "status": IMPLEMENTADO, "escopo": "Arquivo interno append-only encadeado por SHA-256, verificação estrita, âncora externa histórica no backup e validação na restauração; cópia fora da máquina ainda depende da infraestrutura."},
    {"codigo": "fila_retentativas", "nome": "Fila, consulta e retentativas", "status": IMPLEMENTADO, "escopo": "Fila do ERP, retry exponencial somente em consultas idempotentes, circuit breaker por host e telemetria segura em memória."},
    {"codigo": "contingencia_nfce", "nome": "Contingência NFC-e offline", "status": IMPLEMENTADO, "escopo": "tpEmis 9, prazo, fila, consulta antes de reenvio, confirmação dupla de ausência, correção sem perder chave e bloqueio de cancelamento local; homologação real pendente."},
    {"codigo": "distribuicao_dfe", "nome": "Distribuição DF-e por CNPJ/NSU", "status": IMPLEMENTADO, "escopo": "Consulta distNSU, notas, resumos, eventos, cursor e cooldown; homologação real pendente."},
    {"codigo": "manifestacao_destinatario", "nome": "Manifestação do destinatário", "status": IMPLEMENTADO, "escopo": "Ciência, confirmação, desconhecimento e operação não realizada com histórico, XML, auditoria e travas; homologação real pendente."},
    {"codigo": "carta_correcao", "nome": "Carta de Correção Eletrônica", "status": IMPLEMENTADO, "escopo": "Evento 110110 assinado, sequencial 1-20, histórico, XML, auditoria e travas legais; homologação real pendente."},
    {"codigo": "consulta_cadastro", "nome": "Consulta cadastro do contribuinte", "status": IMPLEMENTADO, "escopo": "ConsCad 2.00 em Goiás, com histórico, XML, auditoria e bloqueio de produção; homologação real pendente."},
    {"codigo": "contingencia_nfe_svc", "nome": "Contingência NF-e SVC", "status": IMPLEMENTADO, "escopo": "SVC-RS para NF-e de Goiás: tpEmis 7, nova chave/XML, ativação Master, endpoint separado e feature flag desligada; homologação real pendente."},
    {"codigo": "multi_uf", "nome": "Catálogo multi-UF", "status": PLANEJADO, "escopo": "Goiás é o único perfil estrutural atual."},
    {"codigo": "ibs_cbs", "nome": "IBS/CBS no XML", "status": PARCIAL, "escopo": "Cadastro preparado e XML bloqueado; depende de schemas vigentes, implementação do cálculo/grupos XML e aceite fiscal."},
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
