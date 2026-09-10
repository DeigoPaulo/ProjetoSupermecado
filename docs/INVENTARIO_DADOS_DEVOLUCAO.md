# Inventário atômico de dados da devolução

10/09/2026 · atualizado no ciclo 88 · diagnóstico somente leitura.

O contrato `supplier_return_atomic_data_inventory_v1` acompanha 107 campos atômicos dos blocos de identificação, partes, referências, produtos, tributos, ajustes, transporte, totais, pagamento fiscal, observações, IPI devolvido, ICMS-ST/FCP e RTC. O inventário não inclui os valores: registra apenas fonte, ocorrências, quantidade preenchida e estado de disponibilidade.

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

1. `indTot` ainda não está modelado no produto da devolução.
2. Modalidade de base do ICMS ainda não está modelada.
3. Redução da base de ICMS ainda não está modelada.
4. Enquadramento legal `cEnq` do IPI não está no contrato da devolução.
5. Variantes de cálculo de PIS/COFINS ainda não estão discriminadas.
6. Gerador específico de XML da devolução não existe.
7. O conversor Focus não possui paridade para todos os grupos da devolução.

## Regra de segurança cadastral

O XML original é evidência histórica e pode fornecer dados da operação recebida. Ele não atualiza nem substitui automaticamente o cadastro fiscal vigente do fornecedor. Uma futura conferência deve mostrar divergências entre cadastro e XML para decisão humana, sem sobrescrever nenhum dos dois lados.

## Próximo marco

Modelar `indTot` por item como decisão explícita, inicialmente vazia e não confirmada. Nenhum item deve compor ou deixar de compor o total por default, e a totalização atual não deve ser alterada.
