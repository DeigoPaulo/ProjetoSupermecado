# Matriz de paridade - Focus NFe x Deigo Fiscal direto

Atualizada em 20/08/2026. Esta matriz compara o que o ERP utiliza e não representa todas as funcionalidades comerciais do provedor.

| Capacidade | Focus no ERP | Deigo Fiscal direto | Próxima evidência necessária |
|---|---|---|---|
| Emissão NF-e/NFC-e | Implementada | Implementada estruturalmente | Homologação real GO |
| Consulta por chave | Implementada | Implementada | Respostas reais e reconciliação |
| Cancelamento | Implementado | Implementado | Evento real homologado |
| Inutilização | Implementada | Implementada | Protocolo real homologado |
| Status do autorizador | Abstraído pelo provedor | Implementado | Teste real GO |
| XML/protocolo autorizado | Retornado pelo provedor | Montado com retorno SEFAZ | Comparação com XML oficial |
| Fila e retentativas | Provedor + ERP | Parcial no ERP | Circuit breaker e telemetria |
| Contingência NFC-e | Gerenciada pelo provedor | Parcial | Reconciliação e homologação offline |
| Distribuição DF-e/NSU | Adaptador Focus separado | Implementada estruturalmente | Homologação real no Ambiente Nacional com A1 |
| Manifestação do destinatário | Disponível no ecossistema do provedor | Implementada estruturalmente | Homologação real no Ambiente Nacional com A1 |
| Carta de Correção Eletrônica | Disponível no ecossistema do provedor | Implementada estruturalmente | Homologação real do evento 110110 em Goiás com A1 |
| Carta de Correção | Disponível no ecossistema do provedor | Planejada | Evento 110110 |
| Consulta cadastro | Abstraída quando oferecida | Planejada | Catálogo por UF |
| Contingência NF-e SVC | Gerenciada pelo provedor | Planejada | Regras SVC-AN/SVC-RS |
| Multi-UF | Coberta pelo provedor | Planejada | Catálogos e homologação por UF |
| Retenção/SLA/suporte | Serviço comercial | Não equivalente | Infraestrutura e operação próprias |
| IBS/CBS | Evolui conforme provedor | Dependência externa | Schemas, cálculo e aceite fiscal |

## Critério de paridade

Paridade não é somente obter HTTP 200. Cada operação deve possuir:

1. XML/schema válido;
2. assinatura e TLS válidos;
3. interpretação de todos os estados relevantes;
4. idempotência e recuperação após timeout;
5. persistência de XML, chave, protocolo e eventos;
6. auditoria e isolamento por empresa;
7. teste de rejeição e indisponibilidade;
8. homologação real por UF/modelo;
9. aceite fiscal e contábil;
10. monitoramento e procedimento de suporte.

A fonte executável desta matriz é `apps/fiscal/sefaz_direta/capacidades.py`, contrato `deigo_fiscal_capabilities_v1`.
