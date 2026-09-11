# Inventário atômico de dados da devolução

11/09/2026 · atualizado no ciclo 94 · diagnóstico somente leitura.

O contrato `supplier_return_atomic_data_inventory_v1` acompanha 115 campos atômicos dos blocos de identificação, partes, referências, produtos, tributos, ajustes, transporte, totais, pagamento fiscal, observações, IPI devolvido, ICMS-ST/FCP e RTC. O inventário não inclui os valores: registra apenas fonte, ocorrências, quantidade preenchida e estado de disponibilidade.

## Fontes reconhecidas

| Fonte | Uso no contrato |
|---|---|
| Cadastro da filial e configuração fiscal | Emitente, endereço, município IBGE, IE e CRT. |
| XML original autorizado | Destinatário da devolução, identidade/classificação histórica dos produtos e unidades. |
| Rascunho | Quantidade efetivamente selecionada para devolução. |
| Parecer e parametrização do contador | Natureza, CFOP, códigos e hipóteses tributárias. |
| Memória aprovada | Valores, bases, alíquotas e tributos informados. |
| Rateio/reflexos aprovados | Frete, seguro, despesas e desconto por item. |
| Ficha de transporte | Modalidade, transportador e volumes. |
| Política documental | `tPag=90` e `vPag=0.00`. |
| Texto fiscal aprovado | Futuro `infAdic`/`infAdProd`, hoje intencionalmente vazios. |
| Vigência e contador | IPI devolvido, ST/FCP e RTC ainda não definidos. |

## Lacunas de modelagem restantes

1. Gerador específico de XML da devolução não existe.
2. O conversor Focus não possui paridade para todos os grupos da devolução.

## Regra de segurança cadastral

O XML original é evidência histórica e pode fornecer dados da operação recebida. Ele não atualiza nem substitui automaticamente o cadastro fiscal vigente do fornecedor. Uma futura conferência deve mostrar divergências entre cadastro e XML para decisão humana, sem sobrescrever nenhum dos dois lados.

## Matriz consolidada

O ciclo 94 vinculou todos os 115 campos à sua regra e ao destino futuro no leiaute. A especificação está em [MATRIZ_ATOMICA_XML_DEVOLUCAO.md](MATRIZ_ATOMICA_XML_DEVOLUCAO.md). O destino não autoriza uso: todos permanecem com serialização desativada.

## Próximo marco

Especificar o limite de entrada e a ordem estrutural do gerador offline, com recusa fechada para qualquer pendência e sem assinatura ou transmissão.
